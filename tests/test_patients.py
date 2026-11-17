"""Any patient file (and chronic conditions): stabilized once by BioGears, then loaded from the cache.

Nothing is mocked. Each cold stabilization runs BioGears' InitializeEngine (about
40 s, 70 s with a condition), so the module shares one cache directory; the cache
is observed through the files it writes and their modification times.
"""
import re
import time

import pytest
from circuit_helpers import CORE, make, run

from viva_biogears.patients import (
    CACHE_ENV_VAR,
    CONDITIONS,
    cache_path,
    conditions_xml,
    resolve_patient_file,
    stabilized_state,
)
from viva_biogears.processes import BioGearsProcess
from viva_biogears.runtime import import_pybiogears, runtime_dir

ANEMIA = {"ChronicAnemia": {"ReductionFactor": 0.3}}


def _patient_xml(heart_rate=64.0, weight_lb=190.0):
    """StandardMale, heavier and with a lower heart-rate baseline: a patient BioGears ships no state for."""
    xml = (runtime_dir() / "patients" / "StandardMale.xml").read_text()
    xml = xml.replace("<Name>StandardMale</Name>", "<Name>VivaTestPatient</Name>")
    xml = re.sub(r'(<HeartRateBaseline [^>]*value=")[^"]+', rf"\g<1>{heart_rate}", xml)
    return re.sub(r'(<Weight [^>]*value=")[^"]+', rf"\g<1>{weight_lb}", xml)


@pytest.fixture(scope="module")
def cache(tmp_path_factory):
    directory = tmp_path_factory.mktemp("states")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(CACHE_ENV_VAR, str(directory))
        yield directory


@pytest.fixture(scope="module")
def patient(tmp_path_factory):
    path = tmp_path_factory.mktemp("patients") / "VivaTestPatient.xml"
    path.write_text(_patient_xml())
    return path


# -- no engine ------------------------------------------------------------------------

def test_conditions_xml_and_its_checks():
    xml = conditions_xml({"ChronicAnemia": {"ReductionFactor": 0.3}, "Starvation": {"TimeSinceMeal": "72 hr"}})
    assert '<Condition xsi:type="ChronicAnemiaData"><ReductionFactor value="0.3"/></Condition>' in xml
    assert '<TimeSinceMeal value="72.0" unit="hr"/>' in xml
    for bad, match in [({"Anemia": {"ReductionFactor": 0.3}}, "unknown condition"),
                       ({"ChronicAnemia": {}}, "needs its fields"),
                       ({"ChronicAnemia": {"ReductionFactor": "lots"}}, "number"),
                       ({"ChronicAnemia": {"ReductionFactor": float("nan")}}, "finite"),
                       ({"ChronicAnemia": {"Reduction Factor": 0.3}}, "bad field")]:
        with pytest.raises(ValueError, match=match):
            conditions_xml(bad)
    assert len(CONDITIONS) == 10


def test_patient_files_resolve_by_name_or_path(patient):
    rt = runtime_dir()
    assert resolve_patient_file("StandardMale.xml", rt) == rt / "patients" / "StandardMale.xml"
    assert resolve_patient_file(str(patient), rt) == patient
    with pytest.raises(FileNotFoundError, match="Nobody.xml"):
        resolve_patient_file("Nobody.xml", rt)


def test_cache_key_covers_the_patient_bytes_and_the_conditions(cache, patient, tmp_path):
    rt = runtime_dir()
    same = tmp_path / patient.name
    same.write_text(patient.read_text())
    other = tmp_path / "Other.xml"
    other.write_text(_patient_xml(heart_rate=65.0))
    base = cache_path(str(patient), rt)
    assert cache_path(str(same), rt) == base                       # same bytes, other place
    assert cache_path(str(other), rt) != base                      # one baseline changed
    assert cache_path(str(patient), rt, ANEMIA) != base
    assert cache_path(str(patient), rt, {"ChronicAnemia": {"ReductionFactor": 0.31}}) != \
        cache_path(str(patient), rt, ANEMIA)
    assert base.parent == cache


