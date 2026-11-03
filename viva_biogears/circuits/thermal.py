"""Thermal circuit module: BioGears' internal and external temperature circuits.

BioGears solves body heat as one circuit (``Temperature``): the internal circuit
(core and five skin segments) joined to the external one (skin surfaces, clothing,
enclosure, ambient air, and the applied-temperature node ``Active``). It couples to
the cardiovascular circuit through skin blood flow, and the nervous model drives
shivering and sweating.

Readings:

- ``energy``: core and skin temperature (mean and per segment), sweat rate and
  total metabolic rate (``SEEnergySystem``).
- ``heat_loss``: the environment's heat-loss rates and transfer coefficients
  (``SEEnvironment``; BioGears spells "Tranfer" so). A negative loss is a net gain.
- ``environment``: the environmental conditions BioGears is using, read back.
- ``compartments``: thermal compartments: temperature; stored heat for the
  internal core and skin segments (the only ones BioGears gives a heat for); heat
  flow in and out, including for ``active``, the applied-temperature node (its
  temperature reads 0 K while nothing is applied, so it isn't a port). The
  ground references aren't read (``ExternalGround`` reads 0 K, ``InternalGround`` NaN).

Setpoints:

- ``environment`` group: ambient and mean radiant temperature, the temperature of
  the air breathed (``RespirationAmbientTemperature``, kept separate by BioGears),
  relative humidity, air velocity and clothing resistance, sent as one
  ``EnvironmentChange``, which BioGears merges into the current conditions. The
  baselines are BioGears' ``environments/Standard.xml``, which the shipped states
  use; a state whose environment differs fails the load (``check_loaded``), because
  the group is always sent whole and would silently reset it.
- ``thermal_application`` group: active heating and cooling power, each with the
  fraction of skin area it covers, and an applied temperature (on/off, temperature,
  area fraction), sent as one ``ThermalApplication`` that replaces the previous one.
  BioGears applies ``power x fraction`` as heat, and holds the clothing node at
  ``applied x fraction + ambient x (1 - fraction)``.

  BioGears 8.2.0 loses the parts of a thermal application left out of it (they
  come back with NaN values and the next step fails), and applies an applied
  temperature even when its state is Off. pybiogears works around both by removing
  the absent or off parts after BioGears stores the action
  (``BioGearsThunk::prune_thermal_application``); probe
  ``workspace/experiments/circuits-probe-2026-11-03``.

Thermal changes are slow: skin responds in minutes, core temperature in tens of
minutes. ``StandardMale@0s`` is not thermally settled (skin warms by about 0.6 C over
10 minutes at rest), so compare an intervention with an unperturbed run.
"""

from __future__ import annotations

from .base import (
    ActionBinding,
    CircuitModule,
    Request,
    check_fraction,
    check_nonnegative,
    scalar,
    validate_switch,
)

