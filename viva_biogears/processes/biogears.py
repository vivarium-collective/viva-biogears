"""Process-bigraph bridge to the BioGears physiology engine (8.2.0, through pybiogears)."""

from __future__ import annotations

import math
import re
from typing import Any

from process_bigraph import Process

from ..runtime import compound_names, import_pybiogears, runtime_dir, state_path

#: Output port -> (BioGears physiology property, unit). Order is the data-request
#: order, i.e. the order of BioGearsEngine.pull()[1:].
VITALS: dict[str, tuple[str, str]] = {
    "heart_rate_bpm": ("HeartRate", "1/min"),
    "mean_arterial_pressure_mmHg": ("MeanArterialPressure", "mmHg"),
    "systolic_pressure_mmHg": ("SystolicArterialPressure", "mmHg"),
    "diastolic_pressure_mmHg": ("DiastolicArterialPressure", "mmHg"),
    "oxygen_saturation": ("OxygenSaturation", ""),
    "respiration_rate_bpm": ("RespirationRate", "1/min"),
    "cardiac_output_L_per_min": ("CardiacOutput", "L/min"),
    "central_venous_pressure_mmHg": ("CentralVenousPressure", "mmHg"),
    "blood_volume_mL": ("BloodVolume", "mL"),
    # NaN until the first hemorrhage (BioGears creates the value then).
    "total_blood_volume_lost_mL": ("TotalBloodVolumeLost", "mL"),
}

#: Compartments BioGears 8.2.0 can bleed from: those with a "<name>Bleed" path in
#: the cardiovascular circuit (BioGearsCircuits.h). Any other name is accepted by
#: BioGears and then segfaults on the next step (pybiogears probe P7).
HEMORRHAGE_COMPARTMENTS = (
    "Aorta", "Brain", "Myocardium", "LeftLung", "RightLung", "LeftArm", "RightArm", "Spleen",
    "SmallIntestine", "LargeIntestine", "Splanchnic", "RightKidney", "LeftKidney", "Liver",
    "Portal", "LeftLeg", "RightLeg", "VenaCava",
)

_ACTIVE_ACTION = re.compile(r'<ActiveAction xsi:type="(\w+)"')


def check_loadable_state(path) -> None:
    """Refuse a state that already holds a hemorrhage or an infusion.

    The process sends its setpoints only when they change from the baseline 0.0,
    so an action already active in the state would keep running unseen by the
    setpoint ports.
    """
    head = path.read_text(errors="ignore")
    active = sorted({t for t in _ACTIVE_ACTION.findall(head)
                     if t in ("HemorrhageData", "SubstanceCompoundInfusionData")})
    if active:
        raise ValueError(f"state {path.name} has active {', '.join(active)}; BioGearsProcess starts "
                         "from states without an active hemorrhage or infusion")


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

    config_schema = {
        "state_file": {"_type": "string", "_default": "StandardMale@0s.xml"},
        "runtime_dir": {"_type": "string", "_default": ""},
        "hemorrhage_compartment": {"_type": "string", "_default": "RightLeg"},
        "iv_compound": {"_type": "string", "_default": "Saline"},
        "iv_bag_volume_L": {"_type": "float", "_default": 10.0},
    }

    def __init__(self, config=None, core=None):
        super().__init__(config=config, core=core)
        if self.config["hemorrhage_compartment"] not in HEMORRHAGE_COMPARTMENTS:
            raise ValueError(f"hemorrhage_compartment must be one of {HEMORRHAGE_COMPARTMENTS}, "
                             f"got {self.config['hemorrhage_compartment']!r}")
        if not (self.config["iv_bag_volume_L"] > 0 and math.isfinite(self.config["iv_bag_volume_L"])):
            raise ValueError(f"iv_bag_volume_L must be > 0, got {self.config['iv_bag_volume_L']}")
        self._engine = None
        self._alive = True
        self._applied: dict[str, float] = {"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": 0.0}

    def inputs(self):
        return {
            "hemorrhage_rate_mL_per_min": "overwrite[float]",
            "iv_rate_mL_per_min": "overwrite[float]",
        }

    def outputs(self):
        ports: dict[str, Any] = {name: "overwrite[float]" for name in VITALS}
        ports["irreversible_state"] = "boolean"
        return ports

    def initial_state(self):
        return {
            "hemorrhage_rate_mL_per_min": 0.0,
            "iv_rate_mL_per_min": 0.0,
            **self._read_vitals(),
            "irreversible_state": False,
        }

    # -- engine lifecycle -------------------------------------------------

    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine
        pb = import_pybiogears()
        runtime = runtime_dir(self.config["runtime_dir"])
        if self.config["iv_compound"] not in compound_names(runtime):
            raise ValueError(f"iv_compound {self.config['iv_compound']!r} is not a BioGears compound; "
                             f"available: {compound_names(runtime)}")
        path = state_path(runtime, self.config["state_file"])
        check_loadable_state(path)
        engine = pb.BioGearsEngine(runtime)
        engine.set_requests([pb.DataRequest("Physiology", prop, unit) for prop, unit in VITALS.values()])
        engine.load_state(path)
        if engine.unconnected:
            raise RuntimeError(f"BioGears did not connect {[r.property for r in engine.unconnected]}")
        self._engine = engine
        return engine

    def _read_vitals(self) -> dict[str, float]:
        values = self._ensure_engine().pull()
        return {name: float(v) for name, v in zip(VITALS, values[1:])}

    def _send(self, engine, port: str, value: float) -> None:
        from pybiogears import actions
        if port == "hemorrhage_rate_mL_per_min":
            xml = actions.hemorrhage(self.config["hemorrhage_compartment"], value)
        else:
            xml = actions.substance_compound_infusion(self.config["iv_compound"],
                                                      self.config["iv_bag_volume_L"] * 1000.0, value)
        engine.process_actions(xml)
        self._applied[port] = value

    def _apply_interventions(self, engine, state):
        for port in ("hemorrhage_rate_mL_per_min", "iv_rate_mL_per_min"):
            value = float(state[port])
            if value == self._applied[port]:
                continue
            if not (value >= 0.0 and math.isfinite(value)):
                raise ValueError(f"{port} must be a finite number >= 0, got {value}")
            self._send(engine, port, value)

    def update(self, state, interval):
        import pybiogears as pb
        engine = self._ensure_engine()
        if not self._alive:
            return {}
        self._apply_interventions(engine, state)
        n_log = len(engine.log)
        try:
            engine.advance(float(interval))
        except pb.IrreversibleStateError:
            self._alive = False
            return {"irreversible_state": True}
        refused = [m.text for m in list(engine.log)[n_log:] if "bleed rate higher than the cardiac output" in m.text]
        if refused:
            raise ValueError(f"BioGears refused hemorrhage_rate_mL_per_min = "
                             f"{self._applied['hemorrhage_rate_mL_per_min']}: {refused[0]}")
        return self._read_vitals()
