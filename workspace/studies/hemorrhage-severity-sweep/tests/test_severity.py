"""Pre-registered criteria for the BioGears hemorrhage severity sweep (see study.yaml).

Thresholds come from the 2026-11-16 pilot of the same arms (study.yaml, preregistered)."""

import math
from itertools import pairwise

import pytest

BV = "vitals.blood_volume_mL"
HR = "vitals.heart_rate_bpm"
LOST = "vitals.total_blood_volume_lost_mL"
MAP = "vitals.mean_arterial_pressure_mmHg"
RATES = ["0", "50", "100", "150", "200", "250"]
DURATION_S = 600.0


@pytest.fixture(scope="module")
def grid(latest):
    missing = [r for r in RATES if f"rate-{r}" not in latest]
    assert not missing, f"no completed run for rates {missing}"
    runs = [latest[f"rate-{r}"] for r in RATES]
    for run in runs:
        assert run.time[-1] == DURATION_S, f"{run.label} ran to t={run.time[-1]}"
    return runs


def _largest_deviation(run, observable):
    """Largest distance of any recorded sample (1 s apart) from the run's first one."""
    series = run.observable(observable)
    return max(abs(x - series[0]) for x in series)


def test_no_bleed_control_is_flat(grid):
    control = grid[0]
    lost = control.final(LOST)
    assert math.isnan(lost) or lost < 1.0          # BioGears reports NaN until a bleed starts
    assert abs(control.final(MAP) - control.initial(MAP)) < 1.0
    assert abs(control.final(HR) - control.initial(HR)) < 1.0
    assert abs(control.final(BV) - control.initial(BV)) < 30.0


def test_blood_loss_rises_with_rate(grid):
    lost = [run.final(LOST) for run in grid[1:]]
    assert all(a < b for a, b in pairwise(lost)), lost
    volume = [run.final(BV) for run in grid]
    assert all(a > b for a, b in pairwise(volume)), volume


def test_heart_rate_rises_with_rate(grid):
    rates = [run.final(HR) for run in grid]
    assert all(a < b for a, b in pairwise(rates)), rates


def test_pressure_falls_with_rate(grid):
    pressures = [run.final(MAP) for run in grid]
    assert all(a > b for a, b in pairwise(pressures)), pressures


def test_every_bleed_leaves_the_band(grid):
    """Unlike Pulse at severity 0.2-0.4, no BioGears bleed here keeps MAP within 2 mmHg."""
    deviations = [_largest_deviation(run, MAP) for run in grid[1:]]
    assert min(deviations) > 2.0, deviations


def test_pressure_falls_for_the_fastest_bleed(grid):
    fastest = grid[-1]
    assert fastest.initial(MAP) - fastest.final(MAP) >= 7.0


def test_loss_grows_more_slowly_than_the_rate(grid):
    """BioGears scales a bleed with the compartment pressure: five times the initial rate
    loses well under five times the blood (pilot: 2.2 times)."""
    assert grid[-1].final(LOST) < 3.0 * grid[1].final(LOST)


def test_blood_lost_bounds_the_volume_drop(grid):
    """Physical bound: blood volume can't fall by more than was lost (fluid shifts refill it)."""
    for run in grid[1:]:
        assert run.final(LOST) >= run.initial(BV) - run.final(BV) - 1.0, run.label


def test_reproduces_pilot(grid):
    run = grid[RATES.index("200")]
    assert run.final(BV) == pytest.approx(4888, abs=5)
    assert run.final(MAP) == pytest.approx(87.9, abs=0.5)
