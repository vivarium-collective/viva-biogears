"""Per-circuit composites driving the real BioGears engine.

Store layout:

- ``interventions/<module>/``: setpoints;
- ``circuits/<module>/``: the module's BioGears readings;
- ``circuits/irreversible_state``;
- a ``RAMEmitter`` step at ``emitter`` that emits both subtrees and time every update.
"""

from process_bigraph.composite_generator import composite_generator

from ..circuits import MODULES
from ..circuits.cardiovascular import CARDIOVASCULAR, HEMORRHAGE_COMPARTMENTS
from ..circuits.respiratory import (
    INTUBATION_TYPES,
    MECHANICAL_VENTILATOR,
    RESPIRATORY,
    VENTILATOR_BASELINE,
    VENTILATOR_CONNECTIONS,
)
from ..circuits.supplemental_oxygen import OXYGEN_BASELINE, SUPPLEMENTAL_OXYGEN
from ..circuits.thermal import (
    ENVIRONMENT_BASELINE,
    THERMAL,
    THERMAL_APPLICATION_BASELINE,
)
from ..core import build_core


def circuit_node(modules, *, state_file="StandardMale@0s.xml", patient_file="", conditions=None,
                 circuit_additions=None, interval=1.0, **params):
    """A ``BioGearsCircuitProcess`` node wired to the standard store layout."""
    return {
        "_type": "process",
        "address": "local:BioGearsCircuitProcess",
        "config": {"modules": list(modules), "state_file": state_file, "patient_file": patient_file,
                   "conditions": dict(conditions or {}),
                   "circuit_additions": dict(circuit_additions or {}), **params},
        "interval": interval,
        "inputs": {"setpoints": ["interventions"]},
        "outputs": {**{name: ["circuits", name] for name in modules},
                    "irreversible_state": ["circuits", "irreversible_state"]},
    }


def circuit_emitter():
    """A ``RAMEmitter`` recording the ``circuits`` and ``interventions`` subtrees and time."""
    return {
        "_type": "step",
        "address": "local:RAMEmitter",
        "config": {"emit": {"circuits": "node", "interventions": "node", "time": "float"}},
        "inputs": {"circuits": ["circuits"], "interventions": ["interventions"], "time": ["global_time"]},
    }


def setpoints(module, overrides, config):
    """The module's setpoint values: baselines updated from ``overrides`` (popped), each
    group validated with the same check the process applies at run time, so a bad
    parameter fails when the document is built."""
    values = {}
    for binding in module.bindings:
        group = {port: float(overrides.pop(port, default)) for port, default in binding.ports.items()}
        if binding.validate:
            binding.validate(group, config)
        values.update(group)
    return values


def reject_unknown(overrides):
    if overrides:
        raise TypeError(f"unexpected parameters: {sorted(overrides)}")


_INTERVAL = {"type": "float", "default": 1.0,
             "description": "Seconds per update; 0.02 (BioGears' timestep) resolves per-beat/per-breath "
                            "waveforms. A non-binary-exact interval can lose the final update of a run "
                            "to float time accumulation."}
_STATE_FILE = {"type": "string", "default": "StandardMale@0s.xml",
               "description": "BioGears state in <runtime>/states or the package's states/ (or an absolute path)"}
_PATIENT_FILE = {"type": "string", "default": "",
                 "description": "Patient file in <runtime>/patients (or a path), stabilized once (about 40 s) and "
                                "then cached; replaces state_file"}
_CONDITIONS = {"type": "map", "default": {},
               "description": "Chronic conditions applied while the patient stabilizes, e.g. "
                              "{ChronicAnemia: {ReductionFactor: 0.3}}; with no patient_file, StandardMale.xml. "
                              "A different patient, not a perturbation"}
_CIRCUIT_ADDITIONS = {"type": "map", "default": {},
                      "description": "New path name -> {source, target, resistance_mmHg_s_per_mL}: a resistance "
                                     "path between two FullCardiovascular nodes in different vascular compartments, "
                                     "added with its compartment link so substances follow. A perturbation: the "
                                     "body responds over time"}
_POINT_READS = {"type": "boolean", "default": False,
                "description": "Also read every node and path of the circuit, under circuits/<circuit>_points/"}
