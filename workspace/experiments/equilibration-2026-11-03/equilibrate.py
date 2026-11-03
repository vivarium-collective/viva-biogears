"""Equilibration probe: how long until StandardMale@0s settles at rest, with and without water?

    python equilibrate.py CONDITION OUTDIR [--hours 5]
      CONDITION: none  | water (150 mL every hour, as BioGears' long scenarios)

pybiogears probe P5 found StandardMale@0s drifting at rest for hours (lymph pool
tau ~ 91 min, blood volume +230 mL in 2 h), so lymph studies need a settled
baseline. Samples every simulated minute to OUTDIR/<condition>.csv; saves
OUTDIR/<condition>@<h>h.xml every 30 simulated minutes and resumes from the last.
"""
import argparse
import csv
import os
import time
from pathlib import Path

import pybiogears as pb

TISSUES = ["Bone", "Brain", "Fat", "Gut", "LeftKidney", "LeftLung", "Liver", "Muscle",
           "Myocardium", "RightKidney", "RightLung", "Skin", "Spleen"]
REQ = ([("LymphPool", pb.DataRequest("FluidNode", "Volume", "mL", "Lymph")),
        ("LymphReturn", pb.DataRequest("FluidPath", "Flow", "mL/min", "LymphToVenaCava")),
        ("CVP", pb.DataRequest("Physiology", "CentralVenousPressure", "mmHg")),
        ("BloodVolume", pb.DataRequest("Physiology", "BloodVolume", "mL")),
        ("ExtravascularFluid", pb.DataRequest("Physiology", "ExtravascularFluidVolume", "mL")),
        ("IntracellularFluid", pb.DataRequest("Physiology", "IntracellularFluidVolume", "mL")),
        ("TotalBodyFluid", pb.DataRequest("Physiology", "TotalBodyFluidVolume", "mL")),
        ("UrineRate", pb.DataRequest("Physiology", "UrineProductionRate", "mL/min")),
        ("MAP", pb.DataRequest("Physiology", "MeanArterialPressure", "mmHg")),
        ("HR", pb.DataRequest("Physiology", "HeartRate", "1/min")),
        ("Albumin", pb.DataRequest("LiquidCompartment", "Concentration", "g/dL", "Aorta", "Albumin")),
        ("CoreTemperature", pb.DataRequest("Physiology", "CoreTemperature", "degC"))]
       + [(f"{t}Lymph", pb.DataRequest("FluidPath", "Flow", "mL/min", f"{t}ToLymphValve")) for t in TISSUES])
STEPS_PER_MIN = 3000
CKPT_MIN = 30
WATER = ('<Action xsi:type="ConsumeNutrientsData"><Nutrition><Name>Water</Name>'
         '<Water value="0.15" unit="L"/></Nutrition></Action>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("condition", choices=["none", "water"])
    ap.add_argument("out")
    ap.add_argument("--hours", type=float, default=5.0)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rt = Path(os.environ["BIOGEARS_RUNTIME"])
    eng = pb.BioGearsEngine(rt)
    eng.set_requests([r for _, r in REQ])
    ckpts = sorted(out.glob(f"{a.condition}@*min.xml"), key=lambda p: int(p.stem.split("@")[1][:-3]))
    data = out / f"{a.condition}.csv"
    if ckpts:
        eng.load_state(ckpts[-1])
        minute = int(ckpts[-1].stem.split("@")[1][:-3])
        rows = list(csv.reader(open(data)))
        rows = [rows[0]] + [r for r in rows[1:] if float(r[0]) <= minute + 1e-9]
        csv.writer(open(data, "w", newline="")).writerows(rows)
        f = open(data, "a", newline="")
        w = csv.writer(f)
    else:
        eng.load_state(rt / "states" / "StandardMale@0s.xml")
        minute = 0
        f = open(data, "w", newline="")
        w = csv.writer(f)
        w.writerow(["t_min"] + [n for n, _ in REQ])
        w.writerow([0] + [repr(float(x)) for x in eng.pull()[1:]])
    assert not eng.unconnected, eng.unconnected
    t0 = time.perf_counter()
    end = int(round(a.hours * 60))
    while minute < end:
        if a.condition == "water" and minute % 60 == 0:
            eng.process_actions(WATER)  # at t = 0, 60, 120, ... min
        eng.advance_steps(STEPS_PER_MIN)
        minute += 1
        w.writerow([minute] + [repr(float(x)) for x in eng.pull()[1:]])
        if minute % CKPT_MIN == 0:
            f.flush()
            eng.save_state(out / f"{a.condition}@{minute}min.xml")
            print(f"{time.ctime()} {a.condition} {minute} min ({time.perf_counter() - t0:.0f} s wall)", flush=True)
    f.close()


if __name__ == "__main__":
    main()
