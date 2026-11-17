"""Analysis of the McDaniel 2019 replication runs (run.py's output).

    python analyze.py [OUT]     (default: ./out)

Ported from pybiogears studies/mcdaniel2019/analyze.py; run.py writes the same columns.

Writes OUT/summary.md (event timings vs the paper, lymph and fluid numbers, the
treatment arms) and OUT/fig4.png ... fig13.png, fig_lymph.png. Works on partial runs
(whatever hours and arms exist). As in the paper, Fig 9 is in hours after infection and
Figs 10-13 in hours since the treatment start (Fig 10: "0 h post-antibiotics" = 46 h).
"""
import sys
from pathlib import Path

import numpy as np

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "out"
RUNS = ["control", "mild", "moderate", "severe"]
TREATED = ["challenge", "antibiotic", "refresh_control", "refresh_experimental", "refresh_control_delayed", "untreated"]
COLORS = {"control": "0.5", "mild": "#2a9d8f", "moderate": "#e9c46a", "severe": "#e76f51", "challenge": "#264653",
          "antibiotic": "#8e44ad", "refresh_control": "#2a78d6", "refresh_experimental": "#eb6834",
          "refresh_control_delayed": "#1baf7a", "untreated": "0.35"}
#: Treatment start (h) of each REFRESH arm, for the summary and Fig 13.
STARTS = {"antibiotic": 46.0, "refresh_control": 46.0, "refresh_experimental": 46.0, "refresh_control_delayed": 58.0}
LYMPH_TISSUES = ["Bone", "Brain", "Fat", "Gut", "LeftKidney", "LeftLung", "Liver", "Muscle",
                 "Myocardium", "RightKidney", "RightLung", "Skin", "Spleen"]


def load(run):
    f = OUT / run / "data.csv"
    if not f.exists():
        return None
    d = np.genfromtxt(f, delimiter=",", names=True)
    d = np.atleast_1d(d)
    return {k: d[k] for k in d.dtype.names}


def first_time(t, cond, sustain_h=0.0):
    """First time cond holds and keeps holding for sustain_h (None if never)."""
    idx = np.flatnonzero(cond)
    for i in idx:
        j = np.searchsorted(t, t[i] + sustain_h, side="right")
        if np.all(cond[i:j]):
            return float(t[i])
    return None


def fmt(x, unit="h"):
    return "not reached" if x is None else f"{x:.1f} {unit}"


def events(run):
    f = OUT / run / "events.csv"
    if not f.exists():
        return []
    rows = [line.strip().split(",") for line in f.read_text().splitlines()[1:] if line.strip()]
    return [(float(t), e, a == "1") for t, e, a in rows]


data = {r: load(r) for r in RUNS + TREATED}
lines = ["# McDaniel et al. 2019 replication on BioGears 8.2.0: summary", ""]
for r in RUNS + TREATED:
    d = data[r]
    lines.append(f"- {r}: " + ("no data" if d is None else f"{d['t_h'][0]:.1f}–{d['t_h'][-1]:.1f} h, {len(d['t_h'])} rows"))