_SUBSTANCE_OUTPUTS = {"type": "list", "default": [],
                      "description": "Substance quantities to read, each {substance, compartment (omit for "
                                     "whole-body values), property, unit}, e.g. {substance: Oxygen, compartment: "
                                     "Aorta, property: PartialPressure, unit: mmHg}; emitted under "
                                     "circuits/substances/<substance>/<compartment or body>/. Checked against the "
                                     "state when the composite's process is built"}
_TISSUE_OUTPUTS = {"type": "list", "default": [],
                   "description": "Tissue values to read, each {compartment, property, unit}: a tissue's "
                                  "composition (MuscleTissue: MatrixVolume, TotalMass, ...) or its fluid "
                                  "(MuscleTissueExtracellular: Volume, Pressure, WaterVolumeFraction); emitted "
                                  "under circuits/tissues/<compartment>/"}


def _reading_config(substance_outputs, tissue_outputs):
    config = {"substance_outputs": list(substance_outputs or []), "tissue_outputs": list(tissue_outputs or [])}
    return {k: v for k, v in config.items() if v}


def with_readings(modules, substance_outputs, tissue_outputs):
    """``modules`` plus the ``substances``/``tissues`` modules when their lists are non-empty."""
    return [*modules, *(name for name, entries in (("substances", substance_outputs),
                                                   ("tissues", tissue_outputs)) if entries)]


def with_points(modules, point_reads):
    """``modules`` plus each one's ``<name>_points`` module when ``point_reads`` is set."""
    if not point_reads:
        return list(modules)
    return [*modules, *(f"{name}_points" for name in modules if f"{name}_points" in MODULES)]


_CARDIOVASCULAR_PARAMETERS = {
    "hemorrhage_compartment": {"type": "string", "default": "RightLeg", "choices": list(HEMORRHAGE_COMPARTMENTS),
                               "description": "Hemorrhage site"},
    "hemorrhage_rate_mL_per_min": {"type": "float", "default": 0.0,
                                   "description": "Initial bleeding rate (BioGears then lowers it with the local "
                                                  "pressure); 0 = no bleed"},
    "iv_compound": {"type": "string", "default": "Saline",
                    "description": "Infused BioGears compound (e.g. Saline, Blood_ONegative, RingersLactate)"},
    "iv_bag_volume_L": {"type": "float", "default": 10.0, "description": "Infusion bag volume"},
    "iv_rate_mL_per_min": {"type": "float", "default": 0.0, "description": "Infusion rate from t = 0; 0 = none"},
}


@composite_generator(
    name="biogears_cardiovascular",
    description="The BioGears cardiovascular circuit (with its renal, cerebral and tissue branches) in the real "
                "engine: hemodynamics plus per-compartment pressures, volumes and flows, driven by a hemorrhage "
                "and an IV infusion. Optional point, substance and tissue readings.",
    parameters={"state_file": _STATE_FILE, "patient_file": _PATIENT_FILE, "conditions": _CONDITIONS, "circuit_additions": _CIRCUIT_ADDITIONS, "interval": _INTERVAL, "point_reads": _POINT_READS,
                "substance_outputs": _SUBSTANCE_OUTPUTS, "tissue_outputs": _TISSUE_OUTPUTS,
                **_CARDIOVASCULAR_PARAMETERS},
    core_extensions=[build_core],
    default_n_steps=600,
    fidelity="real-bridge",
)
def biogears_cardiovascular(core=None, *, state_file="StandardMale@0s.xml", patient_file="", conditions=None, circuit_additions=None, interval=1.0, point_reads=False,
                            substance_outputs=None, tissue_outputs=None, hemorrhage_compartment="RightLeg",
                            iv_compound="Saline", iv_bag_volume_L=10.0, **overrides):
    config = {"hemorrhage_compartment": hemorrhage_compartment, "iv_compound": iv_compound,
              "iv_bag_volume_L": iv_bag_volume_L}
    CARDIOVASCULAR.check_config(config)
    values = setpoints(CARDIOVASCULAR, overrides, config)
    reject_unknown(overrides)
    modules = with_readings(with_points(["cardiovascular"], point_reads), substance_outputs, tissue_outputs)
    return {
        "biogears": circuit_node(modules, state_file=state_file, patient_file=patient_file, conditions=conditions, circuit_additions=circuit_additions, interval=interval, **config,
                                 **_reading_config(substance_outputs, tissue_outputs)),
        "interventions": {"cardiovascular": values},
        "circuits": {},
        "emitter": circuit_emitter(),
    }


