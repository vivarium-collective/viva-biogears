"""``vitals``: BioGearsProcess's vital signs, as a module (read only)."""

from __future__ import annotations

from .base import CircuitModule, Request

#: Output port -> (BioGears physiology property, unit). Order is the data-request
#: order of BioGearsProcess, i.e. the order of BioGearsEngine.pull()[1:].
VITALS: dict[str, tuple[str, str]] = {
    "heart_rate_bpm": ("HeartRate", "1/min"),
    "mean_arterial_pressure_mmHg": ("MeanArterialPressure", "mmHg"),
    "systolic_pressure_mmHg": ("SystolicArterialPressure", "mmHg"),
    "diastolic_pressure_mmHg": ("DiastolicArterialPressure", "mmHg"),
    "oxygen_saturation": ("OxygenSaturation", ""),
    "respiration_rate_bpm": ("RespirationRate", "1/min"),
    "cardiac_output_L_per_min": ("CardiacOutput", "L/min"),
    "central_venous_pressure_mmHg": ("CentralVenousPressure", "mmHg"),
    "blood_volume_mL": ("BloodVolume", "mL"),
    # NaN until the first hemorrhage (BioGears creates the value then).
    "total_blood_volume_lost_mL": ("TotalBloodVolumeLost", "mL"),
}

VITALS_MODULE = CircuitModule(
    name="vitals",
    description="BioGearsProcess's vital signs.",
    outputs=tuple(Request((name,), "Physiology", p, u, allow_nan=(p == "TotalBloodVolumeLost"))
                  for name, (p, u) in VITALS.items()),
)
