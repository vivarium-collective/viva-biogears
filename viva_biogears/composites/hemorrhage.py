"""Hemorrhage and fluid-resuscitation composites driving the real BioGears engine."""

from process_bigraph.composite_generator import composite_generator

from ..core import build_core
from ..processes import VITALS

_VITAL_PATHS = {name: ["vitals", name] for name in VITALS}


def _biogears_node(state_file, compartment, compound):
    return {
        "_type": "process",
        "address": "local:BioGearsProcess",
        "config": {
            "state_file": state_file,
            "hemorrhage_compartment": compartment,
            "iv_compound": compound,
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
    "compartment": {"type": "string", "default": "RightLeg",
                    "description": "Hemorrhage site (a compartment with a BioGears bleed path)"},
    "rate_mL_per_min": {"type": "float", "default": 250.0,
                        "description": "Initial bleeding rate; BioGears' rate then falls with local pressure"},
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
                        rate_mL_per_min=250.0):
    return {
        "biogears": _biogears_node(state_file, compartment, "Saline"),
        "interventions": {"hemorrhage_rate_mL_per_min": rate_mL_per_min, "iv_rate_mL_per_min": 0.0},
        "vitals": {},
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
                           rate_mL_per_min=250.0, compound="Saline",
                           target_map_mmHg=90.0, gain=25.0, max_rate_mL_per_min=250.0):
    doc = biogears_hemorrhage(core, state_file=state_file, compartment=compartment, rate_mL_per_min=rate_mL_per_min)
    doc["biogears"] = _biogears_node(state_file, compartment, compound)
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
