# McDaniel et al. 2019 on BioGears 8.2.0 (viva-biogears study)

**Paper:** M. McDaniel, J. M. Keller, S. White, A. Baird (2019). *A Whole-Body Mathematical Model of Sepsis Progression and Treatment Designed in the BioGears Physiology Engine.* Front. Physiol. 10:1321. [doi:10.3389/fphys.2019.01321](https://doi.org/10.3389/fphys.2019.01321)

**Scope (decided 2026-11-02):** the three core experiments, on BioGears 8.2.0 only:
1. the course of mild, moderate and severe infection over 48 h, with an uninfected control (paper Figs 4–5);
2. the untreated progression of severe infection, with its event timings (Figs 6–7);
3. the 1000 mL saline challenge (Fig 9).

Lymph and tissue fluid are recorded throughout, because the paper's endothelial-leak / oncotic-pressure / lymph model is what turns inflammation into hypovolemia. This study runs on viva-biogears' `biogears_sepsis` composite and `BioGearsCircuitProcess` (modules `infection`, `nutrition`, `lymph`, `tissue_fluid`, `cardiovascular`). It replaces the standalone scripts in pybiogears `studies/mcdaniel2019`, whose protocol and analysis it keeps.

**Why results may differ from the paper.** The paper's code is closest to BioGears 7.3.0. Up to 8.2.0 there have been 93 further commits to `BloodChemistry.cpp` and `Tissue.cpp`. Differences mix model drift since 2019 with anything not reproducible from the paper's description, and 8.2.0 alone can't tell them apart.

## Protocol

| element | value | source |
|---|---|---|
| patient | StandardMale, `states/StandardMale@0s.xml` | BioGears' infection scenarios |
| infection | `infection_severity` 1/2/3 (Mild/Moderate/Severe) at t = 0, Skin, MIC 16 mg/L | paper; the shipped scenarios use 8 mg/L, which acts only through antibiotics (none here) |
| duration | 48 h at 60 s updates | paper |
| water and meals | BioGears' `InfectionModerate` schedule: 150 mL water hourly, meals at 4, 9, 24, 28, 33 h, the same for every arm (`nutrition="infection_scenario"`) | paper: "periodic water and meal actions", same for the control |
| control | same schedule, no infection | paper |
| fluid challenge | from severe's 44 h checkpoint: saline 16.67 mL/min from 44.0 to 45.0 h (two 500 mL boluses over 30 min each), observed to 46 h | paper Fig 9 |

**Events** (`analyze.py`; a condition counts once it holds 30 min): lactate > 2 mM (paper: after 20 h); SBP < 100 mmHg (26 h); sepsis, SBP < 100 and RR ≥ 22/min (~30 h; the paper doesn't define its tachypnea threshold, 22/min is qSOFA's); septic shock, MAP < 65 and lactate > 2 mM (45 h); mean urine output < 0.625 mL/min; lowest SVR relative to baseline (about 60 %).

## Running

Each 48 h arm takes about 8 h of wall time (BioGears runs ~6× real time), so run the arms in parallel on a machine with enough cores, kept awake:

```sh
cd ~/projects/viva-biogears && source .venv/bin/activate
export BIOGEARS_RUNTIME=~/biogears-8.2.0-install/share/biogears/runtime
caffeinate -i python workspace/studies/mcdaniel-2019-sepsis/run.py all --jobs 4
python workspace/studies/mcdaniel-2019-sepsis/analyze.py      # any time, on partial results too
```

- `all` runs control, mild, moderate and severe in parallel, then the challenge from severe's 44 h checkpoint.
- Progress: `tail workspace/studies/mcdaniel-2019-sepsis/out/*/log.txt` (a line every 4 simulated hours).
- An interrupted arm resumes from its last checkpoint when you run the same command again. The process reads the infection from the checkpoint and skips the meals before it, so the resumed run continues the original (`tests/test_sepsis.py` checks this).

## Outputs (`out/`, not committed)

- `<arm>/data.csv`: one row per simulated minute: inflammation (pathogens, TNF, IL-6, IL-10, NO, tissue integrity), vitals, blood volume, urine, lactate, SVR, CO, SV, CVP, body fluids, plasma albumin, lymph return, the lymph pool, the 13 tissue lymph flows, muscle endothelial resistance, and the IV rate.
- `<arm>/events.csv`: BioGears' patient events (SevereSepsis, Hypotension, ...).
- `summary.md`, `fig4.png` … `fig9.png`, `fig_lymph.png`: from `analyze.py`.
