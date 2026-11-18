"""Respiratory circuit and mechanical-ventilator modules.

BioGears solves the airway as one circuit: the respiratory circuit combined with
whichever airway device is connected (``BioGearsCircuits::GetActiveRespiratoryCircuit``:
``RespiratoryAnesthesia``, ``RespiratoryNasalCannula``, ...).

``respiratory`` readings:

- ``mechanics``: BioGears' respiratory-system scalars (``SERespiratorySystem``).
  Pressures are cmH2O relative to atmosphere; per-breath values update once a breath.
- ``lungs`` and ``pleura``: gas compartments. Their ``absolute_pressure_cmH2O`` is
  absolute (ambient is about 1033 cmH2O); subtract ambient for gauge pressure.
  Instantaneous within a breath; compartments are hierarchical (a lung contains
  its bronchi and alveoli), so volumes don't add up.

``respiratory`` setpoint: ``intubated`` (0/1), with the tube placement from config
``intubation_type`` (``Tracheal``, ``Esophageal``, ``LeftMainstem``, ``RightMainstem``).
BioGears accepts extubation (type ``Off``), so 1 -> 0 works.

There are no resistance or compliance multipliers: BioGears 8.2.0 has no action that
changes its respiratory mechanics directly.

``mechanical_ventilator``: BioGears' ventilator is its anesthesia machine, a
pressure-controlled ventilator with a gas source (``AnesthesiaMachineConfiguration``).

- Setpoints, one group: ``connected`` (0/1), ``ventilator_pressure_cmH2O`` (the
  inspiratory pressure the bellows apply), ``peep_cmH2O``, ``respiration_rate_bpm``,
  ``inspiratory_expiratory_ratio``, ``oxygen_fraction`` and ``inlet_flow_L_per_min``,
  sent as one configuration with connection config ``ventilator_connection``
  (``Tube``, which needs ``respiratory/intubated``, or ``Mask``) or ``Off``. The
  oxygen comes from the wall supply; nitrogen is the balance gas.
- Readings: the settings BioGears is using, read back (``settings/``), and the gas
  compartments of the ventilator circuit (``circuit/``). Breathing itself (tidal
  volume, airway pressures) is in the ``respiratory`` module.
- ``connected`` is the module's airway device: BioGears allows one at a time, and
  connecting a second one makes every step fail ("Can only change airway mode to
  ... from the Free mode"), so the process refuses it.
"""

from __future__ import annotations

from typing import Any

from .base import (
    ActionBinding,
    Module,
    Request,
    check_fraction,
    scalar,
    validate_switch,
)
from .state import scalar as state_scalar
from .state import text

INTUBATION_TYPES = ("Tracheal", "Esophageal", "LeftMainstem", "RightMainstem")
VENTILATOR_CONNECTIONS = ("Tube", "Mask")

# port -> (SERespiratorySystem property, unit)
_MECHANICS = {
    "respiration_rate_bpm": ("RespirationRate", "1/min"),
    "tidal_volume_mL": ("TidalVolume", "mL"),
    "total_lung_volume_mL": ("TotalLungVolume", "mL"),
    "total_pulmonary_ventilation_L_per_min": ("TotalPulmonaryVentilation", "L/min"),
    "total_alveolar_ventilation_L_per_min": ("TotalAlveolarVentilation", "L/min"),
    "total_dead_space_ventilation_L_per_min": ("TotalDeadSpaceVentilation", "L/min"),
    "inspiratory_flow_L_per_min": ("InspiratoryFlow", "L/min"),
    "expiratory_flow_L_per_min": ("ExpiratoryFlow", "L/min"),
    "inspiratory_expiratory_ratio": ("InspiratoryExpiratoryRatio", ""),
    "pulmonary_compliance_L_per_cmH2O": ("PulmonaryCompliance", "L/cmH2O"),
    "pulmonary_resistance_cmH2O_s_per_L": ("PulmonaryResistance", "cmH2O s/L"),
    "transpulmonary_pressure_cmH2O": ("TranspulmonaryPressure", "cmH2O"),
    "mean_pleural_pressure_cmH2O": ("MeanPleuralPressure", "cmH2O"),
    "respiration_muscle_pressure_cmH2O": ("RespirationMusclePressure", "cmH2O"),
    "respiration_driver_pressure_cmH2O": ("RespirationDriverPressure", "cmH2O"),
    "end_tidal_carbon_dioxide_pressure_mmHg": ("EndTidalCarbonDioxidePressure", "mmHg"),
    "end_tidal_carbon_dioxide_fraction": ("EndTidalCarbonDioxideFraction", ""),
    "alveolar_arterial_gradient_mmHg": ("AlveolarArterialGradient", "mmHg"),
}

