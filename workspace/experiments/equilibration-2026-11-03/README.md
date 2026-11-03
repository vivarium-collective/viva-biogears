# Equilibration probe (2026-11-03)

**Question.** How long until BioGears' `StandardMale@0s` settles at rest, and does it need water intake to stay settled? pybiogears P5 found its lymph pool relaxing with τ ≈ 91 min, so lymph studies need a settled baseline.

**Method.** `equilibrate.py` advances `StandardMale@0s` 5 simulated hours at rest, under two conditions: `none`, and `water` (150 mL every hour from t = 0, via ConsumeNutrients). It samples every simulated minute to `out/<condition>.csv`. `analyze.py out` writes `out/summary.md`. About 1.5 h of wall time per run, with two runs on two cores.

**Results** (`out/summary.md`):
- The state starts with 0.5 L of water in the stomach. Absorbing it drives the early drift in both conditions: blood volume about +240 mL/h, lymph pool about +95 mL/h and MAP about +3 mmHg/h in the first hour. Most of this settles by about 120 min.
- `none` then dehydrates slowly. In the last hour, blood volume falls 15 mL/h, total body fluid falls 45 mL/h, and urine falls from 1.2 to 0.45 mL/min.
- `water` is stationary in the last hour. Blood volume drifts −2.6 mL/h, the lymph pool +6.8 mL/h, CVP, MAP and HR by less than 0.2 per hour, and urine holds at 0.97 mL/min. Blood volume swings by tens of mL within each hour, between drinks.

**Decision.** The `water` state at 300 min is shipped as `viva_biogears/states/StandardMale@equilibrated.xml`, the default for `biogears_lymph`. The 30-min checkpoints in `out/` are gitignored.
