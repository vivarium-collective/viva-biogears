"""Declarative registry of BioGears readout modules (modules compute nothing).

A module is a list of ``Request``s, each one BioGears data request placed at an
output port path. ``BioGearsCircuitProcess`` nests a module's ports under its
name, e.g. ``lymph/formation/muscle_mL_per_min``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..processes.biogears import VITALS

#: Tissues with a lymph drainage path (BioGears.cpp SetupTissue), as port keys -> BioGears names.
TISSUES = {
    "bone": "Bone", "brain": "Brain", "fat": "Fat", "gut": "Gut", "left_kidney": "LeftKidney",
    "left_lung": "LeftLung", "liver": "Liver", "muscle": "Muscle", "myocardium": "Myocardium",
    "right_kidney": "RightKidney", "right_lung": "RightLung", "skin": "Skin", "spleen": "Spleen",
}
#: The vascular-to-tissue path carrying the plasma oncotic pressure source; Gut has
#: three (small/large intestine, splanchnic), all with the same source.
_V_TO_E1 = {t: f"{t}VTo{t}E1" for t in TISSUES.values()} | {"Gut": "SplanchnicVToGutE1"}


@dataclass(frozen=True)
class Request:
    path: tuple[str, ...]          # port path inside the module
    category: str                  # pybiogears DataRequest category
    property: str
    unit: str
    compartment: str = ""
    substance: str = ""
    negate: bool = False           # BioGears stores some pressures as negative sources

    def as_tuple(self):
        return (self.category, self.property, self.unit, self.compartment, self.substance)


@dataclass(frozen=True)
class CircuitModule:
    name: str
    description: str
    requests: tuple[Request, ...] = field(default_factory=tuple)


def _vitals() -> CircuitModule:
    return CircuitModule("vitals", "BioGearsProcess's vital signs",
                         tuple(Request((name,), "Physiology", p, u) for name, (p, u) in VITALS.items()))


def _lymph() -> CircuitModule:
    r = [
        Request(("return_mL_per_min",), "FluidPath", "Flow", "mL/min", "LymphToVenaCava"),
        Request(("return_resistance_mmHg_min_per_mL",), "FluidPath", "Resistance", "mmHg min/mL", "LymphToVenaCava"),
        Request(("pool_volume_mL",), "FluidNode", "Volume", "mL", "Lymph"),
        Request(("pool_pressure_mmHg",), "FluidNode", "Pressure", "mmHg", "Lymph"),
        # Lymph return is a passive resistor from the pool into the vena cava, so it
        # tracks venous pressure (pybiogears P5); report both with it.
        Request(("vena_cava_pressure_mmHg",), "FluidNode", "Pressure", "mmHg", "VenaCava"),
        Request(("central_venous_pressure_mmHg",), "Physiology", "CentralVenousPressure", "mmHg"),
    ]
    r += [Request(("formation", f"{key}_mL_per_min"), "FluidPath", "Flow", "mL/min", f"{name}ToLymphValve")
          for key, name in TISSUES.items()]
    return CircuitModule(
        "lymph",
        "Lymph formation (13 tissue valves), the lymph pool, and its return to the vena cava. "
        "BioGears 8.2.0 has no compartment links for lymph, so these are circuit reads (pybiogears P5).",
        tuple(r))


def _tissue_fluid() -> CircuitModule:
    r = [
        Request(("plasma_albumin_g_per_dL",), "LiquidCompartment", "Concentration", "g/dL", "Aorta", "Albumin"),
        Request(("blood_volume_mL",), "Physiology", "BloodVolume", "mL"),
        Request(("extravascular_fluid_mL",), "Physiology", "ExtravascularFluidVolume", "mL"),
        Request(("intracellular_fluid_mL",), "Physiology", "IntracellularFluidVolume", "mL"),
        Request(("total_body_fluid_mL",), "Physiology", "TotalBodyFluidVolume", "mL"),
    ]
    for key, t in TISSUES.items():
        r += [
            Request((key, "extracellular_volume_mL"), "LiquidCompartment", "Volume", "mL", f"{t}TissueExtracellular"),
            Request((key, "intracellular_volume_mL"), "LiquidCompartment", "Volume", "mL", f"{t}TissueIntracellular"),
            Request((key, "interstitial_albumin_g_per_dL"), "LiquidCompartment", "Concentration", "g/dL",
                    f"{t}TissueExtracellular", "Albumin"),
            # Capillary filtration through the endothelium (E1 -> E2) and its resistance,
            # which BioGears lowers as tissue integrity falls (McDaniel 2019).
            Request((key, "filtration_mL_per_min"), "FluidPath", "Flow", "mL/min", f"{t}E1To{t}E2"),
            Request((key, "endothelial_resistance_mmHg_min_per_mL"), "FluidPath", "Resistance", "mmHg min/mL",
                    f"{t}E1To{t}E2"),
            # Oncotic pressures as BioGears' pressure sources: the vascular one is stored
            # as -COP on the vessel -> tissue path, hence negate.
            Request((key, "plasma_oncotic_pressure_mmHg"), "FluidPath", "PressureSource", "mmHg", _V_TO_E1[t],
                    negate=True),
            Request((key, "interstitial_oncotic_pressure_mmHg"), "FluidPath", "PressureSource", "mmHg",
                    f"{t}E2To{t}E3"),
            Request((key, "interstitial_pressure_mmHg"), "FluidNode", "Pressure", "mmHg", f"{t}E3"),
        ]
    return CircuitModule(
        "tissue_fluid",
        "Per-tissue extracellular/intracellular volumes, capillary filtration, endothelial resistance, "
        "plasma and interstitial oncotic pressures, interstitial pressure and albumin; whole-body fluid totals.",
        tuple(r))


MODULES: dict[str, CircuitModule] = {m.name: m for m in (_vitals(), _lymph(), _tissue_fluid())}
