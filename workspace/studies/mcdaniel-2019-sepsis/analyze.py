"""Analysis of the McDaniel 2019 replication runs (run.py's output).

    python analyze.py [OUT]     (default: ./out)

Ported from pybiogears studies/mcdaniel2019/analyze.py; run.py writes the same columns.

Writes OUT/summary.md (event timings vs the paper, lymph and fluid numbers) and
OUT/fig4.png ... fig9.png, fig_lymph.png. Works on partial runs (whatever hours exist).
"""
import sys
from pathlib import Path

import numpy as np

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "out"
RUNS = ["control", "mild", "moderate", "severe"]
COLORS = {"control": "0.5", "mild": "#2a9d8f", "moderate": "#e9c46a", "severe": "#e76f51", "challenge": "#264653"}
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


data = {r: load(r) for r in RUNS + ["challenge"]}
lines = ["# McDaniel et al. 2019 replication on BioGears 8.2.0: summary", ""]
for r in RUNS + ["challenge"]:
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
    lines += ["", "## Fluid challenge (1000 mL saline, 44–45 h)", "", "| t (h) | SBP | MAP | HR | mean urine mL/min | blood vol mL | lymph return mL/min |", "|---|---|---|---|---|---|---|"]
    for hh in [44.0, 44.5, 45.0, 45.5, 46.0]:
        i = int(np.argmin(np.abs(c["t_h"] - hh)))
        if abs(c["t_h"][i] - hh) < 0.05:
            lines.append(f"| {hh} | {c['SBP'][i]:.1f} | {c['MAP'][i]:.1f} | {c['HR'][i]:.0f} | {c['MeanUrineOutput'][i]:.3f} | "
                         f"{c['BloodVolume'][i]:.0f} | {c['LymphReturn'][i]:.2f} |")
    lines.append("")
    lines.append("Paper (Fig 9): compared with the REFRESH goals SBP 90 mmHg and urine output 0.625 mL/min.")
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
if data["challenge"] is not None:
    c = data["challenge"]
    fig, axes = plt.subplots(1, 4, figsize=(14, 3))
    for ax, col, lab, ref in zip(axes, ["SBP", "MAP", "MeanUrineOutput", "HR"],
                                 ["SBP (mmHg)", "MAP (mmHg)", "mean urine (mL/min)", "HR (1/min)"], [90, 65, 0.625, None]):
        ax.plot(c["t_h"], c[col], color=COLORS["challenge"])
        if ref is not None:
            ax.axhline(ref, color="k", ls=":", lw=0.8)
        for x in (44.0, 44.5):
            ax.axvline(x, color="0.7", lw=0.6)
        ax.set_ylabel(lab, fontsize=8)
        ax.set_xlabel("time since infection (h)", fontsize=8)
    fig.suptitle("Fig 9 analogue: 1000 mL saline challenge at 44 h", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig9.png", dpi=110)
    plt.close(fig)
