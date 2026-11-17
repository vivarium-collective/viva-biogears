"""Deprecated names keep working: BioGearsCircuitProcess (now BioGearsModularProcess),
the viva_biogears.circuits package (now viva_biogears.modules) and
biogears_whole_body_circuits (now biogears_whole_body)."""
import importlib
import sys

import pytest
from process_bigraph import Composite, gather_emitter_results

from viva_biogears.core import build_core


def test_the_old_package_name_imports_the_same_objects():
    import viva_biogears.modules.treatment as treatment
    sys.modules.pop("viva_biogears.circuits", None)
    with pytest.warns(DeprecationWarning, match="viva_biogears.modules"):
        old = importlib.import_module("viva_biogears.circuits")
    from viva_biogears.circuits.treatment import TREATMENT
    from viva_biogears.modules import MODULES
    assert old.MODULES is MODULES and TREATMENT is treatment.TREATMENT


def test_the_old_composite_name_is_the_new_one():
    from viva_biogears.composites import biogears_whole_body, biogears_whole_body_circuits
    assert biogears_whole_body_circuits is biogears_whole_body


def test_a_document_with_the_old_process_address_runs_the_same():
    """Falsifies: the alias not registered, or behaving differently from the new class."""
    from viva_biogears.composites import biogears_cardiovascular
    rows = {}
    for address in ("local:BioGearsModularProcess", "local:BioGearsCircuitProcess"):
        core = build_core()
        doc = biogears_cardiovascular(core, hemorrhage_rate_mL_per_min=100.0)
        doc["biogears"]["address"] = address
        with pytest.warns(DeprecationWarning) if "Circuit" in address else _nothing():
            sim = Composite({"state": doc}, core=core)
            sim.run(3.0)
        rows[address] = gather_emitter_results(sim)[("emitter",)][-1]["readings"]
    assert rows["local:BioGearsCircuitProcess"] == rows["local:BioGearsModularProcess"]


class _nothing:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
