"""Saved states: saving during a run, the command line, and branching from a checkpoint.

The oracle for branching is the uninterrupted run: a branch with the checkpoint's own
setpoints must continue it (pybiogears reloads to about 1e-11; probe save-states-2026-11-03),
and a branch that changes a setpoint must change the run."""
import math
import re

import pytest
from circuit_helpers import CORE, make, run

from viva_biogears.circuits.cardiovascular import hemorrhage_xml
from viva_biogears.processes import VITALS, BioGearsProcess
from viva_biogears.processes._bridge import load_engine
from viva_biogears.runtime import runtime_dir
from viva_biogears.states import main, save_states


def _engine():
    rt = runtime_dir()
    return load_engine(rt, rt / "states" / "StandardMale@0s.xml", [])


def _time(path):
    return float(re.search(rb'<SimulationTime[^>]*value="([^"]+)"', path.read_bytes()).group(1))


def _run(generator, seconds, save=None, **params):
    from process_bigraph import Composite, gather_emitter_results
    document = generator(CORE, **params)
    if save:
        document["biogears"]["config"].update(save)
    sim = Composite({"state": document}, core=CORE)
    sim.run(seconds)
    return gather_emitter_results(sim)[("emitter",)]


# -- save_states and the command line -----------------------------------------------

def test_states_are_saved_at_each_time_and_named_by_it(tmp_path):
    e = _engine()
    paths = save_states(e, tmp_path, [0, 1, 2.5], "run")
    assert [p.name for p in paths] == ["run@0s.xml", "run@1s.xml", "run@2.5s.xml"]
    assert [_time(p) for p in paths] == pytest.approx([0, 1, 2.5], abs=1e-9)


def test_a_time_between_steps_saves_at_the_next_step(tmp_path):
    assert save_states(_engine(), tmp_path, [0.01], "run")[0].name == "run@0.02s.xml"


@pytest.mark.parametrize("times, message", [
    ([], "empty"), ([2, 1], "strictly increasing"), ([1, float("nan")], "finite"), (5, "sequence")])
def test_bad_times_raise(tmp_path, times, message):
    with pytest.raises(ValueError, match=message):
        save_states(_engine(), tmp_path, times, "run")


@pytest.mark.parametrize("name", ["", "a/b", "a@b"])
def test_bad_names_raise(tmp_path, name):
    with pytest.raises(ValueError, match="name must be"):
        save_states(_engine(), tmp_path, [0], name)


def test_two_times_in_one_step_and_overwrites_raise(tmp_path):
    with pytest.raises(ValueError, match="both fall"):
        save_states(_engine(), tmp_path, [0.001, 0.002], "run")
    (tmp_path / "x@0s.xml").write_text("")
    with pytest.raises(FileExistsError, match="never overwrites"):
        save_states(_engine(), tmp_path, [0], "x")


def test_a_time_before_the_engine_raises(tmp_path):
    e = _engine()
    e.advance(1.0)
    with pytest.raises(ValueError, match="before the engine"):
        save_states(e, tmp_path, [0.5], "run")


def test_the_command_line_saves_a_sequence(tmp_path):
    paths = main(["StandardMale@0s.xml", "--times", "1", "2", "--out", str(tmp_path)])
    assert [p.name for p in paths] == ["StandardMale@1s.xml", "StandardMale@2s.xml"]
    # A saved state loads as a process's start, at its own time.
    assert BioGearsProcess({"state_file": str(paths[1])}, core=CORE).initial_state()["heart_rate_bpm"] > 0


# -- saving from a process ------------------------------------------------------------------

@pytest.mark.parametrize("generator, params", [
    ("biogears_hemorrhage", {"rate_mL_per_min": 200.0}),
    ("biogears_cardiovascular", {"hemorrhage_rate_mL_per_min": 200.0}),
], ids=["BioGearsProcess", "BioGearsCircuitProcess"])
def test_a_process_saves_at_update_boundaries_without_changing_the_run(tmp_path, generator, params):
    """Falsifies: saving off update boundaries (stepping the engine mid-update), saving a
    time twice or not at all, or saving changing what the composite emits."""
    import viva_biogears.composites as composites
    gen = getattr(composites, generator)
    save = {"save_state_times_s": [0, 2.5, 5], "save_state_dir": str(tmp_path), "save_state_name": "run"}
    saved = _run(gen, 6, save, **params)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["run@0s.xml", "run@3s.xml", "run@5s.xml"]
    plain = _run(gen, 6, **params)
    assert repr(saved[-1]) == repr(plain[-1])


