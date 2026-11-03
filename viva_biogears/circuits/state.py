"""What a BioGears state file holds, parsed once: circuits, compartments, substances, actions.

Modules whose outputs depend on the starting state (points, substances, tissues)
and the load-time checks read a ``StateInfo`` instead of the engine, so a bad
entry fails before BioGears loads (BioGears segfaults on some bad requests, and
reads NaN for others).
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _tag(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _child(el, name):
    for c in el:
        if _tag(c) == name:
            return c
    return None


def _text(el, name, default=""):
    c = _child(el, name)
    return c.text if c is not None and c.text is not None else default


@dataclass
class Compartment:
    kind: str                       # LiquidCompartment, GasCompartment, ThermalCompartment, TissueCompartment
    name: str
    children: tuple[str, ...]
    has_nodes: bool
    properties: frozenset[str]      # scalar elements stored on the compartment (pH, MatrixVolume, ...)
    quantities: dict[str, frozenset[str]] = field(default_factory=dict)  # substance -> its properties

    def leaves(self, by_name: dict[str, "Compartment"]) -> list["Compartment"]:
        if not self.children:
            return [self]
        return [leaf for c in self.children for leaf in by_name[c].leaves(by_name)]


@dataclass
class StateInfo:
    path: Path
    circuits: dict[str, tuple[list[str], list[str]]]          # fluid circuit -> (nodes, paths)
    node_volume: dict[str, float]                               # fluid node -> stored volume (NaN: none)
    path_ends: dict[str, tuple[str, str]]                       # fluid path -> (source node, target node)
    compartments: dict[str, dict[str, Compartment]]             # kind -> name -> compartment
    graphs: dict[str, dict[str, set[str]]]                      # LiquidGraph/GasGraph -> name -> compartments
    substances: dict[str, frozenset[str]]                       # active substance -> its whole-body properties
    active_actions: list[str]                                   # xsi:type of each active action
    airway_mode: str
    intubation: str


@lru_cache(maxsize=16)
def _parse(path: str, mtime: float) -> StateInfo:
    root = ET.parse(path).getroot()
    xsi_type = "{http://www.w3.org/2001/XMLSchema-instance}type"
    circuits, node_volume, path_ends = {}, {}, {}
    compartments: dict[str, dict[str, Compartment]] = {}
    graphs: dict[str, dict[str, set[str]]] = {}
    substances, actions = {}, []
    airway, intubation = "Free", "Off"
    for el in root:
        t = _tag(el)
        if t == "CircuitManager":
            for c in el:
                ct = _tag(c)
                if ct == "FluidCircuit":
                    circuits[_text(c, "Name")] = ([n.text for n in c if _tag(n) == "Node"],
                                                   [p.text for p in c if _tag(p) == "Path"])
                elif ct == "FluidNode":
                    v = _child(c, "Volume")
                    node_volume[_text(c, "Name")] = float(v.get("value")) if v is not None else math.nan
                elif ct == "FluidPath":
                    path_ends[_text(c, "Name")] = (_text(c, "SourceNode"), _text(c, "TargetNode"))
        elif t == "CompartmentManager":
            for c in el:
                ct = _tag(c)
                if ct in ("LiquidCompartment", "GasCompartment", "ThermalCompartment", "TissueCompartment"):
                    quantities = {}
                    props = set()
                    for x in c:
                        xt = _tag(x)
                        if xt == "SubstanceQuantity":
                            quantities[_text(x, "Substance")] = frozenset(
                                _tag(y) for y in x if _tag(y) != "Substance")
                        elif xt not in ("Name", "Node", "Child", "Link"):
                            props.add(xt)
                    comp = Compartment(ct, _text(c, "Name"), tuple(x.text for x in c if _tag(x) == "Child"),
                                       any(_tag(x) == "Node" for x in c), frozenset(props), quantities)
                    compartments.setdefault(ct, {})[comp.name] = comp
                elif ct in ("LiquidGraph", "GasGraph"):
                    graphs.setdefault(ct, {})[_text(c, "Name")] = {
                        x.text for x in c if _tag(x) == "Compartment"}
        elif t == "ActiveSubstance":
            substances[_text(el, "Name")] = frozenset(_tag(x) for x in el if _tag(x) not in ("Name", "State"))
        elif t == "ActiveAction":
            actions.append(el.get(xsi_type, ""))
        elif t == "AirwayMode":
            airway = el.text or "Free"
        elif t == "Intubation":
            intubation = el.text or "Off"
    return StateInfo(Path(path), circuits, node_volume, path_ends, compartments, graphs, substances, actions,
                     airway, intubation)


def read_state(path: Path) -> StateInfo:
    """The parsed state (cached per path and modification time)."""
    path = Path(path).resolve()
    return _parse(str(path), path.stat().st_mtime)
