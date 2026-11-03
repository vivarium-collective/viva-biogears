"""Circuit modules with setpoints and state-dependent outputs, on the real engine:
respiratory, mechanical ventilator, supplemental oxygen, thermal, points, substances, tissues."""
import math

import numpy as np
import pytest
from circuit_helpers import direct, direct_values, flat, make, run

from viva_biogears.circuits.cardiovascular import hemorrhage_xml
from viva_biogears.circuits.respiratory import VENTILATOR_BASELINE
from viva_biogears.circuits.state import read_state
from viva_biogears.circuits.thermal import (
    ENVIRONMENT_BASELINE,
    THERMAL_APPLICATION_BASELINE,
)
from viva_biogears.runtime import runtime_dir

VENT_ON = {**VENTILATOR_BASELINE, "connected": 1.0, "ventilator_pressure_cmH2O": 15.0, "peep_cmH2O": 5.0,
           "respiration_rate_bpm": 16.0, "oxygen_fraction": 0.5}


# -- airway devices and intubation ------------------------------------------------

def test_ventilator_settings_apply_and_oxygenate():
    """The settings read back are the ones sent, and FiO2 0.5 on a tube raises PaO2."""
    p = make(["respiratory", "mechanical_ventilator", "supplemental_oxygen"])
    init = p.initial_state()
    out = run(p, 120, respiratory={"intubated": 1.0}, mechanical_ventilator=VENT_ON)[-1]
    s = out["mechanical_ventilator"]["settings"]
    for port in ("ventilator_pressure_cmH2O", "peep_cmH2O", "respiration_rate_bpm", "oxygen_fraction",
                 "inspiratory_expiratory_ratio", "inlet_flow_L_per_min"):
        assert s[port] == pytest.approx(VENT_ON[port]), port
    assert out["supplemental_oxygen"]["oxygenation"]["arterial_oxygen_pressure_mmHg"] > \
        init["supplemental_oxygen"]["oxygenation"]["arterial_oxygen_pressure_mmHg"] + 50
    # Disconnecting and extubating (which BioGears allows) returns to room air.
    off = run(p, 180, respiratory={"intubated": 0.0})[-1]
    assert off["supplemental_oxygen"]["oxygenation"]["arterial_oxygen_pressure_mmHg"] < \
        out["supplemental_oxygen"]["oxygenation"]["arterial_oxygen_pressure_mmHg"] - 40


def test_two_airway_devices_are_refused_before_any_action():
    p = make(["mechanical_ventilator", "supplemental_oxygen"])
    p.initial_state()
    with pytest.raises(ValueError, match="one airway device"):
        run(p, 1, mechanical_ventilator={"connected": 1.0}, supplemental_oxygen={"oxygen_connected": 1.0})
    assert list(p._applied.values()) == [dict(VENTILATOR_BASELINE),
                                         {"oxygen_connected": 0.0, "oxygen_flow_L_per_min": 4.0}]


def test_device_swap_needs_one_update_between():
    """Falsifies: the swap rule. BioGears processes the new device before the old one's
    removal and fails every step ("Can only change airway mode ... from the Free mode")."""
    p = make(["mechanical_ventilator", "supplemental_oxygen"])
    p.initial_state()
    run(p, 5, mechanical_ventilator={"connected": 1.0})
    with pytest.raises(ValueError, match="same update"):
        run(p, 1, supplemental_oxygen={"oxygen_connected": 1.0})
    run(p, 1)                                                     # disconnect
    out = run(p, 30, supplemental_oxygen={"oxygen_connected": 1.0})[-1]   # then connect
    assert out["supplemental_oxygen"]["cannula"]["nosepiece_oxygen_volume_fraction"] > 0.3  # room air: 0.21


def test_unguarded_device_conflict_is_a_value_error():
    """Without the process's rule (two processes, or a direct engine), BioGears' own
    refusal surfaces as ValueError from advance, not a crash."""
    from viva_biogears.circuits.respiratory import anesthesia_machine_xml
    from viva_biogears.circuits.supplemental_oxygen import nasal_cannula_xml
    from viva_biogears.processes._bridge import advance
    p = make(["supplemental_oxygen"])
    e = direct(p)
    e.process_actions(nasal_cannula_xml(4.0))
    advance(e, 1.0)
    e.process_actions(anesthesia_machine_xml("Mask", VENT_ON))
    with pytest.raises(ValueError, match="airway device"):
        advance(e, 1.0)


