"""Pre-registered criteria for the REFRESH protocols (McDaniel et al. 2019, Figs 11-13;
see study.yaml). The goals and doses are the paper's; comparisons are directions."""

import numpy as np
import pytest

CLIN = "circuits.infection.clinical."
MAP = CLIN + "mean_arterial_pressure_mmHg"
SBP = CLIN + "systolic_pressure_mmHg"
PATHOGEN = "circuits.infection.inflammation.blood_pathogen"
IV = "interventions.cardiovascular.iv_rate_mL_per_min"
NOR = "interventions.treatment.vasopressor_rate_ug_per_min"
GIVEN = "protocol.saline_given_mL"
WEIGHT_kg = 75.8                        # StandardMale
#: arm -> (run length h, protocol start h)
ARMS = {"refresh-control": (52.0, 46.0), "refresh-experimental": (52.0, 46.0),
        "refresh-control-delayed": (64.0, 58.0)}


@pytest.fixture(scope="module")
def arms(latest):
    missing = [arm for arm in ARMS if arm not in latest]
    assert not missing, f"no completed run for arms {missing}"
    for arm, (duration_h, _) in ARMS.items():
        assert len(latest[arm].time) >= duration_h * 60, f"{arm} recorded {len(latest[arm].time)} rows"
    return latest


def hours(run, arm):
    t = run.time
    return (t - t[0]) / (t[-1] - t[0]) * ARMS[arm][0]


def at(runs, arm, observable, h):
    run = runs[arm]
    return float(run.observable(observable)[np.argmin(np.abs(hours(run, arm) - h))])


def window(runs, arm, observable, a_h, b_h):
    run = runs[arm]
    t = hours(run, arm)
    return run.observable(observable)[(t >= a_h - 1e-6) & (t < b_h - 1e-6)]


@pytest.mark.parametrize("arm, until_h", [("refresh-experimental", 46.0), ("refresh-control-delayed", 44.0)])
def test_arms_agree_before_treatment(arms, arm, until_h):
    a, b = window(arms, arm, MAP, 0, until_h), window(arms, "refresh-control", MAP, 0, until_h)
    np.testing.assert_allclose(a, b, rtol=1e-6)


def test_protocols_start_on_time(arms):
    assert window(arms, "refresh-control", IV, 46.0, 46.25).max() > 0.0
    assert window(arms, "refresh-control-delayed", IV, 45.0, 56.0).max() == 0.0
    assert window(arms, "refresh-control-delayed", IV, 58.0, 58.25).max() > 0.0
    nor = window(arms, "refresh-experimental", NOR, 46.0, 46.1)
    assert nor.max() == pytest.approx(0.18 * WEIGHT_kg)
    assert window(arms, "refresh-control", NOR, 0, 52.0).max() == 0.0


@pytest.mark.parametrize("arm", list(ARMS))
def test_saline_given_matches_the_recorded_rate(arms, arm):
    run = arms[arm]
    assert run.observable(IV).sum() * 1.0 == pytest.approx(run.final(GIVEN), abs=1.0)


@pytest.mark.parametrize("arm", list(ARMS))
def test_each_protocol_meets_the_goals(arms, arm):
    end = ARMS[arm][0]
    assert at(arms, arm, SBP, end) > 90.0 and at(arms, arm, MAP, end) > 65.0


def test_experimental_uses_less_saline(arms):
    assert arms["refresh-experimental"].final(GIVEN) < arms["refresh-control"].final(GIVEN)


def test_delay_meets_a_sicker_patient(arms):
    assert at(arms, "refresh-control-delayed", MAP, 58.0) < at(arms, "refresh-control", MAP, 46.0)


def test_delay_costs_more_saline(arms):
    assert arms["refresh-control-delayed"].final(GIVEN) > arms["refresh-control"].final(GIVEN)


@pytest.mark.parametrize("arm", list(ARMS))
def test_the_antibiotic_lowers_the_pathogen(arms, arm):
    start = ARMS[arm][1]
    assert arms[arm].final(PATHOGEN) < at(arms, arm, PATHOGEN, start)
