"""Substance and tissue readings: modules whose outputs come from their config.

BioGears tracks every active substance in every compartment, and composition
values for every tissue; requesting them all would be tens of thousands of outputs.
So these modules read only the entries listed in their config:

- ``substances`` (config ``substance_outputs``): a substance's quantity in a liquid
  or gas compartment (``Concentration``, ``PartialPressure``, ...), or a whole-body
  value with no compartment (``MassInBlood``). Ports ``<Substance>/<Compartment>/<port>``
  or ``<Substance>/body/<port>``, e.g. ``Oxygen/Aorta/partial_pressure_mmHg``.
- ``tissues`` (config ``tissue_outputs``): a tissue compartment's composition
  (``MuscleTissue``: ``MatrixVolume``, ``TotalMass``, ... constants) or a tissue fluid
  compartment's volume and pressure (``MuscleTissueExtracellular``,
  ``...Intracellular``). Ports ``<Compartment>/<port>``.

Each entry is a map of strings: ``substance`` (``substances`` only), ``compartment``
(omitted for whole-body values), ``property``, ``unit`` (BioGears' spelling, e.g.
``mmHg``, ``g/L``, ``ug/mL``, ``mmol/L``; omitted for unitless properties) and,
for a name that is both, ``kind`` (``liquid`` or ``gas``). The port name is the
property in snake_case plus the unit, with ``/`` written ``_per_``.

Every entry is checked against the starting state before BioGears loads: an active
substance of the state; a compartment holding a quantity of it in every leaf, in a
transport graph (the circulation, kidneys and brain included, or the airway) or a
tissue fluid (a parent needs one such leaf: ``Heart`` counts its ``Pericardium``);
and a property that quantity, substance or compartment stores. That refuses
``Ground``, ``Ambient``, the pneumothorax leak compartments, the equipment
compartments, ``Pericardium`` on its own (in no transport graph, so its quantities
stay at their loaded values) and the liquid copy of the airway (``LeftAlveoli`` as a
liquid holds no substances). ``Saturation`` is offered only where every leaf holds
hemoglobin (the ureters, bladder and other urine compartments hold none). A wrong unit is caught when the engine loads (BioGears does
not connect the request). Unlike Pulse 4.4.0, BioGears' ``Lymph`` carries fluid and
substances, so it can be read.

The modules edit nothing, so the simulation is the same with or without them.
"""

from __future__ import annotations

import re
from typing import Any

from .base import CircuitModule, Request

#: The properties each kind of entry can read, with a BioGears unit for each ("" for
#: unitless; any unit of the same kind works, and a wrong one fails the load). These are
#: the scalar properties BioGears' data requests serve (``SELiquidSubstanceQuantity``,
#: ``SEGasSubstanceQuantity``, ``SESubstance``, ``SETissueCompartment``,
#: ``SELiquidCompartment``); an entry must also name one the state stores for it.
#: Substance quantity in a liquid (vascular or tissue fluid) compartment.
LIQUID_PROPERTIES = {
    "Concentration": "g/L", "Mass": "g", "MassCleared": "g", "MassDeposited": "g", "MassExcreted": "g",
    "Molarity": "mmol/L", "PartialPressure": "mmHg", "Saturation": "",
}
#: Substance quantity in a gas (airway) compartment.
GAS_PROPERTIES = {"PartialPressure": "mmHg", "Volume": "mL", "VolumeFraction": ""}
#: Whole-body substance values (no compartment). A substance has only some of them (the
#: gas ones for gases, BloodConcentration and SystemicMassCleared for solutes): the state
#: says which. Left out because BioGears 8.2.0 doesn't serve them for its active
#: substances: AreaUnderCurve, MaximumDiffusionFlux, MembraneResistance (not connected),
#: MichaelisCoefficient, PlasmaConcentration, EffectSiteConcentration (drug values; no
#: drug is active until dosed, and viva-biogears can't dose one yet).
BODY_PROPERTIES = {
    "MassInBody": "g", "MassInBlood": "g", "MassInTissue": "g", "BloodConcentration": "g/L",
    "SystemicMassCleared": "g", "EndTidalFraction": "", "EndTidalPressure": "mmHg", "AlveolarTransfer": "mL/s",
    "DiffusingCapacity": "mL/s mmHg", "RelativeDiffusionCoefficient": "", "SolubilityCoefficient": "1/mmHg",
    "Density": "g/mL", "MolarMass": "g/mol",
}
#: A tissue compartment's composition (constants).
TISSUE_PROPERTIES = {
    "MatrixVolume": "mL", "TotalMass": "g", "AcidicPhospohlipidConcentration": "mg/g", "MembranePotential": "mV",
    "NeutralLipidsVolumeFraction": "", "NeutralPhospholipidsVolumeFraction": "", "ReflectionCoefficient": "",
    "TissueToPlasmaAlbuminRatio": "", "TissueToPlasmaAlphaAcidGlycoproteinRatio": "",
    "TissueToPlasmaLipoproteinRatio": "",
}
#: A tissue fluid compartment (``<Tissue>TissueExtracellular`` / ``Intracellular``).
#: Not InFlow/OutFlow (tissue fluid has no compartment links in BioGears 8.2.0, so they
#: read NaN; the ``tissue_fluid`` module reads filtration from the circuit) or pH (NaN).
TISSUE_FLUID_PROPERTIES = {"Volume": "mL", "Pressure": "mmHg", "WaterVolumeFraction": ""}

