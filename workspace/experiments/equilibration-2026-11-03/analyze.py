"""Summarize the equilibration probe: drift per hour of each fluid quantity, by condition.

    python analyze.py OUTDIR      -> prints a table and writes OUTDIR/summary.md
"""
import csv
import sys
from pathlib import Path

import numpy as np

COLS = ["LymphPool", "LymphReturn", "CVP", "BloodVolume", "ExtravascularFluid", "IntracellularFluid",
        "TotalBodyFluid", "UrineRate", "MAP", "HR", "Albumin"]


def load(path):
    rows = list(csv.reader(open(path)))
    head, data = rows[0], np.array(rows[1:], dtype=float)
    return {h: data[:, i] for i, h in enumerate(head)}


def slope_per_h(t_min, y, t0, t1):
    m = (t_min >= t0) & (t_min <= t1)
    return np.polyfit(t_min[m] / 60.0, y[m], 1)[0] if m.sum() > 2 else float("nan")


def main():
    out = Path(sys.argv[1])
    lines = []
    for cond in ("none", "water"):
        f = out / f"{cond}.csv"
        if not f.exists():
            continue
        d = load(f)
        t = d["t_min"]
        end = t[-1]
        lines.append(f"\n### {cond} (0 to {end:.0f} min)\n")
        lines.append("| quantity | t=0 | end | drift/h, first hour | drift/h, last hour |")
        lines.append("|---|---|---|---|---|")
        for c in COLS:
            y = d[c]
            lines.append(f"| {c} | {y[0]:.4g} | {y[-1]:.4g} | {slope_per_h(t, y, 0, 60):+.3g} | "
                         f"{slope_per_h(t, y, end - 60, end):+.3g} |")
    text = "\n".join(lines)
    print(text)
    (out / "summary.md").write_text(text.lstrip() + "\n")


if __name__ == "__main__":
    main()