_ENERGY = {
    "core_temperature_C": ("CoreTemperature", "degC"),
    "skin_temperature_C": ("SkinTemperature", "degC"),
    "skin_temperature_torso_C": ("SkinTemperatureTorso", "degC"),
    "skin_temperature_head_C": ("SkinTemperatureHead", "degC"),
    "skin_temperature_left_arm_C": ("SkinTemperatureLeftArm", "degC"),
    "skin_temperature_right_arm_C": ("SkinTemperatureRightArm", "degC"),
    "skin_temperature_left_leg_C": ("SkinTemperatureLeftLeg", "degC"),
    "skin_temperature_right_leg_C": ("SkinTemperatureRightLeg", "degC"),
    "sweat_rate_g_per_min": ("SweatRate", "g/min"),
    "total_metabolic_rate_W": ("TotalMetabolicRate", "W"),
}
_HEAT_LOSS = {
    "skin_W": ("SkinHeatLoss", "W"),
    "convective_W": ("ConvectiveHeatLoss", "W"),
    "radiative_W": ("RadiativeHeatLoss", "W"),
    "evaporative_W": ("EvaporativeHeatLoss", "W"),
    "respiration_W": ("RespirationHeatLoss", "W"),
    "convective_coefficient_W_per_m2_K": ("ConvectiveHeatTranferCoefficient", "W/m^2 K"),
    "radiative_coefficient_W_per_m2_K": ("RadiativeHeatTranferCoefficient", "W/m^2 K"),
    "evaporative_coefficient_W_per_m2_K": ("EvaporativeHeatTranferCoefficient", "W/m^2 K"),
}
_CONDITIONS = {
    "ambient_temperature_C": ("AmbientTemperature", "degC"),
    "mean_radiant_temperature_C": ("MeanRadiantTemperature", "degC"),
    "respiration_ambient_temperature_C": ("RespirationAmbientTemperature", "degC"),
    "relative_humidity": ("RelativeHumidity", ""),
    "air_velocity_m_per_s": ("AirVelocity", "m/s"),
    "clothing_resistance_clo": ("ClothingResistance", "clo"),
    "atmospheric_pressure_mmHg": ("AtmosphericPressure", "mmHg"),
}
_SEGMENTS = ("Torso", "Head", "LeftArm", "RightArm", "LeftLeg", "RightLeg")


def _snake(name: str) -> str:
    return "".join("_" + c.lower() if c.isupper() else c for c in name).lstrip("_")


# store name -> BioGears thermal compartment; the internal ones hold heat.
_INTERNAL = {"internal_core": "InternalCore",
             **{f"internal_{_snake(s)}_skin": f"Internal{s}Skin" for s in _SEGMENTS}}
_EXTERNAL = {"external_core": "ExternalCore",
             **{f"external_{_snake(s)}_skin": f"External{s}Skin" for s in _SEGMENTS},
             "clothing": "Clothing", "enclosure": "Enclosure", "ambient": "Ambient"}

ENVIRONMENT_BASELINE = {
    "ambient_temperature_C": 22.0,
    "mean_radiant_temperature_C": 22.0,
    "respiration_ambient_temperature_C": 22.0,
    "relative_humidity": 0.6,
    "air_velocity_m_per_s": 0.1,
    "clothing_resistance_clo": 0.5,
}
THERMAL_APPLICATION_BASELINE = {
    "active_heating_W": 0.0,
    "active_heating_area_fraction": 1.0,
    "active_cooling_W": 0.0,
    "active_cooling_area_fraction": 1.0,
    "applied_temperature_on": 0.0,
    "applied_temperature_C": 22.0,
    "applied_temperature_area_fraction": 1.0,
}
_ABSOLUTE_ZERO_C = -273.15


def _outputs() -> tuple[Request, ...]:
    out = [Request(("energy", p), "Physiology", prop, u) for p, (prop, u) in _ENERGY.items()]
    out += [Request(("heat_loss", p), "Environment", prop, u) for p, (prop, u) in _HEAT_LOSS.items()]
    out += [Request(("environment", p), "Environment", f"Conditions-{prop}", u) for p, (prop, u) in _CONDITIONS.items()]
    for name, comp in {**_INTERNAL, **_EXTERNAL}.items():
        out.append(Request(("compartments", name, "temperature_C"), "ThermalCompartment", "Temperature", "degC", comp))
        if name in _INTERNAL:
            out.append(Request(("compartments", name, "heat_kJ"), "ThermalCompartment", "Heat", "kJ", comp))
    for name, comp in {**_INTERNAL, **_EXTERNAL, "active": "Active"}.items():
        out.append(Request(("compartments", name, "heat_in_W"), "ThermalCompartment", "HeatTransferRateIn", "W", comp))
        out.append(Request(("compartments", name, "heat_out_W"), "ThermalCompartment", "HeatTransferRateOut", "W", comp))
    return tuple(out)


