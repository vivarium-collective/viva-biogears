"""Lymph and tissue fluid at rest or under an IV infusion (real BioGears 8.2.0)."""

from process_bigraph.composite_generator import composite_generator

from ..circuits.cardiovascular import CARDIOVASCULAR
from ..core import build_core
from ..runtime import EQUILIBRATED_STATE
from .circuits import (
    _CONDITIONS,
    _PATIENT_FILE,
    circuit_emitter,
    circuit_node,
    reject_unknown,
    setpoints,
)

#: Modules on the process: readings (lymph, tissue fluid, vitals) plus cardiovascular for its setpoints.
MODULES = ("vitals", "lymph", "tissue_fluid", "cardiovascular")


@composite_generator(
    name="biogears_lymph",
    description="Lymph formation, pool and return, and tissue-fluid exchange in the real BioGears 8.2.0 engine, "
                "at rest or under a saline (or other compound) infusion, from the equilibrated StandardMale; "
                "emits every circuit reading each second.",
    parameters={
        "state_file": {"type": "string", "default": EQUILIBRATED_STATE,
                       "description": "BioGears state (default: StandardMale equilibrated 5 h at rest; "
                                      "see viva_biogears/states/README.md)"},
        "patient_file": {**_PATIENT_FILE, "description": _PATIENT_FILE["description"]
                         + " (not equilibrated: see viva_biogears/states/README.md)"},
        "conditions": _CONDITIONS,
        "iv_rate_mL_per_min": {"type": "float", "default": 0.0,
                               "description": "Constant infusion rate from t = 0; 0 for rest"},
        "iv_compound": {"type": "string", "default": "Saline", "description": "Infused BioGears compound"},
        "interval": {"type": "float", "default": 1.0, "description": "Seconds per update"},
    },
    core_extensions=[build_core],
    default_n_steps=600,
    fidelity="real-bridge",
)
def biogears_lymph(core=None, *, state_file=EQUILIBRATED_STATE, patient_file="", conditions=None, iv_compound="Saline",
                   interval=1.0, **overrides):
    config = {"iv_compound": iv_compound, "iv_bag_volume_L": 10.0, "hemorrhage_compartment": "RightLeg"}
    values = setpoints(CARDIOVASCULAR, overrides, config)
    reject_unknown(overrides)
    return {
        # A patient starts from its own stabilized state, so the equilibrated default steps aside.
        "biogears": circuit_node(MODULES, state_file=("StandardMale@0s.xml" if (patient_file or conditions)
                                                      and state_file == EQUILIBRATED_STATE else state_file),
                                 patient_file=patient_file, conditions=conditions, interval=interval, **config),
        "interventions": {"cardiovascular": values},
        "circuits": {},
        "emitter": circuit_emitter(),
    }
