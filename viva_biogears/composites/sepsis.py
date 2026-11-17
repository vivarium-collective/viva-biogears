"""Sepsis (BioGears' infection model, McDaniel et al. 2019) with lymph, tissue fluid and nutrition."""

from process_bigraph.composite_generator import composite_generator

from ..circuits.cardiovascular import CARDIOVASCULAR
from ..circuits.sepsis import INFECTION, INFECTION_SCENARIO_SCHEDULE
from ..circuits.state import state_time_s
from ..circuits.treatment import TREATMENT
from ..core import build_core
from ..protocols import PROTOCOL_CODES, PROTOCOLS, TreatmentProtocol
from ..runtime import runtime_dir, state_path
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
#: drives, meals, cardiovascular for hemodynamics and the saline setpoint, and treatment
#: (the antibiotic, the vasopressor setpoint and the drugs' concentrations).
MODULES = ("infection", "nutrition", "lymph", "tissue_fluid", "cardiovascular", "treatment")
#: Drugs whose concentrations a treated run reads (only then: asking activates them).
TREATMENT_READOUTS = ["Piperacillin", "Norepinephrine"]
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
        "iv_compound": {"type": "string", "default": "Saline", "description": "IV fluid (the protocols' saline)"},
        "iv_rate_mL_per_min": {"type": "float", "default": 0.0,
                               "description": "Infusion rate from t = 0 (no protocol only)"},
        "treatment": {"type": "string", "default": "none", "choices": list(PROTOCOLS),
                      "description": "McDaniel et al. 2019 treatment protocol (viva_biogears.protocols): "
                                     "fluid_challenge (Fig 9), antibiotic (Fig 10), refresh_control and "
                                     "refresh_experimental (Figs 11-13); run to its end_h"},
        "challenge_h": {"type": "float", "default": 44.0, "description": "Saline challenge (2 x 500 mL) at"},
        "treatment_start_h": {"type": "float", "default": 46.0,
                              "description": "Antibiotic and REFRESH start (58 for Fig 13's delayed arm)"},
        "treatment_duration_h": {"type": "float", "default": 6.0, "description": "REFRESH reassessment period"},
        "drug_readouts": {"type": "list", "default": None,
                          "description": "Drugs whose concentrations are read (circuits/treatment/<drug>); default "
                                         "Piperacillin and Norepinephrine when treated, none otherwise. Give an "
                                         "untreated arm the treated arms' list to record the same stores"},
        "state_file": _STATE_FILE, "patient_file": _PATIENT_FILE, "conditions": _CONDITIONS,
        "circuit_additions": _CIRCUIT_ADDITIONS,
        "interval": {"type": "float", "default": 60.0, "description": "Seconds per update"},
        "time_step_s": {"type": "float", "default": 0.02,
                        "description": "BioGears' solver step (validated at 0.02 s; must be < 0.1 s)"},
    },
    core_extensions=[build_core],
    default_n_steps=2880,
    fidelity="real-bridge",
)
def biogears_sepsis(core=None, *, severity="severe", infection_location="Skin", infection_mic_mg_per_L=16.0,
                    nutrition="infection_scenario", iv_compound="Saline", state_file="StandardMale@0s.xml",
                    patient_file="", conditions=None, circuit_additions=None, interval=60.0, treatment="none",
                    challenge_h=44.0, treatment_start_h=46.0, treatment_duration_h=6.0, drug_readouts=None,
                    time_step_s=0.02, **overrides):
    if severity not in SEVERITY_LEVELS:
        raise ValueError(f"severity must be one of {list(SEVERITY_LEVELS)}, got {severity!r}")
    if nutrition not in NUTRITION_SCHEDULES:
        raise ValueError(f"nutrition must be one of {list(NUTRITION_SCHEDULES)}, got {nutrition!r}")
    protocol = TreatmentProtocol(treatment, challenge_h=challenge_h, start_h=treatment_start_h,
                                 duration_h=treatment_duration_h, interval_s=interval)
    config = {"infection_location": infection_location, "infection_mic_mg_per_L": infection_mic_mg_per_L,
              "iv_compound": iv_compound, "iv_bag_volume_L": 10.0, "hemorrhage_compartment": "RightLeg",
              "nutrition_schedule": list(NUTRITION_SCHEDULES[nutrition]),
              "treatment_schedule": protocol.schedule(),
              "treatment_readouts": list(drug_readouts if drug_readouts is not None
                                         else TREATMENT_READOUTS if treatment != "none" else []),
              "vasopressor_substance": "Norepinephrine", "vasopressor_concentration_ug_per_mL": 14.0,
              "time_step_s": float(time_step_s)}
    INFECTION.check_config(config)
    TREATMENT.check_config(config)
    cardiovascular = setpoints(CARDIOVASCULAR, overrides, config)
    if treatment != "none" and cardiovascular["iv_rate_mL_per_min"] != 0.0:
        raise ValueError("iv_rate_mL_per_min is set by the treatment protocol; leave it at 0")
    reject_unknown(overrides)
    # A run can start from a saved septic state (McDaniel et al. ran every treatment from
    # states saved during the untreated severe infection): the protocol keeps engine time.
    branch_s = 0.0 if patient_file else state_time_s(state_path(runtime_dir(), state_file))
    if treatment != "none" and branch_s > protocol.challenge_s + 1e-6:
        raise ValueError(f"state_file {state_file!r} was saved at {branch_s / 3600:.2f} h, after the protocol's "
                         f"challenge at {challenge_h:g} h; start from an earlier state or move challenge_h")
    doc = {
        "biogears": circuit_node(MODULES, state_file=state_file, patient_file=patient_file, conditions=conditions,
                                 circuit_additions=circuit_additions, interval=interval, **config),
        "interventions": {"infection": {"infection_severity": SEVERITY_LEVELS[severity]},
                          "cardiovascular": cardiovascular,
                          "treatment": {"vasopressor_rate_ug_per_min": 0.0}},
        "circuits": {},
        "engine": {"time_step_s": float(time_step_s)},  # recorded so figures can tell runs apart
        "emitter": circuit_emitter(),
    }
    if treatment != "none":
        clinical = ["circuits", "infection", "clinical"]
        doc["controller"] = {
            "_type": "step",
            "address": "local:TreatmentController",
            "config": {"protocol": treatment, "challenge_h": challenge_h, "start_h": treatment_start_h,
                       "duration_h": treatment_duration_h, "interval_s": interval, "time_offset_s": branch_s},
            "inputs": {"time": ["global_time"],
                       "systolic_pressure_mmHg": [*clinical, "systolic_pressure_mmHg"],
                       "mean_arterial_pressure_mmHg": [*clinical, "mean_arterial_pressure_mmHg"],
                       "mean_urine_output_mL_per_min": [*clinical, "mean_urine_output_mL_per_min"]},
            "outputs": {"iv_rate_mL_per_min": ["interventions", "cardiovascular", "iv_rate_mL_per_min"],
                        "vasopressor_rate_ug_per_min": ["interventions", "treatment", "vasopressor_rate_ug_per_min"],
                        "saline_given_mL": ["protocol", "saline_given_mL"],
                        "protocol_code": ["protocol", "code"],
                        "branch_h": ["protocol", "branch_h"],
                        "treatment_start_h": ["protocol", "treatment_start_h"]},
        }
    # Every run records its protocol (code 0 and no saline when untreated), the engine hour
    # it started at and the hour its treatment starts (the challenge for fluid_challenge),
    # so figures and tests can tell the arms apart and put them on one clock.
    doc["protocol"] = {"code": PROTOCOL_CODES[treatment], "saline_given_mL": 0.0, "branch_h": branch_s / 3600.0,
                       "treatment_start_h": float(challenge_h if treatment == "fluid_challenge" else treatment_start_h)}
    emitter = doc["emitter"]
    emitter["config"]["emit"]["protocol"] = "node"
    emitter["inputs"]["protocol"] = ["protocol"]
    return doc
