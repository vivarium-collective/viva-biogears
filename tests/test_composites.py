"""Composite generators: registration, wiring, and real-engine runs."""
import math

import pytest
from process_bigraph.composite_generator import _REGISTRY

from viva_biogears.composites import biogears_hemorrhage, biogears_resuscitation
from viva_biogears.processes import VITALS


@pytest.mark.parametrize("name", ["biogears_hemorrhage", "biogears_resuscitation"])
def test_generator_is_registered(name):
    assert [eid for eid in _REGISTRY if eid.endswith(f".{name}")], list(_REGISTRY)[:5]


def test_first_emitted_row_carries_loaded_vitals(run_composite):
    """Falsifies: the t=0 row doesn't carry the loaded state (process-bigraph < 1.10.1
    dropped initial_state() on overwrite[float] ports)."""
    _, rows = run_composite(biogears_hemorrhage, 1.0)
    first = rows[0]
    assert first["time"] == 0.0
    assert first["heart_rate_bpm"] == pytest.approx(72.0, abs=0.5)
    assert first["blood_volume_mL"] == pytest.approx(5532.4, abs=1.0)
    assert first["irreversible_state"] is False


def test_hemorrhage_composite_stores_track_the_engine(run_composite):
    """Falsifies: the stores don't hold BioGears' reading while it changes (deltas
    emitted into overwrite ports, or readings into additive ones)."""
    sim, rows = run_composite(biogears_hemorrhage, 60.0)
    assert len(rows) == 61
    truth = sim.state["biogears"]["instance"]._read_vitals()
    for k in VITALS:
        assert rows[-1][k] == pytest.approx(truth[k], rel=1e-12)
    assert rows[-1]["total_blood_volume_lost_mL"] > 100.0


def test_resuscitation_controller_engages_and_preserves_volume(run_composite):
    kw = dict(compartment="Aorta", rate_mL_per_min=600.0)
    _, untreated = run_composite(biogears_hemorrhage, 300.0, **kw)
    _, treated = run_composite(biogears_resuscitation, 300.0, **kw)
    assert treated[0]["iv_rate_mL_per_min"] == 0.0  # MAP starts above target
    assert max(r["iv_rate_mL_per_min"] for r in treated) > 0.0
    assert treated[-1]["blood_volume_mL"] > untreated[-1]["blood_volume_mL"] + 50.0
    assert treated[-1]["mean_arterial_pressure_mmHg"] > untreated[-1]["mean_arterial_pressure_mmHg"]


def test_lethal_hemorrhage_reaches_irreversible_state_and_stops(run_composite):
    _, rows = run_composite(biogears_hemorrhage, 220.0, compartment="Aorta", rate_mL_per_min=1500.0)
    dead = [i for i, r in enumerate(rows) if r["irreversible_state"]]
    assert dead, "BioGears never reported an irreversible state"
    frozen = rows[dead[0]:]
    assert all(r["blood_volume_mL"] == frozen[0]["blood_volume_mL"] for r in frozen)
    assert not math.isnan(frozen[0]["blood_volume_mL"])


CIRCUIT_COMPOSITES = ["biogears_cardiovascular", "biogears_respiratory", "biogears_mechanical_ventilation",
                      "biogears_thermal", "biogears_supplemental_oxygen", "biogears_whole_body",
                      "biogears_lymph"]


def _leaves(tree, prefix=()):
    for k, v in tree.items():
        if isinstance(v, dict):
            yield from _leaves(v, prefix + (k,))
        else:
            yield prefix + (k,), v


@pytest.mark.parametrize("name", CIRCUIT_COMPOSITES)
def test_circuit_composite_stores_track_the_engine(run_composite, name):
    """Falsifies: the store layout (interventions/<module>, readings/<module>) or the
    emitter drops or misplaces readings; every emitted leaf equals the process's reading."""
    import viva_biogears.composites as composites
    assert [eid for eid in _REGISTRY if eid.endswith(f".{name}")]
    sim, rows = run_composite(getattr(composites, name), 5.0)
    assert len(rows) == 6 and rows[0]["time"] == 0.0
    truth = sim.state["biogears"]["instance"].read()
    emitted = dict(_leaves(rows[-1]["readings"]))
    for path, value in _leaves(truth):
        assert emitted[path] == value or (math.isnan(value) and math.isnan(emitted[path])), path
    assert set(rows[-1]["interventions"]) == {m.name for m in sim.state["biogears"]["instance"]._modules
                                              if m.bindings}


def test_lymph_composite_infuses_from_the_equilibrated_state(run_composite):
    from viva_biogears.composites import biogears_lymph
    sim, rows = run_composite(biogears_lymph, 30.0, iv_rate_mL_per_min=200.0)
    first, last = rows[0]["readings"], rows[-1]["readings"]
    assert first["tissue_fluid"]["blood_volume_mL"] == pytest.approx(5880, abs=1)
    assert rows[-1]["interventions"]["cardiovascular"]["iv_rate_mL_per_min"] == 200.0
    assert last["lymph"]["central_venous_pressure_mmHg"] > first["lymph"]["central_venous_pressure_mmHg"]


def test_composites_validate_parameters_when_built():
    from viva_biogears.composites import biogears_thermal, biogears_whole_body
    with pytest.raises(ValueError):
        biogears_thermal(None, relative_humidity=2.0)
    with pytest.raises(TypeError, match="unexpected"):
        biogears_thermal(None, humidity=0.5)
    with pytest.raises(ValueError, match="one airway device"):
        biogears_whole_body(None, connected=1.0, oxygen_connected=1.0)