def test_cannula_raises_oxygen_and_stops_at_zero():
    p = make(["supplemental_oxygen"])
    init = p.initial_state()["supplemental_oxygen"]
    on = run(p, 90, supplemental_oxygen={"oxygen_connected": 1.0, "oxygen_flow_L_per_min": 6.0})[-1]["supplemental_oxygen"]
    off = run(p, 120)[-1]["supplemental_oxygen"]
    pao2 = "arterial_oxygen_pressure_mmHg"
    assert on["oxygenation"][pao2] > init["oxygenation"][pao2] + 50
    assert off["oxygenation"][pao2] < on["oxygenation"][pao2] - 20
    assert on["oxygenation"]["oxygen_saturation"] > init["oxygenation"]["oxygen_saturation"]


def test_intubated_state_is_refused():
    """A state intubated before load would make the intubated store (0) wrong."""
    p = make(["respiratory"])
    e = direct(p)
    e.process_actions('<Action xsi:type="IntubationData" Type="Tracheal"/>')
    e.advance(1.0)
    path = runtime_dir() / ".." / "viva_test_intubated.xml"
    try:
        e.save_state(path)
        assert read_state(path).intubation != "Off"
        with pytest.raises(ValueError, match="intubated"):
            make(["respiratory"], state_file=str(path.resolve())).initial_state()
        make(["vitals"], state_file=str(path.resolve())).initial_state()  # no intubation setpoint: fine
    finally:
        path.unlink(missing_ok=True)


def test_state_with_an_active_driven_action_is_refused():
    p = make(["cardiovascular"])
    e = direct(p)
    e.process_actions(hemorrhage_xml("RightLeg", 100.0))
    e.advance(2.0)
    path = (runtime_dir() / ".." / "viva_test_bleeding.xml").resolve()
    try:
        e.save_state(path)
        with pytest.raises(ValueError, match="HemorrhageData"):
            make(["cardiovascular"], state_file=str(path)).initial_state()
        make(["thermal"], state_file=str(path)).initial_state()  # doesn't drive hemorrhages: fine
    finally:
        path.unlink(missing_ok=True)


# -- thermal ------------------------------------------------------------------------

def test_thermal_heating_cooling_and_applied_temperature():
    """Heating warms the skin and cooling cools it relative to an unperturbed run;
    an applied temperature pins the clothing node to it. Heating alone works only with
    pybiogears' thermal-application workaround (BioGears 8.2.0 fails with NaN, and
    applies an Off applied temperature)."""
    control = make(["thermal"])
    control.initial_state()
    ref = run(control, 300)[-1]["thermal"]
    skin = lambda o: o["energy"]["skin_temperature_C"]  # noqa: E731
    for change, sign in ((dict(active_heating_W=500.0), 1), (dict(active_cooling_W=300.0), -1)):
        p = make(["thermal"])
        p.initial_state()
        out = run(p, 300, thermal={**ENVIRONMENT_BASELINE, **THERMAL_APPLICATION_BASELINE, **change})[-1]["thermal"]
        assert sign * (skin(out) - skin(ref)) > 1.0, change
    p = make(["thermal"])
    p.initial_state()
    out = run(p, 120, thermal={**ENVIRONMENT_BASELINE, **THERMAL_APPLICATION_BASELINE,
                               "applied_temperature_on": 1.0, "applied_temperature_C": 40.0})[-1]["thermal"]
    assert out["compartments"]["clothing"]["temperature_C"] == pytest.approx(40.0, abs=0.01)


def test_environment_change_is_read_back_and_cools():
    p = make(["thermal"])
    p.initial_state()
    cold = {**ENVIRONMENT_BASELINE, "ambient_temperature_C": 5.0, "mean_radiant_temperature_C": 5.0}
    out = run(p, 300, thermal=cold)[-1]["thermal"]
    assert out["environment"]["ambient_temperature_C"] == 5.0
    assert out["environment"]["relative_humidity"] == ENVIRONMENT_BASELINE["relative_humidity"]
    assert out["heat_loss"]["skin_W"] > 150


