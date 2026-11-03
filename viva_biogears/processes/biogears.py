"""Process-bigraph bridge to the BioGears physiology engine (8.2.0, through pybiogears)."""

from __future__ import annotations

from typing import Any

from process_bigraph import Process

from ..circuits.vitals import VITALS  # noqa: E402  (re-exported)
from ._bridge import (  # noqa: F401
    HEMORRHAGE_COMPARTMENTS,
    INTERVENTION_CONFIG,
    EngineBridge,
    check_intervention_config,
    check_loadable_state,
)


class BioGearsProcess(Process):
    """Time-stepped bridge to the real BioGears 8.2.0 engine.

    The engine is loaded from a BioGears state file (``state_file``, a name in
    ``<runtime>/states`` or an absolute path) on first use and advanced by
    ``interval`` seconds on every update. Interventions arrive as setpoints on the
    input ports and are forwarded to BioGears as actions only when they change.

    Inputs
    ------
    hemorrhage_rate_mL_per_min : overwrite[float]
        Initial bleeding rate at ``config.hemorrhage_compartment``; 0 stops the
        bleed. BioGears' bleed rate falls with the local pressure from this initial
        value. It must stay below cardiac output: BioGears refuses a larger rate on
        every step without stopping, which this process raises as an error.
    iv_rate_mL_per_min : overwrite[float]
        Infusion rate of ``config.iv_compound`` (e.g. Saline, Blood_ONegative); 0 stops it.

    Outputs
    -------
    Vital signs (see ``VITALS``) as ``overwrite[float]``: ``initial_state()``
    seeds each store with the loaded state's reading and every update emits
    BioGears' current reading, so the store always equals BioGears' own value.
    ``irreversible_state`` turns True once BioGears reports its irreversible state
    (it does at 50 % blood loss); the engine is not advanced after that, so the
    vitals stores keep the last reading BioGears produced.
    """

    config_schema = dict(INTERVENTION_CONFIG)

    def __init__(self, config=None, core=None):
        super().__init__(config=config, core=core)
        check_intervention_config(self.config)
        self._bridge = EngineBridge(self.config, [("Physiology", p, u, "", "") for p, u in VITALS.values()])

    def inputs(self):
        return {"hemorrhage_rate_mL_per_min": "overwrite[float]", "iv_rate_mL_per_min": "overwrite[float]"}

    def outputs(self):
        ports: dict[str, Any] = {name: "overwrite[float]" for name in VITALS}
        ports["irreversible_state"] = "boolean"
        return ports

    def initial_state(self):
        return {"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0,
                **self._read_vitals(), "irreversible_state": False}

    def _read_vitals(self) -> dict[str, float]:
        return dict(zip(VITALS, self._bridge.values()))

    def update(self, state, interval):
        if not self._bridge.alive:
            return {}
        self._bridge.apply(state)
        if not self._bridge.advance(interval):
            return {"irreversible_state": True}
        return self._read_vitals()
