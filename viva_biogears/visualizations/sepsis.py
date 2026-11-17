"""Figures for the McDaniel et al. 2019 studies: SepsisProgression (Figs 4-7) and
SepsisTreatmentResponse (Figs 9-13).

A Visualization gets no run names, so the runs are told apart from their data: the
progression arms by their peak blood pathogen (none for the control, then rising with
severity), the treatment arms by ``protocol.code`` (every biogears_sepsis run records it)
and, for the delayed REFRESH arm, by its treatment start hour.

The treatment figure follows the paper (Fig 10: "0 h post-antibiotics" = 46 h): time is
hours since each arm's treatment start, from the engine hour the run started at
(``protocol.branch_h``, 44 for a run from the saved septic state) and the arm's
``protocol.treatment_start_h``. So arms started from different states, or delayed, line up.
"""

from process_bigraph.visualization import Visualization

from ..protocols import PROTOCOLS
from ._figure import CATEGORICAL, MUTED, axis, layout, missing_runs, render

#: Extra categorical slots after _figure.CATEGORICAL, for up to six arms.
_MORE = ["#9b59b6", "#c0392b", "#16a085"]
_COLORS = [*CATEGORICAL, *_MORE]
_SEVERITY_NAMES = ["control", "mild", "moderate", "severe"]
_PROTOCOL_NAMES = {"none": "untreated", "fluid_challenge": "fluid challenge", "antibiotic": "challenge + antibiotic",
                   "refresh_control": "REFRESH control", "refresh_experimental": "REFRESH experimental"}


def _hours(times):
    return [t / 3600.0 for t in times]


def _grid(panels, ncol=2, xlabel="Time since infection (h)"):
    """Axis layouts for a ``ncol``-wide grid of len(panels) small multiples sharing x."""
    nrow = (len(panels) + ncol - 1) // ncol
    gap_x, gap_y = 0.08, 0.07
    width = (1.0 - gap_x * (ncol - 1)) / ncol
    height = (1.0 - gap_y * (nrow - 1)) / nrow
    axes, shapes = {}, []
    for i, (title, ref) in enumerate(panels):
        r, c = divmod(i, ncol)
        n = "" if i == 0 else str(i + 1)
        x0 = c * (width + gap_x)
        y1 = 1.0 - r * (height + gap_y)
        last_row = r == nrow - 1 or i + ncol >= len(panels)
        axes[f"xaxis{n}"] = axis(xlabel if last_row else "", domain=[x0, x0 + width],
                                 anchor=f"y{n}", matches="x" if i else None, showticklabels=last_row)
        axes[f"yaxis{n}"] = axis(title, domain=[y1 - height, y1], anchor=f"x{n}")
        if ref is not None:
            shapes.append({"type": "line", "xref": f"x{n} domain", "yref": f"y{n}", "x0": 0, "x1": 1, "y0": ref,
                           "y1": ref, "line": {"color": MUTED, "width": 1, "dash": "dot"}})
    for v in axes.values():
        if v.get("matches") is None:
            v.pop("matches", None)
    return axes, shapes, nrow


def _traces(runs, keys, names, colors):
    traces = []
    for i, key in enumerate(keys):
        n = "" if i == 0 else str(i + 1)
        for run, name, color in zip(runs, names, colors):
            traces.append({"x": run.get("x") or _hours(run["time"]), "y": run[key], "xaxis": f"x{n}", "yaxis": f"y{n}",
                           "type": "scatter", "mode": "lines", "name": name, "legendgroup": name,
                           "showlegend": i == 0,
                           "line": {"color": color, "width": 1.8, "dash": "dash" if color == MUTED else "solid"},
                           "hovertemplate": f"{name}<br>%{{x:.1f}} h: %{{y:.3g}}<extra></extra>"})
    return traces


