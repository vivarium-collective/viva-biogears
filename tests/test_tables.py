"""Patients and substances from BioGears' spreadsheet templates, and BioGears' patient check.

Nothing is mocked. The tables are converted by BioGears' own converters (through
pybiogears.generate_data), patients are judged by BioGears' own rules (through
pybiogears.check_patient, whose oracle is BioGears' log), and the engine runs the
results: a patient from a new CSV column stabilizes at its own heart rate, and a
substance and a compound from new columns are infused.
"""

import csv
import warnings

import pytest
from circuit_helpers import CORE

from viva_biogears.patients import CACHE_ENV_VAR, check_report_path, stabilized_state
from viva_biogears.processes import BioGearsProcess
from viva_biogears.processes._bridge import load_engine, resolve_state
from viva_biogears.runtime import BASE_MARKER, base_runtime, runtime_dir
from viva_biogears.modules.treatment import TREATMENT
from viva_biogears.tables import (
    PatientAdjustedWarning,
    patients_from_table,
    runtime_with_substances,
    start_patient,
    substances_from_table,
)


@pytest.fixture(scope="module", autouse=True)
def cache(tmp_path_factory):
    directory = tmp_path_factory.mktemp("cache")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(CACHE_ENV_VAR, str(directory))
        yield directory


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


def add_column(rows, values, copy_of=None, label="Name"):
    """``rows`` with a column appended: ``values`` by row label, the rest copied from the
    column whose ``label`` row holds ``copy_of``."""
    names = [c.strip() for c in next(r for r in rows if r and r[0] == label)]
    src = names.index(copy_of) if copy_of else None
    width = max(len(r) for r in rows)
    out = []
    for r in rows:
        r = r + [""] * (width - len(r))
        cell = values.get(r[0], r[src] if src is not None and r[0] else "") if r else ""
        out.append(r + [cell])
    return out


AVERY = {"Name": "Avery", "Sex": "Female", "Age": "30 yr", "Weight": "140 lb", "Height": "65 in",
         "BodyFatFraction": "0.25", "HeartRateBaseline": "68 bpm", "SystolicArterialPressureBaseline": "110 mmHg",
         "DiastolicArterialPressureBaseline": "72 mmHg", "RespirationRateBaseline": "14 bpm"}


@pytest.fixture(scope="module")
def patient_table(tmp_path_factory):
    """BioGears' own Patients.csv with three new columns: Avery (fine), Kid (refused:
    age 12) and Racer (heart rate 120 /min, which BioGears lowers to 109)."""
    rows = read_csv(runtime_dir() / "templates" / "Patients.csv")
    rows = add_column(rows, AVERY)
    rows = add_column(rows, {**AVERY, "Name": "Kid", "Age": "12 yr"})
    rows = add_column(rows, {**AVERY, "Name": "Racer", "HeartRateBaseline": "120 bpm"})
    path = tmp_path_factory.mktemp("tables") / "Patients.csv"
    write_csv(path, rows)
    return path


@pytest.fixture(scope="module")
def substance_table(tmp_path_factory):
    """A folder with Substances.csv (Morphine2, a copy of Morphine) and Compounds.csv
    (Saline2, a copy of Saline)."""
    folder = tmp_path_factory.mktemp("substances")
    templates = runtime_dir() / "templates"
    write_csv(folder / "Substances.csv",
              add_column(read_csv(templates / "Substances.csv"), {"Name": "Morphine2"}, copy_of="Morphine"))
    write_csv(folder / "Compounds.csv", add_column(read_csv(templates / "Compounds.csv"),
                                                   {"Compound Name": "Saline2"}, copy_of="Saline",
                                                   label="Compound Name"))
    return folder


def process(**config):
    return BioGearsProcess(config, core=CORE)


# -- configuration --------------------------------------------------------------------------

def test_patient_table_settings_go_together():
    for config, match in [({"patient_table": "P.csv"}, "go together"),
                          ({"patient": "Avery"}, "go together"),
                          ({"patient_table": "P.csv", "patient": "A", "patient_file": "StandardMale.xml"}, "set one"),
                          ({"patient_table": "P.csv", "patient": "A", "state_file": "Female@0s.xml"}, "stabilized")]:
        with pytest.raises(ValueError, match=match):
            process(**config)


def test_patients_come_from_the_table_and_are_converted_once(patient_table, cache, tmp_path):
    table = patients_from_table(patient_table)
    assert {"Avery", "Kid", "Racer", "StandardMale"} <= set(table)
    assert table["Avery"].parent.parent.parent == cache / "tables"
    mtime = table["Avery"].stat().st_mtime_ns
    assert patients_from_table(patient_table)["Avery"].stat().st_mtime_ns == mtime     # cached
    changed = tmp_path / "Patients.csv"
    write_csv(changed, add_column(read_csv(patient_table), {**AVERY, "Name": "Blake"}))
    other = patients_from_table(changed)
    assert "Blake" in other and other["Avery"] != table["Avery"]                         # a new conversion
    with pytest.raises(ValueError, match="'Nobody' is not in patient_table"):
        start_patient({"patient_table": str(patient_table), "patient": "Nobody"})


