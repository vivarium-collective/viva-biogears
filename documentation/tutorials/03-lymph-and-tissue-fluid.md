---
file_format: mystnb
kernelspec:
  name: python3
  display_name: Python 3
  language: python
---

# Tutorial 3: lymph and tissue fluid under a fluid load

```{include} _hosted.md
```

**What you will do:** infuse saline into the equilibrated StandardMale and follow what
BioGears does with the fluid: capillary filtration into the tissues, lymph formation, the
lymph pool, and its return to the veins.

**What you need:** {doc}`../installation`. About three minutes of BioGears time.

## Rest and a saline load, side by side

`biogears_lymph` starts from `StandardMale@equilibrated.xml` (5 h at rest with hourly water;
`StandardMale@0s` still drifts for hours) and reads the `vitals`, `lymph`, `tissue_fluid` and
`cardiovascular` modules.

```{code-cell} python
from process_bigraph import Composite, gather_emitter_results

from viva_biogears.composites import biogears_lymph
from viva_biogears.core import build_core


def run(seconds, **params):
    core = build_core()
    sim = Composite({"state": biogears_lymph(core, **params)}, core=core)
    sim.run(seconds)
    return [r["readings"] | {"time": r["time"]} for r in gather_emitter_results(sim)[("emitter",)]]


rest = run(600)
load = run(600, iv_rate_mL_per_min=200.0)
end_rest, end_load = rest[-1], load[-1]


def get(row, path):
    for key in path:
        row = row[key]
    return row


for label, path in [("lymph return (mL/min)", ("lymph", "return_mL_per_min")),
                    ("CVP (mmHg)", ("lymph", "central_venous_pressure_mmHg")),
                    ("lymph pool (mL)", ("lymph", "pool_volume_mL")),
                    ("muscle filtration (mL/min)", ("tissue_fluid", "muscle", "filtration_mL_per_min")),
                    ("muscle extracellular (mL)", ("tissue_fluid", "muscle", "extracellular_volume_mL")),
                    ("plasma albumin (g/dL)", ("tissue_fluid", "plasma_albumin_g_per_dL"))]:
    print(f"{label:28s} start {get(rest[0], path):9.3f}   rest {get(end_rest, path):9.3f}   "
          f"saline {get(end_load, path):9.3f}")
```

Saline dilutes plasma albumin, so plasma oncotic pressure falls and capillary filtration
rises: the muscle's interstitial space swells. Lymph formation rises with it. But BioGears'
lymph returns through a passive resistance into the vena cava, and the infusion raises
venous pressure, so the return falls, and within minutes *reverses*: the return path has no
valve, so once vena cava pressure exceeds the pool's, fluid flows from the vena cava back
into the lymph pool. The pool fills from both ends. Keep this in mind when reading lymph
results under large fluid loads: real lymphatics have valves.

## The lymph pool's mass balance

The pool changes by what forms minus what returns. This holds on BioGears' own circuit, so
it checks the readings:

```{code-cell} python
import numpy as np

net = [sum(r["lymph"]["formation"].values()) - r["lymph"]["return_mL_per_min"] for r in load]
change = load[-1]["lymph"]["pool_volume_mL"] - load[0]["lymph"]["pool_volume_mL"]
print(f"pool change {change:.2f} mL; integral of formation - return {np.trapezoid(net, dx=1 / 60):.2f} mL")
```

## Plot the exchange

```{code-cell} python
import matplotlib.pyplot as plt

fig, axes = plt.subplots(3, 1, figsize=(7, 7), sharex=True)
panels = [(lambda r: r["lymph"]["return_mL_per_min"], "Lymph return (mL/min)"),
          (lambda r: sum(r["lymph"]["formation"].values()), "Lymph formation (mL/min)"),
          (lambda r: r["lymph"]["central_venous_pressure_mmHg"], "CVP (mmHg)")]
for ax, (get, label) in zip(axes, panels):
    for rows, name, color in ((rest, "rest", "#2a78d6"), (load, "saline 200 mL/min", "#eb6834")):
        ax.plot([r["time"] / 60 for r in rows], [get(r) for r in rows], color=color, label=name, lw=2)
    ax.set_ylabel(label); ax.grid(color="#e1e0d9")
axes[0].legend(frameon=False)
axes[-1].set_xlabel("Time (min)")
fig.tight_layout()
```

## What to try next

- Infuse albumin-containing fluid (`iv_compound="Blood_ONegative"`) and compare filtration.
- Start from a patient with chronic heart failure (`conditions={"ChronicHeartFailure": {...}}`)
  to raise venous pressure before the load.
- The McDaniel et al. 2019 sepsis study used this lymph model; its replication is planned as
  a workspace study.
