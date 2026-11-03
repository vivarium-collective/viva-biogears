"""Controllers that write setpoints for BioGearsProcess."""

from __future__ import annotations

from process_bigraph import Step


class MapFluidController(Step):
    """Proportional fluid-resuscitation controller on mean arterial pressure.

    Sets the IV infusion rate in proportion to how far MAP is below
    ``target_map_mmHg``, clipped to ``[0, max_rate_mL_per_min]``. It writes a
    setpoint, so its output port is ``overwrite[float]``. Same contract as
    viva-pulse's ``MapFluidController``.
    """

    config_schema = {
        "target_map_mmHg": {"_type": "float", "_default": 90.0},
        "gain_mL_per_min_per_mmHg": {"_type": "float", "_default": 25.0},
        "max_rate_mL_per_min": {"_type": "float", "_default": 250.0},
    }

    def inputs(self):
        return {"mean_arterial_pressure_mmHg": "float"}

    def outputs(self):
        return {"iv_rate_mL_per_min": "overwrite[float]"}

    def update(self, state, interval=None):
        deficit = self.config["target_map_mmHg"] - float(state["mean_arterial_pressure_mmHg"])
        rate = self.config["gain_mL_per_min_per_mmHg"] * deficit
        rate = min(max(rate, 0.0), self.config["max_rate_mL_per_min"])
        return {"iv_rate_mL_per_min": rate}