_RESPIRATORY_PARAMETERS = {
    "state_file": _STATE_FILE, "patient_file": _PATIENT_FILE, "conditions": _CONDITIONS, "circuit_additions": _CIRCUIT_ADDITIONS, "interval": _INTERVAL, "point_reads": _POINT_READS,
    "intubation_type": {"type": "string", "default": "Tracheal", "choices": list(INTUBATION_TYPES),
                        "description": "Tube placement used when intubated = 1"},
}


@composite_generator(
    name="biogears_respiratory",
    description="The BioGears respiratory (airway) circuit coupled to the whole body: breathing mechanics plus "
                "per-compartment airway, lung and pleural pressures, volumes and flows, driven by intubation.",
    parameters={**_RESPIRATORY_PARAMETERS,
                "intubated": {"type": "float", "default": 0.0, "description": "1 = intubated, 0 = not"}},
    core_extensions=[build_core],
    default_n_steps=120,
    fidelity="real-bridge",
)
def biogears_respiratory(core=None, *, state_file="StandardMale@0s.xml", patient_file="", conditions=None, circuit_additions=None, interval=1.0, point_reads=False,
                         intubation_type="Tracheal", **overrides):
    config = {"intubation_type": intubation_type}
    RESPIRATORY.check_config(config)
    values = setpoints(RESPIRATORY, overrides, config)
    reject_unknown(overrides)
    return {
        "biogears": circuit_node(with_points(["respiratory"], point_reads), state_file=state_file, patient_file=patient_file, conditions=conditions, circuit_additions=circuit_additions,
                                 interval=interval, **config),
        "interventions": {"respiratory": values},
        "circuits": {},
        "emitter": circuit_emitter(),
    }


_VENTILATOR_DESCRIPTIONS = {
    "connected": "1 = ventilator connected, 0 = off",
    "ventilator_pressure_cmH2O": "Inspiratory pressure the ventilator applies",
    "peep_cmH2O": "Positive end-expiratory pressure",
    "respiration_rate_bpm": "Set breathing rate",
    "inspiratory_expiratory_ratio": "Inspiratory to expiratory time (0.5 = 1:2)",
    "oxygen_fraction": "Oxygen fraction of the delivered gas (wall supply, nitrogen balance)",
    "inlet_flow_L_per_min": "Fresh gas flow into the circuit",
}


@composite_generator(
    name="biogears_mechanical_ventilation",
    description="A patient on BioGears' anesthesia-machine ventilator (pressure control) in the real engine: the "
                "respiratory circuit combined with the ventilator circuit, emitting breathing mechanics, airway "
                "and lung compartments and the ventilator's settings and circuit. Defaults: intubated, tube, "
                "12 cmH2O / PEEP 1, 12 bpm, I:E 1:2, FiO2 0.21.",
    parameters={**_RESPIRATORY_PARAMETERS,
                "intubated": {"type": "float", "default": 1.0, "description": "1 = intubated, 0 = not"},
                "ventilator_connection": {"type": "string", "default": "Tube", "choices": list(VENTILATOR_CONNECTIONS),
                                          "description": "Tube (with intubation) or Mask"},
                **{port: {"type": "float", "default": (1.0 if port == "connected" else value),
                          "description": _VENTILATOR_DESCRIPTIONS[port]}
                   for port, value in VENTILATOR_BASELINE.items()}},
    core_extensions=[build_core],
    default_n_steps=120,
    fidelity="real-bridge",
)
def biogears_mechanical_ventilation(core=None, *, state_file="StandardMale@0s.xml", patient_file="", conditions=None, circuit_additions=None, interval=1.0, point_reads=False,
                                    intubation_type="Tracheal", ventilator_connection="Tube", **overrides):
    overrides.setdefault("intubated", 1.0)
    overrides.setdefault("connected", 1.0)
    config = {"intubation_type": intubation_type, "ventilator_connection": ventilator_connection}
    RESPIRATORY.check_config(config)
    MECHANICAL_VENTILATOR.check_config(config)
    respiratory = setpoints(RESPIRATORY, overrides, config)
    ventilator = setpoints(MECHANICAL_VENTILATOR, overrides, config)
    reject_unknown(overrides)
    return {
        "biogears": circuit_node(with_points(["respiratory", "mechanical_ventilator"], point_reads),
                                 state_file=state_file, patient_file=patient_file, conditions=conditions, circuit_additions=circuit_additions, interval=interval, **config),
        "interventions": {"respiratory": respiratory, "mechanical_ventilator": ventilator},
        "circuits": {},
        "emitter": circuit_emitter(),
    }


