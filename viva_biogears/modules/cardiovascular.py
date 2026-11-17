"""Cardiovascular circuit module (with its renal, cerebral and tissue branches).

BioGears solves the cardiovascular circuit as one matrix with the renal, cerebral
and tissue sub-circuits (``FullCardiovascular``), so all are one module here,
grouped into sub-stores that follow the circuit's branches:

- ``hemodynamics``: BioGears' cardiovascular-system scalars
  (``SECardiovascularSystem``). Mean, systolic and diastolic values are per beat;
  the rest are instantaneous.
- ``central``: heart chambers, great vessels and the pulmonary circulation.
- ``cerebral``: neck and cerebral vessels (BioGears' cerebral sub-circuit).
- ``renal``: kidney vasculature.
- ``peripheral``: the organ and limb branches.

Every compartment reports ``pressure_mmHg``, ``volume_mL``, ``inflow_mL_per_min``
and ``outflow_mL_per_min``. These are instantaneous within each heartbeat: sample
at BioGears' 0.02 s timestep to see waveforms; 1 s sampling aliases the cycle.
``Pericardium`` has no blood path, so it has no flows (BioGears reads NaN).
Compartments are hierarchical (``Heart`` contains the chambers), so values don't add up.

Setpoints:

- ``hemorrhage_rate_mL_per_min`` at config ``hemorrhage_compartment``: BioGears'
  initial bleeding rate, which it then lowers with the local pressure; 0 stops it.
  Resending restarts the bleed, so it is sent only on change. A rate above cardiac
  output is refused by BioGears on every step, which the process raises.
- ``iv_rate_mL_per_min`` of config ``iv_compound`` (``SubstanceCompoundInfusion``
  from a bag of ``iv_bag_volume_L``); 0 stops it.

There are no resistance or compliance multipliers: BioGears 8.2.0 has no action that
modifies its circuit mechanics (its overrides set outputs, not the circuit).
"""

from __future__ import annotations

import math
from typing import Any

from .base import ActionBinding, CircuitModule, Request, check_nonnegative
from .state import scalar, text

#: Compartments BioGears 8.2.0 can bleed from: those with a "<name>Bleed" path in
#: the cardiovascular circuit (BioGearsCircuits.h). Any other name is accepted by
#: BioGears and then segfaults on the next step (pybiogears probe P7).
HEMORRHAGE_COMPARTMENTS = (
    "Aorta", "Brain", "Myocardium", "LeftLung", "RightLung", "LeftArm", "RightArm", "Spleen",
    "SmallIntestine", "LargeIntestine", "Splanchnic", "RightKidney", "LeftKidney", "Liver",
    "Portal", "LeftLeg", "RightLeg", "VenaCava",
)

# port -> (SECardiovascularSystem property, unit)
_HEMODYNAMICS = {
    "heart_rate_bpm": ("HeartRate", "1/min"),
    "mean_arterial_pressure_mmHg": ("MeanArterialPressure", "mmHg"),
    "systolic_pressure_mmHg": ("SystolicArterialPressure", "mmHg"),
    "diastolic_pressure_mmHg": ("DiastolicArterialPressure", "mmHg"),
    "arterial_pressure_mmHg": ("ArterialPressure", "mmHg"),
    "pulse_pressure_mmHg": ("PulsePressure", "mmHg"),
    "cardiac_output_L_per_min": ("CardiacOutput", "L/min"),
    "cardiac_index_L_per_min_m2": ("CardiacIndex", "L/min m^2"),
    "stroke_volume_mL": ("HeartStrokeVolume", "mL"),
    "ejection_fraction": ("HeartEjectionFraction", ""),
    "central_venous_pressure_mmHg": ("CentralVenousPressure", "mmHg"),
    "mean_central_venous_pressure_mmHg": ("MeanCentralVenousPressure", "mmHg"),
    "pulmonary_arterial_pressure_mmHg": ("PulmonaryArterialPressure", "mmHg"),
    "pulmonary_mean_arterial_pressure_mmHg": ("PulmonaryMeanArterialPressure", "mmHg"),
    "pulmonary_capillary_wedge_pressure_mmHg": ("PulmonaryCapillariesWedgePressure", "mmHg"),
    "systemic_vascular_resistance_mmHg_min_per_L": ("SystemicVascularResistance", "mmHg min/L"),
    "pulmonary_vascular_resistance_mmHg_min_per_L": ("PulmonaryVascularResistance", "mmHg min/L"),
    "blood_volume_mL": ("BloodVolume", "mL"),
    "cerebral_blood_flow_mL_per_min": ("CerebralBloodFlow", "mL/min"),
    "cerebral_perfusion_pressure_mmHg": ("CerebralPerfusionPressure", "mmHg"),
    "intracranial_pressure_mmHg": ("IntracranialPressure", "mmHg"),
    "mean_skin_flow_mL_per_min": ("MeanSkinFlow", "mL/min"),
}
#: NaN until the first hemorrhage (BioGears creates the value then).
_BLOOD_LOST = ("total_blood_volume_lost_mL", "TotalBloodVolumeLost", "mL")