# group -> {store name: BioGears gas compartment (BGE::PulmonaryCompartment)}
_COMPARTMENTS = {
    "lungs": {
        "mouth": "Mouth",
        "trachea": "Trachea",
        "left_bronchi": "LeftBronchi",
        "right_bronchi": "RightBronchi",
        "left_lung": "LeftLungPulmonary",
        "right_lung": "RightLungPulmonary",
        "left_alveoli": "LeftAlveoli",
        "right_alveoli": "RightAlveoli",
    },
    "pleura": {
        "left_pleural_cavity": "LeftPleuralCavity",
        "right_pleural_cavity": "RightPleuralCavity",
    },
}
_COMPARTMENT_PROPERTIES = {
    "absolute_pressure_cmH2O": ("Pressure", "cmH2O"),
    "volume_mL": ("Volume", "mL"),
    "inflow_L_per_min": ("InFlow", "L/min"),
    "outflow_L_per_min": ("OutFlow", "L/min"),
}

# port -> (SEAnesthesiaMachine property, unit), read through Equipment requests.
_SETTINGS = {
    "ventilator_pressure_cmH2O": ("VentilatorPressure", "cmH2O"),
    "peep_cmH2O": ("PositiveEndExpiredPressure", "cmH2O"),
    "respiration_rate_bpm": ("RespiratoryRate", "1/min"),
    "inspiratory_expiratory_ratio": ("InspiratoryExpiratoryRatio", ""),
    "oxygen_fraction": ("OxygenFraction", ""),
    "inlet_flow_L_per_min": ("InletFlow", "L/min"),
    "relief_valve_pressure_cmH2O": ("ReliefValvePressure", "cmH2O"),
}
# store name -> anesthesia-machine gas compartment (BGE::AnesthesiaMachineCompartment)
_VENTILATOR_COMPARTMENTS = {
    "ventilator": "Ventilator",
    "inspiratory_limb": "InspiratoryLimb",
    "expiratory_limb": "ExpiratoryLimb",
    "y_piece": "YPiece",
    "connection": "AnesthesiaConnection",
}

#: BioGears' shipped anesthesia-machine scenarios: 12 bpm, I:E 1:2, PEEP 1 cmH2O.
VENTILATOR_BASELINE = {
    "connected": 0.0,
    "ventilator_pressure_cmH2O": 12.0,
    "peep_cmH2O": 1.0,
    "respiration_rate_bpm": 12.0,
    "inspiratory_expiratory_ratio": 0.5,
    "oxygen_fraction": 0.21,
    "inlet_flow_L_per_min": 5.0,
}


def _respiratory_outputs() -> tuple[Request, ...]:
    out = [Request(("mechanics", port), "Physiology", prop, unit) for port, (prop, unit) in _MECHANICS.items()]
    for group, compartments in _COMPARTMENTS.items():
        for name, compartment in compartments.items():
            for port, (prop, unit) in _COMPARTMENT_PROPERTIES.items():
                out.append(Request((group, name, port), "GasCompartment", prop, unit, compartment))
    return tuple(out)


def _validate_intubation(values, config):
    validate_switch("intubated", values["intubated"])


def intubation_xml(kind: str) -> str:
    return f'<Action xsi:type="IntubationData" Type="{kind}"/>'


def _build_intubation(values, config):
    return intubation_xml(config["intubation_type"] if values["intubated"] == 1.0 else "Off")


def _loaded_intubation(state, config):
    if state.intubation == "Off":
        return {"intubated": 0.0}
    kinds = [el.get("Type") for kind, el in state.actions if kind == "IntubationData"]
    if kinds and kinds[0] != config["intubation_type"]:
        raise ValueError(f"the loaded state is intubated ({kinds[0]}), but intubation_type is "
                         f"{config['intubation_type']!r}; set it to {kinds[0]!r}")
    return {"intubated": 1.0}


_MACHINE = {  # setpoint -> (anesthesia-machine element, unit)
    "ventilator_pressure_cmH2O": ("VentilatorPressure", "cmH2O"),
    "peep_cmH2O": ("PositiveEndExpiredPressure", "cmH2O"),
    "respiration_rate_bpm": ("RespiratoryRate", "1/min"),
    "inspiratory_expiratory_ratio": ("InspiratoryExpiratoryRatio", ""),
    "oxygen_fraction": ("OxygenFraction", ""),
    "inlet_flow_L_per_min": ("InletFlow", "L/min"),
}


