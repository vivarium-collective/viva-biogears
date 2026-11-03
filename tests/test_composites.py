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
