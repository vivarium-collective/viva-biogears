# Processes

viva-biogears has two processes that drive BioGears, and a controller step.

## `BioGearsProcess`

Vital signs plus a hemorrhage and an IV infusion: the simplest bridge.

- **Inputs** `hemorrhage_rate_mL_per_min` and `iv_rate_mL_per_min`, setpoints sent to
  BioGears only when they change: resending a hemorrhage restarts BioGears' bleed. 0 stops
  the action.
- **Outputs**: ten vital signs as `overwrite[float]`, seeded by `initial_state()` with the
  loaded state's readings, so each store always equals BioGears' own value; and the
  `irreversible_state` latch, after which the engine is not advanced.
- **Config**: `hemorrhage_compartment` (one of the 18 with a BioGears bleed path),
  `iv_compound` (a BioGears compound such as `Saline` or `Blood_ONegative`),
  `iv_bag_volume_L`, and the start and save settings below.

BioGears' hemorrhage is an initial rate in mL/min, which BioGears then lowers with the local
pressure. A rate above cardiac output is refused by BioGears on every step; the process
raises instead.

## `BioGearsCircuitProcess`

One BioGears engine exposing the circuit modules listed in `modules`
({doc}`circuits`). Readings nest under each module's name; setpoints sit under one
`setpoints` input port (`setpoints/cardiovascular/hemorrhage_rate_mL_per_min`). The
input and output top-level names are disjoint on purpose: process-bigraph projects
`initial_state()` through both, so a shared name would copy readings into setpoints.
Changed setpoint groups are validated before any action is sent, and BioGears' one airway
device rule is checked: at most one of the ventilator and the cannula connected, and not
swapped within one update.

## `MapFluidController`

A step setting `iv_rate_mL_per_min` in proportion to how far MAP is below
`target_map_mmHg`, clipped to `[0, max_rate_mL_per_min]`.

## Where a run starts

Every process starts from one of:

- `state_file`: a stabilized state, by name in `<runtime>/states` or the package's
  `states/` (`StandardMale@equilibrated.xml`), or a path;
- `patient_file`, optionally with `conditions`: a patient that BioGears stabilizes once
  (40–70 s) and viva-biogears caches. Conditions are BioGears' chronic conditions
  (`ChronicAnemia`, `Dehydration`, `ChronicObstructivePulmonaryDisease`, ...), applied while
  it stabilizes: a different patient, not a perturbation;
- and, on top of either, `circuit_additions`: resistance paths added to the cardiovascular
  circuit with their compartment links ({doc}`circuits`).

## Saved states and branches

`save_state_times_s`, `save_state_dir` and `save_state_name` save the engine at the first
update boundary at or after each time, as `<name>@<t>s.xml`. A saved state starts another
run like any state. The actions active at the save keep running, and the loading process
reads them from the state: each setpoint group starts at the state's values, so a branch
with the same setpoints continues the run exactly (to about 1e-11), and one with different
setpoints sends the change. `python -m viva_biogears.states` saves from the command line.
