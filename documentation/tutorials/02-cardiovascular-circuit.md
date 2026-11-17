---
file_format: mystnb
kernelspec:
  name: python3
  display_name: Python 3
  language: python
---

# Tutorial 2: the cardiovascular circuit, beat by beat and node by node

```{include} _hosted.md
```

**What you will do:** sample the cardiovascular circuit at BioGears' own 0.02 s timestep to
see pressure waveforms, then bleed the patient and follow regional volumes and the flow in
single circuit paths.

**What you need:** {doc}`../installation`. About a minute of BioGears time.

## Waveforms at the engine's timestep

`biogears_cardiovascular` puts one `BioGearsModularProcess` with the `cardiovascular`
module on the standard store layout. With `point_reads=True` it also reads every node and
path of `FullCardiovascular`.

```{code-cell} python
from process_bigraph import Composite, gather_emitter_results

from viva_biogears.composites import biogears_cardiovascular
from viva_biogears.core import build_core


def run(seconds, **params):
    core = build_core()
    sim = Composite({"state": biogears_cardiovascular(core, **params)}, core=core)
    sim.run(seconds)
    return gather_emitter_results(sim)[("emitter",)]


beats = run(3.0, interval=0.02, point_reads=True)
central = [r["readings"]["cardiovascular"]["central"] for r in beats]
nodes = [r["readings"]["cardiovascular_points"]["nodes"] for r in beats]
len(beats), len(nodes[0]), len(beats[0]["readings"]["cardiovascular_points"]["paths"])
```

```{code-cell} python
import matplotlib.pyplot as plt

t = [r["time"] for r in beats]
fig, ax = plt.subplots(figsize=(7, 3.5))
ax.plot(t, [c["aorta"]["pressure_mmHg"] for c in central], label="aorta (compartment)", lw=2)
ax.plot(t, [c["left_ventricle"]["pressure_mmHg"] for c in central], label="left ventricle", lw=2)
ax.plot(t, [n["LeftVentricle1"]["pressure_mmHg"] for n in nodes], "--", label="node LeftVentricle1", lw=1)
ax.set_xlabel("Time (s)"); ax.set_ylabel("Pressure (mmHg)"); ax.legend(frameon=False); ax.grid(color="#e1e0d9")
fig.tight_layout()
```

At 1 s sampling these values would alias the heartbeat; the composite's `interval` sets the
sampling.

## A bleed, region by region

```{code-cell} python
bleed = run(300, hemorrhage_rate_mL_per_min=300.0)
first, last = bleed[0]["readings"]["cardiovascular"], bleed[-1]["readings"]["cardiovascular"]
print(f"{'region':16s}{'start (mL)':>12s}{'5 min (mL)':>12s}")
for group in ("central", "peripheral"):
    for name in ("aorta", "vena_cava", "right_leg", "muscle", "splanchnic", "liver"):
        if name in first[group]:
            print(f"{name:16s}{first[group][name]['volume_mL']:12.1f}{last[group][name]['volume_mL']:12.1f}")
h0, h1 = first["hemodynamics"], last["hemodynamics"]
print(f"\nMAP {h0['mean_arterial_pressure_mmHg']:.1f} -> {h1['mean_arterial_pressure_mmHg']:.1f} mmHg, "
      f"lost {h1['total_blood_volume_lost_mL']:.0f} mL")
```

The right leg loses volume first; venous reservoirs (the splanchnic bed, the liver) give up
blood as the body compensates.

## What to try next

- Read only some points: `point_reads=True` with `cardiovascular_point_nodes=["Aorta1"]`
  on a `BioGearsModularProcess`.
- Add an arteriovenous shunt with `circuit_additions` and read its flow among the points
  ({doc}`../concepts/modules`).
