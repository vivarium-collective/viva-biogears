"""Do BioGears 8.2.0 saved states continue a run, with active actions?

Runs 10 s with a hemorrhage, an infusion, intubation, the anesthesia machine, a thermal
application and an environment change, saves, then (a) continues 20 s, (b) reloads the
save and continues 20 s; compares vitals. Also: does reloading at a step boundary keep
time, and does resending a hemorrhage after reload restart the bleed?
"""
import os, sys
from pathlib import Path
import numpy as np
import pybiogears as pb
from viva_biogears.modules.cardiovascular import hemorrhage_xml, infusion_xml
from viva_biogears.modules.respiratory import anesthesia_machine_xml, intubation_xml, VENTILATOR_BASELINE
from viva_biogears.modules.thermal import (thermal_application_xml, environment_xml, THERMAL_APPLICATION_BASELINE,
                                            ENVIRONMENT_BASELINE)
RT = Path(os.environ["BIOGEARS_RUNTIME"]); OUT = Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
REQ = [pb.DataRequest("Physiology", p, u) for p, u in [("HeartRate", "1/min"), ("MeanArterialPressure", "mmHg"),
       ("BloodVolume", "mL"), ("TotalBloodVolumeLost", "mL"), ("TidalVolume", "mL"), ("SkinTemperature", "degC"),
       ("ArterialOxygenPressure", "mmHg"), ("CentralVenousPressure", "mmHg")]]
ACTIONS = [hemorrhage_xml("RightLeg", 100), infusion_xml("Saline", 10, 50), intubation_xml("Tracheal"),
           anesthesia_machine_xml("Tube", {**VENTILATOR_BASELINE, "connected": 1.0, "ventilator_pressure_cmH2O": 15.0,
                                           "oxygen_fraction": 0.4}),
           thermal_application_xml({**THERMAL_APPLICATION_BASELINE, "active_heating_W": 200.0}),
           environment_xml({**ENVIRONMENT_BASELINE, "ambient_temperature_C": 15.0})]

def eng(path):
    e = pb.BioGearsEngine(RT); e.set_requests(REQ); e.load_state(path); return e

a = eng(RT / "states" / "StandardMale@0s.xml"); a.process_actions(ACTIONS); a.advance_steps(500)
a.save_state(OUT / "mid@10s.xml"); t_save = a.sim_time_s
a.advance_steps(1000); full = a.pull()[1:]
b = eng(OUT / "mid@10s.xml"); t_load = b.sim_time_s; b.advance_steps(1000); branch = b.pull()[1:]
rel = np.abs(branch - full) / np.maximum(np.abs(full), 1e-12)
print("save time", t_save, "load time", t_load)
print("continued vs uninterrupted, max rel diff:", float(np.nanmax(rel)))
for r, x, y in zip(REQ, full, branch): print(f"  {r.property:24s} {x:12.6g} {y:12.6g}")
c = eng(OUT / "mid@10s.xml"); c.process_actions(hemorrhage_xml("RightLeg", 100)); c.advance_steps(1000)
print("resent hemorrhage after reload: blood lost", float(c.pull()[4]), "vs", float(full[3]))