class SepsisProgression(Visualization):
    """Inflammation and clinical signs over 48 h for the uninfected control and the three
    infection severities (McDaniel et al. 2019, Figs 4-7)."""

    PANELS = (("blood_pathogen", "Blood pathogen", None), ("tissue_integrity", "Tissue integrity", None),
              ("mean_arterial_pressure", "MAP (mmHg)", 65.0), ("systolic_pressure", "SBP (mmHg)", 100.0),
              ("lactate", "Lactate (mM)", 2.0), ("blood_volume", "Blood volume (mL)", None))

    def inputs(self):
        return {"time": "list[list[float]]", **{key: "list[list[float]]" for key, _, _ in self.PANELS}}

    @classmethod
    def demo(cls):
        t = [h * 3600.0 for h in range(0, 49, 2)]
        out = {key: [] for key in ["time", *[k for k, _, _ in cls.PANELS]]}
        for s in range(4):
            f = [min(1.0, h / 48.0) * s / 3 for h in range(0, 49, 2)]
            out["time"].append(list(t))
            out["blood_pathogen"].append([60 * x * x if s else 0.0 for x in f])
            out["tissue_integrity"].append([1 - 0.7 * x * x for x in f])
            out["mean_arterial_pressure"].append([96 - 24 * x * x for x in f])
            out["systolic_pressure"].append([115 - 33 * x * x for x in f])
            out["lactate"].append([1.4 + 0.9 * x for x in f])
            out["blood_volume"].append([5530 - 1640 * x * x for x in f])
        return out

    def update(self, state):
        error = missing_runs(state, self.inputs())
        if error:
            return error
        keys = [k for k, _, _ in self.PANELS]
        runs = [dict(zip(["time", *keys], values)) for values in zip(state["time"], *[state[k] for k in keys])]
        runs.sort(key=lambda run: max(run["blood_pathogen"]))
        if len(runs) == 4 and max(runs[0]["blood_pathogen"]) == 0:
            names = list(_SEVERITY_NAMES)
        else:                                 # not the study's four arms: don't guess names
            names = [f"run {i + 1}" for i in range(len(runs))]
        colors = [MUTED if n == "control" else _COLORS[i % len(_COLORS)] for i, n in enumerate(names)]
        axes, shapes, nrow = _grid([(title, ref) for _, title, ref in self.PANELS])
        height = 260 * nrow + 80
        caption = ("Severe, moderate and mild Skin infection and an uninfected control, BioGears 8.2.0 "
                   "StandardMale with the InfectionModerate water and meal schedule. Dotted lines: MAP 65 "
                   "(septic shock with lactate > 2), SBP 100, lactate 2 mM. Runs are ordered by their peak "
                   "blood pathogen.")
        figure = layout("Only the severe infection decompensates", height=height, shapes=shapes,
                        legend={"orientation": "h", "y": -0.08, "font": {"size": 11}}, **axes)
        return render(self.stable_div_id(), _traces(runs, keys, names, colors), figure, height, caption)