# group -> {store name: BioGears liquid compartment (BioGearsCompartments.h, BGE::VascularCompartment)}
COMPARTMENTS = {
    "central": {
        "aorta": "Aorta",
        "heart": "Heart",
        "left_heart": "LeftHeart",
        "right_heart": "RightHeart",
        "left_atrium": "LeftAtrium",
        "left_ventricle": "LeftVentricle",
        "right_atrium": "RightAtrium",
        "right_ventricle": "RightVentricle",
        "myocardium": "MyocardiumVasculature",
        "pericardium": "Pericardium",
        "vena_cava": "VenaCava",
        "pulmonary_arteries": "PulmonaryArteries",
        "pulmonary_capillaries": "PulmonaryCapillaries",
        "pulmonary_veins": "PulmonaryVeins",
    },
    "cerebral": {
        "neck_arteries": "NeckArteries",
        "cerebral_arteries": "CerebralArteries",
        "cerebral_capillaries": "CerebralCapillaries",
        "cerebral_veins": "CerebralVeins",
        "neck_veins": "NeckVeins",
    },
    "renal": {
        "left_kidney": "LeftKidneyVasculature",
        "right_kidney": "RightKidneyVasculature",
        "left_renal_artery": "LeftRenalArtery",
        "right_renal_artery": "RightRenalArtery",
        "left_glomerular_capillaries": "LeftGlomerularCapillaries",
        "right_glomerular_capillaries": "RightGlomerularCapillaries",
        "left_renal_vein": "LeftRenalVein",
        "right_renal_vein": "RightRenalVein",
    },
    "peripheral": {
        "brain": "BrainVasculature",
        "muscle": "MuscleVasculature",
        "skin": "SkinVasculature",
        "fat": "FatVasculature",
        "bone": "BoneVasculature",
        "liver": "LiverVasculature",
        "spleen": "SpleenVasculature",
        "gut": "GutVasculature",
        "splanchnic": "SplanchnicVasculature",
        "small_intestine": "SmallIntestineVasculature",
        "large_intestine": "LargeIntestineVasculature",
        "left_arm": "LeftArmVasculature",
        "right_arm": "RightArmVasculature",
        "left_leg": "LeftLegVasculature",
        "right_leg": "RightLegVasculature",
    },
}

_COMPARTMENT_PROPERTIES = {
    "pressure_mmHg": ("Pressure", "mmHg"),
    "volume_mL": ("Volume", "mL"),
    "inflow_mL_per_min": ("InFlow", "mL/min"),
    "outflow_mL_per_min": ("OutFlow", "mL/min"),
}
_NO_FLOW = {"Pericardium"}

HEMORRHAGE_BASELINE = {"hemorrhage_rate_mL_per_min": 0.0}
INFUSION_BASELINE = {"iv_rate_mL_per_min": 0.0}


def _outputs() -> tuple[Request, ...]:
    out = [Request(("hemodynamics", port), "Physiology", prop, unit) for port, (prop, unit) in _HEMODYNAMICS.items()]
    out.append(Request(("hemodynamics", _BLOOD_LOST[0]), "Physiology", _BLOOD_LOST[1], _BLOOD_LOST[2], allow_nan=True))
    for group, compartments in COMPARTMENTS.items():
        for name, compartment in compartments.items():
            for port, (prop, unit) in _COMPARTMENT_PROPERTIES.items():
                if compartment in _NO_FLOW and prop in ("InFlow", "OutFlow"):
                    continue
                out.append(Request((group, name, port), "LiquidCompartment", prop, unit, compartment))
    return tuple(out)


def hemorrhage_xml(compartment: str, rate_mL_per_min: float) -> str:
    return (f'<Action xsi:type="HemorrhageData" Compartment="{compartment}">'
            f'<InitialRate value="{float(rate_mL_per_min)!r}" unit="mL/min"/></Action>')


def infusion_xml(compound: str, bag_volume_L: float, rate_mL_per_min: float) -> str:
    return ('<Action xsi:type="SubstanceCompoundInfusionData">'
            f"<SubstanceCompound>{compound}</SubstanceCompound>"
            f'<BagVolume value="{float(bag_volume_L) * 1000.0!r}" unit="mL"/>'
            f'<Rate value="{float(rate_mL_per_min)!r}" unit="mL/min"/></Action>')