#: Liquid graphs BioGears moves blood and its substances over.
CIRCULATION_GRAPHS = ("ActiveCardiovascular", "Cardiovascular", "Renal", "Cerebral")
AIRWAY_GRAPH = "Respiratory"
#: Compartments refused whatever the substance, with the reason.
NOT_READ = {
    "Ambient": "the environment, an infinite reservoir; read the environment's gases instead",
    "Ground": "the circuit reference, which holds nothing",
}
_TISSUE_FLUID = re.compile(r"Tissue(Extracellular|Intracellular)$")


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _port(prop: str, unit: str) -> str:
    suffix = "_" + unit.replace("/", "_per_").replace("^", "").replace(" ", "_") if unit else ""
    return _snake(prop) + suffix


def _entries(config: dict[str, Any], key: str, required: set[str], optional: set[str]) -> list[dict[str, str]]:
    if not config[key]:
        raise ValueError(f"{key} is empty: list what to read, or leave the module out")
    entries = []
    for i, entry in enumerate(config[key]):
        name = f"{key}[{i}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{name} must be a map, got {entry!r}")
        unknown = set(entry) - required - optional
        if unknown:
            raise ValueError(f"{name}: unknown keys {sorted(unknown)}; allowed: {sorted(required | optional)}")
        missing = required - set(entry)
        if missing:
            raise ValueError(f"{name}: missing {sorted(missing)}")
        bad = {k: v for k, v in entry.items() if not isinstance(v, str)}
        if bad:
            raise ValueError(f"{name}: values must be strings, got {bad}")
        entries.append(dict(entry, _name=name))
    return entries


def _check_unique(outputs: list[Request]) -> tuple[Request, ...]:
    paths = [r.path for r in outputs]
    dup = sorted({"/".join(p) for p in paths if paths.count(p) > 1})
    if dup:
        raise ValueError(f"entries read the same output more than once: {dup}")
    return tuple(outputs)


def _transport_members(state, kind: str) -> set[str]:
    if kind == "LiquidCompartment":
        return set().union(*(state.graphs["LiquidGraph"].get(g, set()) for g in CIRCULATION_GRAPHS))
    return set(state.graphs["GasGraph"].get(AIRWAY_GRAPH, set()))