def test_a_value_biogears_cannot_convert_raises(tmp_path):
    bad = tmp_path / "Patients.csv"
    write_csv(bad, [["Name", "Typo"], ["Sex", "Male"], ["Age", "forty yr"]])
    with pytest.raises(ValueError, match="Typo Age = 'forty yr'"):
        patients_from_table(bad)


# -- BioGears' patient check ------------------------------------------------------------------

def test_a_patient_biogears_would_refuse_raises_before_anything_runs(patient_table):
    """Falsifies: without the check, the process would only fail when BioGears refuses the
    patient at its first update."""
    with pytest.raises(ValueError, match=r"(?s)refuse.*Age: 12 yr is below 18"):
        process(patient_table=str(patient_table), patient="Kid")


def test_a_patient_biogears_adjusts_warns(patient_table):
    with pytest.warns(PatientAdjustedWarning, match="HeartRateBaseline: 120 /min .* uses 109"):
        process(patient_table=str(patient_table), patient="Racer")
    with warnings.catch_warnings():
        warnings.simplefilter("error", PatientAdjustedWarning)
        process(patient_table=str(patient_table), patient="Avery")
        process(patient_file="StandardMale.xml")


# -- the engine -----------------------------------------------------------------------------------

def test_a_patient_from_the_table_stabilizes_and_runs(patient_table):
    """Oracle: BioGears itself. Avery, a new column, stabilizes near her 68 /min baseline
    and runs; the patient check is written next to her cached state."""
    proc = process(patient_table=str(patient_table), patient="Avery")
    out = proc.initial_state()
    assert abs(out["heart_rate_bpm"] - 68.0) < 5.0
    for _ in range(5):
        out = proc.update({"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0}, 1.0)
    assert abs(out["heart_rate_bpm"] - 68.0) < 5.0
    patient = start_patient({"patient_table": str(patient_table), "patient": "Avery"})
    state = stabilized_state(str(patient), runtime_dir())                 # cached by now
    report = check_report_path(state).read_text()
    assert "Patient Avery" in report and "accepts it" in report
    assert "HeartRateBaseline: 68 -> " in report


def test_substances_from_the_table_join_the_runtime(substance_table):
    files = {f.name for f in substances_from_table(substance_table)}
    assert {"Morphine2.xml", "Saline2.xml"} <= files
    rt = runtime_with_substances(runtime_dir(), substance_table)
    assert (rt / "substances" / "Morphine2.xml").is_file() and (rt / "substances" / "Morphine.xml").is_file()
    assert base_runtime(rt) == runtime_dir() and (rt / BASE_MARKER).is_file()
    assert runtime_with_substances(runtime_dir(), substance_table) == rt                  # built once
    assert base_runtime(runtime_dir()) == runtime_dir()


def test_treatment_checks_know_the_table_substances(substance_table):
    """Falsifies: the treatment schedule is checked against the runtime's substances, so
    without the table's they are refused."""
    config = {"treatment_schedule": [{"hour": 0.0, "substance": "Morphine2", "concentration_ug_per_mL": 1000.0,
                                      "rate_mL_per_min": 1.0}],
              "treatment_readouts": ["Morphine2"], "vasopressor_substance": "Norepinephrine",
              "vasopressor_concentration_ug_per_mL": 14.0}
    with pytest.raises(ValueError, match="Morphine2"):
        TREATMENT.check_config(config)
    TREATMENT.check_config({**config, "substance_table": str(substance_table)})


def test_a_table_substance_and_compound_are_infused(substance_table):
    """Oracle: BioGears itself. Morphine2 reaches the plasma, and the process infuses
    Saline2, which a runtime without the table doesn't have."""
    config = {"state_file": "StandardMale@0s.xml", "patient_file": "", "conditions": {}, "circuit_additions": {},
              "runtime_dir": "", "substance_table": str(substance_table), "patient_table": "", "patient": ""}
    runtime, path = resolve_state(config)
    import pybiogears as pb
    engine = load_engine(runtime, path, [("Substance", "PlasmaConcentration", "ug/L", "", "Morphine2")])
    engine.process_actions(pb.action("SubstanceInfusion", Substance="Morphine2", Concentration=(1.0, "mg/mL"),
                                     Rate=(1.0, "mL/min")))
    engine.advance(60.0)
    assert engine.pull()[1] > 0.0

    with pytest.raises(ValueError, match="Saline2"):
        process(iv_compound="Saline2").update({"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0}, 1.0)
    proc = process(iv_compound="Saline2", substance_table=str(substance_table))
    start = proc.initial_state()["blood_volume_mL"]
    for _ in range(30):
        out = proc.update({"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 500.0}, 1.0)
    assert out["blood_volume_mL"] > start + 100.0
