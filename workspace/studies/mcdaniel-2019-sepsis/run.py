"""Run the McDaniel et al. 2019 replication arms on viva-biogears' BioGearsCircuitProcess.

    python run.py ARM [ARM ...] [--out DIR] [--hours H] [--jobs N]
      ARM: control | mild | moderate | severe | challenge | antibiotic | refresh_control
           | refresh_experimental | refresh_control_delayed | untreated | all

Every arm is the ``biogears_sepsis`` composite's process (modules infection, nutrition,
lymph, tissue_fluid, cardiovascular; BioGears' InfectionModerate meal and water schedule),
driven update by update at 60 s:

- control, mild, moderate, severe: StandardMale@0s, infection severity 0/1/2/3 at t = 0
  (Skin, MIC 16 mg/L), 48 h (paper Figs 4-7);
- the treatment arms branch from severe's 44 h checkpoint and follow a
  viva_biogears.protocols.TreatmentProtocol, the same one the biogears_sepsis composite's
  TreatmentController runs (the workbench studies mcdaniel-2019-treatment and
  mcdaniel-2019-refresh run these arms from t = 0 instead):
  - challenge: two 500 mL saline boluses at 50 mL/min at 44 and 44.5 h, to 46 h (Fig 9);
  - antibiotic: the challenge, then piperacillin/tazobactam at 46 h, to 52 h (Fig 10);
  - refresh_control, refresh_experimental: the challenge, the antibiotic and the REFRESH
    protocol from 46 to 52 h (Figs 11-12);
  - refresh_control_delayed: the same control protocol 12 h later (challenge at 56 h,
    protocol 58-64 h; Fig 13);
  - untreated: severe continued to 64 h with no treatment, the delayed arm's comparator.

Each arm writes OUT/<arm>/data.csv (one row per simulated minute; the columns analyze.py
reads), events.csv (BioGears' patient events) and log.txt, and saves a checkpoint every
4 simulated hours (OUT/<arm>/ckpt<start>@<t>s.xml, one name per segment of a resumed
run, since a state is never overwritten), with the protocol's own state beside it
(protocol@<t>s.json). An interrupted arm resumes from its last
checkpoint: the process reads the infection from the state, so the branch continues the
run (viva_biogears.states), and the meals before it are skipped.
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: Per-beat and per-breath events, left out of events.csv.
CYCLE_EVENTS = {"StartOfCardiacCycle", "StartOfInhale", "StartOfExhale"}
ARMS = {"control": 0.0, "mild": 1.0, "moderate": 2.0, "severe": 3.0}
STEP_S = 60.0
CHECKPOINT_S = 4 * 3600.0
#: Treatment arms: protocol, and the protocol's timing relative to the branch (the
#: challenge time, 44 h): (challenge, start) offsets in hours. All branch from severe.
TREATED = {"challenge": ("fluid_challenge", 0.0, 2.0), "antibiotic": ("antibiotic", 0.0, 2.0),
           "refresh_control": ("refresh_control", 0.0, 2.0),
           "refresh_experimental": ("refresh_experimental", 0.0, 2.0),
           "refresh_control_delayed": ("refresh_control", 12.0, 14.0),
           "untreated": ("none", 0.0, 2.0)}
BRANCH_H = 44.0
UNTREATED_END_H = 64.0


def set_test_timing(checkpoint_h: float | None, challenge_at_h: float | None) -> None:
    """Shorter checkpoints and an earlier branch and challenge, for checking the script quickly."""
    global CHECKPOINT_S, BRANCH_H
    if checkpoint_h:
        CHECKPOINT_S = checkpoint_h * 3600.0
    if challenge_at_h is not None:
        BRANCH_H = challenge_at_h


def protocol_for(arm: str, state: dict | None = None):
    from viva_biogears.protocols import TreatmentProtocol

    name, challenge, start = TREATED[arm]
    return TreatmentProtocol(name, challenge_h=BRANCH_H + challenge, start_h=BRANCH_H + start,
                             interval_s=STEP_S, state=state)


def end_h(arm: str, hours: float) -> float:
    if arm not in TREATED:
        return hours
    if arm == "untreated":
        return BRANCH_H + UNTREATED_END_H - 44.0
    return protocol_for(arm).end_h

#: data.csv column -> path in the process's readings (the names analyze.py reads).
COLUMNS = {
    "BloodPathogen": ("infection", "inflammation", "blood_pathogen"),
    "LocalPathogen": ("infection", "inflammation", "local_pathogen"),
    "TNF": ("infection", "inflammation", "tumor_necrosis_factor"),
    "IL6": ("infection", "inflammation", "interleukin_6"),
    "IL10": ("infection", "inflammation", "interleukin_10"),
    "NO": ("infection", "inflammation", "nitric_oxide"),
    "TissueIntegrity": ("infection", "inflammation", "tissue_integrity"),
    "HR": ("infection", "clinical", "heart_rate_bpm"),
    "RR": ("infection", "clinical", "respiration_rate_bpm"),
    "CoreTemperature": ("infection", "clinical", "core_temperature_C"),
    "WBC": ("infection", "clinical", "white_blood_cell_count_per_uL"),
    "BloodVolume": ("infection", "clinical", "blood_volume_mL"),
    "SBP": ("infection", "clinical", "systolic_pressure_mmHg"),
    "DBP": ("cardiovascular", "hemodynamics", "diastolic_pressure_mmHg"),
    "MAP": ("infection", "clinical", "mean_arterial_pressure_mmHg"),
    "SVR": ("infection", "clinical", "systemic_vascular_resistance_mmHg_s_per_mL"),
    "UrineRate": ("infection", "clinical", "urine_production_mL_per_min"),
    "MeanUrineOutput": ("infection", "clinical", "mean_urine_output_mL_per_min"),
    "Lactate": ("infection", "clinical", "lactate_mmol_per_L"),
    "CardiacOutput": ("infection", "clinical", "cardiac_output_L_per_min"),
    "StrokeVolume": ("cardiovascular", "hemodynamics", "stroke_volume_mL"),
    "CVP": ("lymph", "central_venous_pressure_mmHg"),
    "ExtravascularFluid": ("tissue_fluid", "extravascular_fluid_mL"),
    "TotalBodyFluid": ("tissue_fluid", "total_body_fluid_mL"),
    "Albumin": ("tissue_fluid", "plasma_albumin_g_per_dL"),
    "LymphReturn": ("lymph", "return_mL_per_min"),
    "LymphPool": ("lymph", "pool_volume_mL"),
    "MuscleEndothelialResistance": ("tissue_fluid", "muscle", "endothelial_resistance_mmHg_min_per_mL"),
    "IVRate": ("setpoint", "iv_rate_mL_per_min"),
    "VasopressorRate": ("setpoint", "vasopressor_rate_ug_per_min"),
    "SalineGiven": ("protocol", "given_mL"),
    "AntibioticActivity": ("treatment", "antibiotic_activity_per_hr"),
    "Piperacillin": ("treatment", "Piperacillin", "plasma_concentration_ug_per_mL"),
    "Norepinephrine": ("treatment", "Norepinephrine", "blood_concentration_ug_per_mL"),
}
LYMPH_TISSUES = {"Bone": "bone", "Brain": "brain", "Fat": "fat", "Gut": "gut", "LeftKidney": "left_kidney",
                 "LeftLung": "left_lung", "Liver": "liver", "Muscle": "muscle", "Myocardium": "myocardium",
                 "RightKidney": "right_kidney", "RightLung": "right_lung", "Skin": "skin", "Spleen": "spleen"}
COLUMNS.update({f"{t}Lymph": ("lymph", "formation", f"{k}_mL_per_min") for t, k in LYMPH_TISSUES.items()})


def _get(tree, path):
    """The reading at ``path``; NaN where the arm doesn't read it (drugs, untreated)."""
    for key in path:
        if not isinstance(tree, dict) or key not in tree:
            return float("nan")
        tree = tree[key]
    return tree