_THERMAL_DESCRIPTIONS = {
    "ambient_temperature_C": "Air temperature around the body (not the air breathed; see "
                             "respiration_ambient_temperature_C)",
    "mean_radiant_temperature_C": "Mean radiant temperature of the surroundings",
    "respiration_ambient_temperature_C": "Temperature of the air breathed; drives respiration heat loss",
    "relative_humidity": "Relative humidity in [0, 1]",
    "air_velocity_m_per_s": "Air speed over the body",
    "clothing_resistance_clo": "Clothing thermal resistance (1 clo = 0.155 m^2 K/W)",
    "active_heating_W": "Active heating power; BioGears delivers power x area fraction",
    "active_heating_area_fraction": "Fraction of skin area under active heating, in (0, 1]",
    "active_cooling_W": "Active cooling power; BioGears removes power x area fraction",
    "active_cooling_area_fraction": "Fraction of skin area under active cooling, in (0, 1]",
    "applied_temperature_on": "1 = apply applied_temperature_C over the clothing, 0 = off",
    "applied_temperature_C": "Applied temperature, used when applied_temperature_on = 1",
    "applied_temperature_area_fraction": "Fraction in (0, 1] by which BioGears blends the applied temperature "
                                         "with the ambient temperature",
}


@composite_generator(
    name="biogears_thermal",
    description="The BioGears temperature circuit (core and skin segments joined to clothing, enclosure and "
                "ambient air) in the real engine: core and skin temperatures, sweat, metabolic rate, heat-loss "
                "rates and per-compartment temperatures and heat flows, driven by the environment and by active "
                "heating, cooling or an applied temperature.",
    parameters={"state_file": _STATE_FILE, "patient_file": _PATIENT_FILE, "conditions": _CONDITIONS, "circuit_additions": _CIRCUIT_ADDITIONS, "interval": _INTERVAL,
                **{port: {"type": "float", "default": value, "description": _THERMAL_DESCRIPTIONS[port]}
                   for port, value in {**ENVIRONMENT_BASELINE, **THERMAL_APPLICATION_BASELINE}.items()}},
    core_extensions=[build_core],
    default_n_steps=1800,
    fidelity="real-bridge",
)
def biogears_thermal(core=None, *, state_file="StandardMale@0s.xml", patient_file="", conditions=None, circuit_additions=None, interval=1.0, **overrides):
    values = setpoints(THERMAL, overrides, {})
    reject_unknown(overrides)
    return {
        "biogears": circuit_node(["thermal"], state_file=state_file, patient_file=patient_file, conditions=conditions, circuit_additions=circuit_additions, interval=interval),
        "interventions": {"thermal": values},
        "circuits": {},
        "emitter": circuit_emitter(),
    }


_OXYGEN_FLOW = {"type": "float", "default": OXYGEN_BASELINE["oxygen_flow_L_per_min"],
                "description": "Nasal cannula oxygen flow"}


@composite_generator(
    name="biogears_supplemental_oxygen",
    description="Oxygen by nasal cannula in the real BioGears engine: the cannula circuit combined with the "
                "respiratory circuit, emitting breathing mechanics, airway and lung compartments and arterial "
                "blood gases.",
    parameters={"state_file": _STATE_FILE, "patient_file": _PATIENT_FILE, "conditions": _CONDITIONS, "circuit_additions": _CIRCUIT_ADDITIONS, "interval": _INTERVAL,
                "oxygen_connected": {"type": "float", "default": 1.0, "description": "1 = cannula on, 0 = off"},
                "oxygen_flow_L_per_min": _OXYGEN_FLOW},
    core_extensions=[build_core],
    default_n_steps=300,
    fidelity="real-bridge",
)
def biogears_supplemental_oxygen(core=None, *, state_file="StandardMale@0s.xml", patient_file="", conditions=None, circuit_additions=None, interval=1.0, **overrides):
    overrides.setdefault("oxygen_connected", 1.0)
    config = {"intubation_type": "Tracheal"}
    oxygen = setpoints(SUPPLEMENTAL_OXYGEN, overrides, config)
    reject_unknown(overrides)
    return {
        "biogears": circuit_node(["respiratory", "supplemental_oxygen"], state_file=state_file, patient_file=patient_file, conditions=conditions, circuit_additions=circuit_additions,
                                 interval=interval, **config),
        "interventions": {"respiratory": setpoints(RESPIRATORY, {}, config), "supplemental_oxygen": oxygen},
        "circuits": {},
        "emitter": circuit_emitter(),
    }


