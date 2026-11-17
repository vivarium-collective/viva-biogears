"""The treatment module (timed infusions, the vasopressor setpoint) and the
TreatmentController in biogears_sepsis, on the real engine.

Oracle: a pybiogears engine driven directly with the same actions at the same times;
then the guards the module promises (one infusion per compound or substance).

The two oracle comparisons run in a fresh Python process (``isolated``), with the oracle
engine created before the process runs. Once drugs are infused, engines in one Python
process can differ by ~5e-6 depending on what earlier engines in that process did: an
engine created while another had already advanced differed (piperacillin,
norepinephrine), and the full test suite reproduced it where these tests alone did not.
In the same process the comparison would test that BioGears effect, not the module."""
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pytest
from circuit_helpers import direct, direct_values, flat, make, run

from viva_biogears.circuits.treatment import (
    compound_infusion_xml,
    substance_infusion_xml,
)

PIP = {"hour": 1 / 60, "compound": "PiperacillinTazobactam", "bag_volume_mL": 20.0, "rate_mL_per_min": 0.667}
BOLUS = {"hour": 2 / 60, "compound": "Saline", "bag_volume_mL": 100.0, "rate_mL_per_min": 50.0}
NOR = {"hour": 3 / 60, "substance": "Norepinephrine", "concentration_ug_per_mL": 14.0, "rate_mL_per_min": 1.0}


def isolated(fn):
    """Run ``fn`` (a module-level function) in a fresh Python process and return its result."""
    with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")) as pool:
        return pool.submit(fn).result()


def _scheduled_infusions():
    p = make(["treatment", "cardiovascular"], treatment_schedule=[PIP, BOLUS, NOR],
             treatment_readouts=["Piperacillin", "Norepinephrine"])
    p.initial_state()
    e = direct(p)
    out = run(p, 300, interval=60.0)[-1]
    for minute in range(5):
        if minute == 1:
            e.process_actions(compound_infusion_xml("PiperacillinTazobactam", 20.0, 0.667))
        if minute == 2:
            e.process_actions(compound_infusion_xml("Saline", 100.0, 50.0))
        if minute == 3:
            e.process_actions(substance_infusion_xml("Norepinephrine", 14.0, 1.0))
        e.advance(60.0)
    return flat(p, out), direct_values(p, e), out["treatment"]


def _vasopressor_setpoint():
    p = make(["treatment"], treatment_readouts=["Norepinephrine"])
    p.initial_state()
    e = direct(p)
    out = run(p, 120, interval=60.0, treatment={"vasopressor_rate_ug_per_min": 14.0})[-1]
    e.process_actions(substance_infusion_xml("Norepinephrine", 14.0, 1.0))  # 14 ug/min at 14 ug/mL
    e.advance(120.0)
    return flat(p, out), direct_values(p, e)


def test_scheduled_infusions_equal_a_direct_engine():
    """Falsifies: an infusion sent at the wrong time or with the wrong amounts, readings misplaced."""
    process, oracle, treatment = isolated(_scheduled_infusions)
    np.testing.assert_allclose(process, oracle, rtol=1e-12)
    assert treatment["Piperacillin"]["plasma_concentration_ug_per_mL"] > 10
    assert treatment["Norepinephrine"]["blood_concentration_ug_per_mL"] > 0


def test_vasopressor_setpoint_equals_a_direct_engine():
    process, oracle = isolated(_vasopressor_setpoint)
    np.testing.assert_allclose(process, oracle, rtol=1e-12)