def test_state_file_and_patient_file_are_exclusive():
    with pytest.raises(ValueError, match="one or the other"):
        BioGearsProcess({"state_file": "Male_25_Normal@0s.xml", "patient_file": "StandardMale.xml"}, core=CORE)
    with pytest.raises(ValueError, match="one or the other"):
        make(["vitals"], state_file="Male_25_Normal@0s.xml", conditions=ANEMIA)
    with pytest.raises(ValueError, match="unknown condition"):
        make(["vitals"], conditions={"Flu": {"Severity": 1.0}})


# -- real stabilization -----------------------------------------------------------------

def test_new_patient_is_stabilized_once_then_loaded(cache, patient):
    rt = runtime_dir()
    target = cache_path(str(patient), rt)
    assert not target.exists()
    t = time.perf_counter()
    path = stabilized_state(str(patient), rt)
    cold = time.perf_counter() - t
    assert path == target and path.is_file()
    assert not [p for p in cache.iterdir() if p.name.startswith(".")]   # no temporaries left
    mtime = path.stat().st_mtime_ns
    t = time.perf_counter()
    assert stabilized_state(str(patient), rt) == path
    warm = time.perf_counter() - t
    assert path.stat().st_mtime_ns == mtime and warm < cold / 10

    p = BioGearsProcess({"patient_file": str(patient)}, core=CORE)
    vitals = p.initial_state()
    assert vitals["heart_rate_bpm"] == pytest.approx(64.0, abs=1.0)      # the patient's own baseline
    standard = BioGearsProcess({}, core=CORE).initial_state()
    assert vitals["blood_volume_mL"] > standard["blood_volume_mL"] + 100  # 190 lb vs 170 lb


def test_condition_is_applied_while_stabilizing(cache):
    """Falsifies: conditions not reaching BioGears. Chronic anemia 30 % removes 30 % of the
    hemoglobin (BioGears 8.2.0 leaves hematocrit unchanged; probe stabilization-2026-11-03)."""
    anemic, normal = make(["vitals"], conditions=ANEMIA), make(["vitals"])
    a, n = anemic.initial_state(), normal.initial_state()
    pb = import_pybiogears()

    def hemoglobin(path):
        e = pb.BioGearsEngine(runtime_dir())
        e.set_requests([pb.DataRequest("Physiology", "HemoglobinContent", "g")])
        e.load_state(path)
        return float(e.pull()[1])

    rt = runtime_dir()
    ratio = hemoglobin(cache_path("StandardMale.xml", rt, ANEMIA)) / hemoglobin(rt / "states" / "StandardMale@0s.xml")
    assert ratio == pytest.approx(0.7, abs=0.005)
    assert a["vitals"]["mean_arterial_pressure_mmHg"] < n["vitals"]["mean_arterial_pressure_mmHg"] - 3
    assert len(list(cache.glob("StandardMale-ChronicAnemia-*@0s.xml"))) == 1
    out = run(anemic, 5)[-1]
    assert out["vitals"]["heart_rate_bpm"] > 0


def test_composites_take_a_patient(cache, patient, run_composite):
    from viva_biogears.composites import (
        biogears_hemorrhage,
        biogears_lymph,
        biogears_thermal,
    )
    _, rows = run_composite(biogears_hemorrhage, 2.0, patient_file=str(patient))
    assert rows[0]["heart_rate_bpm"] == pytest.approx(64.0, abs=1.0)
    _, rows = run_composite(biogears_thermal, 2.0, patient_file=str(patient))
    assert rows[0]["readings"]["thermal"]["energy"]["core_temperature_C"] > 35
    _, rows = run_composite(biogears_lymph, 2.0, conditions=ANEMIA)       # replaces the equilibrated default
    assert rows[0]["readings"]["vitals"]["mean_arterial_pressure_mmHg"] < 92
