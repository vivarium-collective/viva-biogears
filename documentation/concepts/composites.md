# Composites

A composite generator builds a ready-to-run document from a few parameters, with
`core_extensions=[build_core]` so the processes are registered.

| composite | what it does |
|---|---|
| `biogears_hemorrhage` | an untreated hemorrhage; vitals every second |
| `biogears_resuscitation` | the same, plus `MapFluidController` setting the IV rate from MAP |
| `biogears_cardiovascular` | the cardiovascular circuit under a hemorrhage and an infusion |
| `biogears_respiratory` | the airway circuit, with intubation |
| `biogears_mechanical_ventilation` | intubated, on the anesthesia-machine ventilator |
| `biogears_thermal` | the temperature circuit under the environment and a thermal application |
| `biogears_supplemental_oxygen` | a nasal cannula |
| `biogears_whole_body_circuits` | every module with setpoints, plus lymph and tissue fluid, on one engine |
| `biogears_lymph` | lymph and tissue fluid at rest or under an infusion, from the equilibrated state |

Every generator takes `state_file`, `patient_file`, `conditions` and `circuit_additions`;
the circuit ones also take `interval`, and some `point_reads`, `substance_outputs` and
`tissue_outputs`. A setpoint parameter is validated when the document is built.

## Store layout

The circuit composites use viva-pulse's layout:

- `interventions/<module>/`: the setpoints;
- `circuits/<module>/`: the module's readings, and `circuits/irreversible_state`;
- `emitter`: a `RAMEmitter` recording both subtrees and time every update.

```python
from process_bigraph import Composite, gather_emitter_results
from viva_biogears.composites import biogears_cardiovascular
from viva_biogears.core import build_core

core = build_core()
sim = Composite({"state": biogears_cardiovascular(core, hemorrhage_rate_mL_per_min=250.0)}, core=core)
sim.run(60)
rows = gather_emitter_results(sim)[("emitter",)]
rows[-1]["circuits"]["cardiovascular"]["hemodynamics"]["mean_arterial_pressure_mmHg"]
```
