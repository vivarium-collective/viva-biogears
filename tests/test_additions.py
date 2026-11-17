"""Circuit additions: a resistance path plus its compartment link, added to the state before it loads.

Oracles: the added path obeys Ohm's law on BioGears' own node pressures, substances follow
it (arterial PO2 stays put; a path without its link corrupts it, probe additions-2026-11-03),
and the body responds as to an arteriovenous shunt (MAP down, HR and cardiac output up)."""
import pytest
from circuit_helpers import CORE, make, run

from viva_biogears.modules.additions import added_state, check_additions
from viva_biogears.modules.state import read_state
from viva_biogears.patients import CACHE_ENV_VAR
from viva_biogears.processes import BioGearsProcess
from viva_biogears.runtime import runtime_dir

SHUNT = {"Shunt": {"source": "Aorta1", "target": "VenaCava", "resistance_mmHg_s_per_mL": 2.0}}
O2 = [{"substance": "Oxygen", "compartment": "Aorta", "property": "PartialPressure", "unit": "mmHg"}]


@pytest.fixture(autouse=True, scope="module")
def cache(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(CACHE_ENV_VAR, str(tmp_path_factory.mktemp("cache") / "states"))
        yield


@pytest.fixture(scope="module")
def shunted():
    p = make(["cardiovascular", "cardiovascular_points", "substances"], circuit_additions=SHUNT,
             substance_outputs=O2, cardiovascular_point_paths=["VivaAddedShunt"],
             cardiovascular_point_nodes=["Aorta1", "VenaCava"])
    control = make(["cardiovascular", "substances"], substance_outputs=O2)
    return p.initial_state(), run(p, 60)[-1], control.initial_state(), run(control, 60)[-1]


def test_the_state_holds_the_path_and_its_link():
    path = added_state(runtime_dir() / "states" / "StandardMale@0s.xml", SHUNT)
    state = read_state(path)
    assert state.path_ends["VivaAddedShunt"] == ("Aorta1", "VenaCava")
    assert "VivaAddedShunt" in state.circuits["FullCardiovascular"][1]
    assert added_state(runtime_dir() / "states" / "StandardMale@0s.xml", SHUNT) == path   # reused
    assert b"<Name>VivaAddedShunt</Name>" in path.read_bytes().split(b"<LiquidLink>", 1)[1]


def test_the_shunt_obeys_ohms_law_and_acts_as_a_shunt(shunted):
    init, out, control_init, control = shunted
    pts = out["cardiovascular_points"]
    drop = pts["nodes"]["Aorta1"]["pressure_mmHg"] - pts["nodes"]["VenaCava"]["pressure_mmHg"]
    flow = pts["paths"]["VivaAddedShunt"]["flow_mL_per_min"]
    assert flow == pytest.approx(drop / 2.0 * 60.0, rel=1e-9)
    assert flow > 1000
    h, c = out["cardiovascular"]["hemodynamics"], control["cardiovascular"]["hemodynamics"]
    assert h["mean_arterial_pressure_mmHg"] < c["mean_arterial_pressure_mmHg"] - 5
    assert h["heart_rate_bpm"] > c["heart_rate_bpm"] + 5
    assert h["cardiac_output_L_per_min"] > c["cardiac_output_L_per_min"] + 0.5


def test_substances_follow_the_shunt(shunted):
    """Falsifies: the link missing (blood moves without its substances; PaO2 drifts and a
    2 mmHg s/mL shunt is irreversible within 3 s)."""
    init, out, _, control = shunted
    pao2 = lambda s: s["substances"]["Oxygen"]["Aorta"]["partial_pressure_mmHg"]  # noqa: E731
    assert pao2(out) == pytest.approx(pao2(control), abs=5)
    assert not out.get("irreversible_state", False)


def test_biogears_process_and_composites_take_additions(run_composite):
    p = BioGearsProcess({"circuit_additions": SHUNT}, core=CORE)
    p.initial_state()
    for _ in range(30):
        out = p.update({"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0}, 1.0)
    assert out["mean_arterial_pressure_mmHg"] < 90
    from viva_biogears.composites import biogears_cardiovascular
    _, rows = run_composite(biogears_cardiovascular, 2.0, circuit_additions=SHUNT, point_reads=True)
    assert rows[-1]["readings"]["cardiovascular_points"]["paths"]["VivaAddedShunt"]["flow_mL_per_min"] > 1000


@pytest.mark.parametrize("additions, message", [
    ({"S": {"source": "Aorta1", "target": "VenaCava"}}, "exactly the fields"),
    ({"S": {**SHUNT["Shunt"], "resistance_mmHg_s_per_mL": 0.0}}, "> 0"),
    ({"S": {**SHUNT["Shunt"], "target": "Aorta1"}}, "to itself"),
    ({"S-1": SHUNT["Shunt"]}, "letters"),
])
def test_bad_fields_raise(additions, message):
    with pytest.raises(ValueError, match=message):
        check_additions(additions)
    with pytest.raises(ValueError, match=message):
        make(["vitals"], circuit_additions=additions)


@pytest.mark.parametrize("source, target, message", [
    ("Aorta9", "VenaCava", "not nodes"),
    ("Aorta1", "MuscleE1", "not in a vascular compartment"),
    ("Aorta1", "Lymph", "not in a vascular compartment"),
    ("Aorta1", "Aorta2", "both nodes are in compartment"),
])
def test_unsupported_paths_raise_at_construction(source, target, message):
    additions = {"S": {"source": source, "target": target, "resistance_mmHg_s_per_mL": 5.0}}
    with pytest.raises(ValueError, match=message):
        BioGearsProcess({"circuit_additions": additions}, core=CORE)
