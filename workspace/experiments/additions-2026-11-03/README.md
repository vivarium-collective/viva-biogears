# Circuit-additions probe (2026-11-03)

**Question.** Can a path be added to BioGears 8.2.0's cardiovascular circuit by editing a state before it loads? And must substances be linked to it?

**Method.** `probe.py out R` adds an aorta-to-vena-cava shunt (`Aorta1` → `VenaCava`, resistance R mmHg s/mL) to `StandardMale@0s.xml`, in two ways:
- the path alone, inserted into every fluid circuit holding both nodes;
- the path plus a liquid link `Aorta` → `VenaCava`, inserted into every liquid graph holding both compartments.

Each runs 5 min against an unedited control. `run.log` has the output.

**Results.**

| R (mmHg s/mL) | variant | shunt flow | MAP | HR | CO | PaO2 |
|---|---|---|---|---|---|---|
| — | control | — | 96.0 | 72.2 | 5.81 | 96.8 |
| 20 | path only | 224 mL/min | 94.7 | 73.5 | 5.90 | **112.4** (drifts up) |
| 20 | path + link | 223 mL/min | 94.3 | 73.6 | 5.95 | 97.0 |
| 2 | path only | — | irreversible state at 2.3 s | | | |
| 2 | path + link | 1658 mL/min | 82.4 | 84.9 | 7.40 | 98.4 |

- BioGears loads an edited state and solves the added path.
- It moves substances only over the compartment graph. A path without a link carries blood without its substances, which corrupts the concentrations: PaO2 drifts, and a large shunt is fatal at once.
- With the link, the body responds as to an arteriovenous fistula: MAP falls, while HR and cardiac output rise. Mixed venous PO2 rises with the shunted arterial blood (39.4 → 43.4 mmHg at R = 2).
- An added path has no stored flow, so it reads NaN until the first step. `viva_biogears.circuits.additions` writes a 0 flow.

**Decision.** `viva_biogears.circuits.additions` adds each path with its link, under these rules: `FullCardiovascular` nodes in two different vascular compartments, with the names prefixed `VivaAdded`.