# Event timings (severe, untreated) vs the paper ------------------------------------
s = data["severe"]
if s is not None:
    t = s["t_h"]
    lac = first_time(t, s["Lactate"] > 2.0, 0.5)
    sbp = first_time(t, s["SBP"] < 100.0, 0.5)
    rr = first_time(t, s["RR"] >= 22.0, 0.5)
    sepsis = first_time(t, (s["SBP"] < 100.0) & (s["RR"] >= 22.0), 0.5)
    mapl = first_time(t, s["MAP"] < 65.0, 0.5)
    shock = first_time(t, (s["MAP"] < 65.0) & (s["Lactate"] > 2.0), 0.5)
    uo = first_time(t, s["MeanUrineOutput"] < 0.625, 0.5)
    svr_min = float(np.nanmin(s["SVR"][t >= 1]) / s["SVR"][0]) if len(t) > 60 else float("nan")
    lines += ["", "## Severe infection, untreated: event times (sustained ≥ 30 min)", "",
              "| event | paper (McDaniel 2019) | this run (8.2.0) |", "|---|---|---|",
              f"| lactate > 2 mM | after 20 h | {fmt(lac)} |",
              f"| SBP < 100 mmHg | 26 h | {fmt(sbp)} |",
              f"| tachypnea (RR ≥ 22/min) | (part of sepsis criterion) | {fmt(rr)} |",
              f"| sepsis (SBP < 100 and tachypnea) | ~30 h | {fmt(sepsis)} |",
              f"| MAP < 65 mmHg | 45 h (septic shock) | {fmt(mapl)} |",
              f"| septic shock (MAP < 65 and lactate > 2 mM) | 45 h | {fmt(shock)} |",
              f"| mean urine output < 0.625 mL/min | reported (Fig 7) | {fmt(uo)} |",
              f"| lowest SVR / baseline | approached 60 % | {svr_min:.0%} |", ""]
    ev = [e for e in events("severe") if e[2] and e[1] not in ("MildDiarrhea", "MildHeadache", "Nausea")]
    seen = {}
    for tt, e, a in ev:
        seen.setdefault(e, tt)
    lines.append("BioGears events (first onset): " + (", ".join(f"{e} {tt:.1f} h" for e, tt in sorted(seen.items(), key=lambda x: x[1])) or "none"))

# Lymph and tissue fluid --------------------------------------------------------------
lines += ["", "## Lymph and tissue fluid", "",
          "| run | t (h) | lymph return mL/min (L/day) | formation mL/min (L/day) | lymph pool mL | blood vol mL | extravascular mL | albumin g/dL | muscle endothelial R | tissue integrity |",
          "|---|---|---|---|---|---|---|---|---|---|"]
for r in RUNS:
    d = data[r]
    if d is None:
        continue
    form = sum(d[f"{x}Lymph"] for x in LYMPH_TISSUES)
    for hh in [0, 6, 12, 24, 36, 48]:
        if hh > d["t_h"][-1] + 1e-6:
            continue
        w = (d["t_h"] >= hh - 0.25) & (d["t_h"] <= hh + 0.25)  # 30-min window smooths pulsatile flows
        if not w.any():
            continue
        m = lambda k: float(np.mean(d[k][w]))
        fm = float(np.mean(form[w]))
        lines.append(f"| {r} | {hh} | {m('LymphReturn'):.2f} ({m('LymphReturn') * 1.44:.1f}) | {fm:.2f} ({fm * 1.44:.1f}) | "
                     f"{m('LymphPool'):.0f} | {m('BloodVolume'):.0f} | {m('ExtravascularFluid'):.0f} | {m('Albumin'):.2f} | "
                     f"{m('MuscleEndothelialResistance'):.3g} | {m('TissueIntegrity'):.3f} |")
lines.append("")
lines.append("Paper: \"the total amount of fluid filtered and returned by the lymph amounts to 4.0 L/day\" at steady state.")

c = data["challenge"]
if c is not None:
    lines += ["", "## Fluid challenge (2 x 500 mL saline at 50 mL/min, 44 and 44.5 h)", "", "| t (h) | SBP | MAP | HR | mean urine mL/min | blood vol mL | lymph return mL/min |", "|---|---|---|---|---|---|---|"]
    for hh in [44.0, 44.5, 45.0, 45.5, 46.0]:
        i = int(np.argmin(np.abs(c["t_h"] - hh)))
        if abs(c["t_h"][i] - hh) < 0.05:
            lines.append(f"| {hh} | {c['SBP'][i]:.1f} | {c['MAP'][i]:.1f} | {c['HR'][i]:.0f} | {c['MeanUrineOutput'][i]:.3f} | "
                         f"{c['BloodVolume'][i]:.0f} | {c['LymphReturn'][i]:.2f} |")
    lines.append("")
    lines.append("Paper (Fig 9): compared with the REFRESH goals SBP 90 mmHg and urine output 0.625 mL/min.")
