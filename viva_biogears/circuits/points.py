"""Point reads: single circuit nodes and paths of BioGears' circuits.

BioGears' circuits are reachable by name (pybiogears ``FluidNode``/``FluidPath``
requests read ``BioGearsCircuits::GetFluidNode``/``GetFluidPath``), so unlike
viva-pulse nothing is added to the state: the modules list the circuit's nodes and
paths from the starting state and read them directly.

| module | BioGears circuit | node ports | path ports |
|---|---|---|---|
| ``cardiovascular_points`` | ``FullCardiovascular`` (with renal, cerebral and tissue branches, 170 nodes, 296 paths) | ``nodes/<node>/pressure_mmHg``, ``nodes/<node>/volume_mL`` | ``paths/<path>/flow_mL_per_min`` |
| ``respiratory_points`` | ``Respiratory`` (17 nodes, 27 paths) | ``nodes/<node>/absolute_pressure_cmH2O``, ``nodes/<node>/volume_mL`` | ``paths/<path>/flow_L_per_min`` |

- **Selecting points.** By default every node and path is read. The config lists
  ``cardiovascular_point_nodes``/``cardiovascular_point_paths`` (and the
  ``respiratory_`` pair) narrow the selection to the names given, BioGears' own; an
  unknown or repeated name raises.
- **Volume** is read only where the state holds a finite one: resistive junctions
  (``Aorta2``, the tissue ``E1``/``E2`` nodes) have none, and ``Ambient``'s is infinite.
  ``Ground`` has no pressure either and is skipped.
- **Flow is signed**: positive from the path's source node to its target.
- **Airway devices.** While a device is connected, BioGears solves the device's
  combined circuit, which replaces ``EnvironmentToMouth``; that path would hold its
  last flow, so it isn't read when the state has a device or a module on the same
  process can connect one, and naming it then raises.
- The lymph nodes and paths are part of ``FullCardiovascular``; the ``lymph``
  module reads the same values under physiological names.
"""

from __future__ import annotations

import math

from .base import CircuitModule, Request

_AIRWAY_OPENING = "EnvironmentToMouth"
_DEVICE_MODULES = ("mechanical_ventilator", "supplemental_oxygen")
_SKIP_NODES = {"Ground"}


def _select(kind: str, available: list[str], wanted: list[str], circuit: str) -> list[str]:
    if not wanted:
        return available
    if len(set(wanted)) != len(wanted):
        raise ValueError(f"{kind} listed more than once: {sorted({w for w in wanted if wanted.count(w) > 1})}")
    unknown = [w for w in wanted if w not in available]
    if unknown:
        raise ValueError(f"{kind} not in BioGears' {circuit} circuit (or not readable): {unknown}")
    return list(wanted)


def _point_module(name: str, circuit: str, pressure: tuple[str, str], flow: tuple[str, str]) -> CircuitModule:
    prefix = name.removesuffix("_points")

    def prepare(config, state, modules) -> tuple[Request, ...]:
        nodes, paths = state.circuits[circuit]
        nodes = [n for n in nodes if n not in _SKIP_NODES]
        if circuit == "Respiratory" and (state.airway_mode != "Free"
                                         or any(m in modules for m in _DEVICE_MODULES)):
            paths = [p for p in paths if p != _AIRWAY_OPENING]
        nodes = _select("nodes", nodes, list(config[f"{prefix}_point_nodes"]), circuit)
        paths = _select("paths", paths, list(config[f"{prefix}_point_paths"]), circuit)
        out = []
        for n in nodes:
            out.append(Request(("nodes", n, pressure[0]), "FluidNode", "Pressure", pressure[1], n))
            if math.isfinite(state.node_volume.get(n, math.nan)):
                out.append(Request(("nodes", n, "volume_mL"), "FluidNode", "Volume", "mL", n))
        out += [Request(("paths", p, flow[0]), "FluidPath", "Flow", flow[1], p) for p in paths]
        return tuple(out)

    return CircuitModule(
        name=name,
        description=f"Pressure (and volume) of every node and signed flow of every path of BioGears' "
                    f"{circuit} circuit, or of the ones listed.",
        params={f"{prefix}_point_nodes": {"_type": "list[string]", "_default": []},
                f"{prefix}_point_paths": {"_type": "list[string]", "_default": []}},
        prepare=prepare,
    )


CARDIOVASCULAR_POINTS = _point_module("cardiovascular_points", "FullCardiovascular",
                                      ("pressure_mmHg", "mmHg"), ("flow_mL_per_min", "mL/min"))
RESPIRATORY_POINTS = _point_module("respiratory_points", "Respiratory",
                                   ("absolute_pressure_cmH2O", "cmH2O"), ("flow_L_per_min", "L/min"))
