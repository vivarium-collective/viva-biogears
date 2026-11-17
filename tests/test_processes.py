"""BioGearsProcess against the real engine. The oracle is a pybiogears engine driven
directly with the same actions (pybiogears itself matches BioGears' own bg-scenario
to 1e-13; pybiogears probe P4), so these tests check the bridge, not the physiology."""
import math

import numpy as np
import pytest

from viva_biogears.processes import VITALS, BioGearsProcess, MapFluidController
from viva_biogears.core import build_core
from viva_biogears.runtime import BioGearsNotFoundError

_CORE = build_core()


def make(config=None, cls=BioGearsProcess):
    return cls(config or {}, core=_CORE)


def _vec(d):
    return np.array([d[k] for k in VITALS], dtype=float)


def _run(proc, seconds, **setpoints):
    state = {"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0, **setpoints}
    out = None
    for _ in range(int(seconds)):
        out = proc.update(state, 1.0)
    return out


def test_initial_state_is_the_loaded_biogears_state(direct_engine):
    p = make({})
    init = p.initial_state()
    truth = direct_engine().pull()[1:]
    np.testing.assert_array_equal(_vec(init)[:-1], truth[:-1])  # last: NaN until a bleed
    assert math.isnan(init["total_blood_volume_lost_mL"])
    assert init["irreversible_state"] is False
    assert init["hemorrhage_rate_mL_per_min"] == 0.0 and init["iv_rate_mL_per_min"] == 0.0


def test_update_emits_biogears_readings_with_actions(direct_engine):
    """Falsifies: the bridge sends actions at the wrong time or emits stale or converted values."""
    p = make({})
    p.initial_state()
    _run(p, 5)
    _run(p, 10, hemorrhage_rate_mL_per_min=200.0)
    out = _run(p, 10, hemorrhage_rate_mL_per_min=200.0, iv_rate_mL_per_min=100.0)
    import pybiogears as pb
    e = direct_engine()
    for _ in range(5):
        e.advance(1.0)
    e.process_actions(pb.actions.hemorrhage("RightLeg", 200.0))
    for _ in range(10):
        e.advance(1.0)
    e.process_actions(pb.actions.substance_compound_infusion("Saline", 10000.0, 100.0))
    for _ in range(10):
        e.advance(1.0)
    np.testing.assert_allclose(_vec(out), e.pull()[1:], rtol=1e-12)


def test_hemorrhage_lowers_blood_volume_and_raises_heart_rate():
    p = make({})
    init = p.initial_state()
    out = _run(p, 120, hemorrhage_rate_mL_per_min=300.0)
    # The leg bleed rate falls with local pressure: 300 mL/min initial removes ~190 mL in 2 min.
    assert out["blood_volume_mL"] < init["blood_volume_mL"] - 100.0
    assert out["heart_rate_bpm"] > init["heart_rate_bpm"]
    # Mass balance: what left the vasculature is at least the blood-volume drop
    # (transcapillary refill only adds blood back).
    assert out["total_blood_volume_lost_mL"] >= init["blood_volume_mL"] - out["blood_volume_mL"] - 1e-6


def test_zero_rate_is_identical_to_no_action(direct_engine):
    p = make({})
    p.initial_state()
    out = _run(p, 20)  # setpoints stay 0.0: nothing is sent
    e = direct_engine()
    for _ in range(20):
        e.advance(1.0)
    assert np.array_equal(_vec(out)[:-1], e.pull()[1:-1])


def test_infusion_adds_volume():
    a, b = make(), make()
    a.initial_state(), b.initial_state()
    plain = _run(a, 60)
    infused = _run(b, 60, iv_rate_mL_per_min=200.0)
    assert infused["blood_volume_mL"] > plain["blood_volume_mL"] + 100.0  # 200 mL infused


def test_infusion_rate_back_to_zero_stops_it():
    p = make({})
    p.initial_state()
    _run(p, 30, iv_rate_mL_per_min=200.0)
    stopped = _run(p, 1)
    later = _run(p, 30)
    assert abs(later["blood_volume_mL"] - stopped["blood_volume_mL"]) < 10.0


def test_rejects_unknown_compartment():
    with pytest.raises(ValueError, match="hemorrhage_compartment"):
        make({"hemorrhage_compartment": "Nowhere"})


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_rejects_bad_setpoints(value):
    p = make({})
    p.initial_state()
    with pytest.raises(ValueError, match="must be a finite number"):
        p.update({"hemorrhage_rate_mL_per_min": value, "iv_rate_mL_per_min": 0.0}, 1.0)


def test_rejects_rate_above_cardiac_output():
    p = make({"hemorrhage_compartment": "Aorta"})
    p.initial_state()
    with pytest.raises(ValueError, match="refused"):
        p.update({"hemorrhage_rate_mL_per_min": 20000.0, "iv_rate_mL_per_min": 0.0}, 1.0)


def test_unknown_iv_compound_is_rejected_at_load():
    p = make({"iv_compound": "Unobtainium"})
    with pytest.raises(ValueError, match="not a BioGears compound"):
        p.initial_state()


def test_shipped_compound_loads():
    p = make({"iv_compound": "Blood_ONegative"})
    p.initial_state()
    out = _run(p, 30, iv_rate_mL_per_min=100.0)
    assert out["blood_volume_mL"] > 5532.0


def test_missing_state_file_is_reported():
    with pytest.raises(FileNotFoundError):
        make({"state_file": "NoSuchPatient@0s.xml"}).initial_state()


def test_state_with_an_active_infusion_starts_at_its_rate(tmp_path, direct_engine):
    """A state saved while infusing starts the iv setpoint at the infusion's rate; an
    infusion of another compound than iv_compound raises (the setpoint couldn't stop it)."""
    import pybiogears as pb
    e = direct_engine()
    e.process_actions(pb.actions.substance_compound_infusion("Saline", 500.0, 100.0))
    e.advance(2.0)
    path = tmp_path / "infusing.xml"
    e.save_state(path)
    p = make({"state_file": str(path)})
    p.initial_state()
    assert p._bridge.applied == {"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 100.0}
    with pytest.raises(ValueError, match="Saline"):
        make({"state_file": str(path), "iv_compound": "RingersLactate"}).initial_state()


def test_explicit_bad_runtime_dir_raises_instead_of_falling_back(tmp_path):
    with pytest.raises(BioGearsNotFoundError, match="runtime_dir"):
        make({"runtime_dir": str(tmp_path)}).initial_state()


def test_bad_env_runtime_dir_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("BIOGEARS_RUNTIME", str(tmp_path))
    with pytest.raises(BioGearsNotFoundError, match="BIOGEARS_RUNTIME"):
        make({}).initial_state()


@pytest.mark.parametrize("map_mmHg, expected", [(95.0, 0.0), (80.0, 250.0), (88.0, 50.0)])
def test_map_fluid_controller(map_mmHg, expected):
    c = make({}, MapFluidController)
    assert c.update({"mean_arterial_pressure_mmHg": map_mmHg})["iv_rate_mL_per_min"] == pytest.approx(expected)


def test_time_step_reaches_the_engine():
    """Falsifies: time_step_s ignored (the engine would keep the state's 0.02 s step).
    Oracle: an engine loaded directly with pybiogears' TimeStep override."""
    import pybiogears as pb

    from viva_biogears.runtime import runtime_dir
    p = make({"time_step_s": 0.04})
    p.initial_state()
    out = _run(p, 10, hemorrhage_rate_mL_per_min=200.0)
    assert p._bridge.engine.time_step_s == 0.04
    rt = runtime_dir()
    e = pb.BioGearsEngine(rt)
    e.set_requests([pb.DataRequest("Physiology", prop, unit) for prop, unit in VITALS.values()])
    e.load_state(rt / "states" / "StandardMale@0s.xml", configuration=pb.configuration(rt, TimeStep=(0.04, "s")))
    e.process_actions(pb.actions.hemorrhage("RightLeg", 200.0))
    for _ in range(10):
        e.advance(1.0)
    np.testing.assert_allclose(_vec(out), e.pull()[1:], rtol=1e-12)
    default = make({})
    default.initial_state()
    assert not np.allclose(_vec(_run(default, 10, hemorrhage_rate_mL_per_min=200.0)), _vec(out), rtol=1e-9)


@pytest.mark.parametrize("value", [0.0, -0.02, 0.1, 0.5, float("nan")])
def test_rejects_bad_time_step(value):
    with pytest.raises(ValueError, match="time_step_s"):
        make({"time_step_s": value})
