"""BioGearsModularProcess against the real engine: the bridge, and the lymph and tissue-fluid modules.

Oracles: a pybiogears engine driven directly with the same requests and actions
(bridge equality), and conservation laws that hold on BioGears' own circuit
(lymph pool mass balance, Ohm's law on the lymph return path)."""
import numpy as np
import pytest
from circuit_helpers import direct, direct_values, flat, make, run

from viva_biogears.modules import MODULES, TISSUES
from viva_biogears.modules.cardiovascular import hemorrhage_xml, infusion_xml
from viva_biogears.modules.supplemental_oxygen import nasal_cannula_xml
from viva_biogears.modules.thermal import ENVIRONMENT_BASELINE, environment_xml
from viva_biogears.processes import VITALS, BioGearsProcess


@pytest.mark.parametrize("modules, match", [
    ([], "empty"), (["lymph", "edema"], "unknown"), (["lymph", "lymph"], "twice")])
def test_invalid_modules_raise(modules, match):
    with pytest.raises(ValueError, match=match):
        make(modules)


def test_every_module_is_documented_and_reachable():
    for name, m in MODULES.items():
        assert m.name == name and m.description, name


def test_ports_nest_per_module_and_are_disjoint_from_inputs():
    p = make(["lymph", "tissue_fluid", "cardiovascular"])
    out = p.outputs()
    assert set(out) == {"lymph", "tissue_fluid", "cardiovascular", "irreversible_state"}
    assert set(out["lymph"]["formation"]) == {f"{k}_mL_per_min" for k in TISSUES}
    assert set(out["tissue_fluid"]) >= set(TISSUES)
    assert set(p.inputs()) == {"setpoints"} and set(p.inputs()["setpoints"]) == {"cardiovascular"}
    assert not set(out) & set(p.inputs())


def test_readings_equal_a_directly_driven_engine():
    """Falsifies: wrong request order, a dropped negate, shared requests mixed up, or
    actions sent at the wrong time. Every module with static outputs, several actions."""
    modules = ["vitals", "cardiovascular", "respiratory", "supplemental_oxygen", "thermal", "lymph", "tissue_fluid"]
    p = make(modules)
    init = p.initial_state()
    e = direct(p)
    want0, got0 = direct_values(p, e), flat(p, init)
    np.testing.assert_array_equal(np.isnan(got0), np.isnan(want0))
    np.testing.assert_array_equal(got0[~np.isnan(got0)], want0[~np.isnan(want0)])

    run(p, 5)
    run(p, 5, cardiovascular={"hemorrhage_rate_mL_per_min": 150.0, "iv_rate_mL_per_min": 100.0},
        supplemental_oxygen={"oxygen_connected": 1.0})
    env = {**ENVIRONMENT_BASELINE, "ambient_temperature_C": 10.0}
    out = run(p, 5, cardiovascular={"hemorrhage_rate_mL_per_min": 150.0, "iv_rate_mL_per_min": 100.0},
              supplemental_oxygen={"oxygen_connected": 1.0}, thermal=env)[-1]

    for _ in range(5):
        e.advance(1.0)
    e.process_actions([hemorrhage_xml("RightLeg", 150.0), infusion_xml("Saline", 10.0, 100.0),
                       nasal_cannula_xml(4.0)])
    for _ in range(5):
        e.advance(1.0)
    e.process_actions(environment_xml(env))
    for _ in range(5):
        e.advance(1.0)
    np.testing.assert_allclose(flat(p, out), direct_values(p, e), rtol=1e-12)
    assert out["thermal"]["environment"]["ambient_temperature_C"] == 10.0


def test_shared_requests_are_read_once():
    p = make(["vitals", "cardiovascular", "lymph"])
    keys = [r.key() for r in p._requests]
    assert len(keys) == len(set(keys))
    assert len(p._slots) > len(p._requests)  # e.g. CVP is in all three


def test_vitals_module_matches_biogears_process():
    from circuit_helpers import CORE
    c, v = make(["vitals", "cardiovascular"]), BioGearsProcess({}, core=CORE)
    c.initial_state(), v.initial_state()
    oc = run(c, 10, cardiovascular={"hemorrhage_rate_mL_per_min": 200.0})[-1]
    for _ in range(10):
        ov = v.update({"hemorrhage_rate_mL_per_min": 200.0, "iv_rate_mL_per_min": 0.0}, 1.0)
    for k in VITALS:
        assert oc["vitals"][k] == ov[k], k