WHOLE_BODY_MODULES = (CARDIOVASCULAR, RESPIRATORY, MECHANICAL_VENTILATOR, THERMAL, SUPPLEMENTAL_OXYGEN)


@composite_generator(
    name="biogears_whole_body_circuits",
    description="Every circuit module with setpoints on one real BioGears engine (cardiovascular, respiratory, "
                "mechanical ventilator, thermal, supplemental oxygen) plus lymph and tissue fluid, so effects "
                "that cross circuits appear in one run. Setpoints start at their baselines; the ventilator and "
                "cannula start disconnected, and only one of them can be connected at a time. Optional point, "
                "substance and tissue readings.",
    parameters={
        "state_file": _STATE_FILE, "patient_file": _PATIENT_FILE, "conditions": _CONDITIONS, "circuit_additions": _CIRCUIT_ADDITIONS, "interval": _INTERVAL, "point_reads": _POINT_READS,
        "substance_outputs": _SUBSTANCE_OUTPUTS, "tissue_outputs": _TISSUE_OUTPUTS,
        **_CARDIOVASCULAR_PARAMETERS,
        "intubation_type": _RESPIRATORY_PARAMETERS["intubation_type"],
        "intubated": {"type": "float", "default": 0.0, "description": "1 = intubated, 0 = not"},
        "ventilator_connection": {"type": "string", "default": "Tube", "choices": list(VENTILATOR_CONNECTIONS),
                                  "description": "Tube (with intubation) or Mask"},
        **{port: {"type": "float", "default": value, "description": _VENTILATOR_DESCRIPTIONS[port]}
           for port, value in VENTILATOR_BASELINE.items()},
        **{port: {"type": "float", "default": value, "description": _THERMAL_DESCRIPTIONS[port]}
           for port, value in {**ENVIRONMENT_BASELINE, **THERMAL_APPLICATION_BASELINE}.items()},
        "oxygen_connected": {"type": "float", "default": 0.0, "description": "1 = cannula on, 0 = off"},
        "oxygen_flow_L_per_min": _OXYGEN_FLOW,
    },
    core_extensions=[build_core],
    default_n_steps=600,
    fidelity="real-bridge",
)
def biogears_whole_body_circuits(core=None, *, state_file="StandardMale@0s.xml", patient_file="", conditions=None, circuit_additions=None, interval=1.0, point_reads=False,
                                 substance_outputs=None, tissue_outputs=None, hemorrhage_compartment="RightLeg",
                                 iv_compound="Saline", iv_bag_volume_L=10.0, intubation_type="Tracheal",
                                 ventilator_connection="Tube", **overrides):
    config = {"hemorrhage_compartment": hemorrhage_compartment, "iv_compound": iv_compound,
              "iv_bag_volume_L": iv_bag_volume_L, "intubation_type": intubation_type,
              "ventilator_connection": ventilator_connection}
    for module in WHOLE_BODY_MODULES:
        if module.check_config:
            module.check_config(config)
    interventions = {m.name: setpoints(m, overrides, config) for m in WHOLE_BODY_MODULES}
    reject_unknown(overrides)
    connected = [m.name for m in WHOLE_BODY_MODULES
                 if m.airway_device and interventions[m.name][m.airway_device] == 1.0]
    if len(connected) > 1:
        raise ValueError(f"only one airway device can be connected at a time, got {connected}")
    modules = with_readings(with_points([m.name for m in WHOLE_BODY_MODULES], point_reads)
                            + ["lymph", "tissue_fluid"], substance_outputs, tissue_outputs)
    return {
        "biogears": circuit_node(modules, state_file=state_file, patient_file=patient_file, conditions=conditions, circuit_additions=circuit_additions, interval=interval, **config,
                                 **_reading_config(substance_outputs, tissue_outputs)),
        "interventions": interventions,
        "circuits": {},
        "emitter": circuit_emitter(),
    }
