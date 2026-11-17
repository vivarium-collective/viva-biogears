"""Pre-registered criteria for sepsis progression by severity (McDaniel et al. 2019, Figs
4-7; see study.yaml). Windows are centred on the paper's onset times; orderings come from
the 2026-11-14 bg-scenario pilot."""

import numpy as np
import pytest

INFL = "readings.infection.inflammation."
CLIN = "readings.infection.clinical."
ARMS = ["control", "mild", "moderate", "severe"]
INFECTED = ARMS[1:]
DURATION_H = 48.0
SUSTAIN_H = 0.5


@pytest.fixture(scope="module")
def arms(latest):
    missing = [arm for arm in ARMS if arm not in latest]
    assert not missing, f"no completed run for arms {missing}"
    for arm in ARMS:
        assert len(latest[arm].time) >= DURATION_H * 60, f"{arm} recorded {len(latest[arm].time)} rows"
    return latest


def hours(run):
    """Recorded rows in hours since the start (one row per 60 s update)."""
    t = run.time
    return (t - t[0]) / (t[-1] - t[0]) * DURATION_H


def onset(run, observable, condition):
    """First time (h) ``condition`` holds and keeps holding for SUSTAIN_H; None if never."""
    t, ok = hours(run), condition(run.observable(observable))
    for i in np.flatnonzero(ok):
        if t[-1] < t[i] + SUSTAIN_H - 1e-6:
            return None                      # not enough run left to tell
        j = np.searchsorted(t, t[i] + SUSTAIN_H + 1e-6)
        if ok[i:j].all():
            return float(t[i])
    return None


def test_control_stays_uninfected_and_stable(arms):
    control = arms["control"]
    assert np.nanmax(control.observable(INFL + "blood_pathogen")) == 0.0
    assert control.observable(CLIN + "lactate_mmol_per_L").max() < 2.0
    assert control.observable(CLIN + "mean_arterial_pressure_mmHg").min() > 85.0


@pytest.mark.parametrize("observable", ["blood_pathogen", "tumor_necrosis_factor", "interleukin_6"])
def test_severity_orders_the_inflammatory_response(arms, observable):
    peaks = [arms[arm].observable(INFL + observable).max() for arm in INFECTED]
    assert peaks[0] < peaks[1] < peaks[2], dict(zip(INFECTED, peaks))


def test_lowest_tissue_integrity_falls_with_severity(arms):
    lows = [arms[arm].observable(INFL + "tissue_integrity").min() for arm in INFECTED]
    assert lows[0] > lows[1] > lows[2], dict(zip(INFECTED, lows))


@pytest.mark.parametrize("arm", ["mild", "moderate"])
def test_mild_and_moderate_stay_compensated(arms, arm):
    run = arms[arm]
    assert onset(run, CLIN + "lactate_mmol_per_L", lambda x: x > 2.0) is None
    assert onset(run, CLIN + "systolic_pressure_mmHg", lambda x: x < 100.0) is None


def test_severe_lactate_onset(arms):
    """Paper: lactate > 2 mM after about 20 h (pilot 16.5 h)."""
    t = onset(arms["severe"], CLIN + "lactate_mmol_per_L", lambda x: x > 2.0)
    assert t is not None and 12.0 <= t <= 24.0, t


def test_severe_hypotension_onset(arms):
    """Paper: SBP < 100 mmHg at about 26 h (pilot 26.8 h)."""
    t = onset(arms["severe"], CLIN + "systolic_pressure_mmHg", lambda x: x < 100.0)
    assert t is not None and 22.0 <= t <= 32.0, t


def test_severe_loses_volume_and_turns_tachycardic(arms):
    severe = arms["severe"]
    bv = severe.observable(CLIN + "blood_volume_mL")
    assert bv[-1] < bv[0] - 1000.0
    assert severe.final(CLIN + "heart_rate_bpm") > 100.0


def test_severe_does_not_reach_septic_shock_by_48_h(arms):
    """A known divergence from the paper (shock at about 45 h): on 8.2.0 MAP stays above
    65 mmHg (pilot low 72.4). Fails, flagging the change, if a later BioGears reaches shock."""
    assert onset(arms["severe"], CLIN + "mean_arterial_pressure_mmHg", lambda x: x < 65.0) is None
