"""Hemorrhage and fluid-resuscitation composites driving the real BioGears engine."""

from process_bigraph.composite_generator import composite_generator

from ..core import build_core
from ..processes import VITALS
from .circuits import _PATIENT, _PATIENT_TABLE, _SUBSTANCE_TABLE

_VITAL_PATHS = {name: ["vitals", name] for name in VITALS}


def _biogears_node(state_file, compartment, compound, patient_file="", conditions=None, circuit_additions=None,
                   time_step_s=0.02, patient_table="", patient="", substance_table=""):
    return {
        "_type": "process",
        "address": "local:BioGearsProcess",
        "config": {
            "state_file": state_file,
            "patient_file": patient_file,
            "patient_table": patient_table,
            "patient": patient,
            "conditions": dict(conditions or {}),
            "substance_table": substance_table,
            "circuit_additions": dict(circuit_additions or {}),
            "hemorrhage_compartment": compartment,
            "iv_compound": compound,
            "time_step_s": time_step_s,
        },
        "interval": 1.0,
        "inputs": {
            "hemorrhage_rate_mL_per_min": ["interventions", "hemorrhage_rate_mL_per_min"],
            "iv_rate_mL_per_min": ["interventions", "iv_rate_mL_per_min"],
        },
        "outputs": {**_VITAL_PATHS, "irreversible_state": ["vitals", "irreversible_state"]},
    }


def _emitter():
    emit = {name: "float" for name in VITALS}
    emit.update({"irreversible_state": "boolean", "iv_rate_mL_per_min": "float", "time": "float"})
    inputs = {name: ["vitals", name] for name in VITALS}
    inputs.update({
        "irreversible_state": ["vitals", "irreversible_state"],
        "iv_rate_mL_per_min": ["interventions", "iv_rate_mL_per_min"],
        "time": ["global_time"],
    })
    return {"_type": "step", "address": "local:RAMEmitter", "config": {"emit": emit}, "inputs": inputs}


_COMMON_PARAMETERS = {
    "state_file": {"type": "string", "default": "StandardMale@0s.xml",
                   "description": "BioGears state in <runtime>/states (or an absolute path)"},
    "patient_file": {"type": "string", "default": "",
                     "description": "Patient file in <runtime>/patients (or a path), stabilized once and cached; "
                                    "replaces state_file"},
    "patient_table": _PATIENT_TABLE,
    "patient": _PATIENT,
    "conditions": {"type": "map", "default": {},
                   "description": "Chronic conditions applied while the patient stabilizes, e.g. "
                                  "{ChronicAnemia: {ReductionFactor: 0.3}}"},
    "substance_table": _SUBSTANCE_TABLE,
    "circuit_additions": {"type": "map", "default": {},
                          "description": "New path name -> {source, target, resistance_mmHg_s_per_mL} added to the "
                                         "cardiovascular circuit with its compartment link (a perturbation)"},
    "compartment": {"type": "string", "default": "RightLeg",
                    "description": "Hemorrhage site (a compartment with a BioGears bleed path)"},
    "rate_mL_per_min": {"type": "float", "default": 250.0,
                        "description": "Initial bleeding rate; BioGears' rate then falls with local pressure"},
    "time_step_s": {"type": "float", "default": 0.02,
                    "description": "BioGears' solver step (validated at 0.02 s; must be < 0.1 s)"},
}


@composite_generator(
    name="biogears_hemorrhage",
    description="Untreated hemorrhage in the real BioGears 8.2.0 engine; emits vital signs every second.",
    parameters=_COMMON_PARAMETERS,
    core_extensions=[build_core],
    default_n_steps=600,
    fidelity="real-bridge",
)
def biogears_hemorrhage(core=None, *, state_file="StandardMale@0s.xml", compartment="RightLeg",
                        rate_mL_per_min=250.0, patient_file="", conditions=None, circuit_additions=None,
                        time_step_s=0.02, patient_table="", patient="", substance_table=""):
    tables = {"patient_table": patient_table, "patient": patient, "substance_table": substance_table}
    return {
        "biogears": _biogears_node(state_file, compartment, "Saline", patient_file, conditions, circuit_additions,
                                   time_step_s, **tables),
        "interventions": {"hemorrhage_rate_mL_per_min": rate_mL_per_min, "iv_rate_mL_per_min": 0.0},
        "vitals": {},
        "engine": {"time_step_s": float(time_step_s)},  # recorded so figures can tell runs apart
        "emitter": _emitter(),
    }


@composite_generator(
    name="biogears_resuscitation",
    description="Hemorrhage in the real BioGears engine with a closed-loop MAP-targeted IV fluid controller.",
    parameters={
        **_COMMON_PARAMETERS,
        "compound": {"type": "string", "default": "Saline",
                     "description": "Infused compound (a BioGears compound, e.g. Saline, Blood_ONegative)"},
        "target_map_mmHg": {"type": "float", "default": 90.0, "description": "Controller MAP target"},
        "gain": {"type": "float", "default": 25.0, "description": "Controller gain, mL/min per mmHg below target"},
        "max_rate_mL_per_min": {"type": "float", "default": 250.0, "description": "Infusion rate ceiling"},
    },
    core_extensions=[build_core],
    default_n_steps=600,
    fidelity="real-bridge",
)
def biogears_resuscitation(core=None, *, state_file="StandardMale@0s.xml", compartment="RightLeg",
                           rate_mL_per_min=250.0, compound="Saline", patient_file="", conditions=None, circuit_additions=None,
                           target_map_mmHg=90.0, gain=25.0, max_rate_mL_per_min=250.0, time_step_s=0.02,
                           patient_table="", patient="", substance_table=""):
    tables = {"patient_table": patient_table, "patient": patient, "substance_table": substance_table}
    doc = biogears_hemorrhage(core, state_file=state_file, compartment=compartment, rate_mL_per_min=rate_mL_per_min,
                              patient_file=patient_file, conditions=conditions, circuit_additions=circuit_additions,
                              time_step_s=time_step_s, **tables)
    doc["biogears"] = _biogears_node(state_file, compartment, compound, patient_file, conditions, circuit_additions,
                                     time_step_s, **tables)
    doc["controller"] = {
        "_type": "step",
        "address": "local:MapFluidController",
        "config": {
            "target_map_mmHg": target_map_mmHg,
            "gain_mL_per_min_per_mmHg": gain,
            "max_rate_mL_per_min": max_rate_mL_per_min,
        },
        "inputs": {"mean_arterial_pressure_mmHg": ["vitals", "mean_arterial_pressure_mmHg"]},
        "outputs": {"iv_rate_mL_per_min": ["interventions", "iv_rate_mL_per_min"]},
    }
    return doc
