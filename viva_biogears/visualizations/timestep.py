"""TimestepHemorrhage and TimestepSepsis: the same run at BioGears time steps 0.02, 0.04
and 0.08 s, for the timestep-hemorrhage and timestep-sepsis studies.

Top row: each readout over time, one line per time step. Bottom row: each run minus the
0.02 s run (BioGears' validated step, the reference), so the error is readable even when
the lines overlap. Runs are told apart by ``engine.time_step_s``, which both composites
record.
"""

from process_bigraph.visualization import Visualization

from ._figure import MUTED, ORDINAL_BLUE, axis, layout, missing_runs, render

_REFERENCE = 0.02


def _figure(viz, state, panels, time_unit, title, caption):
    """``panels``: (input port, axis title). ``time_unit``: seconds per x unit and its name."""
    ports = ["time", "time_step", *[p for p, _ in panels]]
    error = missing_runs(state, {p: None for p in ports})
    if error:
        return error
    runs = sorted((dict(zip(ports, values)) for values in zip(*[state[p] for p in ports])),
                  key=lambda run: run["time_step"][0])
    reference = next((run for run in runs if abs(run["time_step"][0] - _REFERENCE) < 1e-9), None)
    colors = {}
    others = [run["time_step"][0] for run in runs if run is not reference]
    for i, dt in enumerate(others):
        colors[dt] = ORDINAL_BLUE[min(len(ORDINAL_BLUE) - 1, 2 + 2 * i)]
    scale, unit = time_unit
    n = len(panels)
    gap = 0.07
    width = (1.0 - gap * (n - 1)) / n
    traces, axes = [], {}
    for i, (port, label) in enumerate(panels):
        x0 = i * (width + gap)
        top, bottom = f"{2 * i + 1}", f"{2 * i + 2}"
        top = "" if top == "1" else top
        axes[f"xaxis{top}"] = axis("", domain=[x0, x0 + width], anchor=f"y{top}", matches=f"x{bottom}",
                                   showticklabels=False)
        axes[f"yaxis{top}"] = axis(label, domain=[0.45, 1.0], anchor=f"x{top}")
        axes[f"xaxis{bottom}"] = axis(f"Time ({unit})", domain=[x0, x0 + width], anchor=f"y{bottom}")
        axes[f"yaxis{bottom}"] = axis("minus the 0.02 s run", domain=[0.0, 0.33], anchor=f"x{bottom}")
        for run in runs:
            dt = run["time_step"][0]
            name = f"{dt:g} s" + (" (reference)" if run is reference else "")
            color = MUTED if run is reference else colors[dt]
            x = [t / scale for t in run["time"]]
            line = {"color": color, "width": 2, "dash": "dash" if run is reference else "solid"}
            traces.append({"x": x, "y": run[port], "xaxis": f"x{top}", "yaxis": f"y{top}", "type": "scatter",
                           "mode": "lines", "name": name, "legendgroup": name, "showlegend": i == 0, "line": line,
                           "hovertemplate": f"{name}<br>%{{x:.1f}} {unit}: %{{y:.4g}}<extra></extra>"})
            if reference is not None and run is not reference:
                k = min(len(run[port]), len(reference[port]))
                diff = [a - b for a, b in zip(run[port][:k], reference[port][:k])]
                traces.append({"x": x[:k], "y": diff, "xaxis": f"x{bottom}", "yaxis": f"y{bottom}",
                               "type": "scatter", "mode": "lines", "name": name, "legendgroup": name,
                               "showlegend": False, "line": line,
                               "hovertemplate": f"{name} − 0.02 s<br>%{{x:.1f}} {unit}: %{{y:.3g}}<extra></extra>"})
    figure = layout(title, height=560, legend={"orientation": "h", "y": -0.14, "font": {"size": 11}}, **axes)
    return render(viz.stable_div_id(), traces, figure, 560, caption)


def _demo(seconds, step, fn):
    t = [float(x) for x in range(0, seconds + 1, step)]
    return {"time": [t, t, t], "time_step": [[dt] * len(t) for dt in (0.02, 0.04, 0.08)],
            **fn(t)}


class TimestepHemorrhage(Visualization):
    """MAP, heart rate and blood volume of one hemorrhage at three BioGears time steps."""

    PANELS = (("mean_arterial_pressure", "MAP (mmHg)"), ("heart_rate", "Heart rate (1/min)"),
              ("blood_volume", "Blood volume (mL)"))

    def inputs(self):
        return {"time": "list[list[float]]", "time_step": "list[list[float]]",
                **{port: "list[list[float]]" for port, _ in self.PANELS}}

    @classmethod
    def demo(cls):
        def series(t):
            out = {p: [] for p, _ in cls.PANELS}
            for k in (0.0, 0.02, 0.1):
                out["mean_arterial_pressure"].append([95.9 - 0.02 * x * (1 + k) for x in t])
                out["heart_rate"].append([72 + 0.04 * x * (1 + k) for x in t])
                out["blood_volume"].append([5532 - 2.0 * x * (1 + k / 2) for x in t])
            return out
        return _demo(300, 5, series)

    def update(self, state):
        return _figure(self, state, self.PANELS, (60.0, "min"),
                       "Larger time steps: the same bleed, run faster, and how far it drifts",
                       "Right-leg hemorrhage (200 mL/min initial rate), BioGears StandardMale, 5 min, at time steps "
                       "0.02 s (BioGears' validated step, dashed), 0.04 and 0.08 s. Bottom: each run minus the "
                       "0.02 s run. (At 0.08 s BioGears crashes about 6.5 min into this bleed, so the runs stop at "
                       "5 min.)")


class TimestepSepsis(Visualization):
    """MAP, lactate and blood volume of the severe infection at three BioGears time steps."""

    PANELS = (("mean_arterial_pressure", "MAP (mmHg)"), ("lactate", "Lactate (mM)"),
              ("blood_volume", "Blood volume (mL)"))

    def inputs(self):
        return {"time": "list[list[float]]", "time_step": "list[list[float]]",
                **{port: "list[list[float]]" for port, _ in self.PANELS}}

    @classmethod
    def demo(cls):
        def series(t):
            out = {p: [] for p, _ in cls.PANELS}
            for k in (0.0, 0.5, 4.0):
                out["mean_arterial_pressure"].append([95.9 - x / 3600 * (1 + k) for x in t])
                out["lactate"].append([0.9 + 0.1 * x / 3600 * (1 + 5 * k) for x in t])
                out["blood_volume"].append([5532 - 5 * x / 3600 * (1 + k) for x in t])
            return out
        return _demo(6 * 3600, 600, series)

    def update(self, state):
        return _figure(self, state, self.PANELS, (3600.0, "h"),
                       "Larger time steps in a slow process: the severe infection's first 6 h",
                       "Severe Skin infection, BioGears StandardMale with the InfectionModerate water and meal "
                       "schedule, 6 h at 60 s updates, at time steps 0.02 s (BioGears' validated step, dashed), "
                       "0.04 and 0.08 s. Bottom: each run minus the 0.02 s run.")
