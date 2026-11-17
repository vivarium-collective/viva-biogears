# viva-biogears

A [process-bigraph](https://github.com/vivarium-collective/process-bigraph) wrapper that drives the **real** [BioGears](https://github.com/BioGearsEngine/core) physiology engine (8.2.0). BioGears runs as a time-stepped `Process`: interventions are input ports, vital signs are output ports, and simulations are ordinary `process_bigraph.Composite` documents. Nothing is reimplemented or mocked: every number comes from BioGears' C++ engine through [pybiogears](https://github.com/) (`~/projects/biogears/pybiogears`).

It follows [viva-pulse](../viva-pulse)'s architecture and contracts. Its reason to exist is BioGears' tissue-fluid model (endothelial leak, oncotic pressure, albumin, lymph), which Pulse 4.4.0 doesn't simulate.

## Status

- **Available:**
  - processes: `BioGearsProcess`, `BioGearsCircuitProcess` and `MapFluidController`;
  - circuit modules: `vitals`, `cardiovascular`, `respiratory`, `mechanical_ventilator`, `thermal`, `supplemental_oxygen`, `cardiovascular_points`, `respiratory_points`, `substances`, `tissues`, `lymph` and `tissue_fluid`;
  - composites: `biogears_hemorrhage`, `biogears_resuscitation`, `biogears_cardiovascular`, `biogears_respiratory`, `biogears_mechanical_ventilation`, `biogears_thermal`, `biogears_supplemental_oxygen`, `biogears_whole_body_circuits` and `biogears_lymph`.

  All are tested against the real engine.
  - patients: any patient file, with BioGears' chronic conditions, stabilized once and cached (`viva_biogears.patients`);
  - saved states: saved during a run or from the command line, and branching from them (`viva_biogears.states`);
  - circuit additions: resistance paths added to the cardiovascular circuit with their compartment links (`viva_biogears.circuits.additions`);
  - user documentation with five tutorials executed on the real engine (`documentation/`, `make docs`);
  - sepsis: the `infection`, `nutrition` and `treatment` modules, McDaniel et al. 2019's treatment protocols (`viva_biogears.protocols`, run by `TreatmentController`) and `biogears_sepsis`;
  - workbench studies (`workspace/`), each with pre-registered pytest criteria and figures (`viva_biogears/visualizations/`), authored and piloted but not yet run through the workbench:
    - investigation `biogears-hemorrhage`, viva-pulse's three hemorrhage studies ported to BioGears: `hemorrhage-severity-sweep`, `fluid-resuscitation`, `patient-cohort` (10 min runs);
    - investigation `mcdaniel-2019`, replicating McDaniel et al. 2019: `mcdaniel-2019-sepsis` (Figs 4–7), `mcdaniel-2019-treatment` (Figs 9–10), `mcdaniel-2019-refresh` (Figs 11–13). The progression arms are 48 h runs (about 8 h of wall time each); the treatment arms start, as in the paper, from the severe infection's state saved at 44 h (`viva_biogears/states/StandardMale@severe-infection-44h.xml`) and run 8–20 h. `mcdaniel-2019-sepsis/run.py` runs all of them outside the workbench (see its README).

## Requirements

BioGears and pybiogears are not on PyPI; build them from source with pybiogears' one-command installer:

```bash
cd ~/projects/biogears/pybiogears
scripts/install_biogears.sh          # BioGears 8.2.0 -> ~/biogears-8.2.0-install (unmodified; see its README)
```

## Setup

```bash
cd ~/projects/viva-biogears
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -e '.[dev]'
CMAKE_PREFIX_PATH=~/biogears-8.2.0-install uv pip install ~/projects/biogears/pybiogears
export BIOGEARS_RUNTIME=~/biogears-8.2.0-install/share/biogears/runtime
python -m pytest -q        # ~5 min, real engine
```

### Finding BioGears

`viva_biogears.runtime` uses the first of these that is set:
1. the `runtime_dir` process config;
2. `$BIOGEARS_RUNTIME`;
3. `~/biogears-8.2.0-install/share/biogears/runtime`, the installer's default.

A location that is given but is not a BioGears runtime raises `BioGearsNotFoundError`; it never falls back to another location. pybiogears must be importable and drive BioGears 8.2.0. When no build is found, the engine tests are skipped, not failed, so CI without a build stays green.

### Patients and conditions

Every process and composite starts from `state_file` (a stabilized state) or from `patient_file`, optionally with `conditions`:

```python
BioGearsProcess({"patient_file": "Male_44_Normal.xml"})                     # a shipped patient file
BioGearsProcess({"patient_file": "/path/to/MyPatient.xml"})                  # your own
BioGearsCircuitProcess({"modules": ["vitals"], "conditions": {"ChronicAnemia": {"ReductionFactor": 0.3}}})
```

- **Stabilization.** A patient file describes a person (sex, age, weight, height, body fat, resting baselines). BioGears stabilizes it the first time it is used: it builds the body and runs it at rest until it settles. The result is cached in `~/.cache/viva-biogears/states` (`$VIVA_BIOGEARS_CACHE_DIR` overrides it), so later runs load it in about 0.2 s.
- **Cost.** About 40 s, or 70 s with a condition (`workspace/experiments/stabilization-2026-11-03`).
- **Cache key.** It covers the patient file's bytes, the conditions and the BioGears install.
- **Conditions** are BioGears' chronic conditions, applied during stabilization: `ChronicAnemia`, `ChronicHeartFailure`, `ChronicVentricularSystolicDysfunction`, `ChronicObstructivePulmonaryDisease`, `ChronicPericardialEffusion`, `ChronicRenalStenosis`, `Dehydration`, `ImpairedAlveolarExchange`, `LobarPneumonia`, `Starvation`.
  - Fields follow `PatientConditions.xsd`. A value is a number or `"<value> <unit>"` (`{"Starvation": {"TimeSinceMeal": "72 hr"}}`).
  - Conditions without `patient_file` apply to `StandardMale.xml`.
  - They play the role of viva-pulse's `circuit_modifiers`: the result is a different patient, not a perturbation.
  - Chronic anemia removes hemoglobin but leaves hematocrit unchanged in BioGears 8.2.0.
- **Rules.** Setting `state_file` and `patient_file` (or `conditions`) together raises. `biogears_lymph` drops its equilibrated default when a patient is given; that patient is not equilibrated.

### Saved states and branching

A process saves its engine at given simulation times:

```python
config = {"save_state_times_s": [600, 1200], "save_state_dir": "states/", "save_state_name": "bleed"}
# -> states/bleed@600s.xml, states/bleed@1200s.xml
```

The same can be done from the command line: `python -m viva_biogears.states StandardMale@0s.xml --times 60 120 --out states/`.

- **Where saves land.** Each save is at the first update boundary at or after its time, so saving doesn't change the run. Existing files are never overwritten: a name already in the directory raises when the process is built.
- **Branching.** A saved state is an ordinary BioGears state, so `state_file` starts another run from it. Actions active at the save keep running: a bleed, an infusion, intubation, the ventilator, the cannula, a thermal application, a changed environment.
- **Setpoints in a branch.** The loading process reads those actions from the state, and each setpoint group starts at the state's values:
  - a branch with the same setpoints sends nothing and continues the run (to about 1e-11);
  - a branch with different ones sends the change: rate 0 stops the bleed, `connected` 0 disconnects the ventilator.

  This matters in BioGears in particular, because resending a hemorrhage restarts it.
- **What raises.**
  - An active action the process can't address: a bleed in another compartment, an infusion of another compound, another tube type.
  - An airway device the process doesn't control.
- **BioGears bugs.** pybiogears works around four BioGears 8.2.0 save/load bugs: a segfault saving with equipment requests, ventilator states that didn't reload, blood lost reset on load, and NaN thermal parts. See `workspace/experiments/save-states-2026-11-03`.

### Circuit additions

`circuit_additions` adds resistance paths to the cardiovascular circuit before the state loads. It is available on both processes and every composite:

```python
{"circuit_additions": {"Shunt": {"source": "Aorta1", "target": "VenaCava", "resistance_mmHg_s_per_mL": 2.0}}}
```

- **What the body does.** An addition is a perturbation, not a different patient: the body responds over time. A 2 mmHg s/mL aorta-to-vena-cava shunt carries about 1.7 L/min; MAP falls from 96 to 82 mmHg, and HR and cardiac output rise.
- **How it is added.** Each path comes with a liquid link between its nodes' compartments, so blood substances follow it. A path alone corrupts concentrations, and a large one is fatal within seconds.
- **What is accepted.** Both nodes must be in `FullCardiovascular`, in two different vascular compartments. In the state, an addition named `Shunt` becomes path and link `VivaAddedShunt`. `cardiovascular_points` reads its flow.
- **Fixed resistance.** BioGears' vascular tone doesn't scale an added path.
- **When it fails.** A bad addition raises when the process is built.
- **Where the edited state goes.** It is written once to `~/.cache/viva-biogears/additions/`.

See `workspace/experiments/additions-2026-11-03`.

## Documentation

`make docs` builds the user documentation in `documentation/` (Sphinx, MyST notebooks) and opens it. It runs every tutorial against the real engine, about 15 minutes. The tutorials:
1. a hemorrhage, untreated and resuscitated;
2. the cardiovascular circuit, beat by beat and node by node;
3. lymph and tissue fluid under a fluid load;
4. every circuit on one engine;
5. your own patient, and branching from a checkpoint.

On Read the Docs (`.readthedocs.yaml`), which can't build BioGears, the tutorials are published as code only. `tests/test_docs.py` builds both versions.

## Usage

```python
from process_bigraph import Composite, gather_emitter_results

from viva_biogears.composites import biogears_resuscitation
from viva_biogears.core import build_core

core = build_core()
doc = biogears_resuscitation(core, compartment="Aorta", rate_mL_per_min=600.0, target_map_mmHg=90.0)
sim = Composite({"state": doc}, core=core)
sim.run(300)          # 300 simulated seconds -> 301 emitted rows (first at t = 0)
rows = gather_emitter_results(sim)[("emitter",)]
```

### Composites

| composite | what it does | parameters |
|---|---|---|
| `biogears_hemorrhage` | an untreated hemorrhage; emits vitals every second | `state_file`, `compartment`, `rate_mL_per_min` |
| `biogears_resuscitation` | the same, plus `MapFluidController` setting the IV rate from MAP | also `compound`, `target_map_mmHg`, `gain`, `max_rate_mL_per_min` |
| `biogears_cardiovascular` | the cardiovascular circuit (renal, cerebral and tissue branches) under a hemorrhage and an infusion | `hemorrhage_compartment`, `hemorrhage_rate_mL_per_min`, `iv_compound`, `iv_rate_mL_per_min`, `point_reads`, `substance_outputs`, `tissue_outputs` |
| `biogears_respiratory` | the airway circuit, with intubation | `intubated`, `intubation_type`, `point_reads` |
| `biogears_mechanical_ventilation` | intubated, on the anesthesia-machine ventilator | the ventilator settings, `ventilator_connection` |
| `biogears_thermal` | the temperature circuit under the environment and heating, cooling or an applied temperature | the environment and the thermal application |
| `biogears_supplemental_oxygen` | a nasal cannula | `oxygen_connected`, `oxygen_flow_L_per_min` |
| `biogears_whole_body_circuits` | every module with setpoints, plus lymph and tissue fluid, on one engine | all of the above |
| `biogears_lymph` | lymph and tissue fluid at rest or under an infusion, from the equilibrated state | `state_file`, `iv_rate_mL_per_min`, `iv_compound` |
| `biogears_sepsis` | an infection (BioGears' sepsis model) with meals, lymph, tissue fluid and hemodynamics, sampled each minute; optionally treated with one of McDaniel et al. 2019's protocols | `severity`, `infection_location`, `infection_mic_mg_per_L`, `nutrition`, `iv_rate_mL_per_min`; `treatment` (`fluid_challenge`, `antibiotic`, `refresh_control`, `refresh_experimental`), `challenge_h`, `treatment_start_h`, `treatment_duration_h`, `drug_readouts`; from a saved state (e.g. `StandardMale@severe-infection-44h.xml`) the protocol keeps engine time |

Every composite also takes `state_file`, and the circuit composites take `interval` (0.02 s resolves waveforms). The circuit composites use viva-pulse's store layout: setpoints in `interventions/<module>/`, readings in `circuits/<module>/`, and an emitter of both subtrees.

### `BioGearsProcess`

The contract is viva-pulse's `PulseProcess`:

- **Config.**
  - `state_file`: a name in `<runtime>/states`, or an absolute path.
  - `runtime_dir`.
  - `hemorrhage_compartment`: one of the 18 with a BioGears bleed path, e.g. `RightLeg` or `Aorta`.
  - `iv_compound`: a BioGears compound, e.g. `Saline`, `Blood_ONegative` or `RingersLactate`.
  - `iv_bag_volume_L`.
- **Inputs.**
  - `hemorrhage_rate_mL_per_min` and `iv_rate_mL_per_min`, as `overwrite[float]` setpoints.
  - They are sent to BioGears only when they change, because resending a hemorrhage restarts BioGears' bleed. 0 stops the action.
- **Outputs.**
  - Vitals as `overwrite[float]`, seeded with the loaded state's readings, so the store always equals BioGears' own value: HR, MAP, SBP, DBP, SpO2, RR, CO, CVP, blood volume, and total blood volume lost (NaN until the first bleed).
  - The `irreversible_state` latch: BioGears declares it at 50 % blood loss, and the engine is not advanced after that.

How it differs from Pulse:

| | Pulse | BioGears |
|---|---|---|
| hemorrhage setpoint | a severity in [0, 1] | an initial rate in mL/min, which BioGears then lowers with the local pressure |
| a rate above cardiac output | — | BioGears refuses it on every step without stopping; `BioGearsProcess` raises `ValueError` |
| a hemorrhage on an unknown compartment | — | crashes BioGears; it is rejected at construction |
| starting state | — | a state that already holds a hemorrhage or an infusion is refused at load, so the setpoint ports always describe what is running |

### `BioGearsCircuitProcess`

The pattern is viva-pulse's `PulseCircuitProcess`. `config.modules` lists modules from `viva_biogears.circuits.MODULES`.

- **Outputs.** Each module's readings nest under its name, as `overwrite[float]` (e.g. `cardiovascular/central/aorta/pressure_mmHg`).
- **Inputs.** The module's setpoints sit under one `setpoints` input port (e.g. `setpoints/cardiovascular/hemorrhage_rate_mL_per_min`). Each is sent to BioGears only when it changes.
- **Validation.**
  - Changed setpoint groups are validated before any action is sent.
  - A NaN reading raises, naming the request.
  - A request BioGears doesn't connect fails the load.
  - A state that already has an action active that the process's setpoints also send is refused, and so is an intubated state or a state whose airway device is already connected.

| module | readings | setpoints |
|---|---|---|
| `vitals` | `BioGearsProcess`'s vitals | none |
| `cardiovascular` | 23 hemodynamic values; pressure, volume, inflow and outflow for 42 compartments under `central/`, `cerebral/`, `renal/` and `peripheral/` | `hemorrhage_rate_mL_per_min` (at `hemorrhage_compartment`), `iv_rate_mL_per_min` (of `iv_compound`) |
| `respiratory` | 18 breathing-mechanics values; airway, lung and pleural gas compartments | `intubated` (with `intubation_type`); extubation works |
| `mechanical_ventilator` | the anesthesia-machine settings as applied; its circuit's gas compartments | `connected` plus pressure, PEEP, rate, I:E, O2 fraction and inlet flow (with `ventilator_connection` `Tube` or `Mask`) |
| `thermal` | core and skin temperatures, sweat, metabolic rate, heat losses, the environment as applied; temperature and heat flows of 17 thermal compartments, and the heat flows of the applied-temperature node | the environment group and the thermal-application group (heating, cooling, applied temperature) |
| `supplemental_oxygen` | arterial blood gases, end-tidal CO2, nosepiece O2 fraction | `oxygen_connected`, `oxygen_flow_L_per_min` (nasal cannula) |
| `cardiovascular_points` | pressure (and volume, where finite) of each of the 169 nodes of `FullCardiovascular`, signed flow of each of its 296 paths | none |
| `respiratory_points` | the same for the 17 nodes and 27 paths of `Respiratory` | none |
| `substances` | the quantities listed in `substance_outputs` (in a compartment, or whole-body); readable properties in `LIQUID_PROPERTIES`, `GAS_PROPERTIES`, `BODY_PROPERTIES`; `every_substance_output()` lists every valid entry | none |
| `tissues` | the tissue values listed in `tissue_outputs`; readable properties in `TISSUE_PROPERTIES`, `TISSUE_FLUID_PROPERTIES` | none |
| `lymph` | `return_mL_per_min`, `return_resistance_mmHg_min_per_mL`, `pool_volume_mL`, `pool_pressure_mmHg`, `vena_cava_pressure_mmHg`, `central_venous_pressure_mmHg`, `formation/<tissue>_mL_per_min` for 13 tissues | none |
| `tissue_fluid` | per tissue: extracellular and intracellular volume, interstitial albumin, capillary filtration and endothelial resistance, plasma and interstitial oncotic pressure, interstitial pressure; whole-body plasma albumin, blood, extravascular, intracellular and total fluid | none |
| `infection` | BioGears' inflammatory response (pathogens, immune cells, cytokines, nitric oxide, tissue integrity) and the clinical signs of sepsis (WBC, temperature, lactate, SVR, urine, ...) | `infection_severity` 0–3, one-way (BioGears reads it once and can't end an infection) |
| `nutrition` | stomach contents, chyme absorption, body fluid, urine volume | none: meals and drinks come from `nutrition_schedule`, sent at their times |
| `treatment` | antibiotic activity; plasma and blood concentration and AUC of each `treatment_readouts` drug | `vasopressor_rate_ug_per_min` (a substance infusion, norepinephrine by default); timed compound and substance infusions come from `treatment_schedule`. BioGears keeps one infusion per compound and per substance, so a setpoint can't drive what the schedule infuses (raises) |

Each module's docstring in `viva_biogears/circuits/` gives the details.

**How the modules differ from viva-pulse's:**

| | Pulse 4.4.0 | BioGears 8.2.0 |
|---|---|---|
| circuit resistance/compliance multipliers | yes | no equivalent action; not offered |
| lymph | a stub that carries no flow | active; the `lymph` and `tissue_fluid` modules |
| ventilator | a pressure-control ventilator | the anesthesia machine (pressure control, Tube or Mask) |
| supplemental oxygen | nasal cannula, simple mask, non-rebreather | nasal cannula; masks are the anesthesia machine with `Mask` |
| extubation | refused (Pulse's Python API drops it) | works |
| point reads | the process edits the state to add compartments and links | read directly from the circuit; nothing is edited |
| thermal application | works | needs pybiogears' workaround for two BioGears bugs (omitted parts become NaN; an Off applied temperature still applies) |

**Lymph.** BioGears 8.2.0 has no compartment links for lymph, so lymph is read from circuit nodes and paths (pybiogears `FluidPath`/`FluidNode`). The one transformation in any module is a sign: BioGears stores plasma oncotic pressure as a negative pressure source, and it is reported positive.

Lymph return in BioGears is a passive resistor from the lymph pool into the vena cava, so it falls as venous pressure rises: 200 mL/min of saline lowers it from 3.2 to 0.4 mL/min within 5 minutes while formation rises, and from the equilibrated state it reverses within 10 minutes (about −1 mL/min): the return path has no valve, so fluid flows from the vena cava back into the pool. Read CVP with it. `StandardMale@0s` is not at fluid steady state (the lymph pool relaxes with τ ≈ 91 min), so lymph studies should start from the shipped `StandardMale@equilibrated.xml` (5 h at rest with hourly water; `viva_biogears/states/README.md`), the default for `biogears_lymph`. A relative `state_file` is looked up in `<runtime>/states`, then in the package's `states/`.

**What was measured** to choose these: `workspace/experiments/circuits-probe-2026-11-03`.

## License

Apache 2.0, as BioGears.
