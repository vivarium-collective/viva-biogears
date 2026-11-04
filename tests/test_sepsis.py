"""The infection and nutrition modules and biogears_sepsis, on the real engine.

Oracle: a pybiogears engine driven directly with the same actions at the same times;
then the behaviours the modules promise (one-way infection, timed meals, branching)."""
import numpy as np
import pytest
from circuit_helpers import CORE, direct, direct_values, flat, make, run

from viva_biogears.circuits.sepsis import (
    INFECTION_SCENARIO_SCHEDULE,
    infection_xml,
    nutrition_xml,
)

WATER = [{"hour": 0.05, "nutrition": {"Water": 0.3}}, {"hour": 0.1, "nutrition": {"Carbohydrate": 40, "Water": 0.2}}]


def test_infection_and_meals_equal_a_direct_engine():
    """Falsifies: the infection or a meal sent at the wrong time, or readings misplaced."""
    p = make(["infection", "nutrition"], nutrition_schedule=WATER)
    p.initial_state()
    out = run(p, 600, interval=60.0, infection={"infection_severity": 3.0})[-1]
    e = direct(p)
    e.process_actions(infection_xml("Severe", "Skin", 16.0))
    for minute in range(10):
        if minute == 3:
            e.process_actions(nutrition_xml(WATER[0]["nutrition"]))
        if minute == 6:
            e.process_actions(nutrition_xml(WATER[1]["nutrition"]))
        e.advance(60.0)
    np.testing.assert_allclose(flat(p, out), direct_values(p, e), rtol=1e-12)
    assert out["infection"]["inflammation"]["local_pathogen"] > 1e3
    assert out["infection"]["inflammation"]["tumor_necrosis_factor"] > 0


def test_a_control_has_no_inflammation():
    p = make(["infection"])
    p.initial_state()
    out = run(p, 300, interval=60.0)[-1]
    assert out["infection"]["inflammation"]["local_pathogen"] == 0.0
    assert out["infection"]["inflammation"]["tissue_integrity"] == 1.0


@pytest.mark.parametrize("first, then, ok", [(0.0, 3.0, True), (3.0, 0.0, False), (2.0, 3.0, False)])
def test_an_infection_is_one_way(first, then, ok):
    """BioGears reads the severity once and can't eliminate an infection by action."""
    p = make(["infection"])
    p.initial_state()
    run(p, 60, interval=60.0, infection={"infection_severity": first})
    if ok:
        run(p, 60, interval=60.0, infection={"infection_severity": then})
    else:
        with pytest.raises(ValueError, match="only be started"):
            run(p, 60, interval=60.0, infection={"infection_severity": then})


def test_bad_severity_and_schedule_raise():
    p = make(["infection"])
    p.initial_state()
    with pytest.raises(ValueError, match="infection_severity"):
        run(p, 60, interval=60.0, infection={"infection_severity": 1.5})
    for bad, match in [([{"hour": 1}], "must be"), ([{"hour": -1, "nutrition": {"Water": 0.1}}], "hour"),
                       ([{"hour": 1, "nutrition": {"Beer": 0.5}}], "nutrients"),
                       ([{"hour": 1, "nutrition": {"Water": -0.1}}], "amounts")]:
        with pytest.raises(ValueError, match=match):
            make(["nutrition"], nutrition_schedule=bad)
    with pytest.raises(ValueError, match="mic"):
        make(["infection"], infection_mic_mg_per_L=0.0)


def test_a_branch_from_an_infected_checkpoint_continues_it(tmp_path):
    """Falsifies: the branch restarting the infection (its severity is read from the state)
    or resending meals that came before the checkpoint."""
    schedule = [{"hour": 0.05, "nutrition": {"Water": 0.3}}, {"hour": 0.15, "nutrition": {"Water": 0.3}}]
    save = {"save_state_times_s": [300.0], "save_state_dir": str(tmp_path)}
    full = make(["infection", "nutrition"], nutrition_schedule=schedule, **save)
    full.initial_state()
    a = run(full, 600, interval=60.0, infection={"infection_severity": 2.0})[-1]
    branch = make(["infection", "nutrition"], nutrition_schedule=schedule, state_file=str(tmp_path / "state@300s.xml"))
    branch.initial_state()
    assert branch._applied[("infection", 0)] == {"infection_severity": 2.0}
    assert [round(t) for t, _, _ in branch._schedule] == [540]                  # the 0.05 h drink is past
    b = run(branch, 300, interval=60.0, infection={"infection_severity": 2.0})[-1]
    np.testing.assert_allclose(flat(branch, b), flat(full, a), rtol=1e-9)


def test_the_sepsis_composite_runs_an_arm(run_composite):
    from process_bigraph.composite_generator import _REGISTRY

    from viva_biogears.composites import biogears_sepsis
    assert [eid for eid in _REGISTRY if eid.endswith(".biogears_sepsis")]
    _, rows = run_composite(biogears_sepsis, 300.0, severity="moderate")
    assert len(rows) == 6
    assert rows[-1]["circuits"]["infection"]["inflammation"]["local_pathogen"] > 0
    assert rows[-1]["interventions"]["infection"]["infection_severity"] == 2.0
    assert {"lymph", "tissue_fluid", "nutrition", "cardiovascular"} <= set(rows[-1]["circuits"])
    with pytest.raises(ValueError, match="severity"):
        biogears_sepsis(CORE, severity="awful")
    assert len(INFECTION_SCENARIO_SCHEDULE) == 47
