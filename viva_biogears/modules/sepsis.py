"""Infection and nutrition modules: BioGears' sepsis model (McDaniel et al. 2019) and what it needs.

``infection``: BioGears' ``Infection`` action starts its acute inflammatory response
model: a local pathogen grows at the infection site and seeds the blood; macrophages,
neutrophils, cytokines (TNF, IL-6, IL-10, IL-12) and nitric oxide respond; and *tissue
integrity* falls, lowering endothelial resistance so plasma leaks into the tissues
(the ``tissue_fluid`` module reads that), while nitric oxide lowers vascular tone. The
result is the progression to sepsis and septic shock the paper describes.

- Setpoint ``infection_severity``: 0 none, 1 mild, 2 moderate, 3 severe, with config
  ``infection_location`` (a label; BioGears 8.2.0 doesn't use it) and
  ``infection_mic_mg_per_L`` (the pathogen's minimum inhibitory concentration, which
  acts only through antibiotics; the paper used 16 mg/L).
- **One-way.** BioGears reads the severity once, when the infection starts (the
  initial pathogen load), and refuses to eliminate an infection by action ("Manual
  Elimination of Infection currently not supported"). So 0 -> severity is the only
  change; any other raises.
- Readings: ``inflammation/`` (BioGears' ``InflammatoryResponse``: pathogens, immune
  cells, cytokines, nitric oxide, tissue integrity; arbitrary units, as in the paper)
  and ``clinical/`` (the signs the paper's figures use: white cell count, temperature,
  lactate, systemic vascular resistance, urine output, ...).

``nutrition``: meals and drinks at given times (config ``nutrition_schedule``, a list of
``{"hour": h, "nutrition": {"Water": L, "Carbohydrate": g, "Fat": g, "Protein": g,
"Sodium": g, "Calcium": g}}``), sent as ``ConsumeNutrients`` actions at the first update
at or after each time (``Module.schedule``). One-shot actions, so no setpoints.
``INFECTION_SCENARIO_SCHEDULE`` is BioGears' own ``InfectionModerate`` scenario's (water
hourly, five meals in 48 h), which McDaniel et al. used for every arm. Readings: stomach
contents and the body's water balance.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .base import ActionBinding, Module, Request, scalar

SEVERITIES = {0.0: None, 1.0: "Mild", 2.0: "Moderate", 3.0: "Severe"}

_INFLAMMATION = {  # port -> InflammatoryResponse property (unitless)
    "blood_pathogen": "BloodPathogen",
    "local_pathogen": "LocalPathogen",
    "local_macrophage": "LocalMacrophage",
    "local_neutrophil": "LocalNeutrophil",
    "macrophage_active": "MacrophageActive",
    "neutrophil_active": "NeutrophilActive",
    "tumor_necrosis_factor": "TumorNecrosisFactor",
    "interleukin_6": "Interleukin6",
    "interleukin_10": "Interleukin10",
    "interleukin_12": "Interleukin12",
    "nitric_oxide": "NitricOxide",
    "inducible_nos": "InducibleNOS",
    "catecholamines": "Catecholamines",
    "tissue_integrity": "TissueIntegrity",
    "trauma": "Trauma",
}
_CLINICAL = {  # port -> (Physiology property, unit)
    "white_blood_cell_count_per_uL": ("WhiteBloodCellCount", "ct/uL"),
    "core_temperature_C": ("CoreTemperature", "degC"),
    "heart_rate_bpm": ("HeartRate", "1/min"),
    "respiration_rate_bpm": ("RespirationRate", "1/min"),
    "systolic_pressure_mmHg": ("SystolicArterialPressure", "mmHg"),
    "mean_arterial_pressure_mmHg": ("MeanArterialPressure", "mmHg"),
    "systemic_vascular_resistance_mmHg_s_per_mL": ("SystemicVascularResistance", "mmHg s/mL"),
    "cardiac_output_L_per_min": ("CardiacOutput", "L/min"),
    "blood_volume_mL": ("BloodVolume", "mL"),
    "urine_production_mL_per_min": ("UrineProductionRate", "mL/min"),
    "mean_urine_output_mL_per_min": ("MeanUrineOutput", "mL/min"),
    "oxygen_saturation": ("OxygenSaturation", ""),
    "arterial_blood_ph": ("ArterialBloodPH", ""),
}

INFECTION_BASELINE = {"infection_severity": 0.0}


def _infection_outputs() -> tuple[Request, ...]:
    out = [Request(("inflammation", port), "Physiology", f"InflammatoryResponse-{prop}")
           for port, prop in _INFLAMMATION.items()]
    out += [Request(("clinical", port), "Physiology", prop, unit) for port, (prop, unit) in _CLINICAL.items()]
    out.append(Request(("clinical", "lactate_mmol_per_L"), "LiquidCompartment", "Molarity", "mmol/L",
                       "Aorta", "Lactate"))
    return tuple(out)


def infection_xml(severity: str, location: str, mic_mg_per_L: float) -> str:
    return (f'<Action xsi:type="InfectionData" Severity="{severity}">'
            + scalar("MinimumInhibitoryConcentration", mic_mg_per_L, "mg/L")
            + f"<Location>{location}</Location></Action>")


def _validate_infection(values, config):
    if values["infection_severity"] not in SEVERITIES:
        raise ValueError(f"infection_severity must be 0 (none), 1 (mild), 2 (moderate) or 3 (severe), "
                         f"got {values['infection_severity']}")


def _check_infection_transition(previous, values):
    before = None if previous is None else previous["infection_severity"]
    if before not in (None, 0.0) or values["infection_severity"] == 0.0:
        raise ValueError(f"an infection can only be started (0 -> 1, 2 or 3), not changed or ended "
                         f"({before} -> {values['infection_severity']}): BioGears reads the severity once and "
                         "can't eliminate an infection by action")


def _build_infection(values, config):
    return infection_xml(SEVERITIES[values["infection_severity"]], config["infection_location"],
                         config["infection_mic_mg_per_L"])


def _loaded_infection(state, config):
    for kind, el in state.actions:
        if kind == "InfectionData":
            severity = el.get("Severity")
            levels = {v: k for k, v in SEVERITIES.items() if v}
            if severity not in levels:
                return None
            return {"infection_severity": levels[severity]}
    return dict(INFECTION_BASELINE)


def _check_infection_config(config: dict[str, Any]) -> None:
    mic = config["infection_mic_mg_per_L"]
    if not (mic > 0 and math.isfinite(mic)):
        raise ValueError(f"infection_mic_mg_per_L must be > 0, got {mic}")
    if not str(config["infection_location"]).isidentifier():
        raise ValueError(f"infection_location must be a name, got {config['infection_location']!r}")


INFECTION = Module(
    name="infection",
    description="BioGears' acute inflammatory response (pathogens, immune cells, cytokines, nitric oxide, tissue "
                "integrity) and the clinical signs of sepsis; setpoint: infection severity (one-way).",
    outputs=_infection_outputs(),
    bindings=(ActionBinding(ports=dict(INFECTION_BASELINE), build=_build_infection, action_types=("InfectionData",),
                            validate=_validate_infection, check_transition=_check_infection_transition,
                            loaded=_loaded_infection),),
    params={"infection_location": {"_type": "string", "_default": "Skin"},
            "infection_mic_mg_per_L": {"_type": "float", "_default": 16.0}},
    check_config=_check_infection_config,
)

# -- nutrition -------------------------------------------------------------------------

#: Nutrient -> unit, in BioGears' NutritionData element order.
NUTRIENTS = {"Carbohydrate": "g", "Fat": "g", "Protein": "g", "Calcium": "g", "Sodium": "g", "Water": "L"}

INFECTION_SCENARIO_SCHEDULE = json.loads(
    (Path(__file__).resolve().parent.parent / "data" / "infection_nutrition_schedule.json").read_text())["events"]


def nutrition_xml(nutrition: dict[str, float]) -> str:
    parts = "".join(scalar(k, nutrition[k], unit) for k, unit in NUTRIENTS.items() if k in nutrition)
    return f'<Action xsi:type="ConsumeNutrientsData"><Nutrition><Name>Meal</Name>{parts}</Nutrition></Action>'


def _check_nutrition_config(config: dict[str, Any]) -> None:
    for i, event in enumerate(config["nutrition_schedule"]):
        name = f"nutrition_schedule[{i}]"
        if not isinstance(event, dict) or set(event) != {"hour", "nutrition"}:
            raise ValueError(f"{name} must be {{'hour': h, 'nutrition': {{...}}}}, got {event!r}")
        if not (isinstance(event["hour"], (int, float)) and math.isfinite(event["hour"]) and event["hour"] >= 0):
            raise ValueError(f"{name}: hour must be a finite number >= 0, got {event['hour']!r}")
        unknown = set(event["nutrition"]) - set(NUTRIENTS)
        if unknown or not event["nutrition"]:
            raise ValueError(f"{name}: nutrients must be among {list(NUTRIENTS)}, got {sorted(event['nutrition'])}")
        bad = {k: v for k, v in event["nutrition"].items() if not (isinstance(v, (int, float)) and v >= 0)}
        if bad:
            raise ValueError(f"{name}: amounts must be numbers >= 0, got {bad}")


def _nutrition_schedule(config):
    return [(float(e["hour"]) * 3600.0, nutrition_xml(e["nutrition"])) for e in config["nutrition_schedule"]]


NUTRITION = Module(
    name="nutrition",
    description="Meals and drinks at scheduled times (nutrition_schedule); readings: stomach contents and the "
                "body's water balance.",
    outputs=(
        Request(("stomach_water_mL",), "Physiology", "StomachContents-Water", "mL"),
        Request(("stomach_carbohydrate_g",), "Physiology", "StomachContents-Carbohydrate", "g"),
        Request(("chyme_absorption_rate_mL_per_min",), "Physiology", "ChymeAbsorptionRate", "mL/min"),
        Request(("total_body_fluid_mL",), "Physiology", "TotalBodyFluidVolume", "mL"),
        Request(("urine_volume_mL",), "Physiology", "UrineVolume", "mL"),
    ),
    params={"nutrition_schedule": {"_type": "list", "_default": []}},
    check_config=_check_nutrition_config,
    schedule=_nutrition_schedule,
)

__all__ = ["INFECTION", "INFECTION_SCENARIO_SCHEDULE", "NUTRITION", "SEVERITIES", "infection_xml", "nutrition_xml"]
