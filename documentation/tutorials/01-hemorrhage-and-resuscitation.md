---
file_format: mystnb
kernelspec:
  name: python3
  display_name: Python 3
  language: python
---

# Tutorial 1: a hemorrhage, untreated and resuscitated

```{include} _hosted.md
```

**What you will do:** bleed the StandardMale patient from the aorta for ten minutes, once
untreated and once with a closed-loop controller that infuses saline whenever mean arterial
pressure falls below 90 mmHg, then compare the vital signs.

**What you need:** the installation from {doc}`../installation`. This tutorial runs about
three minutes of real BioGears time.

## Build and run the two composites

`biogears_hemorrhage` wires one `BioGearsProcess` to an `interventions` store (the
setpoints) and a `vitals` store (the readings). `biogears_resuscitation` adds a
`MapFluidController` step that reads `vitals/mean_arterial_pressure_mmHg` and writes
`interventions/iv_rate_mL_per_min`.

```{code-cell} python
from process_bigraph import Composite, gather_emitter_results

from viva_biogears.composites import biogears_hemorrhage, biogears_resuscitation
from viva_biogears.core import build_core


def run(generator, seconds, **params):
    core = build_core()  # registers viva-biogears' processes on a fresh core
    sim = Composite({"state": generator(core, **params)}, core=core)
    sim.run(seconds)
    return gather_emitter_results(sim)[("emitter",)]


bleed = dict(compartment="Aorta", rate_mL_per_min=500.0)
untreated = run(biogears_hemorrhage, 600, **bleed)
treated = run(biogears_resuscitation, 600, target_map_mmHg=90.0, **bleed)
len(untreated), len(treated)
```

Each run emits one row per simulated second, plus the first row at t = 0.

## Compare the end of the two runs

```{code-cell} python
keys = ["mean_arterial_pressure_mmHg", "heart_rate_bpm", "blood_volume_mL", "total_blood_volume_lost_mL"]
print(f"{'':30s}{'start':>10s}{'untreated':>12s}{'treated':>10s}")
for key in keys:
    print(f"{key:30s}{untreated[0][key]:10.1f}{untreated[-1][key]:12.1f}{treated[-1][key]:10.1f}")
infused = sum(row["iv_rate_mL_per_min"] for row in treated[:-1]) / 60.0
first = next((row["time"] for row in treated if row["iv_rate_mL_per_min"] > 0), None)
print(f"\ncontroller first infuses at t = {first:.0f} s and delivers {infused:.0f} mL")
```

`total_blood_volume_lost_mL` is NaN at t = 0: BioGears creates the value with the first bleed.
BioGears' bleed rate is an *initial* rate: it falls with the local pressure, so the bleed
slows as the patient becomes hypotensive. The controller starts infusing once MAP drops
below its target, and ends the run with more blood volume and a higher MAP, though it also
bleeds more: the higher pressure drives more blood out of the aortic wound.

## Plot the vital signs over time

```{code-cell} python
import matplotlib.pyplot as plt

fig, axes = plt.subplots(3, 1, figsize=(7, 7), sharex=True)
panels = [("mean_arterial_pressure_mmHg", "MAP (mmHg)"),
          ("blood_volume_mL", "Blood volume (mL)"),
          ("iv_rate_mL_per_min", "Infusion (mL/min)")]
for ax, (key, label) in zip(axes, panels):
    for rows, name, color in ((untreated, "untreated", "#2a78d6"), (treated, "MAP-targeted saline", "#eb6834")):
        ax.plot([r["time"] / 60 for r in rows], [r[key] for r in rows], color=color, label=name, lw=2)
    ax.set_ylabel(label)
    ax.grid(color="#e1e0d9")
axes[0].legend(frameon=False)
axes[-1].set_xlabel("Time (min)")
fig.suptitle("Aortic hemorrhage, 500 mL/min initial rate, StandardMale")
fig.tight_layout()
```

## What to try next

- Change `rate_mL_per_min` or the site (`compartment`, for example `"RightLeg"`). A large
  aortic bleed reaches BioGears' irreversible state; the `irreversible_state` column turns
  `True` and the vitals stop changing.
- Set `compound="Blood_ONegative"` to infuse blood, or raise `gain`.
- Start from another patient: `state_file="Female_30_Normal@0s.xml"`, or any patient file
  with `patient_file` ({doc}`05-patients-and-checkpoints`).
