"""Controllers that write setpoints for BioGearsProcess."""

from __future__ import annotations

from process_bigraph import Step


class MapFluidController(Step):
    """Proportional fluid-resuscitation controller on mean arterial pressure.

    Sets the IV infusion rate in proportion to how far MAP is below
    ``target_map_mmHg``, clipped to ``[0, max_rate_mL_per_min]``. It writes a
    setpoint, so its output port is ``overwrite[float]``.
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


class TreatmentController(Step):
    """McDaniel et al. 2019's sepsis treatment protocols (``viva_biogears.protocols``):
    reads systolic and mean arterial pressure and mean urine output once per update and
    writes the saline rate and the vasopressor rate setpoints of a
    ``BioGearsCircuitProcess`` with the ``cardiovascular`` and ``treatment`` modules, plus
    the saline given so far, the protocol's code, the engine hour the run started at and
    the hour its treatment starts (so figures can tell runs apart and align them).
    The antibiotic is a static ``treatment_schedule`` event (``TreatmentProtocol.schedule``).

    The protocol's hours are engine time (hours since the infection): a composite started
    from a saved state at engine time T has ``time_offset_s`` = T, so composite time t is
    engine time t + T.
    """

    config_schema = {
        "protocol": {"_type": "string", "_default": "none"},
        "challenge_h": {"_type": "float", "_default": 44.0},
        "start_h": {"_type": "float", "_default": 46.0},
        "duration_h": {"_type": "float", "_default": 6.0},
        "bolus_rate_mL_per_min": {"_type": "float", "_default": 50.0},
        "weight_kg": {"_type": "float", "_default": 75.8},
        "interval_s": {"_type": "float", "_default": 60.0},
        "time_offset_s": {"_type": "float", "_default": 0.0},
    }

    def __init__(self, config=None, core=None):
        super().__init__(config=config, core=core)
        from ..protocols import PROTOCOL_CODES, TreatmentProtocol
        c = self.config
        self.protocol = TreatmentProtocol(c["protocol"], challenge_h=c["challenge_h"], start_h=c["start_h"],
                                          duration_h=c["duration_h"], bolus_rate_mL_per_min=c["bolus_rate_mL_per_min"],
                                          weight_kg=c["weight_kg"], interval_s=c["interval_s"])
        self.code = PROTOCOL_CODES[c["protocol"]]
        self._last_t = None

    def inputs(self):
        return {"time": "float", "systolic_pressure_mmHg": "float", "mean_arterial_pressure_mmHg": "float",
                "mean_urine_output_mL_per_min": "float"}

    def outputs(self):
        return {"iv_rate_mL_per_min": "overwrite[float]", "vasopressor_rate_ug_per_min": "overwrite[float]",
                "saline_given_mL": "overwrite[float]", "protocol_code": "overwrite[float]",
                "branch_h": "overwrite[float]", "treatment_start_h": "overwrite[float]"}

    def update(self, state, interval=None):
        t = float(state["time"]) + self.config["time_offset_s"]
        if self._last_t is not None and t <= self._last_t + 1e-9:
            # Called again without time advancing: repeat the current setpoints.
            st = self.protocol.state
            rate = st.get("last_rate", 0.0)
        else:
            rate, _ = self.protocol.setpoints(t, float(state["systolic_pressure_mmHg"]),
                                              float(state["mean_arterial_pressure_mmHg"]),
                                              float(state["mean_urine_output_mL_per_min"]))
            self.protocol.state["last_rate"] = rate
            self._last_t = t
        st = self.protocol.state
        return {"iv_rate_mL_per_min": rate, "vasopressor_rate_ug_per_min": st["vasopressor_ug_per_min"],
                "saline_given_mL": st["given_mL"], "protocol_code": self.code,
                "branch_h": self.config["time_offset_s"] / 3600.0,
                "treatment_start_h": (self.protocol.challenge_s if self.config["protocol"] == "fluid_challenge"
                                      else self.protocol.start_s) / 3600.0}