def _find(state, entry) -> tuple[str, Any]:
    name, kind = entry["compartment"], entry.get("kind")
    kinds = {"liquid": "LiquidCompartment", "gas": "GasCompartment"}
    if kind is not None and kind not in kinds:
        raise ValueError(f"{entry['_name']}: kind must be 'liquid' or 'gas', got {kind!r}")
    found = [(k, state.compartments[k][name]) for k in kinds.values()
             if name in state.compartments.get(k, {}) and (kind is None or k == kinds[kind])]
    if not found:
        raise ValueError(f"{entry['_name']}: no {'compartment' if kind is None else kind + ' compartment'} "
                         f"named {name!r} in the state")
    if len(found) > 1:
        # Prefer the one that holds the substance; ask when both do.
        holding = [f for f in found if entry.get("substance") in f[1].quantities]
        if not holding:
            raise ValueError(f"{entry['_name']}: {name} holds no {entry.get('substance')} (as a liquid or a gas)")
        if len(holding) != 1:
            raise ValueError(f"{entry['_name']}: {name!r} is both a liquid and a gas compartment; set kind")
        found = holding
    return found[0]


def _refusal(state, kind, comp, substance) -> str | None:
    """Why ``comp`` can't be read for ``substance``, or None. A parent counts its leaves
    outside the transport graphs (Heart includes Pericardium) but must have one inside."""
    if comp.name in NOT_READ:
        return NOT_READ[comp.name]
    if "Leak" in comp.name:
        return "an injury compartment (pneumothorax leak), empty unless the injury is active"
    by_name = state.compartments[kind]
    members = _transport_members(state, kind)
    leaves = comp.leaves(by_name)
    moving = [leaf for leaf in leaves
              if leaf.name in members or (kind == "LiquidCompartment" and _TISSUE_FLUID.search(leaf.name))]
    if not moving:
        return f"{comp.name} is in no transport graph, so BioGears moves no substances through it"
    for leaf in leaves:
        if substance is not None and substance not in leaf.quantities:
            return f"{leaf.name} holds no {substance}"
    return None


def _substance_outputs(config, state, modules) -> tuple[Request, ...]:
    out = []
    for e in _entries(config, "substance_outputs", {"substance", "property"}, {"compartment", "unit", "kind"}):
        sub, prop, unit = e["substance"], e["property"], e.get("unit", "")
        if sub not in state.substances:
            raise ValueError(f"{e['_name']}: {sub!r} is not an active substance of the state; "
                             f"active: {sorted(state.substances)}")
        if "compartment" not in e:
            if prop not in BODY_PROPERTIES:
                raise ValueError(f"{e['_name']}: {prop!r} is not a whole-body substance property; "
                                 f"BODY_PROPERTIES: {sorted(BODY_PROPERTIES)}")
            if prop not in state.substances[sub]:
                raise ValueError(f"{e['_name']}: {sub} has no whole-body {prop!r}; it has {sorted(state.substances[sub])}")
            out.append(Request((sub, "body", _port(prop, unit)), "Substance", prop, unit, "", sub))
            continue
        kind, comp = _find(state, e)
        why = _refusal(state, kind, comp, sub)
        if why:
            raise ValueError(f"{e['_name']}: {comp.name} can't be read for {sub}: {why}")
        table = LIQUID_PROPERTIES if kind == "LiquidCompartment" else GAS_PROPERTIES
        if prop not in table:
            raise ValueError(f"{e['_name']}: {prop!r} is not a {kind[:-11].lower()} substance property; "
                             f"{'LIQUID' if table is LIQUID_PROPERTIES else 'GAS'}_PROPERTIES: {sorted(table)}")
        leaves = comp.leaves(state.compartments[kind])
        if prop == "Saturation" and not all(leaf.blood for leaf in leaves):
            empty = [leaf.name for leaf in leaves if not leaf.blood]
            raise ValueError(f"{e['_name']}: Saturation is a property of blood; {', '.join(empty)} holds no "
                             f"hemoglobin in this state (it reads 0, or NaN for a parent)")
        leaf = leaves[0]
        if prop not in leaf.quantities[sub]:
            raise ValueError(f"{e['_name']}: {sub} in {comp.name} has no {prop!r}; it has {sorted(leaf.quantities[sub])}")
        out.append(Request((sub, comp.name, _port(prop, unit)), kind, prop, unit, comp.name, sub))
    return _check_unique(out)


