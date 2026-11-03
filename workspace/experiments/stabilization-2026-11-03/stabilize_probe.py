"""How long does BioGears 8.2.0 take to stabilize a patient, and does the result match its shipped state?

    python stabilize_probe.py OUTDIR
Stabilizes StandardMale (plain) and StandardMale with ChronicAnemia 30 %, saves both
states, and compares vitals after loading with the shipped StandardMale@0s.xml.
"""
import json, os, sys, time
from pathlib import Path
import pybiogears as pb

RT = Path(os.environ["BIOGEARS_RUNTIME"])
OUT = Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
REQ = [pb.DataRequest("Physiology", p, u) for p, u in [("HeartRate", "1/min"), ("MeanArterialPressure", "mmHg"),
       ("BloodVolume", "mL"), ("Hematocrit", ""), ("CardiacOutput", "L/min"), ("RespirationRate", "1/min"),
       ("OxygenSaturation", ""), ("CoreTemperature", "degC")]]
NAMES = ["HR", "MAP", "BV", "Hct", "CO", "RR", "SpO2", "Tcore"]
ANEMIA = '<Condition xsi:type="ChronicAnemiaData"><ReductionFactor value="0.3"/></Condition>'
res = {}
for tag, cond in [("plain", ""), ("anemia30", ANEMIA)]:
    e = pb.BioGearsEngine(RT)
    e.set_requests(REQ)
    t = time.perf_counter()
    e.initialize(str(RT / "patients" / "StandardMale.xml"), cond)
    dt = time.perf_counter() - t
    print(tag, "stabilized in", round(dt), "s", flush=True)
    e.save_state(OUT / f"StandardMale-{tag}@0s.xml")
    res[tag] = {"seconds": dt, "sim_time_s": e.sim_time_s, **dict(zip(NAMES, map(float, e.pull()[1:])))}
    print(tag, res[tag], flush=True)
e = pb.BioGearsEngine(RT); e.set_requests(REQ); e.load_state(RT / "states" / "StandardMale@0s.xml")
res["shipped"] = dict(zip(NAMES, map(float, e.pull()[1:])))
for tag in ("plain", "anemia30"):
    e = pb.BioGearsEngine(RT); e.set_requests(REQ); t = time.perf_counter(); e.load_state(OUT / f"StandardMale-{tag}@0s.xml")
    res[tag]["reload_seconds"] = time.perf_counter() - t
    res[tag]["reloaded"] = dict(zip(NAMES, map(float, e.pull()[1:])))
json.dump(res, open(OUT / "summary.json", "w"), indent=1)
print(json.dumps(res, indent=1))
