"""Engine handling shared by BioGearsProcess and BioGearsCircuitProcess."""

from __future__ import annotations

import math

from ..circuits.cardiovascular import (  # noqa: F401
    HEMORRHAGE_COMPARTMENTS,
    check_hemorrhage_config,
    hemorrhage_xml,
    infusion_xml,
)
from ..circuits.state import read_state
from ..patients import conditions_xml, stabilized_state
from ..runtime import compound_names, import_pybiogears, runtime_dir, state_path

SETPOINTS = ("hemorrhage_rate_mL_per_min", "iv_rate_mL_per_min")
_BLEED_REFUSED = "bleed rate higher than the cardiac output"
_AIRWAY_REFUSED = "Can only change airway mode"


#: Config keys every process has for choosing its starting state.
START_CONFIG = {
    "state_file": {"_type": "string", "_default": "StandardMale@0s.xml"},
    "patient_file": {"_type": "string", "_default": ""},
    "conditions": {"_type": "map", "_default": {}},
    "runtime_dir": {"_type": "string", "_default": ""},
}


def check_loadable_state(path, action_types=("HemorrhageData", "SubstanceCompoundInfusionData")) -> None:
    """Refuse a state that already holds an action the process's setpoints send.

    Setpoints are sent only when they change from their baselines, so an action
    already active in the state would keep running unseen by the setpoint ports.
    """
    active = sorted(set(read_state(path).active_actions) & set(action_types))
    if active:
        raise ValueError(f"state {path.name} has active {', '.join(active)}, which this process's setpoints "
                         "also drive; viva-biogears processes start from states without them")


def check_intervention_config(config) -> None:
    check_start(config)
    check_hemorrhage_config(config)
    if not (config["iv_bag_volume_L"] > 0 and math.isfinite(config["iv_bag_volume_L"])):
        raise ValueError(f"iv_bag_volume_L must be > 0, got {config['iv_bag_volume_L']}")


INTERVENTION_CONFIG = {
    **START_CONFIG,
    "hemorrhage_compartment": {"_type": "string", "_default": "RightLeg"},
    "iv_compound": {"_type": "string", "_default": "Saline"},
    "iv_bag_volume_L": {"_type": "float", "_default": 10.0},
}


def check_start(config) -> None:
    """A process starts from ``state_file`` or from ``patient_file`` (with optional
    ``conditions``), not both. A process can't tell an explicit default from an omitted
    one, so only a non-default ``state_file`` counts as set."""
    if config["patient_file"] or config["conditions"]:
        if config["state_file"] != START_CONFIG["state_file"]["_default"]:
            raise ValueError(f"state_file {config['state_file']!r} is a stabilized state; patient_file "
                             f"{config['patient_file']!r} and conditions {config['conditions']} start from a "
                             "patient that is stabilized first, so set one or the other")
        if config["conditions"]:
            conditions_xml(config["conditions"])  # validates names and values


def resolve_state(config):
    """(runtime directory, absolute state path) for a process config: ``state_file``,
    or, when ``patient_file`` or ``conditions`` is set, that patient (default
    StandardMale.xml) stabilized with them, from the cache (``viva_biogears.patients``)."""
    runtime = runtime_dir(config["runtime_dir"])
    if config.get("patient_file") or config.get("conditions"):
        return runtime, stabilized_state(config["patient_file"] or "StandardMale.xml", runtime,
                                         dict(config["conditions"]))
    return runtime, state_path(runtime, config["state_file"])


def check_compound(runtime, compound: str) -> None:
    if compound not in compound_names(runtime):
        raise ValueError(f"iv_compound {compound!r} is not a BioGears compound; "
                         f"available: {compound_names(runtime)}")


def load_engine(runtime, path, requests):
    """A pybiogears engine with ``requests`` ((category, property, unit, compartment,
    substance) tuples), loaded from ``path``; raises if BioGears connects any request."""
    pb = import_pybiogears()
    engine = pb.BioGearsEngine(runtime)
    engine.set_requests([pb.DataRequest(c, p, u, compartment=cm, substance=s) for c, p, u, cm, s in requests])
    engine.load_state(path)
    if engine.unconnected:
        raise RuntimeError("BioGears did not connect "
                           f"{[(r.category, r.compartment, r.substance, r.property, r.unit) for r in engine.unconnected]}")
    return engine


def advance(engine, seconds: float, applied_bleed: float | None = None) -> bool:
    """Advance ``engine``; False if BioGears reached its irreversible state.

    Raises ``ValueError`` for what BioGears refuses on every step without stopping
    (a bleed rate above cardiac output) and for a second airway device.
    """
    import pybiogears as pb
    n_log = len(engine.log)
    try:
        engine.advance(float(seconds))
    except pb.IrreversibleStateError:
        return False
    except RuntimeError as ex:
        if _AIRWAY_REFUSED in str(ex):
            raise ValueError(f"BioGears refused an airway device: {ex}") from ex
        raise
    refused = [m.text for m in list(engine.log)[n_log:] if _BLEED_REFUSED in m.text]
    if refused:
        raise ValueError(f"BioGears refused hemorrhage_rate_mL_per_min = {applied_bleed}: {refused[0]}")
    return True


class EngineBridge:
    """One BioGears engine for BioGearsProcess: loads lazily, sends setpoints on change, advances safely."""

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
        runtime, path = resolve_state(self.config)
        check_compound(runtime, self.config["iv_compound"])
        check_loadable_state(path)
        self.engine = load_engine(runtime, path, self.requests)
        return self.engine

    def values(self) -> list[float]:
        return [float(v) for v in self.ensure().pull()[1:]]

    def _send(self, port: str, value: float) -> None:
        if port == "hemorrhage_rate_mL_per_min":
            xml = hemorrhage_xml(self.config["hemorrhage_compartment"], value)
        else:
            xml = infusion_xml(self.config["iv_compound"], self.config["iv_bag_volume_L"], value)
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
        engine = self.ensure()
        if not self.alive:
            return False
        self.alive = advance(engine, seconds, self.applied["hemorrhage_rate_mL_per_min"])
        return self.alive