@pytest.mark.parametrize("config, message", [
    ({"save_state_times_s": [1.0]}, "save_state_dir must be set"),
    ({"save_state_times_s": [2.0, 1.0], "save_state_dir": "x"}, "strictly increasing"),
    ({"save_state_times_s": [1.0], "save_state_dir": "x", "save_state_name": "a@b"}, "name must be"),
])
def test_bad_process_save_config_raises(config, message):
    with pytest.raises(ValueError, match=message):
        BioGearsProcess(config, core=CORE)
    with pytest.raises(ValueError, match=message):
        make(["vitals"], **config)


def test_existing_states_raise_when_the_process_is_built(tmp_path):
    (tmp_path / "run@600s.xml").write_text("")
    with pytest.raises(FileExistsError, match="already holds states named 'run'"):
        BioGearsProcess({"save_state_times_s": [600.0], "save_state_dir": str(tmp_path),
                         "save_state_name": "run"}, core=CORE)


# -- branching ---------------------------------------------------------------------------------

def _bleed_checkpoint(tmp_path, rate=250.0):
    from viva_biogears.composites import biogears_hemorrhage
    full = _run(biogears_hemorrhage, 30, {"save_state_times_s": [10], "save_state_dir": str(tmp_path)},
                rate_mL_per_min=rate)
    return tmp_path / "state@10s.xml", full


def test_a_branch_with_the_checkpoint_setpoints_continues_it(tmp_path):
    """Falsifies: the branch resending the hemorrhage (BioGears restarts the bleed) or the
    blood-lost counter restarting at 0 (BioGears doesn't save it; pybiogears restores it)."""
    from viva_biogears.composites import biogears_hemorrhage
    checkpoint, full = _bleed_checkpoint(tmp_path)
    branch = _run(biogears_hemorrhage, 20, state_file=str(checkpoint), rate_mL_per_min=250.0)
    for name in VITALS:
        assert branch[-1][name] == pytest.approx(full[-1][name], rel=1e-8), name


def test_a_branch_can_stop_or_change_a_checkpoint_bleed(tmp_path):
    from viva_biogears.composites import biogears_hemorrhage
    checkpoint, full = _bleed_checkpoint(tmp_path)
    stopped = _run(biogears_hemorrhage, 20, state_file=str(checkpoint), rate_mL_per_min=0.0)
    faster = _run(biogears_hemorrhage, 20, state_file=str(checkpoint), rate_mL_per_min=500.0)
    lost = lambda rows: rows[-1]["total_blood_volume_lost_mL"] - rows[0]["total_blood_volume_lost_mL"]  # noqa: E731
    assert lost(stopped) < 0.5
    assert lost(faster) > lost(full[10:]) + 10


def test_a_bleed_in_another_compartment_raises(tmp_path):
    checkpoint, _ = _bleed_checkpoint(tmp_path)
    with pytest.raises(ValueError, match="RightLeg"):
        BioGearsProcess({"state_file": str(checkpoint), "hemorrhage_compartment": "Aorta"}, core=CORE).initial_state()
    with pytest.raises(ValueError, match="RightLeg"):
        make(["cardiovascular"], state_file=str(checkpoint), hemorrhage_compartment="Aorta").initial_state()


def _ventilated_checkpoint(tmp_path):
    from viva_biogears.composites import biogears_mechanical_ventilation
    _run(biogears_mechanical_ventilation, 10, {"save_state_times_s": [10], "save_state_dir": str(tmp_path)},
         ventilator_pressure_cmH2O=15.0, oxygen_fraction=0.4)
    return tmp_path / "state@10s.xml"


