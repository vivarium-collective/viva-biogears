"""The committed I/O schema (viva_biogears/data/schema) matches the code, its units mean
what BioGears means, and bigraph-schema reads them. The schema comes from the process's
interface and modules, without running the engine; building the sepsis composite reads
its starting state's time, so the tests that build it skip without a BioGears runtime."""
import json
from functools import reduce
from pathlib import Path

import pytest
import yaml
from bigraph_schema.contract import ProcessContract
from bigraph_schema.units import units as REGISTRY

from viva_biogears import schema
from viva_biogears.modules import MODULES
from viva_biogears.modules.base import port_units
from viva_biogears.core import build_core
from viva_biogears.processes import BioGearsModularProcess

STUDIES = Path(__file__).resolve().parents[1] / "workspace" / "studies"

#: What each BioGears unit means, written in explicit pint syntax (independent of the
#: translation in port_units): BioGears puts everything after "/" in the denominator
#: and writes counts as "ct". None: pint has no such unit.
MEANING = {
    "1/min": "1/min", "L/cmH2O": "L/cmH2O", "L/min": "L/min", "L/min m^2": "L/(min*m**2)",
    "W": "W", "W/m^2 K": "W/(m**2*K)", "clo": None, "cmH2O": "cmH2O", "cmH2O s/L": "cmH2O*s/L",
    "ct/uL": "count/uL", "degC": "degC", "g": "g", "g/dL": "g/dL", "g/min": "g/min", "kJ": "kJ",
    "m/s": "m/s", "mL": "mL", "mL/min": "mL/min", "mmHg": "mmHg", "mmHg min/L": "mmHg*min/L",
    "mmHg min/mL": "mmHg*min/mL", "mmHg s/mL": "mmHg*s/mL", "mmol/L": "mmol/L",
    # Units of outputs built from config (substances, tissues, treatment readouts).
    "1/mmHg": "1/mmHg", "g/L": "g/L", "g/mL": "g/mL", "g/mol": "g/mol", "mL/s": "mL/s",
    "mL/s mmHg": "mL/(s*mmHg)", "mV": "mV", "mg/g": "mg/g", "ug/mL": "ug/mL", "s ug/mL": "s*ug/mL",
}


def _units_modules_define() -> set[str]:
    """Every BioGears unit the modules define: static module outputs, the property tables
    substances/tissues outputs are built from, and the treatment readouts. (A unit a user
    gives a substance or tissue entry goes through the same translation, unchecked.)"""
    from viva_biogears.modules import substances, treatment

    tables = (substances.LIQUID_PROPERTIES, substances.GAS_PROPERTIES, substances.BODY_PROPERTIES,
              substances.TISSUE_PROPERTIES, substances.TISSUE_FLUID_PROPERTIES)
    readouts = treatment._outputs({"treatment_readouts": ["Piperacillin"]}, None, None)
    return ({r.unit for m in MODULES.values() for r in m.outputs if r.unit}
            | {unit for table in tables for unit in table.values() if unit}
            | {r.unit for r in readouts if r.unit})


def test_output_ports_carry_their_requests_units():
    """No BioGears needed: a process of every module with fixed outputs types each port with
    its request's units, where bigraph-schema's own reader finds them. Falsifies untyped
    ports (the committed-schema check catches them only with a BioGears runtime)."""
    core = build_core()
    process = BioGearsModularProcess({"modules": [n for n, m in MODULES.items() if m.outputs]}, core=core)
    face = process.interface()["outputs"]
    with_units = 0
    for path, i, _ in process._slots:
        read = core._port_units(core.access(reduce(lambda tree, key: tree[key], path, face)))
        assert read == (port_units(process._requests[i].unit) or ""), "/".join(path)
        with_units += bool(read)
    assert with_units > 400  # the check covers the ports, not an empty set


def test_study_readouts_declare_their_ports_units():
    """The workbench checks a readout's units against its port's (by dimension). Falsifies
    a readout in BioGears' unit syntax: "ct/uL" is pint's carat, its port is count/uL."""
    face = json.loads((schema.SCHEMA_DIR / "biogears_sepsis.contract.json").read_text())["face"]["outputs"]
    core = build_core()
    checked = 0
    for study in sorted(STUDIES.glob("*/study.yaml")):
        for readout in yaml.safe_load(study.read_text()).get("readouts") or []:
            path = readout.get("store_path", "").split(".")
            if path[0] != "readings" or not readout.get("units"):
                continue
            try:
                port_type = reduce(lambda tree, key: tree[key], path[1:], face)
            except (KeyError, TypeError):
                continue  # a port this schema doesn't cover (another composite's, a drug readout)
            units = core._port_units(core.access(port_type))
            if units:
                assert (REGISTRY.parse_expression(readout["units"]).dimensionality
                        == REGISTRY.parse_expression(units).dimensionality), (study.parent.name, readout["name"])
                checked += 1
    assert checked > 10


def test_committed_schema_matches_the_code():
    """A port, unit or setpoint change must come with the regenerated schema, so it
    shows up as a reviewable diff (run: python -m viva_biogears.schema)."""
    assert schema.stale() == []


def test_every_biogears_unit_keeps_its_meaning():
    """pint reads "L/min m^2" as L m^2/min and "ct" as the carat; the translated
    units must have the dimensions of what BioGears means."""
    used = _units_modules_define()
    assert used <= set(MEANING), sorted(used - set(MEANING))  # every unit the modules define is covered
    for unit, meaning in MEANING.items():
        translated = port_units(unit)
        if meaning is None:
            assert translated is None, unit
            continue
        assert translated is not None, unit
        assert REGISTRY.Unit(translated).dimensionality == REGISTRY.parse_expression(meaning).dimensionality, unit


@pytest.mark.parametrize("name", list(schema.SCHEMAS))
def test_bigraph_schema_reads_the_units_of_every_port(name):
    """The units are where bigraph-schema's unit handling looks (inside overwrite),
    checked with its own reader, and they are the translated BioGears units."""
    data = json.loads((schema.SCHEMA_DIR / f"{name}.contract.json").read_text())
    core = build_core()
    with_units = 0
    for path, port_type in schema.leaves(data["face"]["outputs"]):
        meaning = data["outputs"][path]
        read = core._port_units(core.access(port_type))
        assert read == (port_units(meaning.get("biogears_units", "")) or ""), path
        with_units += bool(read)
    assert with_units > 100  # the check covers the ports, not an empty set


@pytest.mark.parametrize("name", list(schema.SCHEMAS))
def test_the_file_loads_as_a_process_contract_and_describes_every_port(name):
    data = json.loads((schema.SCHEMA_DIR / f"{name}.contract.json").read_text())
    contract = ProcessContract(**data)
    assert contract.to_dict() == data
    for direction in ("inputs", "outputs"):
        typed = {path for path, _ in schema.leaves(data["face"][direction])}
        assert typed == set(data[direction]), direction  # every typed port is described, and only those
