"""HemorrhageSeverityResponse: final vitals against the initial bleed rate, plus MAP over time.

For the hemorrhage-severity-sweep study. BioGears takes a bleed as an initial rate
(mL/min, falling with local pressure), so the x axis is that rate.
"""

import math

from process_bigraph.visualization import Visualization

from ._figure import (
    AXIS,
    CATEGORICAL,
    MUTED,
    ORDINAL_BLUE,
    axis,
    layout,
    missing_runs,
    render,
)

_DEMO_RATES = [0.0, 50.0, 100.0, 150.0, 200.0, 250.0]


def _demo(fn):
    return [[fn(s, t) for t in range(0, 601, 120)] for s in _DEMO_RATES]


class HemorrhageSeverityResponse(Visualization):
    """Small multiples of final blood loss, heart rate and MAP vs initial bleed rate, and MAP vs time."""

    def inputs(self):
        return {
            "time": "list[list[float]]",
            "bleed_rate": "list[list[float]]",
            "mean_arterial_pressure": "list[list[float]]",
            "heart_rate": "list[list[float]]",
            "hemorrhaged_volume": "list[list[float]]",
        }

    @classmethod
    def demo(cls):
        return {
            "time": _demo(lambda s, t: float(t)),
            "bleed_rate": _demo(lambda s, t: s),
            "mean_arterial_pressure": _demo(lambda s, t: 94.0 - 0.08 * max(0.0, s - 100) * t / 600),
            "heart_rate": _demo(lambda s, t: 72 + 0.15 * s * t / 600),
            "hemorrhaged_volume": _demo(lambda s, t: 7 * s * t / 600),
        }

    def update(self, state):
        error = missing_runs(state, self.inputs())
        if error:
            return error
        # BioGears reports blood lost as NaN until a bleed starts (all of the no-bleed run).
        state = {**state, "hemorrhaged_volume": [[0.0 if math.isnan(v) else v for v in run]
                                                 for run in state["hemorrhaged_volume"]]}
        runs = sorted(zip(state["bleed_rate"], state["time"], state["mean_arterial_pressure"],
                          state["heart_rate"], state["hemorrhaged_volume"]),
                      key=lambda run: run[0][-1])
        rate = [run[0][-1] for run in runs]
        finals = {
            "lost": [run[4][-1] for run in runs],
            "hr": [run[3][-1] for run in runs],
            "map": [run[2][-1] for run in runs],
        }
        start_map = runs[0][2][0]

        traces = []
        panels = [("lost", "Blood lost (mL)", "x", "y"),
                  ("hr", "Heart rate (1/min)", "x2", "y2"),
                  ("map", "MAP (mmHg)", "x3", "y3")]
        for key, title, xa, ya in panels:
            traces.append({
                "x": rate, "y": finals[key], "xaxis": xa, "yaxis": ya,
                "type": "scatter", "mode": "lines+markers", "name": title, "showlegend": False,
                "line": {"color": CATEGORICAL[0], "width": 2}, "marker": {"size": 8},
                "hovertemplate": f"bleed %{{x}} mL/min<br>{title} at 10 min: %{{y:.1f}}<extra></extra>",
            })

        bleeding = [run for run in runs if run[0][-1] > 0.0]
        colors = ORDINAL_BLUE[-len(bleeding):] if bleeding else []
        for run in runs:
            level = run[0][-1]
            color = MUTED if level == 0.0 else colors[bleeding.index(run)]
            traces.append({
                "x": [t / 60.0 for t in run[1]], "y": run[2], "xaxis": "x4", "yaxis": "y4",
                "type": "scatter", "mode": "lines", "name": f"{level:g} mL/min",
                "line": {"color": color, "width": 2, "dash": "dash" if level == 0.0 else "solid"},
                "hovertemplate": f"{level:g} mL/min<br>%{{x:.1f}} min: %{{y:.1f}} mmHg<extra></extra>",
            })

        band = {"type": "rect", "xref": "x3 domain", "yref": "y3", "x0": 0, "x1": 1,
                "y0": start_map - 2, "y1": start_map + 2, "fillcolor": AXIS, "opacity": 0.35,
                "line": {"width": 0}, "layer": "below"}
        caption = ("Right-leg hemorrhage, StandardMale, 10 min per run. Top: values at 10 min against "
                   "the initial bleed rate (BioGears lowers the rate as local pressure falls); the gray "
                   "band is the starting MAP ±2 mmHg, which every bleed leaves. Bottom: MAP over time "
                   "(dashed gray = no bleed).")
        figure = layout(
            "Every bleed lowers MAP; loss grows more slowly than the bleed rate",
            height=700, shapes=[band],
            legend={"orientation": "h", "y": -0.2, "font": {"size": 11}},
            xaxis=axis("Initial bleed rate (mL/min)", domain=[0.0, 0.28], anchor="y"),
            xaxis2=axis("Initial bleed rate (mL/min)", domain=[0.36, 0.64], anchor="y2"),
            xaxis3=axis("Initial bleed rate (mL/min)", domain=[0.72, 1.0], anchor="y3"),
            xaxis4=axis("Time (min)", domain=[0.0, 1.0], anchor="y4"),
            yaxis=axis("Blood lost (mL)", domain=[0.6, 1.0], anchor="x"),
            yaxis2=axis("Heart rate (1/min)", domain=[0.6, 1.0], anchor="x2"),
            yaxis3=axis("MAP (mmHg)", domain=[0.6, 1.0], anchor="x3"),
            yaxis4=axis("MAP (mmHg)", domain=[0.0, 0.42], anchor="x4"),
        )
        return render(self.stable_div_id(), traces, figure, 700, caption)
