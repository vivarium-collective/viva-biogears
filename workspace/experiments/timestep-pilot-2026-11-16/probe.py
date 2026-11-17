"""Timestep pilot: run one arm of the timestep studies as the workbench does (the
composite plus an emitter of the study's readouts) and save its readouts and wall time.

    python probe.py STUDY ARM OUT.json      (STUDY: timestep-hemorrhage | timestep-sepsis)
"""
import importlib
import json
import sys
import time
from pathlib import Path

import yaml
from process_bigraph import Composite, gather_emitter_results
from vivarium_workbench.lib.composite_runs import inject_emitter_for_declared_paths

from viva_biogears.core import build_core

study, arm, out = sys.argv[1], sys.argv[2], sys.argv[3]
spec = yaml.safe_load((Path(__file__).parents[2] / "studies" / study / "study.yaml").read_text())
entry = next(e for e in spec["baseline"] + spec["variants"] if e["name"] == arm)
params = dict(entry.get("params") or entry.get("parameter_overrides"))
n_steps = params.pop("n_steps")
mod, fn = entry["composite"].rsplit(".", 1)
core = build_core()
doc = getattr(importlib.import_module(mod), fn)(core, **params)
doc = inject_emitter_for_declared_paths(doc, [r["store_path"].replace(".", "/") for r in spec["readouts"]])
interval = params.get("interval", 1.0)
wall = time.perf_counter()
sim = Composite({"state": doc}, core=core)
sim.run(n_steps * interval)
wall = time.perf_counter() - wall
rows = gather_emitter_results(sim)[("user_emitter",)]
json.dump({"study": study, "arm": arm, "params": params, "wall_s": wall, "rows": rows}, open(out, "w"))
print(arm, f"{wall:.0f} s", flush=True)
