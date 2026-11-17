"""Pre-registered criteria for BioGears' time step in the severe infection (see study.yaml).

Every arm is compared with the 0.02 s run (BioGears' validated step). Thresholds sit
outside the 2026-11-16 pilot of every arm (workspace/experiments/timestep-pilot-2026-11-16)."""

import sqlite3
from pathlib import Path

import numpy as np
import pytest

CLIN = "readings.infection.clinical."
INFL = "readings.infection.inflammation."
STEPS = {"dt-0.02": 0.02, "dt-0.04": 0.04, "dt-0.08": 0.08}
ROWS = 361                                   # 6 h at 60 s, plus the starting row
DB = Path(__file__).parents[1] / "runs.db"


@pytest.fixture(scope="module")
def arms(latest):
    missing = [arm for arm in STEPS if arm not in latest]
    assert not missing, f"no completed run for arms {missing}"
    for arm in STEPS:
        assert len(latest[arm].time) >= ROWS, f"{arm} recorded {len(latest[arm].time)} rows"
    return latest


def deviation(arms, arm, observable):
    return arms[arm].observable(observable) - arms["dt-0.02"].observable(observable)


def wall_s(run):
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as conn:
        started, completed = conn.execute("SELECT started_at, completed_at FROM runs_meta WHERE run_id = ?",
                                          (run.run_id,)).fetchone()
    return completed - started


@pytest.mark.parametrize("arm", list(STEPS))
def test_each_run_used_its_time_step(arms, arm):
    assert set(arms[arm].observable("engine.time_step_s")) == {STEPS[arm]}


@pytest.mark.parametrize("arm", ["dt-0.04", "dt-0.08"])
def test_inflammation_is_step_independent(arms, arm):
    pathogen = arms["dt-0.02"].observable(INFL + "blood_pathogen")
    assert (np.abs(deviation(arms, arm, INFL + "blood_pathogen")) <= 0.002 * np.abs(pathogen) + 1e-9).all()
    assert np.abs(deviation(arms, arm, INFL + "tissue_integrity")).max() <= 0.001


def test_hemodynamics_stay_close(arms):
    for observable, band in ((CLIN + "mean_arterial_pressure_mmHg", 3.0), (CLIN + "systolic_pressure_mmHg", 3.0),
                             (CLIN + "blood_volume_mL", 25.0)):
        largest = [np.abs(deviation(arms, arm, observable)).max() for arm in ("dt-0.04", "dt-0.08")]
        assert max(largest) <= band, (observable, largest)
        assert largest[0] < largest[1], (observable, largest)


def test_lactate_breaks_above_0_02_s(arms):
    lactate = CLIN + "lactate_mmol_per_L"
    assert arms["dt-0.02"].observable(lactate).max() < 2.0
    assert arms["dt-0.04"].final(lactate) > 5.0
    assert arms["dt-0.08"].final(lactate) > arms["dt-0.04"].final(lactate)


def test_larger_steps_run_faster(arms):
    ref = wall_s(arms["dt-0.02"])
    assert ref >= 1.5 * wall_s(arms["dt-0.04"])
    assert ref >= 2.2 * wall_s(arms["dt-0.08"])
