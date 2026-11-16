"""Pre-registered criteria for the BioGears hemorrhage patient cohort (see study.yaml).

Thresholds sit below the 2026-11-16 pilot of every arm."""

import math
from pathlib import Path

import numpy as np
import pytest
import yaml

BV = "vitals.blood_volume_mL"
CO = "vitals.cardiac_output_L_per_min"
HR = "vitals.heart_rate_bpm"
LOST = "vitals.total_blood_volume_lost_mL"
MAP = "vitals.mean_arterial_pressure_mmHg"
SPEC = yaml.safe_load((Path(__file__).parents[1] / "study.yaml").read_text())
PATIENTS = [entry["name"] for entry in SPEC["baseline"] + SPEC["variants"]]
DURATION_S = 600.0


def spearman(x, y):
    ranks = lambda values: np.asarray(values).argsort().argsort()
    return float(np.corrcoef(ranks(x), ranks(y))[0, 1])


@pytest.fixture(scope="module")
def runs(latest):
    missing = [p for p in PATIENTS if p not in latest]
    assert not missing, f"no completed run for {missing}"
    return [latest[p] for p in PATIENTS]


def test_every_shipped_patient_ran(latest, runs):
    assert len(PATIENTS) == 17
    short = [p for p in PATIENTS if latest[p].time[-1] != DURATION_S]
    assert not short, f"runs that stopped before {DURATION_S} s: {short}"


@pytest.mark.parametrize("patient", PATIENTS)
def test_every_patient_bleeds_and_compensates(latest, patient):
    run = latest[patient]
    lost = run.final(LOST)
    assert not math.isnan(lost) and lost > 0.0
    assert run.final(BV) < run.initial(BV)
    assert run.final(HR) > run.initial(HR)
    assert run.final(MAP) < run.initial(MAP)


def test_smaller_patients_lose_a_larger_fraction(runs):
    volume = np.array([run.initial(BV) for run in runs])
    fraction = np.array([run.final(LOST) for run in runs]) / volume
    assert spearman(volume, fraction) <= -0.4
    resting = np.array([abs(run.initial(HR) - 72.0) < 1.0 for run in runs])
    assert resting.sum() >= 8
    assert spearman(volume[resting], fraction[resting]) <= -0.7


def test_loss_rises_with_resting_cardiac_output(runs):
    assert spearman([run.initial(CO) for run in runs], [run.final(LOST) for run in runs]) >= 0.5


def test_reference_patient_reproduces_pilot(latest):
    run = latest["StandardMale"]
    assert run.final(BV) == pytest.approx(4888, abs=5)
    assert run.final(MAP) == pytest.approx(87.9, abs=0.5)
