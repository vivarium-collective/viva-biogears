"""Run the McDaniel et al. 2019 replication arms on viva-biogears' BioGearsCircuitProcess.

    python run.py ARM [ARM ...] [--out DIR] [--hours H] [--jobs N]
      ARM: control | mild | moderate | severe | challenge | all

Every arm is the ``biogears_sepsis`` composite's process (modules infection, nutrition,
lymph, tissue_fluid, cardiovascular; BioGears' InfectionModerate meal and water schedule),
driven update by update at 60 s:

- control, mild, moderate, severe: StandardMale@0s, infection severity 0/1/2/3 at t = 0
  (Skin, MIC 16 mg/L), 48 h (paper Figs 4-7);
- challenge: branches from severe's 44 h checkpoint; saline at 16.67 mL/min from 44.0 to
  45.0 h (two 500 mL boluses, each over 30 min), observed to 46 h (paper Fig 9).

Each arm writes OUT/<arm>/data.csv (one row per simulated minute; the columns analyze.py
reads), events.csv (BioGears' patient events) and log.txt, and saves a checkpoint every
4 simulated hours (OUT/<arm>/ckpt<start>@<t>s.xml, one name per segment of a resumed
run, since a state is never overwritten). An interrupted arm resumes from its last
checkpoint: the process reads the infection from the state, so the branch continues the
run (viva_biogears.states), and the meals before it are skipped.
"""
import argparse
import csv
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
CHALLENGE = (44 * 3600.0, 45 * 3600.0, 46 * 3600.0, 1000.0 / 60.0)  # start, stop, end, mL/min


def set_test_timing(checkpoint_h: float | None, challenge_at_h: float | None) -> None:
    """Shorter checkpoints and an earlier challenge, for checking the script quickly."""
    global CHECKPOINT_S, CHALLENGE
    if checkpoint_h:
        CHECKPOINT_S = checkpoint_h * 3600.0
    if challenge_at_h is not None:
        h = challenge_at_h * 3600.0
        CHALLENGE = (h, h + 3600.0, h + 7200.0, CHALLENGE[3])

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
}
LYMPH_TISSUES = {"Bone": "bone", "Brain": "brain", "Fat": "fat", "Gut": "gut", "LeftKidney": "left_kidney",
                 "LeftLung": "left_lung", "Liver": "liver", "Muscle": "muscle", "Myocardium": "myocardium",
                 "RightKidney": "right_kidney", "RightLung": "right_lung", "Skin": "skin", "Spleen": "spleen"}
COLUMNS.update({f"{t}Lymph": ("lymph", "formation", f"{k}_mL_per_min") for t, k in LYMPH_TISSUES.items()})


def _get(tree, path):
    for key in path:
        tree = tree[key]
    return tree


def process(arm: str, out: Path, state_file: str, save_times, name: str):
    from viva_biogears.composites import biogears_sepsis
    from viva_biogears.core import build_core
    from viva_biogears.processes import BioGearsCircuitProcess

    severity = "severe" if arm == "challenge" else {0.0: "none", 1.0: "mild", 2.0: "moderate", 3.0: "severe"}[ARMS[arm]]
    node = biogears_sepsis(None, severity=severity, state_file=state_file)["biogears"]
    config = {**node["config"], "save_state_times_s": list(save_times), "save_state_dir": str(out),
              "save_state_name": name}
    proc = BioGearsCircuitProcess(config, core=build_core())
    return proc, {"infection": {"infection_severity": 3.0 if arm == "challenge" else ARMS[arm]},
                  "cardiovascular": {"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0}}


def _seconds(path: Path) -> float:
    return float(path.stem.split("@")[1][:-1])


def checkpoints(out: Path):
    return sorted(out.glob("ckpt*@*s.xml"), key=_seconds)


def run_arm(arm: str, root: Path, hours: float) -> None:
    out = root / arm
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "log.txt", "a")
    say = lambda msg: (log.write(f"{time.ctime()} {msg}\n"), log.flush())  # noqa: E731
    end = CHALLENGE[2] if arm == "challenge" else hours * 3600.0
    saved = checkpoints(out)
    if saved:
        start_file, start = str(saved[-1]), _seconds(saved[-1])
    elif arm == "challenge":
        source = [p for p in checkpoints(root / "severe") if abs(_seconds(p) - CHALLENGE[0]) < 1]
        if not source:
            raise SystemExit("challenge needs severe's 44 h checkpoint: run severe first")
        start_file, start = str(source[0]), CHALLENGE[0]
    else:
        start_file, start = "StandardMale@0s.xml", 0.0
    if start >= end - 1:
        say(f"{arm}: already complete")
        return
    save_times = [t for t in [CHECKPOINT_S * k for k in range(1, 100)] if start < t <= end]
    proc, setpoints = process(arm, out, start_file, save_times, f"ckpt{round(start)}")
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
        reading = {**reading, "setpoint": setpoints["cardiovascular"]}
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
    t, wall = start, time.perf_counter()
    while t < end - 1e-6:
        if arm == "challenge":
            on = CHALLENGE[0] - 1e-6 <= t < CHALLENGE[1] - 1e-6
            setpoints["cardiovascular"]["iv_rate_mL_per_min"] = CHALLENGE[3] if on else 0.0
        reading = proc.update({"setpoints": setpoints}, STEP_S)
        t += STEP_S
        write_events()
        if reading.get("irreversible_state"):
            say(f"{arm}: irreversible state at {t / 3600:.2f} h")
            break
        write(t, reading)
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
    ap.add_argument("arms", nargs="+", choices=[*ARMS, "challenge", "all"])
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument("--jobs", type=int, default=1, help="arms to run at once (separate processes)")
    ap.add_argument("--checkpoint-h", type=float, default=None, help=argparse.SUPPRESS)  # testing only
    ap.add_argument("--challenge-at-h", type=float, default=None, help=argparse.SUPPRESS)  # testing only
    a = ap.parse_args()
    set_test_timing(a.checkpoint_h, a.challenge_at_h)
    arms = [*ARMS, "challenge"] if "all" in a.arms else a.arms
    root = Path(a.out).resolve()
    if a.jobs > 1 and len(arms) > 1:
        first = [x for x in arms if x != "challenge"]
        procs = [subprocess.Popen([sys.executable, __file__, x, "--out", str(root), "--hours", str(a.hours)])
                 for x in first[: a.jobs]]
        pending = first[a.jobs:]
        while procs:
            procs = [p for p in procs if p.poll() is None]
            while pending and len(procs) < a.jobs:
                x = pending.pop(0)
                procs.append(subprocess.Popen([sys.executable, __file__, x, "--out", str(root), "--hours",
                                               str(a.hours)]))
            time.sleep(5)
        if "challenge" in arms:
            run_arm("challenge", root, a.hours)
        return
    for arm in arms:
        run_arm(arm, root, a.hours)


if __name__ == "__main__":
    main()
