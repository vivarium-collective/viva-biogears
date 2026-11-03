## Current session

**State (2026-11-03): viva-pulse parity, circuits and patients batches done.**
- Phase 1: `BioGearsProcess`, `MapFluidController`, `biogears_hemorrhage`, `biogears_resuscitation`.
- Phase 2: `lymph` and `tissue_fluid` modules, `biogears_lymph`, and the equilibrated baseline `viva_biogears/states/StandardMale@equilibrated.xml`.
- **viva-pulse parity, batch 1 (circuits).**
  - `viva_biogears/circuits/` now has one file per family, following viva-pulse: cardiovascular, respiratory and mechanical ventilator, thermal, supplemental oxygen, points, substances and tissues.
  - `BioGearsCircuitProcess` takes setpoints under `setpoints/<module>`.
  - The per-circuit composites and `biogears_whole_body_circuits` use viva-pulse's store layout.
  - What BioGears can and can't do is recorded in `workspace/experiments/circuits-probe-2026-11-03`:
    - it has no circuit multipliers;
    - its ventilator is the anesthesia machine;
    - its oxygen device is a nasal cannula;
    - its thermal application needs pybiogears' `prune_thermal_application` (pybiogears commit de52065).
- **Patients** (batch 2): `patient_file` and chronic `conditions` on every process and composite, stabilized once (40–70 s) and cached (`viva_biogears/patients.py`; pybiogears 3cdba22 adds conditions to `initialize`). Probe: `workspace/experiments/stabilization-2026-11-03`.
- All engine tests pass on Linux (cloud). The Mac run is still to do; first reinstall pybiogears there (it now has the thermal fix and conditions).

**Decided with the user:**
- D3 = both, vitals first. Phase 1: vitals plus hemorrhage and infusion. Phase 2: lymph and tissue-fluid modules. Phase 3: the McDaniel 2019 sepsis replication as a study.
- BioGears 8.2.0, unmodified (D1, D2).
- viva-pulse parity, circuits first. Then patients, saved states and branching, circuit additions, and the Sphinx docs.

**Next:**
1. Saved states: a `StateSaver` (`save_state_times_s`), branching from a saved state, and handling of mid-run active actions (viva-pulse `states.py` and `_loaded_controls`). The thermal application's NaN parts also affect saved states, so check that case.
2. Circuit additions (viva-pulse `circuits/additions.py`), then `documentation/` with the tutorials.
3. Phase 3: McDaniel 2019 in `workspace/studies/`.