def test_a_ventilated_checkpoint_loads_and_continues(tmp_path):
    """Falsifies: the saved anesthesia machine not reloading (BioGears writes empty chamber
    states its schema rejects; pybiogears drops them), or the branch resending the same
    ventilator settings."""
    checkpoint = _ventilated_checkpoint(tmp_path)
    p = make(["respiratory", "mechanical_ventilator"], state_file=str(checkpoint))
    p.initial_state()
    on = {"connected": 1.0, "ventilator_pressure_cmH2O": 15.0, "oxygen_fraction": 0.4}
    assert p._applied[("mechanical_ventilator", 0)] == pytest.approx({**p._applied[("mechanical_ventilator", 0)], **on})
    assert p._applied[("respiratory", 0)] == {"intubated": 1.0}
    out = run(p, 10, respiratory={"intubated": 1.0},
              mechanical_ventilator={**p._applied[("mechanical_ventilator", 0)]})[-1]
    assert out["mechanical_ventilator"]["settings"]["ventilator_pressure_cmH2O"] == 15.0


def test_a_branch_can_disconnect_and_extubate_a_checkpoint(tmp_path):
    """Falsifies: baselines sending nothing (the process assuming nothing active at load),
    so the ventilator keeps running behind a store that says disconnected."""
    checkpoint = _ventilated_checkpoint(tmp_path)
    modules = ["respiratory", "mechanical_ventilator", "supplemental_oxygen"]
    kept, freed = make(modules, state_file=str(checkpoint)), make(modules, state_file=str(checkpoint))
    kept.initial_state(), freed.initial_state()
    on = dict(kept._applied[("mechanical_ventilator", 0)])
    k = run(kept, 120, respiratory={"intubated": 1.0}, mechanical_ventilator=on)[-1]
    run(freed, 1)                                                    # baselines: disconnect, extubate
    f = run(freed, 119)[-1]
    pao2 = "arterial_oxygen_pressure_mmHg"
    assert f["supplemental_oxygen"]["oxygenation"][pao2] < k["supplemental_oxygen"]["oxygenation"][pao2] - 30
    # The ventilator was disconnected first, so the cannula may connect now.
    run(freed, 5, supplemental_oxygen={"oxygen_connected": 1.0})


def test_a_ventilated_checkpoint_refuses_a_device_it_cant_control(tmp_path):
    checkpoint = _ventilated_checkpoint(tmp_path)
    with pytest.raises(ValueError, match="doesn't control"):
        make(["supplemental_oxygen"], state_file=str(checkpoint)).initial_state()


def test_thermal_and_environment_checkpoint_continue(tmp_path):
    """A saved thermal application reloads (pybiogears drops the NaN parts BioGears recreates)
    and the changed environment is read back as the group's starting values."""
    from viva_biogears.composites import biogears_thermal
    params = dict(active_heating_W=300.0, ambient_temperature_C=10.0)
    full = _run(biogears_thermal, 20, {"save_state_times_s": [10], "save_state_dir": str(tmp_path)}, **params)
    branch = _run(biogears_thermal, 10, state_file=str(tmp_path / "state@10s.xml"), **params)
    a, b = full[-1]["circuits"]["thermal"], branch[-1]["circuits"]["thermal"]
    for k in ("core_temperature_C", "skin_temperature_C"):
        assert b["energy"][k] == pytest.approx(a["energy"][k], rel=1e-9), k
    assert b["environment"]["ambient_temperature_C"] == 10.0


def test_an_engine_checkpoint_keeps_blood_lost(tmp_path):
    e = _engine()
    e.process_actions(hemorrhage_xml("RightLeg", 200.0))
    e.advance(5.0)
    path = save_states(e, tmp_path, [5], "bleed")[0]
    rt = runtime_dir()
    import pybiogears as pb
    f = pb.BioGearsEngine(rt)
    f.set_requests([pb.DataRequest("Physiology", "TotalBloodVolumeLost", "mL")])
    f.load_state(path)
    lost = float(f.pull()[1])
    assert lost > 5 and not math.isnan(lost)


def test_a_saver_counts_a_time_reached_when_the_clock_runs_microseconds_behind(tmp_path):
    """BioGears' clock read 43199.999999 s at "12 h" in a 48 h run, and a saver comparing at
    1 µs saved a whole update (60 s) late. Falsifies the strict comparison."""
    from viva_biogears.states import StateSaver

    class Clock:
        sim_time_s = 43199.999999

        def save_state(self, path):
            path.write_text("<state/>")

    saver = StateSaver([43200.0], tmp_path, "ckpt")
    saver(Clock())
    assert [p.name for p in saver.saved] == ["ckpt@43199.999999s.xml"] and saver.pending == []
