"""Sepsis treatment protocols of McDaniel et al. 2019 (Figs 9-13), as setpoint schedules.

A ``TreatmentProtocol`` turns the paper's protocols into two setpoints of
``BioGearsCircuitProcess``: the saline rate (``cardiovascular/iv_rate_mL_per_min``, a bag
of ``iv_compound`` = Saline) and the vasopressor rate
(``treatment/vasopressor_rate_ug_per_min``, norepinephrine), plus static ``treatment``
schedule events (the antibiotic). It is evaluated once per update from the readings
(systolic and mean arterial pressure, mean urine output) and keeps its own small state,
``state``, which ``run.py`` saves with each checkpoint so a resumed run continues it.
``viva_biogears.processes.controllers.TreatmentController`` wraps it as a Step.

The protocols (paper, Methods; the paper leaves bolus rates, the norepinephrine
concentration and the reassessment values' timing open, so these follow BioGears' own
sepsis treatment scenario, Scenarios/Patient/InfectionSevere.xml, by the same group):

- ``fluid_challenge`` (Fig 9): two 500 mL saline boluses at ``challenge_h`` and
  ``challenge_h`` + 0.5 h (44 and 44.5 h).
- ``antibiotic`` (Fig 10): the challenge, then 4.5 g piperacillin/tazobactam over 30 min
  at ``start_h`` (46 h): BioGears' PiperacillinTazobactam compound, 20 mL at
  0.667 mL/min (0.2 g/mL piperacillin, 0.025 g/mL tazobactam).
- ``refresh_control`` (Figs 11-13): the challenge and the antibiotic; at ``start_h`` a
  1000 mL bolus; then every 30 min for ``duration_h`` (6 h): a 500 mL bolus if SBP < 90
  or MAP < 65 mmHg, and every hour an extra 500 mL if mean urine output < 0.625 mL/min.
  Once SBP > 90 and MAP > 65 at a reassessment, the protocol stops and maintenance
  fluid runs at 75 mL/h.
- ``refresh_experimental`` (Figs 11-12): the challenge and the antibiotic; at
  ``start_h`` maintenance fluid at 1 mL/kg/h and norepinephrine at 0.18 ug/kg/min; then
  every hour for ``duration_h``: a 250 mL bolus if mean urine output < 0.625 mL/min.
  Once SBP > 90 and MAP > 65 at a reassessment, everything but the maintenance fluid
  stops.
- Fig 13 is ``refresh_control`` with ``challenge_h`` and ``start_h`` 12 h later (56, 58).

Boluses run at ``bolus_rate_mL_per_min`` (50, BioGears' scenario's), one after another,
on top of the maintenance rate. ``weight_kg`` (75.8, StandardMale@0s's weight) scales the
per-kg doses.
"""

from __future__ import annotations

import math
from typing import Any

PROTOCOLS = ("none", "fluid_challenge", "antibiotic", "refresh_control", "refresh_experimental")
#: Numeric code of each protocol, written to the store so runs can be told apart in figures.
PROTOCOL_CODES = {name: float(i) for i, name in enumerate(PROTOCOLS)}

SBP_GOAL_mmHg = 90.0
MAP_GOAL_mmHg = 65.0
UO_GOAL_mL_per_min = 0.625            # 0.5 mL/kg/h for the standard BioGears patient (paper)
#: An event time counts as reached within this much (s): BioGears' clock runs a few µs
#: behind after hours (the shipped 44 h state is at 158399.999994 s).
TIME_TOLERANCE_S = 1e-3
ANTIBIOTIC = {"compound": "PiperacillinTazobactam", "bag_volume_mL": 20.0, "rate_mL_per_min": 0.667}