def _tissue_outputs(config, state, modules) -> tuple[Request, ...]:
    out = []
    tissues = state.compartments.get("TissueCompartment", {})
    liquids = state.compartments["LiquidCompartment"]
    for e in _entries(config, "tissue_outputs", {"compartment", "property"}, {"unit"}):
        name, prop, unit = e["compartment"], e["property"], e.get("unit", "")
        if name in tissues:
            if prop not in TISSUE_PROPERTIES or prop not in tissues[name].properties:
                readable = sorted(set(TISSUE_PROPERTIES) & tissues[name].properties)
                raise ValueError(f"{e['_name']}: tissue {name} has no {prop!r}; it has {readable}")
            out.append(Request((name, _port(prop, unit)), "TissueCompartment", prop, unit, name))
        elif _TISSUE_FLUID.search(name) and name in liquids:
            allowed = set(TISSUE_FLUID_PROPERTIES)
            if prop not in allowed:
                raise ValueError(f"{e['_name']}: tissue fluid {name} has no {prop!r}; it has {sorted(allowed)}")
            out.append(Request((name, _port(prop, unit)), "LiquidCompartment", prop, unit, name))
        else:
            raise ValueError(f"{e['_name']}: {name!r} is not a tissue or tissue fluid compartment; tissues: "
                             f"{sorted(tissues)}, fluids: <Tissue>TissueExtracellular/Intracellular")
    return _check_unique(out)


def every_substance_output(state_file: str = "StandardMale@0s.xml", *, substances=None, compartments=None,
                           properties=None, runtime_dir: str = "") -> list[dict[str, str]]:
    """Every ``substance_outputs`` entry the state allows, in substance, compartment, property order.

    ``state_file`` is found like the processes' (``<runtime>/states``, the package's
    ``states/``, or an absolute path). ``substances`` and ``compartments`` narrow the
    search (default: every active substance; whole-body values and every liquid and gas
    compartment, ``None`` meaning whole-body); ``properties`` maps property to unit
    (default: ``LIQUID_PROPERTIES``, ``GAS_PROPERTIES`` and ``BODY_PROPERTIES``, with their
    units). Each candidate is checked exactly as the ``substances`` module checks it, so
    the result can be passed as ``substance_outputs``. For StandardMale@0s.xml that is
    about 17,000 entries; BioGears serves them all, and reading them adds little per step.
    """
    from ..runtime import runtime_dir as find_runtime
    from ..runtime import state_path
    from .state import read_state

    state = read_state(state_path(find_runtime(runtime_dir), state_file))
    properties = properties or {**LIQUID_PROPERTIES, **GAS_PROPERTIES, **BODY_PROPERTIES}
    if compartments is None:
        compartments = [None, *sorted(set(state.compartments["LiquidCompartment"])
                                      | set(state.compartments.get("GasCompartment", {})))]
    entries = []
    for sub in sorted(substances or state.substances):
        for comp in compartments:
            for prop, unit in properties.items():
                entry = {"substance": sub, "property": prop}
                if comp is not None:
                    entry["compartment"] = comp
                if unit:
                    entry["unit"] = unit
                try:
                    _substance_outputs({"substance_outputs": [entry]}, state, ["substances"])
                except ValueError:
                    continue
                entries.append(entry)
    return entries


_LIST = {"_type": "list", "_default": []}

SUBSTANCES = CircuitModule(
    name="substances",
    description="The substance quantities listed in substance_outputs.",
    params={"substance_outputs": dict(_LIST)},
    prepare=_substance_outputs,
)
TISSUES = CircuitModule(
    name="tissues",
    description="The tissue values listed in tissue_outputs.",
    params={"tissue_outputs": dict(_LIST)},
    prepare=_tissue_outputs,
)
