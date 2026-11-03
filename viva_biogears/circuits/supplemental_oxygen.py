"""Supplemental oxygen module: BioGears' nasal cannula.

BioGears models the cannula as a small oxygen-tank circuit combined with the
respiratory circuit (``RespiratoryNasalCannula``, airway mode ``NasalCannula``).
Masks are BioGears' anesthesia machine with a ``Mask`` connection (the
``mechanical_ventilator`` module), so this module has one device, unlike Pulse's
(nasal cannula, simple mask, non-rebreather).

Readings (``oxygenation``): inspired-air proxies and the arterial blood gases,
which is what supplemental oxygen changes.

Setpoints, one group: ``oxygen_connected`` (0/1) with ``oxygen_flow_L_per_min``,
sent as ``NasalCannula``. Disconnecting sends flow 0, which BioGears treats as
removal (``SENasalCannula::IsActive``). The tank is BioGears' fixed-pressure source.
``oxygen_connected`` is the module's airway device: BioGears allows one at a time.
"""

from __future__ import annotations

import math

from .base import ActionBinding, CircuitModule, Request, scalar, validate_switch
from .state import scalar as state_scalar

_OXYGENATION = {
    "oxygen_saturation": ("OxygenSaturation", ""),
    "arterial_oxygen_pressure_mmHg": ("ArterialOxygenPressure", "mmHg"),
    "arterial_carbon_dioxide_pressure_mmHg": ("ArterialCarbonDioxidePressure", "mmHg"),
    "end_tidal_carbon_dioxide_pressure_mmHg": ("EndTidalCarbonDioxidePressure", "mmHg"),
}

#: BioGears' scenario Patient/NasalCannula.xml uses 4 L/min (its default when unset is 3).
OXYGEN_BASELINE = {"oxygen_connected": 0.0, "oxygen_flow_L_per_min": 4.0}


def _validate_oxygen(values, config):
    validate_switch("oxygen_connected", values["oxygen_connected"])
    flow = values["oxygen_flow_L_per_min"]
    if not (flow > 0.0 and math.isfinite(flow)):
        raise ValueError(f"oxygen_flow_L_per_min must be a finite value > 0, got {flow}")


def nasal_cannula_xml(flow_L_per_min: float) -> str:
    return '<Action xsi:type="NasalCannulaData">' + scalar("FlowRate", flow_L_per_min, "L/min") + "</Action>"


def _build_oxygen(values, config):
    return nasal_cannula_xml(values["oxygen_flow_L_per_min"] if values["oxygen_connected"] == 1.0 else 0.0)


def _loaded_oxygen(state, config):
    for kind, el in state.actions:
        if kind == "NasalCannulaData":
            flow = state_scalar(el, "FlowRate", "L/min")
            if flow is None:
                return None
            if flow > 0:
                return {"oxygen_connected": 1.0, "oxygen_flow_L_per_min": flow}
    return dict(OXYGEN_BASELINE)


SUPPLEMENTAL_OXYGEN = CircuitModule(
    name="supplemental_oxygen",
    description="A nasal cannula: arterial blood gases and end-tidal CO2; setpoints: connection and flow.",
    outputs=tuple(Request(("oxygenation", p), "Physiology", prop, u) for p, (prop, u) in _OXYGENATION.items())
    + (Request(("cannula", "nosepiece_oxygen_volume_fraction"), "GasCompartment", "VolumeFraction", "",
               "Nosepiece", "Oxygen"),),
    bindings=(ActionBinding(ports=dict(OXYGEN_BASELINE), build=_build_oxygen,
                            action_types=("NasalCannulaData",), validate=_validate_oxygen,
                            loaded=_loaded_oxygen),),
    airway_device="oxygen_connected",
)
