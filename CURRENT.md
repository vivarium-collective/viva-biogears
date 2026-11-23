## Current session

**State (2026-11-21): patient and substance tables** (branch `feat/patient-tables`; needs pybiogears `main` from 2026-11-21, PRs #2 and #3).
- `patient_table` + `patient`, `substance_table` on every process and composite (`viva_biogears/tables.py`); BioGears' patient check before any run (refused raises, adjusted warns, report next to the cached state). Tests: `tests/test_tables.py` (two engine tests, about 1 min).
- Next: a cohort study from one Patients.csv (its own branch).

**State (2026-11-16): workbench studies authored and piloted; canonical runs pending** (to be launched from the workbench on the Mac).
- **Treatment** (2026-11-16): `treatment` module (`readings/treatment.py`: timed compound/substance infusions, norepinephrine setpoint, drug readouts), `viva_biogears/protocols.py` (McDaniel 2019's challenge, antibiotic and REFRESH protocols, tested without the engine), `TreatmentController`, and `biogears_sepsis(treatment=...)`. Every sepsis run records `protocol/code` and `protocol/saline_given_mL`.
- **Workbench studies** (2026-11-16), each with pre-registered tests and a figure (`viva_biogears/visualizations/`):
  - investigation `biogears-hemorrhage`: `hemorrhage-severity-sweep` (rates 0–250 mL/min), `fluid-resuscitation` (Saline vs Blood_ONegative), `patient-cohort` (17 shipped states). Every arm was piloted (600 s each) and the study tests pass on runs.db files built from the pilot. Findings: every bleed leaves the 2 mmHg MAP band, loss saturates with rate, and loss tracks resting cardiac output.
  - investigation `mcdaniel-2019`: `mcdaniel-2019-sepsis` (Figs 4–7; thresholds from the 2026-11-14 bg-scenario runs), `mcdaniel-2019-treatment` (Figs 9–10), `mcdaniel-2019-refresh` (Figs 11–13). The treatment arms start from the severe arm's 44 h state (`viva_biogears/states/StandardMale@severe-infection-44h.xml`), as the paper did; `biogears_sepsis` keeps engine time for the protocol (`TreatmentController.time_offset_s`, `protocol/branch_h`), and the figure plots hours since treatment start. `run.py` runs all arms; `analyze.py` draws Figs 4–13 (10–13 in hours since treatment start, as the paper).
  - `workspace/studies/conftest.py` checks the irreversible latch at `vitals.` or `readings.irreversible_state`. The tests use vivarium-workbench 0.4.1's `Run` (time = global_time), the Mac's pinned version.
- **Renames** (2026-11-17): `BioGearsCircuitProcess` → `BioGearsModularProcess` (it runs the whole engine; the old name is a deprecated subclass, so `local:BioGearsCircuitProcess` documents still run); package `viva_biogears.circuits` → `viva_biogears.modules` (the old import path still works and warns); store `circuits/<module>` → `readings/<module>` in every composite, study, test and doc; `biogears_whole_body_circuits` → `biogears_whole_body` (old name kept as an alias). Module class `CircuitModule` → `Module` (old name still importable, warns). `tests/test_renames.py` checks the aliases.
- **Time step** (2026-11-16): `time_step_s` on every process (pybiogears' configuration override at load) and on `biogears_hemorrhage`/`biogears_resuscitation`/`biogears_sepsis`; investigation `biogears-timestep` (`timestep-hemorrhage`, 5 min; `timestep-sepsis`, 6 h), piloted. Lactate breaks at 0.04 and 0.08 s; BioGears aborts (heap corruption, also in bg-scenario) at 0.08 s about 391 s into a 200 mL/min bleed and at 0.06 s about 29 min in.
- **StateSaver** now counts a time as reached within 10 µs: BioGears' clock ran 1 µs behind ("43199.999999 s"), so 12 h checkpoints were saved one update (60 s) late.
- **BioGears finding**: an engine created while another engine in the same Python process has already advanced can differ by ~5e-6 once drugs are infused; engines created first, or after the others are deleted, agree exactly (tests/test_treatment.py). Not isolated further.

**State (2026-11-03): core features done** (circuits, patients, saved states, circuit additions, documentation). Phase 3 started: sepsis modules and the McDaniel 2019 study (runs pending).
- Phase 1: `BioGearsProcess`, `MapFluidController`, `biogears_hemorrhage`, `biogears_resuscitation`.
- Phase 2: `lymph` and `tissue_fluid` modules, `biogears_lymph`, and the equilibrated baseline `viva_biogears/states/StandardMale@equilibrated.xml`.
- **Batch 1 (circuits).**
  - `viva_biogears/modules/` now has one file per family: cardiovascular, respiratory and mechanical ventilator, thermal, supplemental oxygen, points, substances and tissues.
  - `BioGearsModularProcess` takes setpoints under `setpoints/<module>`.
  - The per-circuit composites and `biogears_whole_body` share one store layout.
  - What BioGears can and can't do is recorded in `workspace/experiments/circuits-probe-2026-11-03`:
    - it has no circuit multipliers;
    - its ventilator is the anesthesia machine;
    - its oxygen device is a nasal cannula;
    - its thermal application needs pybiogears' `prune_thermal_application` (pybiogears commit de52065).
- **Patients** (batch 2): `patient_file` and chronic `conditions` on every process and composite, stabilized once (40–70 s) and cached (`viva_biogears/patients.py`; pybiogears 3cdba22 adds conditions to `initialize`). Probe: `workspace/experiments/stabilization-2026-11-03`.
- **Saved states** (batch 3): `viva_biogears/states.py` (StateSaver, save_states, CLI); branching reads active actions from the state (`ActionBinding.loaded`), so same setpoints continue exactly. pybiogears 1066a39 fixes four BioGears save/load bugs. Probe: `workspace/experiments/save-states-2026-11-03`.
- **Circuit additions** (batch 4): `viva_biogears/modules/additions.py`, a path plus its liquid link. Probe: `workspace/experiments/additions-2026-11-03`.
- **Documentation** (batch 5): `documentation/` with five executed tutorials; `make docs`; `.readthedocs.yaml`. Tutorial 3 shows BioGears' lymph return reversing under saline (no valve on the return path).
- **Phase 3 (sepsis)**: `infection` and `nutrition` modules (`modules/sepsis.py`), timed actions (`Module.schedule`), `biogears_sepsis`, and `workspace/studies/mcdaniel-2019-sepsis` (run.py with checkpoint/resume, tested to 5e-8; analyze.py ported from pybiogears). The 48 h runs (~8 h wall per arm) are to run on the Mac.
- All engine tests pass on Linux (cloud). The Mac run is still to do; first reinstall pybiogears there (it now has the thermal, conditions and save/load fixes).

**Decided with the user:**
- D3 = both, vitals first. Phase 1: vitals plus hemorrhage and infusion. Phase 2: lymph and tissue-fluid modules. Phase 3: the McDaniel 2019 sepsis replication as a study.
- BioGears 8.2.0, unmodified (D1, D2).
- Circuits first. Then patients, saved states and branching, circuit additions, and the Sphinx docs.

**Next:**
1. Launch the hemorrhage studies from the workbench (minutes) and run their tests.
2. Launch the McDaniel studies (or `run.py all --jobs 4`, then `analyze.py`); the treatment studies' criteria were not piloted, so expect to learn from the first runs.
