---
file_format: mystnb
kernelspec:
  name: python3
  display_name: Python 3
  language: python
---

# Tutorial 5: your own patient, and branching from a checkpoint

```{include} _hosted.md
```

**What you will do:** write a patient file BioGears ships no state for, let BioGears
stabilize it once, give it a chronic condition, then bleed it, save a checkpoint mid-bleed
and branch: continue, stop the bleed, or resuscitate.

**What you need:** {doc}`../installation`. About four minutes of BioGears time, two of them
stabilizing (only the first time: the states are cached).

## A patient file

```{code-cell} python
import re
import tempfile
from pathlib import Path

from viva_biogears.runtime import runtime_dir

work = Path(tempfile.mkdtemp())
xml = (runtime_dir() / "patients" / "StandardMale.xml").read_text()
xml = xml.replace("<Name>StandardMale</Name>", "<Name>TutorialPatient</Name>")
xml = re.sub(r'(<HeartRateBaseline [^>]*value=")[^"]+', r"\g<1>60", xml)
xml = re.sub(r'(<Weight [^>]*value=")[^"]+', r"\g<1>200", xml)
patient = work / "TutorialPatient.xml"
patient.write_text(xml)
```

## Stabilized once, then cached

```{code-cell} python
import time

from viva_biogears.core import build_core
from viva_biogears.processes import BioGearsProcess

core = build_core()
for label, config in [("StandardMale", {}), ("TutorialPatient", {"patient_file": str(patient)}),
                      ("TutorialPatient, chronic anemia 30 %",
                       {"patient_file": str(patient), "conditions": {"ChronicAnemia": {"ReductionFactor": 0.3}}})]:
    start = time.perf_counter()
    vitals = BioGearsProcess(config, core=core).initial_state()
    print(f"{label:38s} HR {vitals['heart_rate_bpm']:5.1f}  MAP {vitals['mean_arterial_pressure_mmHg']:5.1f}  "
          f"blood volume {vitals['blood_volume_mL']:6.0f} mL   ({time.perf_counter() - start:4.1f} s)")
```

Run the cell again and every patient loads in well under a second. The heavier patient has
more blood; the anemic one a lower MAP and a higher cardiac output at rest.

## A checkpoint mid-bleed

```{code-cell} python
from process_bigraph import Composite, gather_emitter_results

from viva_biogears.composites import biogears_hemorrhage, biogears_resuscitation


def run(generator, seconds, save=None, **params):
    document = generator(core, **params)
    if save:
        document["biogears"]["config"].update(save)
    sim = Composite({"state": document}, core=core)
    sim.run(seconds)
    return gather_emitter_results(sim)[("emitter",)]


bleed = dict(patient_file=str(patient), compartment="Aorta", rate_mL_per_min=400.0)
full = run(biogears_hemorrhage, 240, {"save_state_times_s": [120], "save_state_dir": str(work)}, **bleed)
checkpoint = work / "state@120s.xml"
checkpoint.name
```

## Three branches

A branch starts from the checkpoint like any state. Its setpoints start at the checkpoint's
own values (the bleed is active in it), so the same rate continues the run, 0 stops the
bleed, and a controller can take over.

```{code-cell} python
same = run(biogears_hemorrhage, 120, state_file=str(checkpoint), compartment="Aorta", rate_mL_per_min=400.0)
stopped = run(biogears_hemorrhage, 120, state_file=str(checkpoint), compartment="Aorta", rate_mL_per_min=0.0)
treated = run(biogears_resuscitation, 120, state_file=str(checkpoint), compartment="Aorta",
              rate_mL_per_min=400.0, target_map_mmHg=80.0, gain=40.0)
print(f"{'':12s}{'MAP':>8s}{'blood volume':>14s}{'lost':>8s}")
for label, rows in [("full run", full), ("continued", same), ("stopped", stopped), ("treated", treated)]:
    r = rows[-1]
    print(f"{label:12s}{r['mean_arterial_pressure_mmHg']:8.1f}{r['blood_volume_mL']:14.0f}"
          f"{r['total_blood_volume_lost_mL']:8.0f}")
print(f"\ncontinued vs full run, MAP: {abs(same[-1]['mean_arterial_pressure_mmHg'] - full[-1]['mean_arterial_pressure_mmHg']):.1e} mmHg")
```

The continued branch matches the uninterrupted run; the others diverge from it at the
checkpoint. Blood lost carries over from before the checkpoint (pybiogears restores it:
BioGears 8.2.0 doesn't save it).

## What to try next

- Save several checkpoints (`save_state_times_s=[60, 120, 180]`) and branch from each.
- Save from the command line: `python -m viva_biogears.states StandardMale@0s.xml --times 60 --out states/`.
