"""Helpers shared by the BioGearsModularProcess tests."""
import numpy as np

from viva_biogears.modules import MODULES
from viva_biogears.core import build_core
from viva_biogears.processes import BioGearsModularProcess
from viva_biogears.runtime import import_pybiogears, runtime_dir, state_path

CORE = build_core()


def make(modules, **config):
    return BioGearsModularProcess({"modules": list(modules), **config}, core=CORE)


def baselines(proc):
    return {m.name: {p: v for b in m.bindings for p, v in b.ports.items()} for m in proc._modules if m.bindings}


def run(proc, seconds, interval=1.0, **changes):
    """Advance ``seconds`` with the setpoints at their baselines updated by ``changes``
    (``module={port: value}``); returns every update's output."""
    sp = baselines(proc)
    for module, ports in changes.items():
        sp[module].update(ports)
    return [proc.update({"setpoints": sp}, interval) for _ in range(int(round(seconds / interval)))]


def leaf(tree, path):
    for p in path:
        tree = tree[p]
    return tree


def flat(proc, out):
    """Process output -> values in request order of its slots (negated as reported)."""
    return np.array([leaf(out, path) for path, _, _ in proc._slots], dtype=float)


def direct(proc, state_file="StandardMale@0s.xml"):
    """A pybiogears engine with the process's requests, loaded from the same state (the oracle)."""
    pb = import_pybiogears()
    rt = runtime_dir()
    e = pb.BioGearsEngine(rt)
    e.set_requests([pb.DataRequest(r.category, r.property, r.unit, compartment=r.compartment, substance=r.substance)
                    for r in proc._requests])
    e.load_state(state_path(rt, state_file))
    return e


def direct_values(proc, engine):
    raw = engine.pull()[1:]
    return np.array([-raw[i] if neg else raw[i] for _, i, neg in proc._slots], dtype=float)


__all__ = ["MODULES", "baselines", "direct", "direct_values", "flat", "leaf", "make", "run"]
