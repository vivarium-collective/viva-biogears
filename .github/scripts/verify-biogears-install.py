"""Check a BioGears install before CI caches it or runs the suite against it.

    python verify-biogears-install.py RUNTIME_DIR

A cached install that loads but can't run would turn every engine test into a
confusing failure, so this proves the install the way the suite uses it: every
shipped state loads through pybiogears, and StandardMale advances 10 s to
physiological vitals.
"""
import math
import sys
from pathlib import Path

import pybiogears as pb

runtime = Path(sys.argv[1])
states = sorted((runtime / "states").glob("*@0s.xml"))
if len(states) < 19:
    raise SystemExit(f"expected BioGears 8.2.0's 19 shipped states in {runtime}/states, found {len(states)}")

requests = [pb.DataRequest("Physiology", "HeartRate", "1/min"),
            pb.DataRequest("Physiology", "MeanArterialPressure", "mmHg")]
for state in states:
    engine = pb.BioGearsEngine(runtime)
    engine.set_requests(requests)
    engine.load_state(state)

engine = pb.BioGearsEngine(runtime)
engine.set_requests(requests)
engine.load_state(runtime / "states" / "StandardMale@0s.xml")
engine.advance(10.0)
vitals = engine.pull_dict()
hr, map_ = vitals["HeartRate(1/min)"], vitals["MeanArterialPressure(mmHg)"]
if not (math.isfinite(hr) and 50 < hr < 100 and math.isfinite(map_) and 70 < map_ < 110):
    raise SystemExit(f"StandardMale after 10 s is not physiological: {vitals}")
print(f"{len(states)} states load; StandardMale after 10 s: HR {hr:.1f}/min, MAP {map_:.1f} mmHg")
