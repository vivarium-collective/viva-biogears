"""Pre-registered criteria for BioGears' time step in a hemorrhage (see study.yaml).

Every arm is compared with the 0.02 s run (BioGears' validated step). Thresholds sit
outside the 2026-11-16 pilot of every arm (workspace/experiments/timestep-pilot-2026-11-16)."""

import sqlite3
from pathlib import Path

import numpy as np
import pytest

BV = "vitals.blood_volume_mL"
HR = "vitals.heart_rate_bpm"
LOST = "vitals.total_blood_volume_lost_mL"
MAP = "vitals.mean_arterial_pressure_mmHg"
STEPS = {"dt-0.02": 0.02, "dt-0.04": 0.04, "dt-0.08": 0.08}
DURATION_S = 300.0
DB = Path(__file__).parents[1] / "runs.db"


@pytest.fixture(scope="module")
def arms(latest):
    missing = [arm for arm in STEPS if arm not in latest]
    assert not missing, f"no completed run for arms {missing}"
    for arm in STEPS:
        assert latest[arm].time[-1] == DURATION_S, f"{arm} ran to t={latest[arm].time[-1]}"
    return latest


def deviation(arms, arm, observable):
    """Per-sample difference from the 0.02 s run."""
    return arms[arm].observable(observable) - arms["dt-0.02"].observable(observable)


def wall_s(run):
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conn:
        started, completed = conn.execute("SELECT started_at, completed_at FROM runs_meta WHERE run_id = ?",
                                          (run.run_id,)).fetchone()
    return completed - started


def test_reference_reproduces_the_pilot(arms):
    ref = arms["dt-0.02"]
    assert ref.final(MAP) == pytest.approx(91.70, abs=0.05)
    assert ref.final(BV) == pytest.approx(5179.3, abs=1.0)


@pytest.mark.parametrize("arm", list(STEPS))
def test_each_run_used_its_time_step(arms, arm):
    assert set(arms[arm].observable("engine.time_step_s")) == {STEPS[arm]}


@pytest.mark.parametrize("arm, volume_mL, lost_mL", [("dt-0.04", 2.0, 1.0), ("dt-0.08", 6.0, 4.0)])
def test_volumes_stay_accurate(arms, arm, volume_mL, lost_mL):
    assert np.abs(deviation(arms, arm, BV)).max() <= volume_mL
    assert abs(arms[arm].final(LOST) - arms["dt-0.02"].final(LOST)) <= lost_mL


@pytest.mark.parametrize("arm, hr_per_min", [("dt-0.04", 0.5), ("dt-0.08", 2.5)])
def test_vitals_agree_at_5_min(arms, arm, hr_per_min):
    assert abs(deviation(arms, arm, MAP)[-1]) <= 1.0
    assert abs(deviation(arms, arm, HR)[-1]) <= hr_per_min


def test_scatter_grows_with_step(arms):
    largest = {arm: np.abs(deviation(arms, arm, MAP)).max() for arm in ("dt-0.04", "dt-0.08")}
    assert largest["dt-0.04"] < largest["dt-0.08"], largest
    assert largest["dt-0.04"] <= 4.0 and largest["dt-0.08"] <= 8.0, largest
    assert np.abs(deviation(arms, "dt-0.04", HR)).max() < np.abs(deviation(arms, "dt-0.08", HR)).max()


def test_larger_steps_run_faster(arms):
    ref = wall_s(arms["dt-0.02"])
    assert ref >= 1.4 * wall_s(arms["dt-0.04"])
    assert ref >= 2.0 * wall_s(arms["dt-0.08"])
