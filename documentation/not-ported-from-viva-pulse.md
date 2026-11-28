# Not ported from viva-pulse

[viva-pulse](https://github.com/vivarium-collective/viva-pulse) wrapped the Pulse engine and is being archived. viva-biogears is the
supported home. This page lists what exists only in viva-pulse, where to find it, and what
viva-biogears offers instead.

## What exists only in viva-pulse

- **A hepatic circuit module** and **a multiscale liver block** (COPASI cells under the
  engine, a liver glucose model, eQuilibrator thermodynamics). They are on the
  `feat/multiscale` branch of viva-pulse, which was never merged to its `main`.
- **Circuit modifiers.** Pulse can scale circuit values with multipliers. BioGears has no
  counterpart, so none is provided here (see
  `workspace/experiments/circuits-probe-2026-11-03/README.md`).

viva-biogears has no hepatic module, no multiscale liver block, no COPASI or eQuilibrator
dependency and no modifiers. None of it has been tested against BioGears.

## Where it lives

The tip of `feat/multiscale` is kept under an annotated tag in viva-pulse:
`archive-feat-multiscale-2026-11-25`, which points at commit `f83cf0d`. The tag keeps the work
reachable after the branch is deleted. It has not been reviewed for this repository and may
not merge cleanly with viva-pulse's current `main`.

## What viva-biogears covers instead

- **Substances and tissues**, **lymph and tissue fluid**, and **sepsis** modules
  ({doc}`concepts/modules`).
- **Patients and substances** from BioGears' spreadsheet templates
  ({doc}`tutorials/05-patients-and-checkpoints`).
- **Blood concentrations.** BioGears reports an `Insulin` concentration in the vena cava
  (pybiogears `experiments/p7`); a liver-specific reading has not been confirmed.

Porting any of the items above is new work and needs BioGears readings that have not been
confirmed to exist.
