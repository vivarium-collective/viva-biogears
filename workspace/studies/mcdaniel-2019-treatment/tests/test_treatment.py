"""Pre-registered criteria for the fluid challenge and antibiotic (McDaniel et al. 2019,
Figs 9-10; see study.yaml). Directions and the paper's MIC; no fitted numbers.

Every arm starts from the severe infection's state saved at 44 h, as in the paper; times
here are engine hours (hours since the infection): the run's ``protocol.branch_h`` plus
its own clock."""

import numpy as np
import pytest

CLIN = "readings.infection.clinical."
PATHOGEN = "readings.infection.inflammation.blood_pathogen"
IV = "interventions.cardiovascular.iv_rate_mL_per_min"
GIVEN = "protocol.saline_given_mL"
PIP = "readings.treatment.Piperacillin.plasma_concentration_ug_per_mL"
ARMS = ["untreated", "fluid-challenge", "antibiotic"]
BRANCH_H, END_H = 44.0, 52.0
MIC_ug_per_mL = 16.0                    # the paper's 16 mg/L


@pytest.fixture(scope="module")
def arms(latest):
    missing = [arm for arm in ARMS if arm not in latest]
    assert not missing, f"no completed run for arms {missing}"
    for arm in ARMS:
        run = latest[arm]
        assert run.initial("protocol.branch_h") == pytest.approx(BRANCH_H), f"{arm} did not start at {BRANCH_H} h"
        assert hours(run)[-1] == pytest.approx(END_H), f"{arm} ran to {hours(run)[-1]:.2f} h"
    return latest


def hours(run):
    """Engine hours of each recorded row (``Run.time`` is the composite's own clock, s)."""
    return run.initial("protocol.branch_h") + (run.time - run.time[0]) / 3600.0


def at(run, observable, h):
    """The recorded value nearest ``h`` hours."""
    return float(run.observable(observable)[np.argmin(np.abs(hours(run) - h))])


@pytest.mark.parametrize("arm, until_h", [("fluid-challenge", 44.0), ("antibiotic", 46.0)])
def test_arms_agree_before_treatment(arms, arm, until_h):
    """Determinism: an arm matches its comparator until its first action (for the
    challenge, the shared starting state)."""
    comparator = arms["untreated" if arm == "fluid-challenge" else "fluid-challenge"]
    before = hours(arms[arm]) <= until_h + 1e-6
    for observable in (CLIN + "mean_arterial_pressure_mmHg", CLIN + "blood_volume_mL", PATHOGEN):
        np.testing.assert_allclose(arms[arm].observable(observable)[before],
                                   comparator.observable(observable)[before], rtol=1e-6)


def test_untreated_gets_nothing(arms):
    assert arms["untreated"].observable(IV).max() == 0.0
    assert arms["untreated"].final(GIVEN) == 0.0


@pytest.mark.parametrize("arm", ARMS[1:])
def test_the_challenge_is_delivered(arms, arm):
    run = arms[arm]
    assert run.final(GIVEN) == pytest.approx(1000.0, abs=1.0)
    t, iv = hours(run), run.observable(IV)
    assert iv[(t < 44.0 - 1e-6) | (t > 45.0 + 1e-6)].max() == 0.0


@pytest.mark.parametrize("arm", ARMS[1:])
def test_saline_given_matches_the_recorded_rate(arms, arm):
    """The rate written each minute (mL/min x 1 min) adds up to the protocol's total."""
    run = arms[arm]
    assert run.observable(IV).sum() * 1.0 == pytest.approx(run.final(GIVEN), abs=1.0)


def test_the_challenge_raises_volume_and_pressure(arms):
    challenge, untreated = arms["fluid-challenge"], arms["untreated"]
    for observable in (CLIN + "blood_volume_mL", CLIN + "mean_arterial_pressure_mmHg"):
        assert at(challenge, observable, 45.0) > at(untreated, observable, 45.0), observable


def test_piperacillin_exceeds_the_mic(arms):
    assert np.nanmax(arms["antibiotic"].observable(PIP)) > MIC_ug_per_mL


def test_the_antibiotic_lowers_the_pathogen(arms):
    antibiotic = arms["antibiotic"]
    assert antibiotic.final(PATHOGEN) < arms["fluid-challenge"].final(PATHOGEN)
    assert antibiotic.final(PATHOGEN) < at(antibiotic, PATHOGEN, 46.0)
