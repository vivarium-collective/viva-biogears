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