def test_lymph_pool_mass_balance_and_return_ohms_law():
    """The pool changes by the integral of (formation - return), and the return path
    is a passive resistor: return = (P_pool - P_venacava) / R."""
    p = make(["lymph"])
    rows = [p.initial_state()["lymph"]] + [o["lymph"] for o in run(p, 60)]
    net = [sum(r["formation"].values()) - r["return_mL_per_min"] for r in rows]
    dpool = rows[-1]["pool_volume_mL"] - rows[0]["pool_volume_mL"]
    assert abs(dpool) > 0.5  # StandardMale@0s is not at fluid steady state (pybiogears P5)
    np.testing.assert_allclose(np.trapezoid(net, dx=1 / 60), dpool, rtol=0.01)
    for r in rows:
        ohm = (r["pool_pressure_mmHg"] - r["vena_cava_pressure_mmHg"]) / r["return_resistance_mmHg_min_per_mL"]
        np.testing.assert_allclose(r["return_mL_per_min"], ohm, rtol=1e-9)
        assert all(f >= 0 for f in r["formation"].values())


def test_infusion_raises_cvp_and_throttles_lymph_return():
    """Saline raises venous pressure, which lowers the passive lymph return while
    formation rises: the coupling McDaniel 2019 relies on for fluid overload."""
    p = make(["lymph", "cardiovascular"])
    init = p.initial_state()["lymph"]
    out = run(p, 120, cardiovascular={"iv_rate_mL_per_min": 200.0})[-1]["lymph"]
    assert out["central_venous_pressure_mmHg"] > init["central_venous_pressure_mmHg"] + 0.2
    assert out["return_mL_per_min"] < init["return_mL_per_min"] - 0.5
    assert sum(out["formation"].values()) > sum(init["formation"].values())


def test_tissue_fluid_readings_are_physical():
    p = make(["tissue_fluid"])
    tf = p.initial_state()["tissue_fluid"]
    for key in TISSUES:
        t = tf[key]
        # Starling: plasma oncotic pressure exceeds interstitial (after the sign fix).
        assert t["plasma_oncotic_pressure_mmHg"] > t["interstitial_oncotic_pressure_mmHg"] > 0, key
        assert t["extracellular_volume_mL"] > 0 and t["intracellular_volume_mL"] > 0, key
        assert 0 < t["interstitial_albumin_g_per_dL"] < tf["plasma_albumin_g_per_dL"], key
        assert t["endothelial_resistance_mmHg_min_per_mL"] > 0, key
    assert tf["total_body_fluid_mL"] == pytest.approx(
        tf["blood_volume_mL"] + tf["extravascular_fluid_mL"], rel=0.15)


def test_equilibrated_state_is_shipped_and_does_not_drift():
    """Falsifies: the shipped baseline isn't found by name, or its lymph pool isn't
    settled (StandardMale@0s gains 3.4 mL in 2 min; this state 0.1 mL). Blood volume
    is not checked: with hourly drinks it swings by tens of mL within each hour."""
    from viva_biogears.runtime import EQUILIBRATED_STATE
    p = make(["lymph", "tissue_fluid"], state_file=EQUILIBRATED_STATE)
    init = p.initial_state()
    out = run(p, 120)[-1]
    assert abs(out["lymph"]["pool_volume_mL"] - init["lymph"]["pool_volume_mL"]) < 1.0
    assert init["tissue_fluid"]["blood_volume_mL"] == pytest.approx(5880, abs=1)


def test_send_on_change_does_not_restart_the_bleed():
    """Falsifies: setpoints resent every update (resending a hemorrhage restarts BioGears' bleed)."""
    p = make(["cardiovascular"])
    p.initial_state()
    out = run(p, 30, cardiovascular={"hemorrhage_rate_mL_per_min": 300.0})[-1]
    e = direct(p)
    e.process_actions(hemorrhage_xml("RightLeg", 300.0))
    for _ in range(30):
        e.advance(1.0)
    np.testing.assert_allclose(flat(p, out), direct_values(p, e), rtol=1e-12, equal_nan=True)


def test_circuit_process_time_step_reaches_the_engine():
    """Falsifies: BioGearsModularProcess ignoring time_step_s."""
    p = make(["vitals"], time_step_s=0.08)
    p.initial_state()
    run(p, 2.0)
    assert p._engine.time_step_s == 0.08
    assert p._engine.sim_time_s == pytest.approx(2.0, abs=0.08)
    with pytest.raises(ValueError, match="time_step_s"):
        make(["vitals"], time_step_s=0.1)
