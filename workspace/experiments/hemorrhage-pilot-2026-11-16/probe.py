import json, sys, time
from process_bigraph import Composite, gather_emitter_results
from viva_biogears.core import build_core
from viva_biogears.composites.hemorrhage import biogears_hemorrhage, biogears_resuscitation
label, kind, kw = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
core = build_core()
gen = biogears_hemorrhage if kind == "hemorrhage" else biogears_resuscitation
t = time.time()
sim = Composite({"state": gen(core, **kw)}, core=core)
sim.run(600)
rows = gather_emitter_results(sim)[("emitter",)]
keys = ["mean_arterial_pressure_mmHg", "heart_rate_bpm", "blood_volume_mL", "total_blood_volume_lost_mL", "cardiac_output_L_per_min", "systolic_pressure_mmHg", "iv_rate_mL_per_min", "irreversible_state"]
series = {k: [r.get(k) for r in rows] for k in keys + ["time"]}
json.dump({"label": label, "kind": kind, "kw": kw, "wall_s": time.time() - t, "series": series}, open(sys.argv[4], "w"))
print(label, round(time.time()-t), "s", {k: series[k][-1] for k in keys}, flush=True)
