"""CohortBloodLoss: fraction of blood lost against starting blood volume, one dot per patient.

Ported from viva-pulse for the patient-cohort study. Patient names do not reach a
Visualization through the workbench (it builds per-run parameter strings under
``_run_labels`` but wires only declared ports), so the per-patient MAP traces are a
labelled comparative visualization instead.
"""

import numpy as np
from process_bigraph.visualization import Visualization

from ._figure import CATEGORICAL, SURFACE, axis, layout, missing_runs, render


def _spearman(x, y):
    ranks = lambda values: np.asarray(values).argsort().argsort()
    return float(np.corrcoef(ranks(x), ranks(y))[0, 1])


class CohortBloodLoss(Visualization):
    """Scatter of starting blood volume vs percent lost; hover shows the loss and MAP change."""

    def inputs(self):
        # 2026-11-16 pilot (BioGears): Female_18_Normal, Female, StandardMale, Bradycardic, Tachycardic.
        return {
            "blood_volume": [[3894, 3256], [4136, 3482], [5532, 4888], [5530, 5049], [5533, 4691]],
            "hemorrhaged_volume": [[0, 685], [0, 697], [0, 679], [0, 512], [0, 886]],
            "mean_arterial_pressure": [[94.8, 83.5], [94.7, 83.7], [95.9, 87.9], [94.6, 89.1], [95.5, 85.1]],
        }

    def update(self, state):
        error = missing_runs(state, self.inputs())
        if error:
            return error
        start = [run[0] for run in state["blood_volume"]]
        percent = [100.0 * lost[-1] / bv for lost, bv in zip(state["hemorrhaged_volume"], start)]
        custom = [[lost[-1], pressure[0], pressure[-1]] for lost, pressure in
                  zip(state["hemorrhaged_volume"], state["mean_arterial_pressure"])]
        rho = _spearman(start, percent)

        traces = [{
            "x": [bv / 1000.0 for bv in start], "y": percent, "customdata": custom,
            "type": "scatter", "mode": "markers", "name": "patient",
            "marker": {"size": 10, "color": CATEGORICAL[0], "line": {"color": SURFACE, "width": 2}},
            "hovertemplate": ("starting blood volume %{x:.2f} L"
                              "<br>lost %{customdata[0]:.0f} mL (%{y:.1f}%)"
                              "<br>MAP %{customdata[1]:.1f} → %{customdata[2]:.1f} mmHg<extra></extra>"),
        }]
        caption = (f"The same right-leg hemorrhage (200 mL/min initial rate, 10 min) in each of the "
                   f"{len(start)} patient states shipped with BioGears. Patients with a fast resting heart rate "
                   "(higher cardiac output) lose more than their size predicts. Hover a dot for the loss and MAP change.")
        figure = layout(
            f"Smaller patients lose a larger share of their blood (Spearman ρ = {rho:.2f})",
            height=480, showlegend=False,
            xaxis=axis("Starting blood volume (L)"),
            yaxis=axis("Blood lost in 10 min (% of starting volume)"),
        )
        return render(self.stable_div_id(), traces, figure, 480, caption)
