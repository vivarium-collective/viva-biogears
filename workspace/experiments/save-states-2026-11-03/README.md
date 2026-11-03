# Save-states probe (2026-11-03)

**Question.** Does a BioGears 8.2.0 state saved mid-run reload and continue the run, with actions active? These actions were tested: a hemorrhage, an infusion, intubation, the anesthesia-machine ventilator, a thermal application and a changed environment.

**Method.** `probe.py out`:
1. From `StandardMale@0s`, apply all of the above, run 10 s and save.
2. Continue the uninterrupted engine 20 s.
3. Reload the save and continue it 20 s.
4. Compare eight vitals between the two.

`run.log` has the output.

**Findings.** Four BioGears 8.2.0 bugs broke this. They are fixed in pybiogears (commit 1066a39), not in BioGears:
1. **Saving with an equipment data request segfaults.** BioGears writes the data requests into the state. pybiogears now saves without the requests and reconnects them afterwards.
2. **A state saved with the anesthesia machine connected doesn't reload.** Its unused vaporizer chambers are written as `<State/>`, which BioGears' schema rejects. pybiogears drops empty `State` elements before loading; the element is optional.
3. **`TotalBloodVolumeLost` isn't saved and is reset to 0 on load.** A branch under-reported blood lost: 23.5 mL instead of 38.5 mL here. pybiogears keeps it in a comment of the saved file and restores it on load.
4. **A saved thermal application comes back with NaN parts.** This is the same unmarshalling bug as when the action is sent, and pybiogears prunes them after a load too.

**Results with the fixes.**
- The reloaded run matches the uninterrupted one to 1.6e-11 relative in every vital.
- Saved at t = 9.999999999999876 s, the state reloads at 9.99999999999988 s.
- Resending the same hemorrhage after a reload restarts the bleed: blood lost is 42.7 mL instead of 38.5 mL.

**Decision.** `viva_biogears.states` saves from processes and from the command line.
- A process loading a saved state reads each active action's values from the state (`ActionBinding.loaded`).
- Same setpoints send nothing, so the run continues exactly.
- Different setpoints send the change.
