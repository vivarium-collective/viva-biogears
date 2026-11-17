# Shipped BioGears states

## `StandardMale@equilibrated.xml`

BioGears' `StandardMale@0s.xml` is not at fluid steady state: it starts with 0.5 L of water in the stomach, and the lymph pool, blood volume and urine output drift for about two hours (pybiogears probe P5). This state is `StandardMale@0s` advanced 5 simulated hours at rest with 150 mL of water every hour (the first at t = 0, the last at 240 min), saved 60 min after the last drink. Engine time inside the state is 300 min.

Over the last hour of that run (`workspace/experiments/equilibration-2026-11-03`):

| quantity | value at save | drift per hour |
|---|---|---|
| blood volume | 5880 mL | −2.6 mL (it swings by tens of mL within each hour, between drinks) |
| lymph pool | 2208 mL | +6.8 mL |
| lymph return | 3.85 mL/min | +0.06 |
| CVP | 4.19 mmHg | −0.004 |
| MAP | 100.4 mmHg | +0.01 |
| heart rate | 67.9 /min | +0.12 |
| plasma albumin | 4.24 g/dL | +0.008 |
| urine | 0.97 mL/min | +0.04 |

It is equilibrated under that hourly intake. Without intake it slowly dehydrates, as `StandardMale@0s` does after its stomach water is absorbed: blood volume about −15 mL/h, total body fluid about −45 mL/h.

`state_file = "StandardMale@equilibrated.xml"` finds it (after `<runtime>/states`); `viva_biogears.runtime.EQUILIBRATED_STATE` names it.

## `StandardMale@severe-infection-44h.xml`

The untreated severe infection of McDaniel et al. 2019 at 44 h: `StandardMale@0s`, a
severe Skin infection (MIC 16 mg/L) from t = 0 and BioGears' InfectionModerate water and
meal schedule, run by `workspace/studies/mcdaniel-2019-sepsis/run.py severe` (the
`biogears_sepsis` modules at 60 s updates) and saved at 44 h. Engine time inside the state
is 158399.999994 s (BioGears' clock runs a few µs behind after hours).

The paper started every treatment from states saved during its untreated severe infection ("All treatment
scenarios were conducted using virtual patient states generated from the nominal BioGears
severe infection action"); the `mcdaniel-2019-treatment` and `mcdaniel-2019-refresh`
studies start from it, as does `run.py` when it has no severe checkpoint of its own.
`biogears_sepsis(state_file="StandardMale@severe-infection-44h.xml", treatment=...)` keeps
the protocol on engine time, so a 44 h challenge starts on the first update.

At save: MAP 74.9 mmHg, SBP 85.6 mmHg, heart rate 109/min,
blood volume 4040 mL (5532 at t = 0), lactate 2.28 mM,
mean urine output 1.18 mL/min, blood pathogen 47.5,
tissue integrity 0.349. In this run lactate first stayed above 2 mM
at 16.3 h and SBP below 100 mmHg at 26.6 h (bg-scenario on the Mac: 16.5 and 26.8 h).

