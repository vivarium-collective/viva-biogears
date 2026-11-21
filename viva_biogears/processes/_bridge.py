"""Engine handling shared by BioGearsProcess and BioGearsModularProcess."""

from __future__ import annotations

import math

from ..modules.additions import added_state, check_additions
from ..modules.cardiovascular import (
    HEMORRHAGE_COMPARTMENTS,  # noqa: F401  (re-exported)
    check_hemorrhage_config,
    hemorrhage_xml,
    infusion_xml,
    loaded_hemorrhage,
    loaded_infusion,
)
from ..modules.state import read_state
from ..patients import conditions_xml, stabilized_state
from ..runtime import compound_names, import_pybiogears, state_path
from ..tables import engine_runtime, require_acceptable, start_patient
from ..states import SAVE_CONFIG, saver_from_config

SETPOINTS = ("hemorrhage_rate_mL_per_min", "iv_rate_mL_per_min")
_BLEED_REFUSED = "bleed rate higher than the cardiac output"
_AIRWAY_REFUSED = "Can only change airway mode"


#: Config keys every process has for choosing its starting state.
START_CONFIG = {
    "state_file": {"_type": "string", "_default": "StandardMale@0s.xml"},
    "patient_file": {"_type": "string", "_default": ""},
    "patient_table": {"_type": "string", "_default": ""},
    "patient": {"_type": "string", "_default": ""},
    "conditions": {"_type": "map", "_default": {}},
    "substance_table": {"_type": "string", "_default": ""},
    "circuit_additions": {"_type": "map", "_default": {}},
    "runtime_dir": {"_type": "string", "_default": ""},
    # BioGears' solver step. BioGears is validated at 0.02 s and fails at 0.1 s or more;
    # larger steps run faster and less accurately (study timestep-accuracy).
    "time_step_s": {"_type": "float", "_default": 0.02},
}

DEFAULT_TIME_STEP_S = 0.02
MAX_TIME_STEP_S = 0.1


def check_intervention_config(config) -> None:
    check_start(config)
    check_hemorrhage_config(config)
    if not (config["iv_bag_volume_L"] > 0 and math.isfinite(config["iv_bag_volume_L"])):
        raise ValueError(f"iv_bag_volume_L must be > 0, got {config['iv_bag_volume_L']}")


INTERVENTION_CONFIG = {
    **START_CONFIG,
    **SAVE_CONFIG,
    "hemorrhage_compartment": {"_type": "string", "_default": "RightLeg"},
    "iv_compound": {"_type": "string", "_default": "Saline"},
    "iv_bag_volume_L": {"_type": "float", "_default": 10.0},
}


def check_start(config) -> None:
    """A process starts from ``state_file``, from ``patient_file``, or from ``patient`` of
    ``patient_table`` (the last two with optional ``conditions``), only one of them. A
    process can't tell an explicit default from an omitted one, so only a non-default
    ``state_file`` counts as set. The patient is checked against BioGears' patient rules
    (``viva_biogears.tables``): one BioGears would refuse raises, one whose values it
    changes warns. A ``substance_table`` is converted now, so a bad one fails here."""
    table, name = config.get("patient_table", ""), config.get("patient", "")
    if bool(table) != bool(name):
        raise ValueError("patient_table and patient go together: patient names a column of the table "
                         f"(got patient_table={table!r}, patient={name!r})")
    if table and config["patient_file"]:
        raise ValueError(f"patient_file {config['patient_file']!r} and patient_table {table!r} both name the "
                         "patient; set one")
    if config["patient_file"] or table or config["conditions"]:
        if config["state_file"] != START_CONFIG["state_file"]["_default"]:
            started = (f"patient {name!r} of {table!r}" if table else f"patient_file {config['patient_file']!r}"
                       if config["patient_file"] else "StandardMale.xml")
            raise ValueError(f"state_file {config['state_file']!r} is a stabilized state; {started} with "
                             f"conditions {config['conditions']} starts from a patient that is stabilized first, "
                             "so set one or the other")
        if config["conditions"]:
            conditions_xml(config["conditions"])  # validates names and values
    patient = start_patient(config) if (config["patient_file"] or table) else None
    if patient is not None:
        require_acceptable(patient)
    if config.get("substance_table"):
        engine_runtime(config)
    check_additions(config["circuit_additions"])
    ts = config.get("time_step_s", DEFAULT_TIME_STEP_S)
    if not (isinstance(ts, (int, float)) and math.isfinite(ts) and 0 < ts < MAX_TIME_STEP_S):
        raise ValueError(f"time_step_s must be > 0 and < {MAX_TIME_STEP_S} s (BioGears fails at 0.1 s and above), "
                         f"got {ts!r}")


def resolve_state(config):
    """(runtime directory, absolute state path) for a process config: ``state_file``,
    or, when a patient (``patient_file``, ``patient`` of ``patient_table``) or
    ``conditions`` is set, that patient (default StandardMale.xml) stabilized with them,
    from the cache (``viva_biogears.patients``); with ``circuit_additions``, that state
    with the paths added (``modules.additions``). With ``substance_table`` the runtime
    also holds the table's substances (``viva_biogears.tables``)."""
    runtime = engine_runtime(config)
    patient = start_patient(config, runtime)
    if patient is not None or config.get("conditions"):
        path = stabilized_state(str(patient or "StandardMale.xml"), runtime, dict(config["conditions"]))
    else:
        path = state_path(runtime, config["state_file"])
    if config.get("circuit_additions"):
        path = added_state(path, dict(config["circuit_additions"]))
    return runtime, path


def check_compound(runtime, compound: str) -> None:
    if compound not in compound_names(runtime):
        raise ValueError(f"iv_compound {compound!r} is not a BioGears compound; "
                         f"available: {compound_names(runtime)}")


def load_engine(runtime, path, requests, time_step_s: float = DEFAULT_TIME_STEP_S):
    """A pybiogears engine with ``requests`` ((category, property, unit, compartment,
    substance) tuples), loaded from ``path``; raises if BioGears connects any request.
    A ``time_step_s`` other than the state's own is merged into the state's configuration
    (pybiogears' ``load_state(configuration=...)``)."""
    pb = import_pybiogears()
    engine = pb.BioGearsEngine(runtime)
    engine.set_requests([pb.DataRequest(c, p, u, compartment=cm, substance=s) for c, p, u, cm, s in requests])
    if time_step_s != DEFAULT_TIME_STEP_S:
        engine.load_state(path, configuration=pb.configuration(runtime, TimeStep=(float(time_step_s), "s")))
    else:
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
        self.saver = saver_from_config(config)

    def ensure(self):
        if self.engine is not None:
            return self.engine
        runtime, path = resolve_state(self.config)
        check_compound(runtime, self.config["iv_compound"])
        # A state saved mid-run carries its bleed and infusion: start from their values,
        # so the same setpoints continue the run and different ones send the change.
        state = read_state(path)
        bleed = loaded_hemorrhage(state, self.config)
        infusion = loaded_infusion(state, self.config)
        self.applied = {**(bleed or {"hemorrhage_rate_mL_per_min": None}),
                        **(infusion or {"iv_rate_mL_per_min": None})}
        self.engine = load_engine(runtime, path, self.requests, self.config.get("time_step_s", DEFAULT_TIME_STEP_S))
        if self.saver:
            self.saver(self.engine)
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
        if self.alive and self.saver:
            self.saver(engine)
        return self.alive