class TreatmentProtocol:
    def __init__(self, protocol: str = "none", *, challenge_h: float = 44.0, start_h: float = 46.0,
                 duration_h: float = 6.0, bolus_rate_mL_per_min: float = 50.0, weight_kg: float = 75.8,
                 interval_s: float = 60.0, state: dict | None = None):
        if protocol not in PROTOCOLS:
            raise ValueError(f"protocol must be one of {list(PROTOCOLS)}, got {protocol!r}")
        for name, v, low in (("challenge_h", challenge_h, 0), ("start_h", start_h, 0), ("duration_h", duration_h, 1),
                             ("bolus_rate_mL_per_min", bolus_rate_mL_per_min, 1), ("weight_kg", weight_kg, 1),
                             ("interval_s", interval_s, 1)):
            if not (isinstance(v, (int, float)) and math.isfinite(v) and (v > 0 if low else v >= 0)):
                raise ValueError(f"{name} must be a number {'> 0' if low else '>= 0'}, got {v!r}")
        if protocol != "fluid_challenge" and protocol != "none" and start_h < challenge_h + 1.0:
            raise ValueError(f"start_h ({start_h}) must be at least 1 h after challenge_h ({challenge_h}): the "
                             "two challenge boluses come first")
        self.protocol = protocol
        self.challenge_s = challenge_h * 3600.0
        self.start_s = start_h * 3600.0
        self.end_s = (start_h + duration_h) * 3600.0
        self.bolus_rate = float(bolus_rate_mL_per_min)
        self.weight_kg = float(weight_kg)
        self.interval_s = float(interval_s)
        self.state = dict(state) if state else {
            "queue_mL": 0.0,          # bolus volume still to give
            "given_mL": 0.0,          # saline given so far (boluses and maintenance)
            "maintenance_mL_per_min": 0.0,
            "vasopressor_ug_per_min": 0.0,
            "done": [],               # one-off events done (challenge boluses, start)
            "next_check_s": None,     # next reassessment
            "stopped": False,         # resuscitation goals met: protocol over
        }

    # -- static parts ---------------------------------------------------------------
    def schedule(self) -> list[dict[str, Any]]:
        """``treatment_schedule`` events (the antibiotic)."""
        if self.protocol in ("antibiotic", "refresh_control", "refresh_experimental"):
            return [{"hour": self.start_s / 3600.0, **ANTIBIOTIC}]
        return []

    @property
    def end_h(self) -> float:
        """When the protocol's observation ends: 2 h after the challenge (Fig 9) or
        ``duration_h`` after the start."""
        if self.protocol == "fluid_challenge":
            return self.challenge_s / 3600.0 + 2.0
        return self.end_s / 3600.0

    # -- per update -------------------------------------------------------------------
    def _once(self, key: str, t: float, at: float) -> bool:
        if key not in self.state["done"] and t >= at - TIME_TOLERANCE_S:
            self.state["done"].append(key)
            return True
        return False

    def setpoints(self, t: float, sbp: float, map_: float, uo: float) -> tuple[float, float]:
        """(saline mL/min, norepinephrine ug/min) for the update starting at ``t`` (s), given
        the readings at ``t``."""
        st = self.state
        if self.protocol == "none":
            return 0.0, 0.0
        if self._once("challenge_1", t, self.challenge_s):
            st["queue_mL"] += 500.0
        if self._once("challenge_2", t, self.challenge_s + 1800.0):
            st["queue_mL"] += 500.0
        refresh = self.protocol in ("refresh_control", "refresh_experimental")
        if refresh and self._once("start", t, self.start_s):
            if self.protocol == "refresh_control":
                st["queue_mL"] += 1000.0
                st["next_check_s"] = self.start_s + 1800.0
            else:
                st["maintenance_mL_per_min"] = 1.0 * self.weight_kg / 60.0
                st["vasopressor_ug_per_min"] = 0.18 * self.weight_kg
                st["next_check_s"] = self.start_s + 3600.0
        if refresh and not st["stopped"] and st["next_check_s"] is not None \
                and t >= st["next_check_s"] - TIME_TOLERANCE_S and t <= self.end_s + TIME_TOLERANCE_S:
            goals = sbp > SBP_GOAL_mmHg and map_ > MAP_GOAL_mmHg
            if goals:
                st["stopped"] = True
                st["queue_mL"] = 0.0
                if self.protocol == "refresh_control":
                    st["maintenance_mL_per_min"] = 75.0 / 60.0
                else:
                    st["vasopressor_ug_per_min"] = 0.0
            elif self.protocol == "refresh_control":
                st["queue_mL"] += 500.0                                   # SBP or MAP below goal
                if round((t - self.start_s) / 1800.0) % 2 == 0 and uo < UO_GOAL_mL_per_min:
                    st["queue_mL"] += 500.0                               # hourly urine check
            elif uo < UO_GOAL_mL_per_min:
                st["queue_mL"] += 250.0
            step = 1800.0 if self.protocol == "refresh_control" else 3600.0
            st["next_check_s"] += step
            if st["next_check_s"] > self.end_s + TIME_TOLERANCE_S:
                st["next_check_s"] = None
        bolus = min(self.bolus_rate, st["queue_mL"] / (self.interval_s / 60.0)) if st["queue_mL"] > 1e-9 else 0.0
        st["queue_mL"] = max(0.0, st["queue_mL"] - bolus * self.interval_s / 60.0)
        rate = bolus + st["maintenance_mL_per_min"]
        st["given_mL"] += rate * self.interval_s / 60.0
        return rate, st["vasopressor_ug_per_min"]
