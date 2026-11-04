## Current session

**State (2026-11-03): viva-pulse parity done** (circuits, patients, saved states, circuit additions, documentation). Phase 3 started: sepsis modules and the McDaniel 2019 study (runs pending).
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
- **Saved states** (batch 3): `viva_biogears/states.py` (StateSaver, save_states, CLI); branching reads active actions from the state (`ActionBinding.loaded`), so same setpoints continue exactly. pybiogears 1066a39 fixes four BioGears save/load bugs. Probe: `workspace/experiments/save-states-2026-11-03`.
- **Circuit additions** (batch 4): `viva_biogears/circuits/additions.py`, a path plus its liquid link. Probe: `workspace/experiments/additions-2026-11-03`.
- **Documentation** (batch 5): `documentation/` with five executed tutorials; `make docs`; `.readthedocs.yaml`. Tutorial 3 shows BioGears' lymph return reversing under saline (no valve on the return path).
- **Phase 3 (sepsis)**: `infection` and `nutrition` modules (`circuits/sepsis.py`), timed actions (`CircuitModule.schedule`), `biogears_sepsis`, and `workspace/studies/mcdaniel-2019-sepsis` (run.py with checkpoint/resume, tested to 5e-8; analyze.py ported from pybiogears). The 48 h runs (~8 h wall per arm) are to run on the Mac.
- All engine tests pass on Linux (cloud). The Mac run is still to do; first reinstall pybiogears there (it now has the thermal, conditions and save/load fixes).

**Decided with the user:**
- D3 = both, vitals first. Phase 1: vitals plus hemorrhage and infusion. Phase 2: lymph and tissue-fluid modules. Phase 3: the McDaniel 2019 sepsis replication as a study.
- BioGears 8.2.0, unmodified (D1, D2).
- viva-pulse parity, circuits first. Then patients, saved states and branching, circuit additions, and the Sphinx docs.

**Next:**
1. Run the McDaniel arms on the Mac (`run.py all --jobs 4`), then `analyze.py`; compare with the paper's event timings.
2. If wanted: antibiotics (the paper's treatment arm) through a substance-infusion module.
