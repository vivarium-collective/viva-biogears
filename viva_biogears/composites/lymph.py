"""Lymph and tissue-fluid readout around a saline fluid challenge (real BioGears 8.2.0)."""

from process_bigraph.composite_generator import composite_generator

from ..core import build_core
from ..runtime import EQUILIBRATED_STATE

#: Emitted scalars: column -> store path.
EMIT = {
    "lymph_return_mL_per_min": ["lymph", "return_mL_per_min"],
    "lymph_pool_volume_mL": ["lymph", "pool_volume_mL"],
    "lymph_pool_pressure_mmHg": ["lymph", "pool_pressure_mmHg"],
    "central_venous_pressure_mmHg": ["lymph", "central_venous_pressure_mmHg"],
    "muscle_lymph_formation_mL_per_min": ["lymph", "formation", "muscle_mL_per_min"],
    "muscle_filtration_mL_per_min": ["tissue_fluid", "muscle", "filtration_mL_per_min"],
    "muscle_extracellular_volume_mL": ["tissue_fluid", "muscle", "extracellular_volume_mL"],
    "plasma_albumin_g_per_dL": ["tissue_fluid", "plasma_albumin_g_per_dL"],
    "blood_volume_mL": ["tissue_fluid", "blood_volume_mL"],
    "extravascular_fluid_mL": ["tissue_fluid", "extravascular_fluid_mL"],
    "mean_arterial_pressure_mmHg": ["vitals", "mean_arterial_pressure_mmHg"],
}


@composite_generator(
    name="biogears_lymph",
    description="Lymph formation, pool and return, and tissue-fluid exchange in the real BioGears 8.2.0 engine, "
                "at rest or under a saline (or other compound) infusion; emits every second.",
    parameters={
        "state_file": {"type": "string", "default": EQUILIBRATED_STATE,
                       "description": "BioGears state (default: StandardMale equilibrated 5 h at rest; "
                                      "see viva_biogears/states/README.md)"},
        "iv_rate_mL_per_min": {"type": "float", "default": 0.0,
                               "description": "Constant infusion rate from t = 0; 0 for rest"},
        "compound": {"type": "string", "default": "Saline", "description": "Infused BioGears compound"},
    },
    core_extensions=[build_core],
    default_n_steps=600,
    fidelity="real-bridge",
)
def biogears_lymph(core=None, *, state_file=EQUILIBRATED_STATE, iv_rate_mL_per_min=0.0, compound="Saline"):
    modules = ["vitals", "lymph", "tissue_fluid"]
    return {
        "biogears": {
            "_type": "process",
            "address": "local:BioGearsCircuitProcess",
            "config": {"state_file": state_file, "iv_compound": compound, "modules": modules},
            "interval": 1.0,
            "inputs": {"interventions": ["interventions"]},
            "outputs": {**{m: [m] for m in modules}, "irreversible_state": ["irreversible_state"]},
        },
        "interventions": {"hemorrhage_rate_mL_per_min": 0.0, "iv_rate_mL_per_min": iv_rate_mL_per_min},
        "emitter": {
            "_type": "step",
            "address": "local:RAMEmitter",
            "config": {"emit": {**{k: "float" for k in EMIT}, "time": "float"}},
            "inputs": {**EMIT, "time": ["global_time"]},
        },
    }