def _validate_hemorrhage(values, config):
    check_nonnegative("hemorrhage_rate_mL_per_min", values["hemorrhage_rate_mL_per_min"])


def _build_hemorrhage(values, config):
    return hemorrhage_xml(config["hemorrhage_compartment"], values["hemorrhage_rate_mL_per_min"])


def _validate_infusion(values, config):
    check_nonnegative("iv_rate_mL_per_min", values["iv_rate_mL_per_min"])
    if values["iv_rate_mL_per_min"] != 0.0 and config["iv_compound"] in _treatment_compounds(config):
        raise ValueError(f"iv_rate_mL_per_min must stay 0: the treatment schedule infuses {config['iv_compound']!r} "
                         "too, and BioGears keeps one infusion per compound (the setpoint would replace the bolus)")


def _treatment_compounds(config) -> set[str]:
    from .treatment import scheduled_compounds
    return scheduled_compounds(config)


def _build_infusion(values, config):
    return infusion_xml(config["iv_compound"], config["iv_bag_volume_L"], values["iv_rate_mL_per_min"])


def check_hemorrhage_config(config: dict[str, Any]) -> None:
    if config["hemorrhage_compartment"] not in HEMORRHAGE_COMPARTMENTS:
        raise ValueError(f"hemorrhage_compartment must be one of {HEMORRHAGE_COMPARTMENTS}, "
                         f"got {config['hemorrhage_compartment']!r}")


def check_infusion_config(config: dict[str, Any]) -> None:
    bag = config["iv_bag_volume_L"]
    if not (bag > 0 and math.isfinite(bag)):
        raise ValueError(f"iv_bag_volume_L must be > 0, got {bag}")
    # The compound itself is checked against <runtime>/substances when the engine loads.


def loaded_hemorrhage(state, config):
    """The bleed the state carries at ``hemorrhage_compartment`` (its initial rate)."""
    values = dict(HEMORRHAGE_BASELINE)
    others = []
    for kind, el in state.actions:
        if kind != "HemorrhageData":
            continue
        if el.get("Compartment") != config["hemorrhage_compartment"]:
            others.append(el.get("Compartment"))
            continue
        rate = scalar(el, "InitialRate", "mL/min")
        if rate is None:
            return None
        values["hemorrhage_rate_mL_per_min"] = rate
    if others:
        raise ValueError(f"the loaded state has active hemorrhages at {others}, which this process's "
                         f"hemorrhage setpoint (at {config['hemorrhage_compartment']}) can't stop; set "
                         "hemorrhage_compartment to it")
    return values


def loaded_infusion(state, config):
    """The infusion of ``iv_compound`` the state carries (its rate). Infusions of compounds
    the treatment schedule gives belong to the ``treatment`` module, not to the setpoint."""
    values = dict(INFUSION_BASELINE)
    others = []
    scheduled = _treatment_compounds(config)
    for kind, el in state.actions:
        if kind != "SubstanceCompoundInfusionData":
            continue
        compound = text(el, "SubstanceCompound")
        if compound in scheduled:
            continue
        if compound != config["iv_compound"]:
            others.append(compound)
            continue
        rate = scalar(el, "Rate", "mL/min")
        if rate is None:
            return None
        values["iv_rate_mL_per_min"] = rate
    if others:
        raise ValueError(f"the loaded state has active infusions of {others}, which this process's infusion "
                         f"setpoint (of {config['iv_compound']}) can't stop; set iv_compound to it")
    return values


HEMORRHAGE = ActionBinding(ports=dict(HEMORRHAGE_BASELINE), build=_build_hemorrhage,
                           action_types=("HemorrhageData",), validate=_validate_hemorrhage,
                           loaded=loaded_hemorrhage)
INFUSION = ActionBinding(ports=dict(INFUSION_BASELINE), build=_build_infusion,
                         action_types=("SubstanceCompoundInfusionData",), validate=_validate_infusion,
                         loaded=loaded_infusion)

HEMORRHAGE_PARAMS = {"hemorrhage_compartment": {"_type": "string", "_default": "RightLeg"}}
INFUSION_PARAMS = {"iv_compound": {"_type": "string", "_default": "Saline"},
                   "iv_bag_volume_L": {"_type": "float", "_default": 10.0}}


def _check_config(config):
    check_hemorrhage_config(config)
    check_infusion_config(config)


CARDIOVASCULAR = CircuitModule(
    name="cardiovascular",
    description="Hemodynamics plus pressure, volume and flows of 42 vascular compartments "
                "(central, cerebral, renal, peripheral); setpoints: a hemorrhage and an IV infusion.",
    outputs=_outputs(),
    bindings=(HEMORRHAGE, INFUSION),
    params={**HEMORRHAGE_PARAMS, **INFUSION_PARAMS},
    check_config=_check_config,
)
