# Circuits probe (2026-11-03)

**Question.** Which of viva-pulse's circuit features can BioGears 8.2.0 serve, and how do its actions behave? This probe settled the data requests and actions behind `viva_biogears/circuits/`.

**Scripts** (run with `$BIOGEARS_RUNTIME` set, from this folder):
- `probe.py`: connectivity of every physiology property BioGears defines (`physiology.json`).
- `probe_compartments.py`: liquid, gas and thermal compartments, the environment, and equipment (`compartments.json`).
- `probe_actions.py vent|o2|o2b|swap|thermal`: airway devices, intubation, the environment and thermal applications.
- `probe_thermal2.py`, `probe_thermal3.py`: thermal-application variants.

**Data requests.**
- Every `SECardiovascularSystem`, `SERespiratorySystem`, `SEEnergySystem`, `SETissueSystem` and `SERenalSystem` property connects.
- NaN at rest:
  - `TotalBloodVolumeLost` until the first bleed;
  - `TargetPulmonaryVentilation`;
  - `CreatinineProductionRate`;
  - `LeftLungVolume` and `RightLungVolume` at load.
- The inflammation values aren't top-level properties. They are read as `InflammatoryResponse-<name>` (e.g. `InflammatoryResponse-TissueIntegrity`).
- Liquid and gas compartments: `Pressure`, `Volume`, `InFlow` and `OutFlow` all connect.
  - NaN flows: `Pericardium`, `Lymph` (no compartment links) and `CerebralSpinalFluid`.
- Thermal compartments: `Temperature` and heat flows connect. `Heat` is finite for the internal compartments only.
  - `Active` and `ExternalGround` read 0 K; `InternalGround` reads NaN.
- The environment (`Conditions-<name>`) and the anesthesia-machine settings (`Equipment`) connect. They read BioGears' `Standard` environment and the machine's stored settings.

**Actions.**
- **Intubation** works, and so does extubation (type `Off`), unlike Pulse's Python API.
- **Anesthesia machine.**
  - With `Tube` or `Mask`, it ventilates. 15/5 cmH2O at FiO2 0.5 raises PaO2 from 97 to 205 mmHg.
  - `Off` disconnects it.
- **Nasal cannula.** 4 L/min raises PaO2 to 197 mmHg; flow 0 removes it.
- **One airway device at a time.** Connecting a second device makes every step fail with "Can only change airway mode to … from the Free mode". This includes connecting the anesthesia machine and switching off the cannula in the same step. After such a failure, the engine was later left in an unrecoverable state ("Unhandled Airway Mode" on every step), so the process refuses it beforehand.
- **Environment change** merges a partial condition set (relative humidity stays 0.6 when only the temperature is sent).
- **Thermal application is broken in BioGears 8.2.0 in two ways** (bg-scenario shows the same from a state):
  1. `SEEnvironmentActionCollection::ProcessAction` stores the action by marshalling it to XML and back. The unmarshalling recreates every part the action left out (`GetActiveCooling()` creates it), with NaN values, so the next step throws "Value is NaN".
  2. `Environment::ProcessActions` applies an applied temperature whatever its `State`, closing the switch to the clothing node. An "Off" applied temperature therefore pins the clothing node to the given temperature.

  Workaround, in pybiogears (`BioGearsThunk::prune_thermal_application`, commit de52065): after BioGears stores the action, remove the heating or cooling without positive power and the applied temperature that isn't On. With it, a 500 W heater raises skin temperature from 35.3 to 40.5 °C in 5 min (the control is 35.3 at 10 min), and 300 W of cooling lowers it.

**Not available in BioGears 8.2.0.** viva-pulse's circuit resistance and compliance multipliers (Pulse's `CardiovascularMechanicsModification` and `RespiratoryMechanicsModification`) have no BioGears equivalent. BioGears' overrides set outputs, not the circuit.
