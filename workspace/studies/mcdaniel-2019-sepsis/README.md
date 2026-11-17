# McDaniel et al. 2019 on BioGears 8.2.0 (viva-biogears study)

**Paper:** M. McDaniel, J. M. Keller, S. White, A. Baird (2019). *A Whole-Body Mathematical Model of Sepsis Progression and Treatment Designed in the BioGears Physiology Engine.* Front. Physiol. 10:1321. [doi:10.3389/fphys.2019.01321](https://doi.org/10.3389/fphys.2019.01321)

**Scope:** on BioGears 8.2.0 only (decided 2026-11-02; treatments added 2026-11-16):
1. the course of mild, moderate and severe infection over 48 h, with an uninfected control (paper Figs 4–5);
2. the untreated progression of severe infection, with its event timings (Figs 6–7);
3. the 1000 mL saline challenge (Fig 9) and piperacillin/tazobactam (Fig 10);
4. the REFRESH protocols, liberal fluid (control) and norepinephrine with restricted fluid (experimental), and the control protocol delayed 12 h (Figs 11–13).

Fig 8 (changing inflammation parameters) needs changes inside BioGears and is out of scope.

**Two ways to run it.** The workbench studies of the `mcdaniel-2019` investigation run `biogears_sepsis`: this folder's `study.yaml` (Figs 4–7, 48 h from t = 0), `../mcdaniel-2019-treatment` (Figs 9–10) and `../mcdaniel-2019-refresh` (Figs 11–13). Their criteria are the pytest files in each `tests/`. `run.py` and `analyze.py` here run the same arms outside the workbench.

**Treatment arms start from a saved septic state, as in the paper** ("All treatment scenarios were conducted using virtual patient states generated from the nominal BioGears severe infection action"). The state is the severe arm at 44 h, shipped as `viva_biogears/states/StandardMale@severe-infection-44h.xml` (see that folder's README). Each treatment arm runs from it to 52 h (64 h for the delayed arm), keeping engine time: the protocol's 44 h challenge is the run's first update. `run.py` uses its own severe arm's 44 h checkpoint when it has one, and the shipped state otherwise. As in the paper, Fig 9 is plotted in hours after infection and Figs 10–13 in hours since the treatment start.

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
| fluid challenge | two 500 mL saline boluses at 44 and 44.5 h, observed to 46 h | paper Fig 9 |
| antibiotic | the challenge, then 4.5 g piperacillin/tazobactam over 30 min at 46 h (BioGears' `PiperacillinTazobactam`, 20 mL at 0.667 mL/min), to 52 h | paper Fig 10 |
| REFRESH control | the challenge and antibiotic; at 46 h 1000 mL; every 30 min to 52 h 500 mL if SBP < 90 or MAP < 65, and hourly 500 mL more if urine < 0.625 mL/min; once both goals are met, only maintenance at 75 mL/h | paper Figs 11–12 |
| REFRESH experimental | the challenge and antibiotic; at 46 h maintenance 1 mL/kg/h and norepinephrine 0.18 µg/kg/min; hourly 250 mL if urine < 0.625 mL/min; once the goals are met, only maintenance | paper Figs 11–12 |
| delayed | the REFRESH control 12 h later (challenge 56 h, protocol 58–64 h) | paper Fig 13 |
| bolus rate, norepinephrine | 50 mL/min; 14 µg/mL (the paper gives neither; from BioGears' `InfectionSevere.xml`) | BioGears |

The protocols are `viva_biogears.protocols.TreatmentProtocol`, reassessed every update from the last readings; the composite runs them as a `TreatmentController` step (`treatment=` parameter).

**Events** (`analyze.py`; a condition counts once it holds 30 min): lactate > 2 mM (paper: after 20 h); SBP < 100 mmHg (26 h); sepsis, SBP < 100 and RR ≥ 22/min (~30 h; the paper doesn't define its tachypnea threshold, 22/min is qSOFA's); septic shock, MAP < 65 and lactate > 2 mM (45 h); mean urine output < 0.625 mL/min; lowest SVR relative to baseline (about 60 %).

## Running

Each 48 h arm takes about 8 h of wall time (BioGears runs ~6× real time), so run the arms in parallel on a machine with enough cores, kept awake:

```sh
cd ~/projects/viva-biogears && source .venv/bin/activate
export BIOGEARS_RUNTIME=~/biogears-8.2.0-install/share/biogears/runtime
caffeinate -i python workspace/studies/mcdaniel-2019-sepsis/run.py all --jobs 4
python workspace/studies/mcdaniel-2019-sepsis/analyze.py      # any time, on partial results too
```

- `all` runs control, mild, moderate and severe in parallel, then the treatment arms (`challenge`, `antibiotic`, `refresh_control`, `refresh_experimental`, `refresh_control_delayed`, and `untreated`, severe continued to 64 h) from severe's 44 h checkpoint. Name arms instead of `all` to run fewer.
- A treatment arm saves its protocol's state with each checkpoint (`protocol@<t>s.json`), so a resumed arm continues the protocol too.
- Progress: `tail workspace/studies/mcdaniel-2019-sepsis/out/*/log.txt` (a line every 4 simulated hours).
- An interrupted arm resumes from its last checkpoint when you run the same command again. The process reads the infection from the checkpoint and skips the meals before it, so the resumed run continues the original (`tests/test_sepsis.py` checks this).

## Outputs (`out/`, not committed)

- `<arm>/data.csv`: one row per simulated minute: inflammation (pathogens, TNF, IL-6, IL-10, NO, tissue integrity), vitals, blood volume, urine, lactate, SVR, CO, SV, CVP, body fluids, plasma albumin, lymph return, the lymph pool, the 13 tissue lymph flows, muscle endothelial resistance, the saline and norepinephrine rates, saline given, antibiotic activity, and plasma piperacillin and blood norepinephrine.
- `<arm>/events.csv`: BioGears' patient events (SevereSepsis, Hypotension, ...).
- `summary.md`, `fig4.png` … `fig7.png`, `fig9.png` … `fig13.png` (`fig11.png` covers Figs 11–12), `fig_lymph.png`: from `analyze.py`.
