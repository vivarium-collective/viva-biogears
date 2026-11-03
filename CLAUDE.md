# CLAUDE.md

Guidance for Claude (and other agents) working in this repository. Read `AGENTS.md` for the framework-wide PR and workspace conventions.

## What this is

`viva-biogears` is a process-bigraph wrapper that drives the **real** BioGears 8.2.0 engine, following viva-pulse's architecture (`../viva-pulse`). BioGears has no PyPI release. It is built from source, unmodified, by `~/projects/biogears/pybiogears/scripts/install_biogears.sh`, and driven through **pybiogears** (the same repository), which is installed into this venv. Everything pybiogears established is recorded in its `experiments/p1`–`p7` folders: build, actions, state round trip, lymph, determinism, request coverage, and the BioGears bugs it works around. Read those before changing how the engine is driven.

Session state and next steps: [CURRENT.md](CURRENT.md).

## Commands

```bash
source .venv/bin/activate
export BIOGEARS_RUNTIME=~/biogears-8.2.0-install/share/biogears/runtime
python -m pytest -q                                   # ~5 min, real engine
python -m pytest -q tests/test_processes.py -k zero   # one test
```

Without a BioGears build, the engine tests are skipped (`tests/conftest.py`), not failed.

## Architecture

- `viva_biogears/runtime.py` finds the BioGears runtime directory: the `runtime_dir` config, then `$BIOGEARS_RUNTIME`, then the installer's default. An explicitly given invalid location raises `BioGearsNotFoundError` and never falls back. It also checks that pybiogears drives 8.2.0.
- `viva_biogears/patients.py` stabilizes a `patient_file` (with optional chronic `conditions`) once through pybiogears' `initialize` and caches the state (`stabilized_state`; key: patient bytes, conditions, install identity). `_bridge.resolve_state` picks `state_file` or the cached patient; `check_start` makes them exclusive.
- `viva_biogears/states.py` saves states (`save_states`, `StateSaver` for `save_state_times_s`, a CLI). pybiogears fixes BioGears' save/load bugs (equipment-request segfault, empty chamber states, blood lost, NaN thermal parts).
- `viva_biogears/processes/` is registered automatically by `core.build_core()` (`register_package_processes`).
  - `biogears.py` has `BioGearsProcess`, with the same contract as viva-pulse's `PulseProcess`:
    - the engine loads lazily; setpoints (`overwrite[float]`) are sent only when they change, because resending a hemorrhage restarts BioGears' bleed;
    - vitals are `overwrite[float]`, seeded by `initial_state()`;
    - an `irreversible_state` latch, after which the engine is not advanced.
  - BioGears-specific guards (in `_bridge.py` and the circuit modules):
    - `HEMORRHAGE_COMPARTMENTS`: an unknown compartment crashes BioGears;
    - a bleed rate above cardiac output raises (BioGears refuses it every step);
    - a second airway device raises (BioGears fails every step, then can be left unrecoverable);
    - a state saved mid-run starts each setpoint group at the state's values (`ActionBinding.loaded`, read by `circuits/state.py`); an active action a group can't address, or an airway device the process doesn't control, raises;
    - `iv_compound` must be a BioGears compound file.
  - `_bridge.py` has the shared engine handling (`load_engine`, `advance`) and `EngineBridge` for `BioGearsProcess`.
  - `circuit.py` has `BioGearsCircuitProcess` (viva-pulse's `PulseCircuitProcess`): setpoints under one `setpoints` input port, readings nested per module, send-on-change, validation before any action, the airway rule.
  - `controllers.py` has `MapFluidController`, identical to viva-pulse's.
- `viva_biogears/circuits/` declares the modules (`base.py`: `Request`, `ActionBinding`, `CircuitModule`); modules compute nothing. `state.py` parses a state file (circuits, compartments, substances, active actions), so `points` and `substances`/`tissues` build their outputs and validate entries before BioGears loads. One file per family, as in viva-pulse: `cardiovascular`, `respiratory` (with `mechanical_ventilator`), `thermal`, `supplemental_oxygen`, `points`, `substances` (with `tissues`), `lymph` (with `tissue_fluid`), `vitals`.
- `viva_biogears/composites/circuits.py` has the per-circuit composites (viva-pulse's store layout: `interventions/<module>`, `circuits/<module>`, an emitter of both); `lymph.py` has `biogears_lymph`, starting from `viva_biogears/states/StandardMale@equilibrated.xml` (see that folder's README; `runtime.state_path` looks there after `<runtime>/states`); `hemorrhage.py` has `biogears_hemorrhage` and `biogears_resuscitation`.
- Thermal applications rely on pybiogears' `prune_thermal_application` (BioGears 8.2.0 bugs; `workspace/experiments/circuits-probe-2026-11-03`). Reinstall pybiogears after pulling it.

## Test oracles

The tests drive a pybiogears engine directly with the same actions and compare the results with `BioGearsProcess`; pybiogears itself matches BioGears' own `bg-scenario` (probe P4). Circuit modules are compared the same way (every module, several actions at once), and checked against conservation laws on BioGears' own circuit: the lymph pool changes by ∫(formation − return), return = (P_pool − P_vena_cava)/R, and signed path flows sum to zero at every junction node of `FullCardiovascular`. Physical checks use bounds, not fitted numbers: for example, blood volume lost is at least the blood-volume drop. Each new guard needs a test that fails without it.

## Conventions

- Keep README.md current with every user-visible change.
- Don't modify BioGears. Work around engine issues in pybiogears or here, and document them where they are worked around.
