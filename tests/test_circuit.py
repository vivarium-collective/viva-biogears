"""BioGearsCircuitProcess against the real engine.

Oracles: a pybiogears engine driven directly with the same requests and actions
(bridge equality), and conservation laws that hold on BioGears' own circuit
(lymph pool mass balance, Ohm's law on the lymph return path)."""
import numpy as np
import pytest

from viva_biogears.circuits import MODULES, TISSUES
from viva_biogears.core import build_core
from viva_biogears.processes import VITALS, BioGearsCircuitProcess, BioGearsProcess
from viva_biogears.runtime import import_pybiogears, runtime_dir

_CORE = build_core()
_REST = {"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0}


def make(modules, **config):
    return BioGearsCircuitProcess({"modules": modules, **config}, core=_CORE)


def _run(proc, seconds, **setpoints):
    state = {"interventions": {**_REST, **setpoints}}
    return [proc.update(state, 1.0) for _ in range(int(seconds))]


def _flat(module, out):
    """Module output -> values in MODULES[module].requests order."""
    vals = []
    for req in MODULES[module].requests:
        d = out[module]
        for p in req.path:
            d = d[p]
        vals.append(d)
    return np.array(vals, dtype=float)


@pytest.mark.parametrize("modules, match", [
    ([], "empty"), (["lymph", "edema"], "unknown"), (["lymph", "lymph"], "twice")])
def test_invalid_modules_raise(modules, match):
    with pytest.raises(ValueError, match=match):
        make(modules)


def test_ports_nest_per_module_and_are_disjoint_from_inputs():
    p = make(["lymph", "tissue_fluid"])
    out = p.outputs()
    assert set(out) == {"lymph", "tissue_fluid", "irreversible_state"}
    assert set(out["lymph"]["formation"]) == {f"{k}_mL_per_min" for k in TISSUES}
    assert set(out["tissue_fluid"]) >= set(TISSUES)
    assert not set(out) & set(p.inputs())


def test_readings_equal_a_directly_driven_engine():
    """Falsifies: wrong request order, a dropped negate, or actions sent at the wrong time."""
    modules = ["vitals", "lymph", "tissue_fluid"]
    p = make(modules)
    init = p.initial_state()
    _run(p, 5)
    out = _run(p, 10, iv_rate_mL_per_min=150.0)[-1]

    pb = import_pybiogears()
    rt = runtime_dir()
    reqs = [r for m in modules for r in MODULES[m].requests]
    e = pb.BioGearsEngine(rt)
    e.set_requests([pb.DataRequest(r.category, r.property, r.unit, compartment=r.compartment,
                                   substance=r.substance) for r in reqs])
    e.load_state(rt / "states" / "StandardMale@0s.xml")
    sign = np.array([-1.0 if r.negate else 1.0 for r in reqs])
    got0 = np.concatenate([_flat(m, init) for m in modules])
    np.testing.assert_array_equal(got0[:9], (e.pull()[1:] * sign)[:9])  # vitals[9]: NaN before a bleed
    np.testing.assert_array_equal(got0[10:], (e.pull()[1:] * sign)[10:])
    for _ in range(5):
        e.advance(1.0)
    e.process_actions(pb.actions.substance_compound_infusion("Saline", 10000.0, 150.0))
    for _ in range(10):
        e.advance(1.0)
    got = np.concatenate([_flat(m, out) for m in modules])
    want = e.pull()[1:] * sign
    np.testing.assert_allclose(got[:9], want[:9], rtol=1e-12)
    np.testing.assert_allclose(got[10:], want[10:], rtol=1e-12)


def test_vitals_module_matches_biogears_process():
    c, v = make(["vitals"]), BioGearsProcess({}, core=_CORE)
    c.initial_state(), v.initial_state()
    oc = _run(c, 10, hemorrhage_rate_mL_per_min=200.0)[-1]
    for _ in range(10):
        ov = v.update({**_REST, "hemorrhage_rate_mL_per_min": 200.0}, 1.0)
    for k in VITALS:
        assert oc["vitals"][k] == ov[k], k


def test_lymph_pool_mass_balance_and_return_ohms_law():
    """The pool changes by the integral of (formation - return), and the return path
    is a passive resistor: return = (P_pool - P_venacava) / R."""
    p = make(["lymph"])
    rows = [p.initial_state()["lymph"]] + [o["lymph"] for o in _run(p, 60)]
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
    p = make(["lymph"])
    init = p.initial_state()["lymph"]
    out = _run(p, 120, iv_rate_mL_per_min=200.0)[-1]["lymph"]
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
