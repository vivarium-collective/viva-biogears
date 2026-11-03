## Current session

**State (2026-11-03): phase 1 done.**
- `BioGearsProcess`, `MapFluidController`, `biogears_hemorrhage` and `biogears_resuscitation` are in place.
- 28 engine tests pass on Linux (cloud), including a mutation check of the send-on-change rule. The Mac run is still to do.
- The workspace was scaffolded by the user with `viva-scaffold workspace --name biogears --target . --in-place --branch main --package viva_biogears` (viva-superpowers 0.24.0).

**Decided with the user:**
- D3 = both, vitals first. Phase 1: vitals plus hemorrhage and infusion. Phase 2: lymph and tissue-fluid modules. Phase 3: the McDaniel 2019 sepsis replication as a study.
- BioGears 8.2.0, unmodified (D1, D2).

**Next:**
1. The user sets up `.venv` on the Mac (README *Setup*) and runs the tests.
2. Phase 2: a circuit process with lymph and tissue-fluid outputs, read through pybiogears' `FluidPath`/`FluidNode` (lymph return, the 13 tissue lymph flows, the lymph pool, endothelial resistances, albumin); an equilibrated baseline state (4–5 h at rest, pybiogears P5); CVP reported alongside lymph.
3. Phase 3: `workspace/studies/` for McDaniel 2019; its run and analysis scripts are in pybiogears `studies/mcdaniel2019`.