def process(arm: str, out: Path, state_file: str, save_times, name: str):
    from viva_biogears.composites import biogears_sepsis
    from viva_biogears.core import build_core
    from viva_biogears.processes import BioGearsCircuitProcess

    treated = arm in TREATED
    severity = "severe" if treated else {0.0: "none", 1.0: "mild", 2.0: "moderate", 3.0: "severe"}[ARMS[arm]]
    kw = {}
    if treated:
        p = protocol_for(arm)
        kw = {"treatment": p.protocol, "challenge_h": p.challenge_s / 3600.0, "treatment_start_h": p.start_s / 3600.0}
    node = biogears_sepsis(None, severity=severity, state_file=state_file, **kw)["biogears"]
    config = {**node["config"], "save_state_times_s": list(save_times), "save_state_dir": str(out),
              "save_state_name": name}
    proc = BioGearsCircuitProcess(config, core=build_core())
    return proc, {"infection": {"infection_severity": 3.0 if treated else ARMS[arm]},
                  "cardiovascular": {"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0},
                  "treatment": {"vasopressor_rate_ug_per_min": 0.0}}


def _seconds(path: Path) -> float:
    return float(path.stem.split("@")[1][:-1])


def checkpoints(out: Path):
    return sorted(out.glob("ckpt*@*s.xml"), key=_seconds)


def run_arm(arm: str, root: Path, hours: float) -> None:
    out = root / arm
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "log.txt", "a")
    say = lambda msg: (log.write(f"{time.ctime()} {msg}\n"), log.flush())  # noqa: E731
    end = end_h(arm, hours) * 3600.0
    saved = checkpoints(out)
    protocol_state = None
    if saved:
        start_file, start = str(saved[-1]), _seconds(saved[-1])
        if arm in TREATED:
            protocol_state = json.loads((out / f"protocol@{round(start)}s.json").read_text())
    elif arm in TREATED:
        branch = BRANCH_H * 3600.0
        source = [p for p in checkpoints(root / "severe") if abs(_seconds(p) - branch) < 1]
        if not source:
            raise SystemExit(f"{arm} needs severe's {BRANCH_H:g} h checkpoint: run severe first")
        start_file, start = str(source[0]), branch
    else:
        start_file, start = "StandardMale@0s.xml", 0.0
    if start >= end - 1:
        say(f"{arm}: already complete")
        return
    save_times = [t for t in [CHECKPOINT_S * k for k in range(1, 100)] if start < t <= end]
    proc, setpoints = process(arm, out, start_file, save_times, f"ckpt{round(start)}")
    protocol = protocol_for(arm, protocol_state) if arm in TREATED else None
    first = proc.initial_state()
    data = out / "data.csv"
    rows = []
    if saved and data.exists():  # resume: keep the rows up to the checkpoint
        rows = [r for r in csv.reader(open(data))][1:]
        rows = [r for r in rows if float(r[0]) <= start / 3600.0 + 1e-9]
    writer_file = open(data, "w", newline="")
    w = csv.writer(writer_file)
    w.writerow(["t_h", *COLUMNS])
    w.writerows(rows)

    def write(t_s, reading):
        reading = {**reading, "setpoint": {**setpoints["cardiovascular"], **setpoints["treatment"]},
                   "protocol": protocol.state if protocol else {"given_mL": 0.0}}
        w.writerow([repr(t_s / 3600.0)] + [repr(float(_get(reading, p))) for p in COLUMNS.values()])

    if not rows:
        write(start, first)
    events_file = out / "events.csv"
    kept = []
    if saved and events_file.exists():
        kept = [r for r in list(csv.reader(open(events_file)))[1:] if float(r[0]) <= start / 3600.0 + 1e-9]
    ev_file = open(events_file, "w", newline="")
    ev = csv.writer(ev_file)
    ev.writerow(["t_h", "event", "active"])
    ev.writerows(kept)
    last_event = start - 1e-9

    def write_events():
        nonlocal last_event
        # pybiogears keeps a bounded log of recent events, so collect them every update.
        for ts, name, active in proc.events():
            if ts > last_event and name not in CYCLE_EVENTS:
                ev.writerow([repr(ts / 3600.0), name, int(active)])
        last_event = max([last_event] + [ts for ts, _, _ in proc.events()])

    say(f"{arm}: from {start_file} at {start / 3600:.2f} h to {end / 3600:.2f} h")
    t, wall, reading = start, time.perf_counter(), first
    while t < end - 1e-6:
        if protocol is not None:
            clinical = reading["infection"]["clinical"]
            saline, nor = protocol.setpoints(t, clinical["systolic_pressure_mmHg"],
                                             clinical["mean_arterial_pressure_mmHg"],
                                             clinical["mean_urine_output_mL_per_min"])
            setpoints["cardiovascular"]["iv_rate_mL_per_min"] = saline
            setpoints["treatment"]["vasopressor_rate_ug_per_min"] = nor
        reading = proc.update({"setpoints": setpoints}, STEP_S)
        t += STEP_S
        write_events()
        if reading.get("irreversible_state"):
            say(f"{arm}: irreversible state at {t / 3600:.2f} h")
            break
        write(t, reading)
        if protocol is not None and any(abs(t - x) < 1e-6 for x in save_times):
            (out / f"protocol@{round(t)}s.json").write_text(json.dumps(protocol.state))
        if round(t) % 3600 == 0:
            writer_file.flush()
            ev_file.flush()
            if round(t) % CHECKPOINT_S == 0:
                say(f"{arm}: {t / 3600:.0f} h ({time.perf_counter() - wall:.0f} s wall)")
    writer_file.close()
    ev_file.close()
    say(f"{arm}: done")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("arms", nargs="+", choices=[*ARMS, *TREATED, "all"])
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument("--jobs", type=int, default=1, help="arms to run at once (separate processes)")
    ap.add_argument("--checkpoint-h", type=float, default=None, help=argparse.SUPPRESS)  # testing only
    ap.add_argument("--challenge-at-h", type=float, default=None, help=argparse.SUPPRESS)  # testing only
    a = ap.parse_args()
    set_test_timing(a.checkpoint_h, a.challenge_at_h)
    test_flags = [*(["--checkpoint-h", str(a.checkpoint_h)] if a.checkpoint_h else []),
                  *(["--challenge-at-h", str(a.challenge_at_h)] if a.challenge_at_h is not None else [])]
    arms = [*ARMS, *TREATED] if "all" in a.arms else a.arms
    root = Path(a.out).resolve()
    if a.jobs > 1 and len(arms) > 1:
        first = [x for x in arms if x not in TREATED]
        procs = [subprocess.Popen([sys.executable, __file__, x, "--out", str(root), "--hours", str(a.hours),
                                   *test_flags]) for x in first[: a.jobs]]
        pending = first[a.jobs:]
        while procs:
            procs = [p for p in procs if p.poll() is None]
            while pending and len(procs) < a.jobs:
                x = pending.pop(0)
                procs.append(subprocess.Popen([sys.executable, __file__, x, "--out", str(root), "--hours",
                                               str(a.hours), *test_flags]))
            time.sleep(5)
        branches = [x for x in arms if x in TREATED]
        procs = []
        while branches or procs:          # the treatment arms, once severe has its checkpoint
            procs = [p for p in procs if p.poll() is None]
            while branches and len(procs) < a.jobs:
                procs.append(subprocess.Popen([sys.executable, __file__, branches.pop(0), "--out", str(root),
                                               "--hours", str(a.hours), *test_flags]))
            time.sleep(5)
        return
    for arm in arms:
        run_arm(arm, root, a.hours)


if __name__ == "__main__":
    main()
