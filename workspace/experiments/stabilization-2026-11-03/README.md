# Stabilization probe (2026-11-03)

**Question.** How long does BioGears 8.2.0 take to stabilize a patient from its patient file, does the result match the shipped state, and do chronic conditions work through pybiogears?

**Method.** `stabilize_probe.py out`:
- stabilizes `patients/StandardMale.xml` twice, once plain and once with `ChronicAnemia` (ReductionFactor 0.3), using pybiogears `BioGearsEngine.initialize(patient, conditions)`;
- saves both states, reloads them and compares them with the shipped `states/StandardMale@0s.xml`.

Results are in `out/summary.json`; the states themselves are not kept.

**Results** (cloud container, one core):
- **Stabilization time:** 37 s plain, 70 s with chronic anemia. Reloading a saved state takes 0.2 s.
- **Plain StandardMale** matches the shipped state to about 1e-12: HR 72, MAP 95.89, blood volume 5532.36 mL. The shipped states were made by this build, and stabilization is deterministic.
- **Chronic anemia 30 %:**
  - Total hemoglobin falls from 846 to 592 g, exactly 30 %.
  - MAP is 88.3 mmHg instead of 95.9; cardiac output is 6.46 L/min instead of 5.78.
  - Hematocrit and red-cell count are unchanged: BioGears models the anemia through hemoglobin only.
  - The condition is saved in the state, so a reload keeps it.
- **pybiogears change needed:** conditions are passed as `<Condition xsi:type="…Data">` elements, read through a scenario's `<InitialParameters>`. A scenario must contain at least one action, so the template carries a 0 s AdvanceTime.

**Decision.** `viva_biogears.patients` stabilizes on first use and caches the result. The first run of a new patient costs 40–70 s; later runs cost a reload.