def test_a_branch_from_mid_infusion_continues_it(tmp_path):
    """Falsifies: the cardiovascular setpoint claiming (and stopping) a scheduled bolus on
    load, or the vasopressor setpoint resending its infusion."""
    sched = [{**BOLUS, "hour": 0.0, "bag_volume_mL": 300.0}]
    save = {"save_state_times_s": [120.0], "save_state_dir": str(tmp_path)}
    full = make(["treatment", "cardiovascular"], treatment_schedule=sched, **save)
    full.initial_state()
    a = run(full, 240, interval=60.0, treatment={"vasopressor_rate_ug_per_min": 10.0})[-1]
    branch = make(["treatment", "cardiovascular"], treatment_schedule=sched, state_file=str(tmp_path / "state@120s.xml"))
    branch.initial_state()
    assert branch._applied[("treatment", 0)] == pytest.approx({"vasopressor_rate_ug_per_min": 10.0})
    assert branch._applied[("cardiovascular", 1)] == {"iv_rate_mL_per_min": 0.0}
    b = run(branch, 120, interval=60.0, treatment={"vasopressor_rate_ug_per_min": 10.0})[-1]
    np.testing.assert_allclose(flat(branch, b), flat(full, a), rtol=1e-9)


@pytest.mark.parametrize("kw, match", [
    ({"treatment_schedule": [{"hour": 1, "compound": "Beer", "bag_volume_mL": 1, "rate_mL_per_min": 1}]}, "not a BioGears compound"),
    ({"treatment_schedule": [{"hour": 1, "substance": "Unobtainium", "concentration_ug_per_mL": 1, "rate_mL_per_min": 1}]}, "not a BioGears substance"),
    ({"treatment_schedule": [{"hour": 1, "compound": "Saline"}]}, "must have the keys"),
    ({"treatment_schedule": [{"hour": -1, "compound": "Saline", "bag_volume_mL": 1, "rate_mL_per_min": 1}]}, "hour"),
    ({"treatment_schedule": [{"hour": 1, "compound": "Saline", "bag_volume_mL": 0, "rate_mL_per_min": 1}]}, "bag_volume_mL"),
    ({"treatment_readouts": ["Caffeine"]}, "not a BioGears substance"),      # its <Name> is "Caffine"
    ({"vasopressor_substance": "Nope"}, "vasopressor_substance"),
])
def test_bad_treatment_config_raises(kw, match):
    with pytest.raises(ValueError, match=match):
        make(["treatment"], **kw)


def test_one_infusion_per_compound_or_substance():
    """BioGears keeps one infusion per compound and per substance, so a setpoint can't drive
    what the schedule also infuses."""
    p = make(["treatment", "cardiovascular"], treatment_schedule=[BOLUS, NOR])
    p.initial_state()
    with pytest.raises(ValueError, match="iv_rate_mL_per_min must stay 0"):
        run(p, 60, interval=60.0, cardiovascular={"iv_rate_mL_per_min": 5.0})
    with pytest.raises(ValueError, match="vasopressor_rate_ug_per_min must stay 0"):
        run(p, 60, interval=60.0, treatment={"vasopressor_rate_ug_per_min": 5.0})


def test_the_treatment_controller_gives_the_challenge(run_composite):
    """biogears_sepsis with a protocol: the controller writes the saline setpoint, so the
    first 500 mL challenge bolus (at 50 mL/min) is given in 10 min."""
    from viva_biogears.composites import biogears_sepsis
    _, rows = run_composite(biogears_sepsis, 720.0, severity="severe", treatment="fluid_challenge",
                            challenge_h=0.0)
    iv = [r["interventions"]["cardiovascular"]["iv_rate_mL_per_min"] for r in rows]
    # The setpoint holds 50 mL/min for ten 1-min updates (rows are emitted after the
    # controller has written the setpoint for the next update), then 0.
    assert iv.count(50.0) == 10 and iv[iv.index(50.0):iv.index(50.0) + 10] == [50.0] * 10 and iv[-1] == 0.0
    assert rows[-1]["protocol"]["saline_given_mL"] == pytest.approx(500)
    assert rows[-1]["protocol"]["code"] == 1.0
    lost = rows[0]["circuits"]["infection"]["clinical"]["blood_volume_mL"]
    assert rows[-1]["circuits"]["infection"]["clinical"]["blood_volume_mL"] > lost + 200


