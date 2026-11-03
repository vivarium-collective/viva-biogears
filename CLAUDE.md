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
- `viva_biogears/processes/` is registered automatically by `core.build_core()` (`register_package_processes`).
  - `biogears.py` has `BioGearsProcess`, with the same contract as viva-pulse's `PulseProcess`:
    - the engine loads lazily; setpoints (`overwrite[float]`) are sent only when they change, because resending a hemorrhage restarts BioGears' bleed;
    - vitals are `overwrite[float]`, seeded by `initial_state()`;
    - an `irreversible_state` latch, after which the engine is not advanced.
  - BioGears-specific guards (in `_bridge.py`, shared with `BioGearsCircuitProcess`):
    - `HEMORRHAGE_COMPARTMENTS`: an unknown compartment crashes BioGears;
    - a bleed rate above cardiac output raises (BioGears refuses it every step);
    - states holding an active hemorrhage or infusion are refused at load;
    - `iv_compound` must be a BioGears compound file.
  - `_bridge.py` has `EngineBridge`, the engine handling both processes share (lazy load, send-on-change, the guards above, the irreversible latch).
  - `circuit.py` has `BioGearsCircuitProcess` (viva-pulse's `PulseCircuitProcess` pattern): readout modules declared in `viva_biogears/circuits/__init__.py` as data requests at port paths; the modules compute nothing.
  - `controllers.py` has `MapFluidController`, identical to viva-pulse's.
- `viva_biogears/composites/lymph.py` has `biogears_lymph` (vitals + lymph + tissue_fluid under an optional infusion), starting from `viva_biogears/states/StandardMale@equilibrated.xml` (see that folder's README; `runtime.state_path` looks there after `<runtime>/states`).
- `viva_biogears/composites/hemorrhage.py` has `biogears_hemorrhage` and `biogears_resuscitation`, built with `composite_generator` and `core_extensions=[build_core]`, with a 1 s interval and a RAM emitter.

## Test oracles

The tests drive a pybiogears engine directly with the same actions and compare the results with `BioGearsProcess`; pybiogears itself matches BioGears' own `bg-scenario` (probe P4). Circuit modules are also checked against conservation laws on BioGears' own circuit: the lymph pool changes by ∫(formation − return), and return = (P_pool − P_vena_cava)/R. Physical checks use bounds, not fitted numbers: for example, blood volume lost is at least the blood-volume drop. Each new guard needs a test that fails without it.

## Conventions

- Keep README.md current with every user-visible change.
- Don't modify BioGears. Work around engine issues in pybiogears or here, and document them where they are worked around.