have = [r for r in STARTS if data[r] is not None]
if have:
    lines += ["", "## Antibiotic and REFRESH protocols (Figs 10-13)", "",
              "| arm | start (h) | to (h) | saline given (mL) | goals met (SBP > 90, MAP > 65) | MAP at start / end | "
              "blood pathogen at start / end | peak piperacillin (ug/mL) |", "|---|---|---|---|---|---|---|---|"]
    for r in have:
        d, st = data[r], STARTS[r]
        t = d["t_h"]
        i0 = int(np.argmin(np.abs(t - st)))
        met = first_time(t[i0:], (d["SBP"][i0:] > 90.0) & (d["MAP"][i0:] > 65.0))
        lines.append(f"| {r} | {st:g} | {t[-1]:.1f} | {np.nanmax(d['SalineGiven']):.0f} | {fmt(met)} | "
                     f"{d['MAP'][i0]:.1f} / {d['MAP'][-1]:.1f} | {d['BloodPathogen'][i0]:.3g} / {d['BloodPathogen'][-1]:.3g} | "
                     f"{np.nanmax(d['Piperacillin']):.1f} |")
    lines += ["", "Paper: both REFRESH protocols reach the goals, the experimental one with less fluid (Figs 11-12); "
              "the control protocol delayed 12 h needs more (Fig 13). Piperacillin MIC 16 mg/L (Fig 10)."]
(OUT / "summary.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))

# Figures --------------------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    sys.exit(0)


def panel_fig(name, cols, runs, title, ylabels=None, hlines=None):
    have = [r for r in runs if data[r] is not None]
    if not have:
        return
    n = len(cols)
    ncol = 3 if n > 4 else 2
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(4.2 * ncol, 2.8 * nrow), squeeze=False, sharex=True)
    for i, col in enumerate(cols):
        ax = axes.flat[i]
        for r in have:
            ax.plot(data[r]["t_h"], data[r][col], color=COLORS[r], label=r, lw=1.2)
        for y in (hlines or {}).get(col, []):
            ax.axhline(y, color="k", ls=":", lw=0.8)
        ax.set_ylabel((ylabels or {}).get(col, col), fontsize=8)
        ax.tick_params(labelsize=7)
    for ax in axes.flat[n:]:
        ax.axis("off")
    for ax in axes[-1]:
        ax.set_xlabel("time since infection (h)", fontsize=8)
    axes.flat[0].legend(fontsize=7)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", dpi=110)
    plt.close(fig)


sev = ["mild", "moderate", "severe"]
panel_fig("fig4", ["BloodPathogen", "TNF", "IL6", "IL10", "NO", "TissueIntegrity"], sev,
          "Fig 4 analogue: acute inflammatory response (arbitrary units)")
panel_fig("fig5", ["HR", "RR", "CoreTemperature", "WBC"], ["control"] + sev, "Fig 5 analogue: vitals vs infection severity",
          {"HR": "HR (1/min)", "RR": "RR (1/min)", "CoreTemperature": "core T (°C)", "WBC": "WBC (ct/µL)"})
panel_fig("fig6", ["BloodVolume", "SBP", "MAP", "SVR", "HR"], ["control", "severe"], "Fig 6 analogue: severe infection, part 1",
          {"BloodVolume": "blood volume (mL)", "SBP": "SBP (mmHg)", "MAP": "MAP (mmHg)", "SVR": "SVR (mmHg s/mL)", "HR": "HR (1/min)"},
          {"SBP": [100], "MAP": [65]})
panel_fig("fig7", ["MeanUrineOutput", "Lactate", "CardiacOutput", "StrokeVolume"], ["control", "severe"],
          "Fig 7 analogue: severe infection, part 2",
          {"MeanUrineOutput": "mean urine (mL/min)", "Lactate": "lactate (mM)", "CardiacOutput": "CO (L/min)", "StrokeVolume": "SV (mL)"},
          {"MeanUrineOutput": [0.625], "Lactate": [2.0]})
for r in RUNS:
    if data[r] is not None:
        data[r]["LymphFormation"] = sum(data[r][f"{x}Lymph"] for x in LYMPH_TISSUES)
panel_fig("fig_lymph", ["LymphFormation", "LymphReturn", "LymphPool", "ExtravascularFluid", "Albumin", "MuscleEndothelialResistance"],
          ["control"] + sev, "Lymph and tissue fluid vs infection severity",
          {"LymphFormation": "lymph formation (mL/min)", "LymphReturn": "lymph return (mL/min)", "LymphPool": "lymph pool (mL)",
           "ExtravascularFluid": "extravascular fluid (mL)", "Albumin": "plasma albumin (g/dL)",
           "MuscleEndothelialResistance": "muscle endothelial R (mmHg min/mL)"},
          {"LymphFormation": [4000 / 1440], "LymphReturn": [4000 / 1440]})


