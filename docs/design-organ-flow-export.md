# Per-region flow export for the atlas circulation network

**Date:** 2026-11-24
**Status:** Proposed design for review (no code)
**Branch:** `docs/organ-flow-export-design`
**Companion:** viva-human-atlas `docs/superpowers/specs/2026-11-24-biogears-flow-link-design.md`
(the consuming side: topology, Uberon mapping, per-edge flow assembly)

## Purpose

The atlas plans a whole-body blood-transport network and needs a heart and a flow per
organ. viva-biogears already reads BioGears' regional vascular compartments
(`viva_biogears/modules/cardiovascular.py`). This design adds a small, general export of
those readings in a form a consumer can rely on. viva-biogears stays free of Uberon and
atlas concepts: it exports by BioGears region name, and the atlas maps names to organs.

## What exists today (read from the code)

- `COMPARTMENTS` in `cardiovascular.py` lists the vascular compartments by group
  (`central`, `cerebral`, `renal`, `peripheral`), e.g. `peripheral/liver ->
  LiverVasculature`, `renal/left_kidney -> LeftKidneyVasculature`.
- Every compartment reports `pressure_mmHg`, `volume_mL`, `inflow_mL_per_min`,
  `outflow_mL_per_min` under `readings/cardiovascular/<group>/<name>/`.
- `hemodynamics/cardiac_output_L_per_min` is BioGears' cardiac output.
- Per the module docstring these flows are **instantaneous within each heartbeat**;
  1 s sampling aliases the cycle. BioGears 8.2.0's fluid-compartment header exposes only
  `InFlow`/`OutFlow` (no averaged accessor); this was checked in the 8.2.0 source tree.
- `cardiovascular_points` can read any node pressure and path flow of the
  `FullCardiovascular` circuit by name.

So a consumer that reads `inflow_mL_per_min` at the process interval gets a sample of a
pulsatile signal, not a flow. That is the gap this design closes.

## Proposal

1. **Cycle-averaged inflow as a first-class reading.** A windowed-mean reading type in the
   module registry (`modules/base.py` `Request`): the process accumulates a request every
   engine step (0.02 s) and, at each update, emits the mean over the last window and resets.
   Window: one cardiac cycle by default (from `hemodynamics/heart_rate_bpm`), or a
   configured number of seconds. Applied to `inflow_mL_per_min` (and `mean_pressure_mmHg`)
   of the compartments in `COMPARTMENTS`.
2. **A `flows` view.** Per BioGears region: `inflow_mL_per_min`, `mean_pressure_mmHg`,
   `volume_mL`, plus `cardiac_output_mL_per_min` at the top, under
   `readings/cardiovascular_flows/`. Keys are the compartment names above, so the view is
   self-describing and BioGears-native.
3. **Typed contract.** The ports are declared floats with units in the module's contract
   (the `contract` attribute work requested in PR #8 applies), so the atlas adapter can
   bind to them by schema, not by convention.

Not proposed: any change to BioGears (stock 8.2.0 stays), any action that modifies the
circuit, or any Uberon or atlas dependency here.

## What a compartment's flow means (to be settled by a probe before code)

In Pulse, a compartment's `Outflow` sums every outgoing link, including links into tissue,
so a vascular compartment's outflow need not equal its inflow. Whether BioGears'
`CalculateOutFlow_mL_Per_s` behaves the same, and whether regional **inflow** is the right
organ-perfusion quantity (versus the path flow into the organ from the circuit), is
**unverified for BioGears**. The first task after review is a probe against the real
engine comparing, for each mapped region, compartment inflow against the corresponding
circuit path flow from `cardiovascular_points`. The export uses whichever is correct; the
probe result goes into the PR that implements this.

## Validation (real engine, nothing mocked)

- Regional cycle-means equal an independent engine driven directly through pybiogears
  (the pattern of `tests/circuit_helpers.py` and
  `tests/test_circuit_modules.py::test_points_equal_a_direct_engine`).
- Cycle-mean aortic output equals cycle-mean `cardiac_output` within a stated tolerance.
- Sum of systemic regional inflows versus cardiac output: measured, tolerance set from the
  measurement (**unverified** that they close; regions such as the splanchnic and portal
  compartments nest, so a naive sum may double count, which the probe must resolve).
- The export leaves the simulation unchanged (accumulating reads must not perturb the
  engine): rows equal a run without it to the tolerance the existing point-read tests use.
- Behaviour under hemorrhage and saline: flows move in the engine's direction.

## Open questions for review

1. Window default: one cardiac cycle versus a fixed number of seconds.
2. Whether the windowed mean belongs in the generic `Request` (usable by every module) or
   only in the cardiovascular module. Proposed: generic, because the same aliasing applies
   to respiratory flows.
3. Naming of the new view (`cardiovascular_flows` proposed) and whether it is a module
   or a composite-level option.
4. Where the Uberon-to-region mapping table lives: atlas (proposed) or here.