class SepsisTreatmentResponse(Visualization):
    """Pressure, urine output, pathogen and saline given for the treatment arms of the
    severe infection, against hours since each arm's treatment start (McDaniel et al.
    2019, Figs 9-13)."""

    PANELS = (("mean_arterial_pressure", "MAP (mmHg)", 65.0), ("systolic_pressure", "SBP (mmHg)", 90.0),
              ("mean_urine_output", "Mean urine output (mL/min)", 0.625), ("blood_pathogen", "Blood pathogen", None),
              ("saline_given", "Saline given (mL)", None))
    CLOCK = ("protocol_code", "branch_h", "treatment_start_h")

    def inputs(self):
        return {"time": "list[list[float]]", **{key: "list[list[float]]" for key in self.CLOCK},
                **{key: "list[list[float]]" for key, _, _ in self.PANELS}}

    @classmethod
    def demo(cls):
        out = {key: [] for key in ["time", *cls.CLOCK, *[k for k, _, _ in cls.PANELS]]}
        for code, start, length in ((0, 46.0, 8), (3, 46.0, 8), (4, 46.0, 8), (3, 58.0, 20)):
            hs = [44.0 + m / 4 for m in range(length * 4 + 1)]
            out["time"].append([(h - 44.0) * 3600.0 for h in hs])
            out["protocol_code"].append([float(code)] * len(hs))
            out["branch_h"].append([44.0] * len(hs))
            out["treatment_start_h"].append([start] * len(hs))
            lift = [0.0 if code == 0 or h < start else min(1.0, (h - start) / 2) for h in hs]
            out["mean_arterial_pressure"].append([96 - 24 * (h / 52) ** 2 + 8 * x for h, x in zip(hs, lift)])
            out["systolic_pressure"].append([115 - 33 * (h / 52) ** 2 + 10 * x for h, x in zip(hs, lift)])
            out["mean_urine_output"].append([1.5 - 0.3 * h / 52 + 0.4 * x for h, x in zip(hs, lift)])
            out["blood_pathogen"].append([60 * (h / 52) ** 2 * (1 - 0.8 * x) for h, x in zip(hs, lift)])
            out["saline_given"].append([0.0 if code == 0 else (3000 if code == 3 else 1500) * x for x in lift])
        return out

    def update(self, state):
        error = missing_runs(state, self.inputs())
        if error:
            return error
        keys = [*self.CLOCK, *[k for k, _, _ in self.PANELS]]
        runs = [dict(zip(["time", *keys], values)) for values in zip(state["time"], *[state[k] for k in keys])]
        names = []
        for run in runs:
            code = round(run["protocol_code"][-1])
            start, branch = run["treatment_start_h"][0], run["branch_h"][0]
            run["x"] = [branch + (t - run["time"][0]) / 3600.0 - start for t in run["time"]]
            name = _PROTOCOL_NAMES.get(PROTOCOLS[code] if 0 <= code < len(PROTOCOLS) else "", f"protocol {code}")
            if code and start > 50.0:
                name += f" (delayed, from {start:g} h)"
            names.append(name)
        order = sorted(range(len(runs)), key=lambda i: (runs[i]["protocol_code"][-1], names[i]))
        runs, names = [runs[i] for i in order], [names[i] for i in order]
        colors = [MUTED if n == "untreated" else _COLORS[i % len(_COLORS)] for i, n in enumerate(names)]
        panels = [(title, ref) for _, title, ref in self.PANELS]
        axes, shapes, nrow = _grid(panels, xlabel="Time since treatment start (h)")
        for i in range(len(panels)):                   # treatment start
            n = "" if i == 0 else str(i + 1)
            shapes.append({"type": "line", "xref": f"x{n}", "yref": f"y{n} domain", "x0": 0, "x1": 0, "y0": 0,
                           "y1": 1, "line": {"color": MUTED, "width": 1}})
        height = 260 * nrow + 80
        starts = sorted({run["treatment_start_h"][0] for run in runs})
        caption = ("Severe Skin infection, BioGears 8.2.0 StandardMale, each arm started from the untreated "
                   f"infection's saved state; time 0 is each arm's treatment start ({', '.join(f'{h:g}' for h in starts)}"
                   " h after infection; for the fluid challenge, the first bolus). Protocols: the 2 x 500 mL "
                   "challenge, piperacillin/tazobactam, and the REFRESH control (liberal boluses) and experimental "
                   "(norepinephrine, restricted fluid) protocols for 6 h. Dotted lines: the REFRESH goals (MAP 65, "
                   "SBP 90 mmHg, urine 0.625 mL/min).")
        figure = layout("Treatment of the severe infection", height=height, shapes=shapes,
                        legend={"orientation": "h", "y": -0.08, "font": {"size": 11}}, **axes)
        return render(self.stable_div_id(), _traces(runs, keys[len(self.CLOCK):], names, colors), figure, height,
                      caption)
