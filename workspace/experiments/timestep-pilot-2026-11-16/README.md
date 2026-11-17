# Time-step pilot (2026-11-16)

Pilot of every arm of the `biogears-timestep` investigation (`timestep-hemorrhage`,
`timestep-sepsis`), run before their criteria were written, plus the crash it found.

- `probe.py STUDY ARM OUT.json` runs one arm as the workbench does (the study's composite
  and parameters, an emitter of its readouts) and records the wall time; `run_all.sh`,
  `run_hemorrhage.sh` ran them (Linux, 2 cores, other BioGears runs alongside, so wall
  times are only comparable within a study). `out/` has every arm.
- `fake_runs_db.py STUDIES DEST` builds both studies' `runs.db` from `out/` in a copy of
  `workspace/studies`; the study tests pass on it (18 passed).

## Results

Hemorrhage (RightLeg, 200 mL/min, StandardMale@0s, 5 min at 1 s updates):

| step | MAP at 5 min | HR | blood volume | blood lost | largest per-sample deviation from 0.02 s (MAP / HR / BV) | wall |
|---|---|---|---|---|---|---|
| 0.02 s | 91.70 mmHg | 78.42 | 5179.3 mL | 362.6 mL | – | 35.9 s |
| 0.04 s | 91.31 | 78.32 | 5180.1 | 362.0 | 2.4 / 3.3 / 0.8 | 17.2 s |
| 0.08 s | 91.76 | 79.99 | 5182.6 | 360.6 | 5.3 / 6.3 / 3.3 | 9.6 s |

Severe infection (6 h at 60 s updates):

| step | lactate at 6 h | MAP | blood volume | blood pathogen | largest deviation (MAP / BV) | wall |
|---|---|---|---|---|---|---|
| 0.02 s | 1.53 mM | 99.75 mmHg | 5877 mL | 8.744 | – | 2459 s |
| 0.04 s | 10.28 | 99.63 | 5885 | 8.742 | 1.4 / 11 | 1313 s |
| 0.08 s | 26.1 | 99.70 | 5895 | 8.736 | 2.0 / 17 | 866 s |

- Volumes, hemodynamics and the inflammatory response barely depend on the step; lactate
  does not survive it (BioGears' own bg-scenario gave about 26 mM at 0.08 s too, Mac test
  `Fig4_Mild_6h_08`).
- Switching a 0.02 s state to a larger step gives a start-up transient (at 0.08 s, MAP
  95.9 → 90.5 mmHg and heart rate 72 → 66 in the first second, recovering within a minute).

## BioGears crashes with large steps during a hemorrhage

`crash_probe.py STEP RATE SECONDS` drives a pybiogears engine directly. With a RightLeg
bleed, BioGears aborts with heap corruption (`free(): invalid next size`, SIGABRT):

| step | rate | crash at |
|---|---|---|
| 0.08 s | 200 mL/min | 391 s |
| 0.08 s | 100 mL/min | about 891 s |
| 0.06 s | 200 mL/min | about 1740–1800 s |
| 0.04 s | 200 mL/min | none in 1800 s |
| 0.08 s | none | none in 600 s |

BioGears' own `bg-scenario` crashes at the same 391 s (`bg-scenario/HemDt008.xml`, from a
copy of StandardMale@0s with TimeStep 0.08; `HemDt008.log`), so it is BioGears, not
pybiogears or viva-biogears. Not investigated further (BioGears is not modified here); the
hemorrhage study runs 5 min for this reason.
