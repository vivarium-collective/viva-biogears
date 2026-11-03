# viva-biogears

A [process-bigraph](https://github.com/vivarium-collective/process-bigraph) wrapper that drives the **real** [BioGears](https://github.com/BioGearsEngine/core) physiology engine (8.2.0). BioGears runs as a time-stepped `Process`: interventions are input ports, vital signs are output ports, and simulations are ordinary `process_bigraph.Composite` documents. Nothing is reimplemented or mocked: every number comes from BioGears' C++ engine through [pybiogears](https://github.com/) (`~/projects/biogears/pybiogears`).

It follows [viva-pulse](../viva-pulse)'s architecture and contracts. Its reason to exist is BioGears' tissue-fluid model (endothelial leak, oncotic pressure, albumin, lymph), which Pulse 4.4.0 doesn't simulate.

## Status

- **Available (phase 1):**
  - processes: `BioGearsProcess` and `MapFluidController`;
  - composites: `biogears_hemorrhage` and `biogears_resuscitation`.

  Both are tested against the real engine.
- **Next:**
  - phase 2: lymph and tissue-fluid circuit modules (pybiogears' `FluidPath`/`FluidNode` requests) and an equilibrated baseline state;
  - phase 3: the McDaniel et al. 2019 sepsis replication as a workspace study.

  The plan and the probe results are in pybiogears' `experiments/` and `docs/plan-viva-biogears.md`.

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

## License

Apache 2.0, as BioGears.
