# Circuits

`BioGearsCircuitProcess` exposes BioGears' circuits through **circuit modules**
(`viva_biogears.circuits`). A module computes nothing: it names the BioGears values that
become its output ports and the actions its setpoints drive.

| Module | Readings | Setpoints |
|---|---|---|
| `vitals` | `BioGearsProcess`'s ten vital signs | none |
| `cardiovascular` | 23 hemodynamic values; pressure, volume, inflow and outflow for 42 compartments under `central/`, `cerebral/`, `renal/`, `peripheral/` | `hemorrhage_rate_mL_per_min`, `iv_rate_mL_per_min` |
| `respiratory` | 18 breathing-mechanics values; airway, lung and pleural gas compartments | `intubated` (extubation works) |
| `mechanical_ventilator` | the anesthesia machine's settings as applied; its circuit's gas compartments | `connected` and pressure, PEEP, rate, I:E, O2 fraction, inlet flow |
| `thermal` | core and skin temperatures, sweat, metabolic rate, heat losses, the environment; 17 thermal compartments | the environment; heating, cooling, an applied temperature |
| `supplemental_oxygen` | arterial blood gases, end-tidal CO2 | `oxygen_connected`, `oxygen_flow_L_per_min` (nasal cannula) |
| `cardiovascular_points` | pressure (and volume) of each of the 169 nodes of `FullCardiovascular`, flow of each of its 296 paths | none |
| `respiratory_points` | the same for the 17 nodes and 27 paths of `Respiratory` | none |
| `substances` | the substance quantities listed in `substance_outputs` | none |
| `tissues` | the tissue values listed in `tissue_outputs` | none |
| `lymph` | lymph formation in 13 tissues, the lymph pool, its return and CVP | none |
| `tissue_fluid` | per tissue: fluid volumes, filtration, endothelial resistance, oncotic and interstitial pressures, albumin; body fluid totals | none |

Each module's docstring (in the {doc}`../api/circuits` reference) gives the details.

## Readings are instantaneous

Compartment and point readings vary within each heartbeat and each breath. The default 1 s
interval aliases the cardiac cycle; `interval=0.02` (BioGears' timestep) resolves waveforms
({doc}`../tutorials/02-cardiovascular-circuit`).

## Points

BioGears' circuits are reachable by name, so the `*_points` modules read nodes and paths
directly, all of them by default or those named in `<circuit>_point_nodes` /
`<circuit>_point_paths`. Flow is signed: positive from a path's source node to its target.
Volume is read only where the state holds a finite one. While an airway device is
connected, `EnvironmentToMouth` is replaced by the device's circuit, so it isn't read.

## Lymph and tissue fluid

BioGears forms lymph in 13 tissues through valves, pools it, and returns it to the vena
cava through a passive resistance. It has no compartment links for lymph, so the `lymph`
module reads the circuit. Two consequences shape lymph studies:

- return tracks venous pressure: 200 mL/min of saline lowers it from 3.2 to 0.4 mL/min within
  5 minutes while formation rises, and within 10 minutes reverses (about −1 mL/min): the
  return path has no valve, so fluid flows from the vena cava back into the pool
  ({doc}`../tutorials/03-lymph-and-tissue-fluid`);
- `StandardMale@0s` is not at fluid steady state (the lymph pool relaxes with τ ≈ 91 min);
  `StandardMale@equilibrated.xml` is (5 h at rest with hourly water).

## Substances and tissues

The `substances` and `tissues` modules read the entries you list, checked against the
starting state before BioGears loads: an active substance, a compartment holding it in a
transport graph or a tissue fluid, and a property it stores. BioGears segfaults or reads
NaN on many bad requests, so a bad entry raises first.

## Circuit additions

`circuit_additions` adds resistance paths between two `FullCardiovascular` nodes in
different vascular compartments, each with a liquid link so substances follow. A path
alone would carry blood without its oxygen; a large one is then fatal within seconds.

## Rules that come from BioGears

- **One airway device at a time**: a second makes every step fail.
- **No circuit multipliers**: BioGears 8.2.0 has no action that changes its circuit
  mechanics, so viva-pulse's resistance and compliance multipliers aren't offered.
- **Ventilator**: BioGears' is its anesthesia machine (pressure control, `Tube` or `Mask`).
- **Thermal application**: works only with pybiogears' workaround for two BioGears bugs.
