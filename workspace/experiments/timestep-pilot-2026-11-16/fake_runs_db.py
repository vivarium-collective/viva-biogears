"""Build the timestep studies' runs.db from this pilot's out/*.json (workbench 0.4.1 layout:
one history.state JSON per step, wall time as completed_at - started_at), in a copy of
workspace/studies, to check the study tests: python fake_runs_db.py STUDIES DEST"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SRC, DST = Path(sys.argv[1]), Path(sys.argv[2])
shutil.rmtree(DST, ignore_errors=True)
shutil.copytree(SRC, DST)
for study in ("timestep-hemorrhage", "timestep-sepsis"):
    spec = yaml.safe_load((DST / study / "study.yaml").read_text())
    db = sqlite3.connect(DST / study / "runs.db")
    db.executescript("""CREATE TABLE runs_meta (run_id TEXT PRIMARY KEY, spec_id TEXT, label TEXT, params_json TEXT,
        started_at REAL, completed_at REAL, n_steps INTEGER, status TEXT, sim_name TEXT, manifest_json TEXT);
        CREATE TABLE history (simulation_id TEXT, step INTEGER, global_time REAL, state TEXT);""")
    for k, entry in enumerate(spec["baseline"] + spec["variants"]):
        p = json.loads((HERE / "out" / f"{study}-{entry['name']}.json").read_text())
        params = {x: v for x, v in (entry.get("params") or entry["parameter_overrides"]).items() if x != "n_steps"}
        start = 1000.0 * k
        db.execute("INSERT INTO runs_meta VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (f"r{k}", "c", entry["name"], json.dumps(params), start, start + p["wall_s"], 0, "completed",
                    entry["name"], json.dumps({"code_version": {"git_sha": "abc"}})))
        for i, row in enumerate(p["rows"]):
            row = {**row, "engine": {"time_step_s": params["time_step_s"]}}   # older pilot rows lack it
            if "circuits" in row:                       # recorded before the store was renamed readings
                row["readings"] = row.pop("circuits")
            db.execute("INSERT INTO history VALUES (?,?,?,?)", (f"r{k}", i, row["global_time"], json.dumps(row)))
    db.commit()
