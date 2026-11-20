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


def summed_clock(seconds, step_s=0.02):
    """BioGears' clock after ``seconds`` from 0: a floating-point sum of its steps, which the
    real engine matches bit for bit (``test_the_clock_is_a_sum_of_steps``). At 0.02 s it reads
    43199.999999 s at 12 h, 144000.000002 s at 40 h and 172799.999987 s at 48 h."""
    t = 0.0
    for _ in range(round(seconds / step_s)):
        t += step_s
    return t


def clock_error(hours, step_s=0.02):
    """How far BioGears' clock reads below the exact time after ``hours`` (negative: above)."""
    return hours * 3600.0 - summed_clock(hours * 3600.0, step_s)


class Drifted:
    """A real engine whose clock reads ``by`` seconds below its true time (above, when
    negative), as BioGears' summed clock does on long runs. Everything else is the engine."""

    def __init__(self, engine, by):
        self._engine, self._by = engine, by

    def __getattr__(self, name):
        return getattr(self._engine, name)

    @property
    def sim_time_s(self):
        return self._engine.sim_time_s - self._by


__all__ = ["MODULES", "Drifted", "baselines", "clock_error", "direct", "direct_values", "flat", "leaf", "make",
           "run", "summed_clock"]
