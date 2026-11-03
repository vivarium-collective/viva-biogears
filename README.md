# viva-biogears

A [process-bigraph](https://github.com/vivarium-collective/process-bigraph) wrapper that drives the **real** [BioGears](https://github.com/BioGearsEngine/core) physiology engine (8.2.0). BioGears runs as a time-stepped `Process`: interventions are input ports, vital signs are output ports, and simulations are ordinary `process_bigraph.Composite` documents. Nothing is reimplemented or mocked: every number comes from BioGears' C++ engine through [pybiogears](https://github.com/) (`~/projects/biogears/pybiogears`).

It follows [viva-pulse](../viva-pulse)'s architecture and contracts. Its reason to exist is BioGears' tissue-fluid model (endothelial leak, oncotic pressure, albumin, lymph), which Pulse 4.4.0 doesn't simulate.

## Status

- **Available:**
  - processes: `BioGearsProcess`, `BioGearsCircuitProcess` and `MapFluidController`;
  - circuit modules: `vitals`, `cardiovascular`, `respiratory`, `mechanical_ventilator`, `thermal`, `supplemental_oxygen`, `cardiovascular_points`, `respiratory_points`, `substances`, `tissues`, `lymph` and `tissue_fluid`;
  - composites: `biogears_hemorrhage`, `biogears_resuscitation`, `biogears_cardiovascular`, `biogears_respiratory`, `biogears_mechanical_ventilation`, `biogears_thermal`, `biogears_supplemental_oxygen`, `biogears_whole_body_circuits` and `biogears_lymph`.

  All are tested against the real engine.
  - patients: any patient file, with BioGears' chronic conditions, stabilized once and cached (`viva_biogears.patients`).
- **Next (viva-pulse parity, in this order):**
  - saved states and branching from them;
  - circuit additions;
  - the Sphinx documentation and tutorials.

  Then phase 3, the McDaniel et al. 2019 sepsis replication as a workspace study.

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
| `substances` | the quantities listed in `substance_outputs` (in a compartment, or whole-body) | none |
| `tissues` | the tissue values listed in `tissue_outputs` | none |
| `lymph` | `return_mL_per_min`, `return_resistance_mmHg_min_per_mL`, `pool_volume_mL`, `pool_pressure_mmHg`, `vena_cava_pressure_mmHg`, `central_venous_pressure_mmHg`, `formation/<tissue>_mL_per_min` for 13 tissues | none |
| `tissue_fluid` | per tissue: extracellular and intracellular volume, interstitial albumin, capillary filtration and endothelial resistance, plasma and interstitial oncotic pressure, interstitial pressure; whole-body plasma albumin, blood, extravascular, intracellular and total fluid | none |

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

Lymph return in BioGears is a passive resistor from the lymph pool into the vena cava, so it falls as venous pressure rises: 200 mL/min of saline lowers it from 3.2 to 0.4 mL/min within 5 minutes while formation rises. Read CVP with it. `StandardMale@0s` is not at fluid steady state (the lymph pool relaxes with τ ≈ 91 min), so lymph studies should start from the shipped `StandardMale@equilibrated.xml` (5 h at rest with hourly water; `viva_biogears/states/README.md`), the default for `biogears_lymph`. A relative `state_file` is looked up in `<runtime>/states`, then in the package's `states/`.

**What was measured** to choose these: `workspace/experiments/circuits-probe-2026-11-03`.

## License

Apache 2.0, as BioGears.