def test_every_sepsis_run_records_its_protocol():
    """Untreated runs carry protocol code 0 and no saline, so a study's figures and tests
    can tell the arms apart (the workbench gives a Visualization no run names)."""
    from viva_biogears.composites import biogears_sepsis
    untreated = biogears_sepsis(None, severity="severe")
    assert untreated["protocol"] == {"code": 0.0, "saline_given_mL": 0.0, "branch_h": 0.0,
                                     "treatment_start_h": 46.0} and "controller" not in untreated
    assert untreated["emitter"]["inputs"]["protocol"] == ["protocol"]
    treated = biogears_sepsis(None, severity="severe", treatment="refresh_experimental")
    assert treated["protocol"]["code"] == 4.0 and "controller" in treated


def test_drug_readouts_default_to_treated_runs_and_can_be_set():
    """Reading a drug activates it in BioGears, so an untreated run reads none by default;
    a study's untreated arm can ask for the treated arms' stores; bad names fail at build."""
    from viva_biogears.composites import biogears_sepsis
    readouts = lambda **kw: biogears_sepsis(None, **kw)["biogears"]["config"]["treatment_readouts"]
    assert readouts() == []
    assert readouts(treatment="antibiotic") == ["Piperacillin", "Norepinephrine"]
    assert readouts(drug_readouts=["Piperacillin"]) == ["Piperacillin"]
    with pytest.raises(ValueError, match="not a BioGears substance"):
        biogears_sepsis(None, drug_readouts=["Caffeine"])


def test_a_protocol_from_a_saved_state_keeps_engine_time(run_composite):
    """McDaniel et al. started every treatment from a saved septic state. From a state saved
    at 5 h (StandardMale@equilibrated), a challenge at 5 h starts on the first update;
    on the composite's own clock (0) it would wait 5 h. Falsifies a missing time offset."""
    from viva_biogears.composites import biogears_sepsis
    _, rows = run_composite(biogears_sepsis, 720.0, severity="severe", treatment="fluid_challenge",
                            state_file="StandardMale@equilibrated.xml", challenge_h=5.0)
    iv = [r["interventions"]["cardiovascular"]["iv_rate_mL_per_min"] for r in rows]
    assert iv[:10] == [50.0] * 10 and iv[-1] == 0.0
    assert rows[-1]["protocol"]["saline_given_mL"] == pytest.approx(500)
    assert rows[-1]["protocol"]["branch_h"] == pytest.approx(5.0)
    assert rows[-1]["protocol"]["treatment_start_h"] == 5.0


def test_a_state_saved_after_the_challenge_raises():
    """A protocol whose challenge is before the starting state would start late, silently."""
    from viva_biogears.composites import biogears_sepsis
    with pytest.raises(ValueError, match="after the protocol's challenge"):
        biogears_sepsis(None, treatment="fluid_challenge", state_file="StandardMale@equilibrated.xml",
                        challenge_h=1.0)


def test_the_shipped_septic_state_starts_the_challenge_on_its_first_update(run_composite):
    """The workbench treatment arms start from StandardMale@severe-infection-44h.xml (the
    severe arm at 44 h, 158399.999994 s on BioGears' clock): the 44 h challenge starts at
    once and the run carries the infection on."""
    from viva_biogears.composites import biogears_sepsis
    _, rows = run_composite(biogears_sepsis, 720.0, severity="severe", treatment="fluid_challenge",
                            state_file="StandardMale@severe-infection-44h.xml")
    iv = [r["interventions"]["cardiovascular"]["iv_rate_mL_per_min"] for r in rows]
    assert iv[:10] == [50.0] * 10 and iv[-1] == 0.0
    assert rows[-1]["protocol"]["branch_h"] == pytest.approx(44.0, abs=1e-6)
    clinical = rows[0]["circuits"]["infection"]["clinical"]
    assert clinical["lactate_mmol_per_L"] > 2.0 and clinical["systolic_pressure_mmHg"] < 100.0
