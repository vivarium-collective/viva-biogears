# Introduction

viva-biogears runs [BioGears](https://github.com/BioGearsEngine/core), a whole-body model of
adult human physiology, inside [process-bigraph](https://github.com/vivarium-collective/process-bigraph)
simulations.

BioGears runs as an ordinary process-bigraph `Process`:

- **interventions** (a bleed, an infusion, intubation, a ventilator, oxygen, the room
  temperature) are input ports;
- **readings** (vital signs, and the pressure, volume and flow in each region and at each
  node of BioGears' circuits) are output ports;
- a **simulation** is an ordinary composite document, built by a composite generator and run
  with `Composite.run`.

Nothing is reimplemented or mocked. Every number comes from BioGears' C++ engine through
[pybiogears](https://github.com/vivarium-collective/pybiogears), a thin binding built against an unmodified BioGears 8.2.0.

## Why BioGears

BioGears models fluid exchange between blood and tissue: endothelial leak, oncotic
pressures, albumin, and an active **lymphatic system** that returns filtered fluid to the
veins. Studies of fluid overload, sepsis and resuscitation need
that exchange ({doc}`tutorials/03-lymph-and-tissue-fluid`).

## What you can do with it

- Run a hemorrhage, with or without closed-loop fluid resuscitation
  ({doc}`tutorials/01-hemorrhage-and-resuscitation`).
- Read the pressure, volume and flow of every region and every circuit node and path of the
  cardiovascular circuit, at BioGears' own 0.02 s timestep
  ({doc}`tutorials/02-cardiovascular-circuit`).
- Follow lymph formation, the lymph pool and its return, and capillary filtration under a
  fluid load ({doc}`tutorials/03-lymph-and-tissue-fluid`).
- Put every circuit on one engine (cardiovascular, respiratory, ventilator, oxygen,
  thermal) and watch an intervention in one show up in the others
  ({doc}`tutorials/04-every-circuit-on-one-engine`).
- Start from any patient file, with chronic conditions, and save checkpoints to branch
  from ({doc}`tutorials/05-patients-and-checkpoints`).

## How BioGears models the body

BioGears models physiology as lumped-parameter circuits, the same mathematics as electrical
circuits: **pressure** pushes fluid like a voltage, **flow** moves like a current,
**resistance** restricts flow, and **compliance** (a vessel's stretchiness) stores volume.
The cardiovascular (with its renal, cerebral, tissue and lymph branches), respiratory and
thermal systems are each such a circuit, solved together every 0.02 s of simulated time.
Substances (gases, electrolytes, proteins, drugs) move between **compartments**, groups of
circuit nodes, along **links**. {doc}`concepts/modules` shows what can be read.

## Where BioGears 8.2.0 needed help

Several BioGears 8.2.0 bugs are worked around in pybiogears and documented where they are:
thermal applications, saved states with a ventilator or a bleed, chronic conditions at
stabilization, and a few requests and actions that crash the engine. BioGears itself is
built unmodified.