def _check_temperature(port: str, value: float) -> None:
    if not value > _ABSOLUTE_ZERO_C:
        raise ValueError(f"{port} must be above absolute zero ({_ABSOLUTE_ZERO_C} C), got {value}")


def _validate_environment(values, config):
    for port in ("ambient_temperature_C", "mean_radiant_temperature_C", "respiration_ambient_temperature_C"):
        _check_temperature(port, values[port])
    check_fraction("relative_humidity", values["relative_humidity"], zero=True)
    for port in ("air_velocity_m_per_s", "clothing_resistance_clo"):
        check_nonnegative(port, values[port])


def environment_xml(values: dict[str, float]) -> str:
    return ('<Action xsi:type="EnvironmentChangeData"><Conditions>'
            + scalar("AirVelocity", values["air_velocity_m_per_s"], "m/s")
            + scalar("AmbientTemperature", values["ambient_temperature_C"], "degC")
            + scalar("ClothingResistance", values["clothing_resistance_clo"], "clo")
            + scalar("MeanRadiantTemperature", values["mean_radiant_temperature_C"], "degC")
            + scalar("RelativeHumidity", values["relative_humidity"])
            + scalar("RespirationAmbientTemperature", values["respiration_ambient_temperature_C"], "degC")
            + "</Conditions></Action>")


def _validate_thermal_application(values, config):
    for port in ("active_heating_W", "active_cooling_W"):
        check_nonnegative(port, values[port])
    for port in ("active_heating_area_fraction", "active_cooling_area_fraction", "applied_temperature_area_fraction"):
        check_fraction(port, values[port])
    validate_switch("applied_temperature_on", values["applied_temperature_on"])
    _check_temperature("applied_temperature_C", values["applied_temperature_C"])


def thermal_application_xml(values: dict[str, float]) -> str:
    state = "On" if values["applied_temperature_on"] == 1.0 else "Off"
    return ('<Action xsi:type="ThermalApplicationData" AppendToPrevious="false">'
            "<ActiveHeating>" + scalar("Power", values["active_heating_W"], "W")
            + scalar("SurfaceAreaFraction", values["active_heating_area_fraction"]) + "</ActiveHeating>"
            "<ActiveCooling>" + scalar("Power", values["active_cooling_W"], "W")
            + scalar("SurfaceAreaFraction", values["active_cooling_area_fraction"]) + "</ActiveCooling>"
            f"<AppliedTemperature><State>{state}</State>"
            + scalar("Temperature", values["applied_temperature_C"], "degC")
            + scalar("SurfaceAreaFraction", values["applied_temperature_area_fraction"])
            + "</AppliedTemperature></Action>")


def _check_loaded_environment(readings) -> None:
    loaded = readings["environment"]
    mismatched = {p: loaded[p] for p, v in ENVIRONMENT_BASELINE.items() if abs(loaded[p] - v) > 1e-9}
    if mismatched:
        raise ValueError(f"the loaded state's environment differs from the thermal module's baselines "
                         f"(BioGears' Standard.xml) at {mismatched}; the first environment change would "
                         f"silently reset them to {ENVIRONMENT_BASELINE}")


THERMAL = CircuitModule(
    name="thermal",
    description="Core and skin temperatures, heat losses, the environment as applied and every "
                "thermal compartment's temperature and heat flows; setpoints: the environment, "
                "active heating or cooling and an applied temperature.",
    outputs=_outputs(),
    bindings=(
        ActionBinding(ports=dict(ENVIRONMENT_BASELINE), build=lambda v, c: environment_xml(v),
                      action_types=("EnvironmentChangeData",), validate=_validate_environment),
        ActionBinding(ports=dict(THERMAL_APPLICATION_BASELINE), build=lambda v, c: thermal_application_xml(v),
                      action_types=("ThermalApplicationData",), validate=_validate_thermal_application),
    ),
    check_loaded=_check_loaded_environment,
)