def test_nonstandard_environment_state_is_refused():
    from viva_biogears.circuits.thermal import environment_xml
    p = make(["thermal"])
    e = direct(p)
    e.process_actions(environment_xml({**ENVIRONMENT_BASELINE, "relative_humidity": 0.2}))
    e.advance(1.0)
    path = (runtime_dir() / ".." / "viva_test_dry.xml").resolve()
    try:
        e.save_state(path)
        with pytest.raises(ValueError, match="environment differs"):
            make(["thermal"], state_file=str(path)).initial_state()
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.parametrize("bad", [dict(relative_humidity=1.5), dict(ambient_temperature_C=-300.0),
                                 dict(active_heating_W=-1.0), dict(applied_temperature_on=0.5)])
def test_thermal_setpoints_are_validated(bad):
    p = make(["thermal"])
    p.initial_state()
    group = {**ENVIRONMENT_BASELINE, **THERMAL_APPLICATION_BASELINE, **bad}
    with pytest.raises(ValueError):
        run(p, 1, thermal=group)


# -- points ---------------------------------------------------------------------------

def _kirchhoff_residuals(state, nodes, out):
    paths = out["paths"]
    res = {}
    for n in nodes:
        total = 0.0
        for path, (src, dst) in state.path_ends.items():
            if path in paths and n in (src, dst):
                f = paths[path][next(iter(paths[path]))]
                total += f if dst == n else -f
        res[n] = total
    return res


def test_cardiovascular_points_cover_the_circuit_and_obey_kirchhoff():
    """Every node and path is read; at each junction without volume, signed flows sum
    to zero (the circuit solution BioGears computes)."""
    p = make(["cardiovascular_points", "lymph"])
    p.initial_state()
    out = run(p, 3)[-1]
    pts = out["cardiovascular_points"]
    state = read_state(runtime_dir() / "states" / "StandardMale@0s.xml")
    nodes, paths = state.circuits["FullCardiovascular"]
    assert set(pts["nodes"]) == set(nodes) - {"Ground"}
    assert set(pts["paths"]) == set(paths)
    assert pts["nodes"]["Lymph"]["volume_mL"] == out["lymph"]["pool_volume_mL"]
    assert pts["paths"]["LymphToVenaCava"]["flow_mL_per_min"] == out["lymph"]["return_mL_per_min"]
    junctions = [n for n in nodes if n != "Ground" and math.isnan(state.node_volume[n])]
    assert all("volume_mL" not in pts["nodes"][n] for n in junctions)
    res = _kirchhoff_residuals(state, junctions, pts)
    worst = max(abs(v) for v in res.values())
    assert worst < 1e-6 * 5000, sorted(res.items(), key=lambda kv: -abs(kv[1]))[:3]


def test_point_selection_and_airway_opening():
    p = make(["respiratory_points"], respiratory_point_nodes=["Trachea"], respiratory_point_paths=["MouthToTrachea"])
    assert [s[0] for s in p._slots] == [("respiratory_points", "nodes", "Trachea", "absolute_pressure_cmH2O"),
                                        ("respiratory_points", "nodes", "Trachea", "volume_mL"),
                                        ("respiratory_points", "paths", "MouthToTrachea", "flow_L_per_min")]
    assert "EnvironmentToMouth" in make(["respiratory_points"]).outputs()["respiratory_points"]["paths"]
    assert "EnvironmentToMouth" not in make(["respiratory_points", "supplemental_oxygen"]).outputs()[
        "respiratory_points"]["paths"]
    with pytest.raises(ValueError, match="not in BioGears"):
        make(["respiratory_points", "mechanical_ventilator"], respiratory_point_paths=["EnvironmentToMouth"])
    with pytest.raises(ValueError, match="not in BioGears"):
        make(["cardiovascular_points"], cardiovascular_point_nodes=["Aorta9"])
    with pytest.raises(ValueError, match="more than once"):
        make(["cardiovascular_points"], cardiovascular_point_paths=["Aorta1ToAorta2", "Aorta1ToAorta2"])


