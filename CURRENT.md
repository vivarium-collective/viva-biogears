## Current session

**State (2026-11-03): phase 2 done.**
- Phase 1: `BioGearsProcess`, `MapFluidController`, `biogears_hemorrhage`, `biogears_resuscitation`.
- Phase 2: `BioGearsCircuitProcess` with `vitals`/`lymph`/`tissue_fluid` modules (`viva_biogears/circuits`), the shared `EngineBridge`, and `biogears_lymph`. 39 engine tests pass on Linux (cloud), including mutation checks of send-on-change and the oncotic-pressure sign. The Mac run is still to do.
- Lymph findings: the pool mass balance and Ohm's law on LymphToVenaCava hold to 0.1 % and 1e-9; saline at 200 mL/min drops lymph return from 3.2 to 0.4 mL/min in 5 min (return is passive, CVP-driven).
- Equilibration probe `workspace/experiments/equilibration-2026-11-03`: `StandardMale@0s` starts with 0.5 L of stomach water; after 5 h at rest with 150 mL water/h it is stationary, and without water it slowly dehydrates. That state ships as `viva_biogears/states/StandardMale@equilibrated.xml` (`biogears_lymph`'s default).
- The workspace was scaffolded with `viva-scaffold workspace --name biogears --target . --in-place --branch main --package viva_biogears` (viva-superpowers 0.24.0).

**Decided with the user:**
- D3 = both, vitals first. Phase 1: vitals plus hemorrhage and infusion. Phase 2: lymph and tissue-fluid modules. Phase 3: the McDaniel 2019 sepsis replication as a study.
- BioGears 8.2.0, unmodified (D1, D2).

**Next:**
1. The user sets up `.venv` on the Mac (README *Setup*) and runs the tests.
2. Phase 3: `workspace/studies/` for McDaniel 2019; its run and analysis scripts are in pybiogears `studies/mcdaniel2019`.
