"""Build each hemorrhage study's runs.db from the pilot JSON (the same composites and
parameters), in a scratch copy of workspace/studies, to check the study tests."""
import json, shutil, sqlite3, sys, yaml
from pathlib import Path
P = Path(sys.argv[1]); SRC = Path(sys.argv[2]); DST = Path(sys.argv[3])
shutil.rmtree(DST, ignore_errors=True); shutil.copytree(SRC, DST)
LABEL_TO_PILOT = {
    "hemorrhage-severity-sweep": {f"rate-{r}": f"rate-{r}" for r in (0, 50, 100, 150, 200, 250)},
    "fluid-resuscitation": {"untreated": "rate-200", "saline-map-90": "saline", "blood-map-90": "blood"},
}
spec = yaml.safe_load((SRC / "patient-cohort/study.yaml").read_text())
LABEL_TO_PILOT["patient-cohort"] = {e["name"]: ("rate-200" if e["name"] == "StandardMale" else f"cohort-{e['name']}")
                                    for e in spec["baseline"] + spec["variants"]}
VIT = ["mean_arterial_pressure_mmHg", "heart_rate_bpm", "blood_volume_mL", "total_blood_volume_lost_mL",
       "cardiac_output_L_per_min", "irreversible_state"]
for study, labels in LABEL_TO_PILOT.items():
    spec = yaml.safe_load((DST / study / "study.yaml").read_text())
    declared = {e["name"]: e.get("params") or e.get("parameter_overrides") for e in spec["baseline"] + spec["variants"]}
    db = sqlite3.connect(DST / study / "runs.db")
    db.executescript("""CREATE TABLE runs_meta (run_id TEXT PRIMARY KEY, spec_id TEXT, label TEXT, params_json TEXT,
        started_at REAL, completed_at REAL, n_steps INTEGER, status TEXT, sim_name TEXT, manifest_json TEXT);
        CREATE TABLE history (simulation_id TEXT, step INTEGER, global_time REAL, state TEXT);""")
    for k, (label, pilot) in enumerate(labels.items()):
        s = json.load(open(P / f"{pilot}.json"))["series"]
        params = {x: v for x, v in declared[label].items() if x != "n_steps"}
        db.execute("INSERT INTO runs_meta VALUES (?,?,?,?,?,?,?,?,?,?)", (f"r{k}", "c", label, json.dumps(params), k, k,
                   600, "completed", label, json.dumps({"code_version": {"git_sha": "abc"}})))
        rate = params.get("rate_mL_per_min", 0.0)
        for i, t in enumerate(s["time"]):
            state = {"global_time": t, "vitals": {v: s[v][i] for v in VIT},
                     "interventions": {"hemorrhage_rate_mL_per_min": rate, "iv_rate_mL_per_min": s["iv_rate_mL_per_min"][i]}}
            db.execute("INSERT INTO history VALUES (?,?,?,?)", (f"r{k}", i, t, json.dumps(state)))
    db.commit()
