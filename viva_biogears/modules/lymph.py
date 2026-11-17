"""Lymph and tissue-fluid modules: BioGears' active lymph model.

``lymph``: lymph formation through the 13 tissue valves, the lymph pool and its
passive return to the vena cava. BioGears 8.2.0 has no compartment links for lymph,
so these are circuit reads (pybiogears P5). Return tracks venous pressure, so CVP is
reported with it.

``tissue_fluid``: per-tissue extracellular and intracellular volumes, capillary
filtration and endothelial resistance (which BioGears lowers as tissue integrity
falls, McDaniel 2019), plasma and interstitial oncotic pressures, interstitial
pressure and albumin; whole-body fluid totals. BioGears stores the plasma oncotic
pressure as a negative pressure source, reported positive.
"""

from __future__ import annotations

from .base import CircuitModule, Request

#: Tissues with a lymph drainage path (BioGears.cpp SetupTissue), as port keys -> BioGears names.
TISSUES = {
    "bone": "Bone", "brain": "Brain", "fat": "Fat", "gut": "Gut", "left_kidney": "LeftKidney",
    "left_lung": "LeftLung", "liver": "Liver", "muscle": "Muscle", "myocardium": "Myocardium",
    "right_kidney": "RightKidney", "right_lung": "RightLung", "skin": "Skin", "spleen": "Spleen",
}
#: The vascular-to-tissue path carrying the plasma oncotic pressure source; Gut has
#: three (small/large intestine, splanchnic), all with the same source.
_V_TO_E1 = {t: f"{t}VTo{t}E1" for t in TISSUES.values()} | {"Gut": "SplanchnicVToGutE1"}


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
        name="lymph",
        description="Lymph formation (13 tissue valves), the lymph pool, and its return to the vena cava. "
        "BioGears 8.2.0 has no compartment links for lymph, so these are circuit reads (pybiogears P5).",
        outputs=tuple(r))


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
        name="tissue_fluid",
        description="Per-tissue extracellular/intracellular volumes, capillary filtration, endothelial resistance, "
        "plasma and interstitial oncotic pressures, interstitial pressure and albumin; whole-body fluid totals.",
        outputs=tuple(r))


LYMPH = _lymph()
TISSUE_FLUID = _tissue_fluid()