def _loaded_ventilator(state, config):
    machine = state.systems.get("BioGearsAnesthesiaMachineData")
    connection = text(machine, "Connection", "Off") or "Off"
    if connection == "Off":
        return dict(VENTILATOR_BASELINE)
    if connection != config["ventilator_connection"]:
        raise ValueError(f"the loaded state's ventilator is connected by {connection}, but "
                         f"ventilator_connection is {config['ventilator_connection']!r}; set it to {connection!r}")
    if text(machine, "OxygenSource", "Wall") != "Wall" or text(machine, "PrimaryGas", "Nitrogen") != "Nitrogen":
        return None  # a configuration this module doesn't send: resend ours on the first update
    values = {"connected": 1.0}
    for port, (tag, unit) in _MACHINE.items():
        v = state_scalar(machine, tag, unit)
        if v is None:
            return None
        values[port] = v
    return values


def _check_respiratory_config(config: dict[str, Any]) -> None:
    if config["intubation_type"] not in INTUBATION_TYPES:
        raise ValueError(f"intubation_type must be one of {INTUBATION_TYPES}, got {config['intubation_type']!r}")


def _validate_ventilator(values, config):
    validate_switch("connected", values["connected"])
    for port in ("ventilator_pressure_cmH2O", "respiration_rate_bpm", "inspiratory_expiratory_ratio",
                 "inlet_flow_L_per_min"):
        if not 0.0 < values[port] < float("inf"):
            raise ValueError(f"{port} must be a finite number > 0, got {values[port]}")
    if not 0.0 <= values["peep_cmH2O"] < values["ventilator_pressure_cmH2O"]:
        raise ValueError("need 0 <= peep_cmH2O < ventilator_pressure_cmH2O, got "
                         f"{values['peep_cmH2O']} and {values['ventilator_pressure_cmH2O']}")
    check_fraction("oxygen_fraction", values["oxygen_fraction"])


def anesthesia_machine_xml(connection: str, values: dict[str, float]) -> str:
    return ('<Action xsi:type="AnesthesiaMachineConfigurationData"><Configuration>'
            f"<Connection>{connection}</Connection>"
            + scalar("InletFlow", values["inlet_flow_L_per_min"], "L/min")
            + scalar("InspiratoryExpiratoryRatio", values["inspiratory_expiratory_ratio"])
            + scalar("OxygenFraction", values["oxygen_fraction"])
            + "<OxygenSource>Wall</OxygenSource>"
            + scalar("PositiveEndExpiredPressure", values["peep_cmH2O"], "cmH2O")
            + "<PrimaryGas>Nitrogen</PrimaryGas>"
            + scalar("RespiratoryRate", values["respiration_rate_bpm"], "1/min")
            + scalar("VentilatorPressure", values["ventilator_pressure_cmH2O"], "cmH2O")
            + "</Configuration></Action>")


def _build_ventilator(values, config):
    return anesthesia_machine_xml(config["ventilator_connection"] if values["connected"] == 1.0 else "Off", values)


def _check_ventilator_config(config: dict[str, Any]) -> None:
    if config["ventilator_connection"] not in VENTILATOR_CONNECTIONS:
        raise ValueError(f"ventilator_connection must be one of {VENTILATOR_CONNECTIONS}, "
                         f"got {config['ventilator_connection']!r}")


RESPIRATORY = Module(
    name="respiratory",
    description="Breathing mechanics plus pressure, volume and flows of the airway, lung and "
                "pleural gas compartments; setpoint: intubation.",
    outputs=_respiratory_outputs(),
    bindings=(ActionBinding(ports={"intubated": 0.0}, build=_build_intubation,
                            action_types=("IntubationData",), validate=_validate_intubation,
                            loaded=_loaded_intubation),),
    params={"intubation_type": {"_type": "string", "_default": "Tracheal"}},
    check_config=_check_respiratory_config,
)

MECHANICAL_VENTILATOR = Module(
    name="mechanical_ventilator",
    description="BioGears' anesthesia-machine ventilator (pressure control): its settings as applied "
                "and its circuit's gas compartments; setpoints: connection and settings.",
    outputs=tuple([Request(("settings", port), "Equipment", prop, unit) for port, (prop, unit) in _SETTINGS.items()]
                  + [Request(("circuit", name, port), "GasCompartment", prop, unit, compartment)
                     for name, compartment in _VENTILATOR_COMPARTMENTS.items()
                     for port, (prop, unit) in (("absolute_pressure_cmH2O", ("Pressure", "cmH2O")),
                                                ("volume_mL", ("Volume", "mL")))]),
    bindings=(ActionBinding(ports=dict(VENTILATOR_BASELINE), build=_build_ventilator,
                            action_types=("AnesthesiaMachineConfigurationData",), validate=_validate_ventilator,
                            loaded=_loaded_ventilator),),
    params={"ventilator_connection": {"_type": "string", "_default": "Tube"}},
    check_config=_check_ventilator_config,
    airway_device="connected",
)