def arm_fig(name, cols, runs, title, ylabels, refs=None, shift=None, xlabel="time since infection (h)", xlim=None):
    """One row of panels for the treatment arms; ``shift`` maps an arm to the hours
    subtracted from its time axis (Fig 13 aligns arms on their protocol start)."""
    have = [r for r in runs if data[r] is not None]
    if not have:
        return
    ncol = min(4, len(cols))
    nrow = int(np.ceil(len(cols) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.6 * ncol, 2.8 * nrow), squeeze=False)
    for ax, col in zip(axes.flat, cols):
        for r in have:
            d = data[r]
            x = d["t_h"] - (shift or {}).get(r, 0.0)
            keep = np.ones_like(x, dtype=bool) if xlim is None else (x >= xlim[0]) & (x <= xlim[1])
            ax.plot(x[keep], d[col][keep], color=COLORS[r], label=r.replace("_", " "), lw=1.2)
        if (refs or {}).get(col) is not None:
            ax.axhline(refs[col], color="k", ls=":", lw=0.8)
        ax.set_ylabel(ylabels.get(col, col), fontsize=8)
        ax.set_xlabel(xlabel, fontsize=8)
        ax.tick_params(labelsize=7)
    for ax in axes.flat[len(cols):]:
        ax.axis("off")
    axes.flat[0].legend(fontsize=7)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", dpi=110)
    plt.close(fig)


LAB = {"SBP": "SBP (mmHg)", "MAP": "MAP (mmHg)", "MeanUrineOutput": "mean urine (mL/min)", "HR": "HR (1/min)",
       "BloodVolume": "blood volume (mL)", "SalineGiven": "saline given (mL)", "VasopressorRate": "norepinephrine (ug/min)",
       "BloodPathogen": "blood pathogen", "Piperacillin": "piperacillin (ug/mL)", "AntibioticActivity": "antibiotic activity",
       "Lactate": "lactate (mM)"}
REFS = {"SBP": 90.0, "MAP": 65.0, "MeanUrineOutput": 0.625, "Piperacillin": 16.0, "Lactate": 2.0}
arm_fig("fig9", ["SBP", "MAP", "MeanUrineOutput", "HR", "BloodVolume"], ["untreated", "challenge"],
        "Fig 9 analogue: 2 x 500 mL saline challenge at 44 and 44.5 h", LAB, REFS, xlim=(43.5, 46.0))
arm_fig("fig10", ["Piperacillin", "AntibioticActivity", "BloodPathogen", "MAP"], ["challenge", "antibiotic"],
        "Fig 10 analogue: piperacillin/tazobactam 4.5 g over 30 min at 46 h (MIC 16 mg/L)", LAB, REFS,
        shift={"challenge": 46.0, "antibiotic": 46.0}, xlabel="time since antibiotic start (h)", xlim=(-2.0, 6.0))
arm_fig("fig11", ["SBP", "MAP", "MeanUrineOutput", "Lactate", "SalineGiven", "VasopressorRate", "BloodVolume",
                  "BloodPathogen"], ["untreated", "refresh_control", "refresh_experimental"],
        "Figs 11-12 analogue: REFRESH control (liberal fluid) vs experimental (norepinephrine, restricted fluid)",
        LAB, REFS, shift={"untreated": 46.0, "refresh_control": 46.0, "refresh_experimental": 46.0},
        xlabel="time since protocol start (h)", xlim=(-2.0, 6.0))
arm_fig("fig13", ["SBP", "MAP", "MeanUrineOutput", "SalineGiven"], ["refresh_control", "refresh_control_delayed"],
        "Fig 13 analogue: the REFRESH control protocol on time (46 h) and delayed 12 h (58 h)", LAB, REFS,
        shift={"refresh_control": 46.0, "refresh_control_delayed": 58.0}, xlabel="time since protocol start (h)",
        xlim=(-2.0, 6.0))
