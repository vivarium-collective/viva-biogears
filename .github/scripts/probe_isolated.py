"""Probe: does a spawned process's engine vs an oracle engine differ run to run? Variants:
A = both engines in one fresh process (current test); B = process engine in one fresh process, oracle in another."""
import multiprocessing, sys, os
from concurrent.futures import ProcessPoolExecutor
import numpy as np
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
from circuit_helpers import direct, direct_values, flat, make, run
from viva_biogears.modules.treatment import compound_infusion_xml, substance_infusion_xml
PIP = {"hour": 1 / 60, "compound": "PiperacillinTazobactam", "bag_volume_mL": 20.0, "rate_mL_per_min": 0.667}
BOLUS = {"hour": 2 / 60, "compound": "Saline", "bag_volume_mL": 100.0, "rate_mL_per_min": 50.0}
NOR = {"hour": 3 / 60, "substance": "Norepinephrine", "concentration_ug_per_mL": 14.0, "rate_mL_per_min": 1.0}

def mk():
    p = make(["treatment", "cardiovascular"], treatment_schedule=[PIP, BOLUS, NOR], treatment_readouts=["Piperacillin", "Norepinephrine"])
    p.initial_state()
    return p

def oracle_run(p, e):
    for minute in range(5):
        if minute == 1: e.process_actions(compound_infusion_xml("PiperacillinTazobactam", 20.0, 0.667))
        if minute == 2: e.process_actions(compound_infusion_xml("Saline", 100.0, 50.0))
        if minute == 3: e.process_actions(substance_infusion_xml("Norepinephrine", 14.0, 1.0))
        e.advance(60.0)
    return direct_values(p, e)

def A():
    p = mk(); e = direct(p)
    out = run(p, 300, interval=60.0)[-1]
    return flat(p, out), oracle_run(p, e)

def Bproc():
    p = mk(); return flat(p, run(p, 300, interval=60.0)[-1])

def Borac():
    p = mk(); e = direct(p); return oracle_run(p, e)

def spawn(fn):
    with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn")) as pool:
        return pool.submit(fn).result()

if __name__ == "__main__":
    v = sys.argv[1]
    if v == "A": a, b = spawn(A)
    else: a, b = spawn(Bproc), spawn(Borac)
    m = np.isfinite(a) & np.isfinite(b)
    print(v, "n", a.size, "nan_a", int((~np.isfinite(a)).sum()), "nan_b", int((~np.isfinite(b)).sum()), "maxrel", float(np.max(np.abs(a[m] - b[m]) / np.maximum(np.abs(b[m]), 1e-300))), "sum", repr(float(np.sum(a[m]))), repr(float(np.sum(b[m]))), flush=True)
