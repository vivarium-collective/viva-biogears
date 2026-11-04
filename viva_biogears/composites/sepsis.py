"""Sepsis (BioGears' infection model, McDaniel et al. 2019) with lymph, tissue fluid and nutrition."""

from process_bigraph.composite_generator import composite_generator

from ..circuits.cardiovascular import CARDIOVASCULAR
from ..circuits.sepsis import INFECTION, INFECTION_SCENARIO_SCHEDULE
from ..core import build_core
from .circuits import (
    _CIRCUIT_ADDITIONS,
    _CONDITIONS,
    _PATIENT_FILE,
    _STATE_FILE,
    circuit_emitter,
    circuit_node,
    reject_unknown,
    setpoints,
)

#: Modules on the process: the infection's readings and setpoint, the fluid exchange it
#: drives, meals, and cardiovascular for hemodynamics and the IV setpoint.
MODULES = ("infection", "nutrition", "lymph", "tissue_fluid", "cardiovascular")
SEVERITY_LEVELS = {"none": 0.0, "mild": 1.0, "moderate": 2.0, "severe": 3.0}
NUTRITION_SCHEDULES = {"infection_scenario": INFECTION_SCENARIO_SCHEDULE, "none": []}


@composite_generator(
    name="biogears_sepsis",
    description="An infection in the real BioGears 8.2.0 engine (McDaniel et al. 2019): the acute inflammatory "
                "response, its clinical signs, the endothelial leak and lymph it drives, with BioGears' own meal "
                "and water schedule; emits every simulated minute by default.",
    parameters={
        "severity": {"type": "string", "default": "severe", "choices": list(SEVERITY_LEVELS),
                     "description": "Infection started at t = 0 ('none' for an uninfected control)"},
        "infection_location": {"type": "string", "default": "Skin", "description": "Infection site (a label)"},
        "infection_mic_mg_per_L": {"type": "float", "default": 16.0,
                                   "description": "Pathogen minimum inhibitory concentration (the paper's 16 mg/L)"},
        "nutrition": {"type": "string", "default": "infection_scenario", "choices": list(NUTRITION_SCHEDULES),
                      "description": "infection_scenario: BioGears' InfectionModerate schedule (water hourly, "
                                     "five meals in 48 h); none: no intake"},
        "iv_compound": {"type": "string", "default": "Saline", "description": "IV fluid for a fluid challenge"},
        "iv_rate_mL_per_min": {"type": "float", "default": 0.0, "description": "Infusion rate from t = 0"},
        "state_file": _STATE_FILE, "patient_file": _PATIENT_FILE, "conditions": _CONDITIONS,
        "circuit_additions": _CIRCUIT_ADDITIONS,
        "interval": {"type": "float", "default": 60.0, "description": "Seconds per update"},
    },
    core_extensions=[build_core],
    default_n_steps=2880,
    fidelity="real-bridge",
)
def biogears_sepsis(core=None, *, severity="severe", infection_location="Skin", infection_mic_mg_per_L=16.0,
                    nutrition="infection_scenario", iv_compound="Saline", state_file="StandardMale@0s.xml",
                    patient_file="", conditions=None, circuit_additions=None, interval=60.0, **overrides):
    if severity not in SEVERITY_LEVELS:
        raise ValueError(f"severity must be one of {list(SEVERITY_LEVELS)}, got {severity!r}")
    if nutrition not in NUTRITION_SCHEDULES:
        raise ValueError(f"nutrition must be one of {list(NUTRITION_SCHEDULES)}, got {nutrition!r}")
    config = {"infection_location": infection_location, "infection_mic_mg_per_L": infection_mic_mg_per_L,
              "iv_compound": iv_compound, "iv_bag_volume_L": 10.0, "hemorrhage_compartment": "RightLeg",
              "nutrition_schedule": list(NUTRITION_SCHEDULES[nutrition])}
    INFECTION.check_config(config)
    cardiovascular = setpoints(CARDIOVASCULAR, overrides, config)
    reject_unknown(overrides)
    return {
        "biogears": circuit_node(MODULES, state_file=state_file, patient_file=patient_file, conditions=conditions,
                                 circuit_additions=circuit_additions, interval=interval, **config),
        "interventions": {"infection": {"infection_severity": SEVERITY_LEVELS[severity]},
                          "cardiovascular": cardiovascular},
        "circuits": {},
        "emitter": circuit_emitter(),
    }
