---
file_format: mystnb
kernelspec:
  name: python3
  display_name: Python 3
  language: python
---

# Tutorial 4: every circuit on one engine

```{include} _hosted.md
```

**What you will do:** drive one `BioGearsModularProcess` directly, update by update, with
the cardiovascular, respiratory, ventilator, oxygen and thermal modules on one engine, and
change setpoints mid-run: a bleed, then a nasal cannula, then a cold room. Each
intervention shows up in circuits other than its own.

**What you need:** {doc}`../installation`. About two minutes of BioGears time.

## The process and its ports

```{code-cell} python
from viva_biogears.core import build_core
from viva_biogears.processes import BioGearsModularProcess

modules = ["cardiovascular", "respiratory", "mechanical_ventilator", "supplemental_oxygen", "thermal"]
p = BioGearsModularProcess({"modules": modules}, core=build_core())
state = p.initial_state()
setpoints = {name: {port: spec["_default"] for port, spec in ports.items()}
             for name, ports in p.inputs()["setpoints"].items()}
sorted(setpoints), len(setpoints["thermal"])
```

`inputs()["setpoints"]` holds each module's setpoints with their baselines; a composite would
keep these in `interventions/`. Here we change them between updates ourselves.

## Three interventions

```{code-cell} python
rows = []


def advance(seconds):
    for _ in range(seconds):
        rows.append(p.update({"setpoints": setpoints}, 1.0))


advance(30)
setpoints["cardiovascular"]["hemorrhage_rate_mL_per_min"] = 300.0
advance(90)
setpoints["cardiovascular"]["hemorrhage_rate_mL_per_min"] = 0.0
setpoints["supplemental_oxygen"]["oxygen_connected"] = 1.0
advance(90)
setpoints["thermal"]["ambient_temperature_C"] = 5.0
setpoints["thermal"]["mean_radiant_temperature_C"] = 5.0
advance(120)
len(rows)
```

The ventilator stays disconnected: BioGears allows one airway device at a time, and the
process would refuse connecting it while the cannula is on.

```{code-cell} python
import matplotlib.pyplot as plt

t = [i + 1 for i in range(len(rows))]
series = [
    (lambda r: r["cardiovascular"]["hemodynamics"]["mean_arterial_pressure_mmHg"], "MAP (mmHg)"),
    (lambda r: r["cardiovascular"]["hemodynamics"]["heart_rate_bpm"], "HR (1/min)"),
    (lambda r: r["supplemental_oxygen"]["oxygenation"]["arterial_oxygen_pressure_mmHg"], "PaO2 (mmHg)"),
    (lambda r: r["respiratory"]["mechanics"]["respiration_rate_bpm"], "RR (1/min)"),
    (lambda r: r["thermal"]["energy"]["skin_temperature_C"], "Skin T (C)"),
    (lambda r: r["thermal"]["heat_loss"]["skin_W"], "Skin heat loss (W)"),
]
fig, axes = plt.subplots(len(series), 1, figsize=(7, 10), sharex=True)
for ax, (get, label) in zip(axes, series):
    ax.plot(t, [get(r) for r in rows], color="#2a78d6", lw=2)
    ax.set_ylabel(label, fontsize=8)
    for x in (30, 120, 210):
        ax.axvline(x, color="#999", lw=0.8, ls="--")
    ax.grid(color="#e1e0d9")
axes[-1].set_xlabel("Time (s): bleed at 30, cannula at 120, cold room at 210")
fig.tight_layout()
```

The bleed lowers MAP and raises heart rate (cardiovascular); the cannula raises arterial
oxygen and the chemoreflex slows breathing (respiratory); the cold room raises skin heat loss
and cools the skin (thermal), with its own small effect on the circulation.

## What to try next

- Disconnect the cannula, wait one update, then connect the ventilator
  (`setpoints["mechanical_ventilator"]["connected"] = 1.0`, with `respiratory/intubated`).
- Add `cardiovascular_points` to `modules` to read single nodes and paths during the bleed.
