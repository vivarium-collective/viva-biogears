"""Engine handling shared by BioGearsProcess and BioGearsCircuitProcess."""

from __future__ import annotations

import math
import re

from ..runtime import compound_names, import_pybiogears, runtime_dir, state_path

#: Compartments BioGears 8.2.0 can bleed from: those with a "<name>Bleed" path in
#: the cardiovascular circuit (BioGearsCircuits.h). Any other name is accepted by
#: BioGears and then segfaults on the next step (pybiogears probe P7).
HEMORRHAGE_COMPARTMENTS = (
    "Aorta", "Brain", "Myocardium", "LeftLung", "RightLung", "LeftArm", "RightArm", "Spleen",
    "SmallIntestine", "LargeIntestine", "Splanchnic", "RightKidney", "LeftKidney", "Liver",
    "Portal", "LeftLeg", "RightLeg", "VenaCava",
)
SETPOINTS = ("hemorrhage_rate_mL_per_min", "iv_rate_mL_per_min")

_ACTIVE_ACTION = re.compile(r'<ActiveAction xsi:type="(\w+)"')


def check_loadable_state(path) -> None:
    """Refuse a state that already holds a hemorrhage or an infusion.

    Setpoints are sent only when they change from the baseline 0.0, so an action
    already active in the state would keep running unseen by the setpoint ports.
    """
    active = sorted({t for t in _ACTIVE_ACTION.findall(path.read_text(errors="ignore"))
                     if t in ("HemorrhageData", "SubstanceCompoundInfusionData")})
    if active:
        raise ValueError(f"state {path.name} has active {', '.join(active)}; viva-biogears processes start "
                         "from states without an active hemorrhage or infusion")


def check_intervention_config(config) -> None:
    if config["hemorrhage_compartment"] not in HEMORRHAGE_COMPARTMENTS:
        raise ValueError(f"hemorrhage_compartment must be one of {HEMORRHAGE_COMPARTMENTS}, "
                         f"got {config['hemorrhage_compartment']!r}")
    if not (config["iv_bag_volume_L"] > 0 and math.isfinite(config["iv_bag_volume_L"])):
        raise ValueError(f"iv_bag_volume_L must be > 0, got {config['iv_bag_volume_L']}")


INTERVENTION_CONFIG = {
    "state_file": {"_type": "string", "_default": "StandardMale@0s.xml"},
    "runtime_dir": {"_type": "string", "_default": ""},
    "hemorrhage_compartment": {"_type": "string", "_default": "RightLeg"},
    "iv_compound": {"_type": "string", "_default": "Saline"},
    "iv_bag_volume_L": {"_type": "float", "_default": 10.0},
}


class EngineBridge:
    """One BioGears engine: loads lazily, sends setpoints on change, advances safely."""

    def __init__(self, config, requests):
        """``requests``: (category, property, unit, compartment, substance) tuples, in pull order."""
        self.config = config
        self.requests = list(requests)
        self.engine = None
        self.alive = True
        self.applied = {k: 0.0 for k in SETPOINTS}

    def ensure(self):
        if self.engine is not None:
            return self.engine
        pb = import_pybiogears()
        runtime = runtime_dir(self.config["runtime_dir"])
        if self.config["iv_compound"] not in compound_names(runtime):
            raise ValueError(f"iv_compound {self.config['iv_compound']!r} is not a BioGears compound; "
                             f"available: {compound_names(runtime)}")
        path = state_path(runtime, self.config["state_file"])
        check_loadable_state(path)
        engine = pb.BioGearsEngine(runtime)
        engine.set_requests([pb.DataRequest(c, p, u, compartment=cm, substance=s)
                             for c, p, u, cm, s in self.requests])
        engine.load_state(path)
        if engine.unconnected:
            raise RuntimeError("BioGears did not connect "
                               f"{[(r.category, r.compartment, r.property) for r in engine.unconnected]}")
        self.engine = engine
        return engine

    def values(self) -> list[float]:
        return [float(v) for v in self.ensure().pull()[1:]]

    def _send(self, port: str, value: float) -> None:
        from pybiogears import actions
        if port == "hemorrhage_rate_mL_per_min":
            xml = actions.hemorrhage(self.config["hemorrhage_compartment"], value)
        else:
            xml = actions.substance_compound_infusion(self.config["iv_compound"],
                                                      self.config["iv_bag_volume_L"] * 1000.0, value)
        self.engine.process_actions(xml)
        self.applied[port] = value

    def apply(self, setpoints: dict) -> None:
        """Send each setpoint that changed (resending a hemorrhage restarts BioGears' bleed)."""
        self.ensure()
        for port in SETPOINTS:
            value = float(setpoints[port])
            if value == self.applied[port]:
                continue
            if not (value >= 0.0 and math.isfinite(value)):
                raise ValueError(f"{port} must be a finite number >= 0, got {value}")
            self._send(port, value)

    def advance(self, seconds: float) -> bool:
        """Advance; False once BioGears has reached its irreversible state (then never again)."""
        import pybiogears as pb
        engine = self.ensure()
        if not self.alive:
            return False
        n_log = len(engine.log)
        try:
            engine.advance(float(seconds))
        except pb.IrreversibleStateError:
            self.alive = False
            return False
        refused = [m.text for m in list(engine.log)[n_log:]
                   if "bleed rate higher than the cardiac output" in m.text]
        if refused:
            raise ValueError(f"BioGears refused hemorrhage_rate_mL_per_min = "
                             f"{self.applied['hemorrhage_rate_mL_per_min']}: {refused[0]}")
        return True