def test_points_equal_a_direct_engine():
    p = make(["respiratory_points"])
    p.initial_state()
    out = run(p, 2, interval=0.02)[-1]
    e = direct(p)
    for _ in range(100):
        e.advance(0.02)
    np.testing.assert_allclose(flat(p, out), direct_values(p, e), rtol=1e-12)


# -- substances and tissues ------------------------------------------------------------------

SUBSTANCES = [
    {"substance": "Oxygen", "compartment": "Aorta", "property": "PartialPressure", "unit": "mmHg"},
    {"substance": "Albumin", "compartment": "MuscleTissueExtracellular", "property": "Concentration", "unit": "g/dL"},
    {"substance": "Albumin", "compartment": "Lymph", "property": "Concentration", "unit": "g/dL"},
    {"substance": "Oxygen", "compartment": "LeftAlveoli", "property": "PartialPressure", "unit": "mmHg"},
    {"substance": "Sodium", "compartment": "Heart", "property": "Molarity", "unit": "mmol/L"},
    {"substance": "Hemoglobin", "property": "MassInBlood", "unit": "g"},
]
TISSUES = [
    {"compartment": "MuscleTissue", "property": "MatrixVolume", "unit": "mL"},
    {"compartment": "MuscleTissueExtracellular", "property": "Volume", "unit": "mL"},
    {"compartment": "BrainTissueIntracellular", "property": "Volume", "unit": "mL"},
]


def test_substance_and_tissue_readings_equal_a_direct_engine():
    p = make(["substances", "tissues"], substance_outputs=SUBSTANCES, tissue_outputs=TISSUES)
    init = p.initial_state()
    assert set(init["substances"]["Oxygen"]) == {"Aorta", "LeftAlveoli"}
    assert "partial_pressure_mmHg" in init["substances"]["Oxygen"]["Aorta"]
    assert "mass_in_blood_g" in init["substances"]["Hemoglobin"]["body"]
    assert "matrix_volume_mL" in init["tissues"]["MuscleTissue"]
    out = run(p, 5)[-1]
    e = direct(p)
    for _ in range(5):
        e.advance(1.0)
    np.testing.assert_allclose(flat(p, out), direct_values(p, e), rtol=1e-12)


@pytest.mark.parametrize("entry, match", [
    ({"substance": "Morphine", "compartment": "Aorta", "property": "Concentration", "unit": "ug/mL"}, "not an active"),
    ({"substance": "Oxygen", "compartment": "Pericardium", "property": "PartialPressure", "unit": "mmHg"}, "transport"),
    ({"substance": "Sodium", "compartment": "LeftAlveoli", "property": "Concentration", "unit": "g/L"}, "holds no"),
    ({"substance": "Oxygen", "compartment": "Aorta", "property": "Volume", "unit": "mL"}, "has no"),
    ({"substance": "Oxygen", "compartment": "Nowhere", "property": "Mass", "unit": "g"}, "no compartment"),
    ({"substance": "Oxygen", "compartment": "Aorta", "property": "Mass", "units": "g"}, "unknown keys"),
    ({"substance": "Oxygen", "compartment": "Ambient", "property": "PartialPressure", "unit": "mmHg"}, "environment"),
    ({"substance": "Oxygen", "compartment": "LeftChestLeak", "property": "PartialPressure", "unit": "mmHg"}, "injury"),
])
def test_bad_substance_entries_are_refused_before_load(entry, match):
    with pytest.raises(ValueError, match=match):
        make(["substances"], substance_outputs=[entry])


def test_wrong_unit_fails_the_load():
    p = make(["substances"], substance_outputs=[
        {"substance": "Oxygen", "compartment": "Aorta", "property": "PartialPressure", "unit": "mL"}])
    with pytest.raises(RuntimeError, match="did not connect"):
        p.initial_state()


@pytest.mark.parametrize("entry, match", [
    ({"compartment": "MuscleTissue", "property": "Volume", "unit": "mL"}, "has no"),
    ({"compartment": "Aorta", "property": "Volume", "unit": "mL"}, "not a tissue"),
])
def test_bad_tissue_entries_are_refused(entry, match):
    with pytest.raises(ValueError, match=match):
        make(["tissues"], tissue_outputs=[entry])


def test_empty_reading_lists_raise():
    with pytest.raises(ValueError, match="empty"):
        make(["substances"])
