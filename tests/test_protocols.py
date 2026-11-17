"""McDaniel et al. 2019's treatment protocols (viva_biogears.protocols), without the engine.

Oracle: the paper's protocol text (Methods), turned into volumes: each test feeds readings
and checks the saline and norepinephrine given, as the paper describes them."""
import pytest

from viva_biogears.protocols import ANTIBIOTIC, TreatmentProtocol

H = 3600.0


def drive(p, until_h, sbp=80.0, map_=60.0, uo=0.3, step=60.0):
    """Run the protocol minute by minute with constant readings; the saline mL per minute
    and norepinephrine ug/min, by update start time."""
    out = {}
    t = 0.0
    while t < until_h * H - 1e-6:
        out[t] = p.setpoints(t, sbp, map_, uo)
        t += step
    return out


def given(rates, a_h, b_h):
    return sum(r * 1.0 for t, (r, _) in rates.items() if a_h * H - 1e-6 <= t < b_h * H - 1e-6)


def test_fluid_challenge_is_two_500_mL_boluses_at_44_and_44_5_h():
    p = TreatmentProtocol("fluid_challenge")
    rates = drive(p, 46)
    assert given(rates, 0, 44) == 0
    assert given(rates, 44, 44.5) == pytest.approx(500)
    assert given(rates, 44.5, 46) == pytest.approx(500)
    assert max(r for r, _ in rates.values()) == 50.0        # BioGears' scenario's bolus rate
    assert p.schedule() == [] and p.end_h == 46.0


def test_antibiotic_adds_piperacillin_at_46_h_and_nothing_else():
    p = TreatmentProtocol("antibiotic")
    rates = drive(p, 52)
    assert p.schedule() == [{"hour": 46.0, **ANTIBIOTIC}]
    assert given(rates, 44, 52) == pytest.approx(1000)
    assert ANTIBIOTIC["bag_volume_mL"] * 0.2 == pytest.approx(4.0)      # 4 g piperacillin (+0.5 g tazobactam)
    assert ANTIBIOTIC["bag_volume_mL"] / ANTIBIOTIC["rate_mL_per_min"] == pytest.approx(30, abs=0.1)
    assert p.end_h == 52.0


def test_refresh_control_while_goals_are_never_met():
    """Hypotensive and oliguric throughout: 1000 mL at the start, 500 mL every 30 min (12
    checks in 6 h) and 500 mL more at each hourly urine check (6)."""
    p = TreatmentProtocol("refresh_control")
    rates = drive(p, 52.5)
    expected = 1000 + 12 * 500 + 6 * 500
    assert given(rates, 46, 52.5) == pytest.approx(expected)
    assert all(v == 0 for _, v in rates.values())           # no vasopressor in the control arm


def test_refresh_control_stops_when_goals_are_met():
    p = TreatmentProtocol("refresh_control")
    drive(p, 46.5, sbp=80, map_=60, uo=0.3)                  # start: 1000 mL queued
    rate, _ = p.setpoints(46.5 * H, 95.0, 70.0, 0.3)         # first check: goals met
    assert p.state["stopped"] and p.state["queue_mL"] == 0
    assert rate == pytest.approx(75 / 60)                    # maintenance at 75 mL/h
    later = drive(p, 52, sbp=60, map_=50)                    # no more boluses, whatever happens
    assert all(r == pytest.approx(75 / 60) for t, (r, _) in later.items() if t > 46.5 * H)


def test_refresh_experimental_maintenance_norepinephrine_and_250_mL_boluses():
    p = TreatmentProtocol("refresh_experimental", weight_kg=75.8)
    rates = drive(p, 52.5)
    maintenance = 75.8 / 60.0
    nor = {v for t, (_, v) in rates.items() if t >= 46 * H}
    assert len(nor) == 1 and nor.pop() == pytest.approx(0.18 * 75.8)
    # 6 hourly checks with low urine output: 6 x 250 mL, plus 1 mL/kg/h for 6.5 h.
    assert given(rates, 46, 52.5) == pytest.approx(6 * 250 + maintenance * 6.5 * 60)


def test_refresh_experimental_stops_all_but_maintenance_at_goals():
    p = TreatmentProtocol("refresh_experimental")
    drive(p, 47)
    rate, nor = p.setpoints(47 * H, 95.0, 70.0, 0.3)
    assert p.state["stopped"] and nor == 0.0 and rate == pytest.approx(75.8 / 60)


def test_state_round_trip_continues_the_protocol():
    """run.py saves ``state`` with each checkpoint; a protocol rebuilt from it continues."""
    a = TreatmentProtocol("refresh_control")
    drive(a, 47.2)
    b = TreatmentProtocol("refresh_control", state=a.state)
    ra = drive(a, 52)
    rb = drive(b, 52)
    assert {t: v for t, v in ra.items() if t >= 47.2 * H} == {t: v for t, v in rb.items() if t >= 47.2 * H}


def test_delayed_treatment_shifts_everything_12_h():
    p = TreatmentProtocol("refresh_control", challenge_h=56, start_h=58)
    rates = drive(p, 64.5)
    assert given(rates, 0, 56) == 0 and given(rates, 56, 57) == pytest.approx(1000)
    assert p.schedule()[0]["hour"] == 58.0 and p.end_h == 64.0


@pytest.mark.parametrize("kw, match", [({"protocol": "magic"}, "protocol"), ({"start_h": 44.5}, "after"),
                                       ({"weight_kg": 0}, "weight_kg")])
def test_bad_protocols_raise(kw, match):
    with pytest.raises(ValueError, match=match):
        TreatmentProtocol(**{"protocol": "refresh_control", **kw})


def test_events_are_due_when_the_clock_runs_microseconds_behind():
    """The shipped 44 h state is at 158399.999994 s; the 44 h challenge must start on the
    first update from it, not one update (60 s) late."""
    p = TreatmentProtocol("fluid_challenge")
    rate, _ = p.setpoints(158399.999994, 80.0, 60.0, 0.3)
    assert rate == 50.0
