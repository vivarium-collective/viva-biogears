"""Probe BioGears 8.2.0's circuits: which data requests connect,
and how airway devices, intubation, environment and thermal actions behave."""
import json, math, os, sys
from pathlib import Path
import pybiogears as pb

RT = Path(os.environ["BIOGEARS_RUNTIME"])
# BioGears' source tree (for its data-request names): $BIOGEARS_SRC, else where pybiogears'
# install_biogears.sh clones it.
SRC = (Path(os.environ.get("BIOGEARS_SRC", "~/biogears-8.2.0-build/src")).expanduser()
       / "projects/biogears/libBiogears/src/cdm/system/physiology")
import re
def ids(name):
    return re.findall(r'constexpr char id\w*\[\] = "(\w+)"', (SRC / f"{name}.cpp").read_text())

def engine(reqs, state="StandardMale@0s.xml"):
    e = pb.BioGearsEngine(RT)
    e.set_requests([pb.DataRequest(*r) for r in reqs])
    e.load_state(RT / "states" / state)
    return e

def connectivity():
    out = {}
    for sysname in ["SECardiovascularSystem", "SERespiratorySystem", "SEEnergySystem",
                    "SEBloodChemistrySystem", "SETissueSystem", "SERenalSystem"]:
        reqs = [("Physiology", p, "") for p in ids(sysname)]
        e = engine(reqs)
        e.advance(2.0)
        v = e.pull()[1:]
        unc = {(r.property) for r in e.unconnected}
        out[sysname] = {r[1]: (None if r[1] in unc else float(x)) for r, x in zip(reqs, v)}
    return out

if __name__ == "__main__":
    json.dump(connectivity(), open("physiology.json", "w"), indent=1, default=str)
