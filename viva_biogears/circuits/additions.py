"""Paths added to the cardiovascular circuit of a state before it loads (viva-pulse's ``circuit_additions``).

An added path is a perturbation of the loaded patient: the body responds to it over
time (an aorta-to-vena-cava shunt lowers MAP and raises HR and cardiac output) and
BioGears does not re-stabilize. BioGears solves a path added to its circuits, but it
moves substances only over the compartment graph, so a path alone carries blood
without its substances: arterial PO2 drifts up, and a large shunt kills the patient in
2 s (probe ``workspace/experiments/additions-2026-11-03``). Each addition is therefore
a path plus a liquid link mapped to it:

- the path goes into every fluid circuit that holds both its nodes;
- the link joins the nodes' liquid compartments and goes into every liquid graph that
  holds both of them.

Only what the probe covered is accepted: resistance paths between nodes of
``FullCardiovascular`` in two different vascular compartments (in both BioGears'
``Cardiovascular`` graph and the ``ActiveCardiovascular`` transport graph). That leaves
out ``Ground``, tissue fluid, lymph, the pericardium, and the renal and urinary
compartments. Anything else raises.

In the state, an addition named ``Shunt`` becomes path and link ``VivaAddedShunt``, so
a user name can't collide with BioGears' own. The edited state is written once to
``<cache>/additions/`` (keyed by the source state's bytes and the additions) and loaded
from there. Its resistance is fixed: BioGears' vascular tone scales only its own paths.
The path is part of ``FullCardiovascular``, so ``cardiovascular_points`` reads its flow.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

CIRCUIT = "FullCardiovascular"
TRANSPORT_GRAPH, VASCULAR_GRAPH = "ActiveCardiovascular", "Cardiovascular"
PREFIX = "VivaAdded"
FIELDS = ("source", "target", "resistance_mmHg_s_per_mL")
_NS = "uri:/mil/tatrc/physiology/datamodel"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"


def _q(tag: str) -> str:
    return f"{{{_NS}}}{tag}"


def check_additions(additions: dict[str, Any]) -> None:
    """Check each addition's fields, without the state."""
    for name, addition in additions.items():
        if not str(name).isidentifier():
            raise ValueError(f"circuit addition name {name!r} must be letters, digits and underscores")
        if not isinstance(addition, dict) or set(addition) != set(FIELDS):
            raise ValueError(f"circuit addition {name!r} must have exactly the fields {list(FIELDS)}, got {addition!r}")
        r = addition["resistance_mmHg_s_per_mL"]
        if isinstance(r, bool) or not isinstance(r, (int, float)) or not math.isfinite(r) or r <= 0:
            raise ValueError(f"circuit addition {name!r}: resistance_mmHg_s_per_mL must be a finite number > 0, "
                             f"got {r!r}")
        if addition["source"] == addition["target"]:
            raise ValueError(f"circuit addition {name!r} joins node {addition['source']!r} to itself")


def add_paths(root: ET.Element, additions: dict[str, Any]) -> None:
    """Add each path and its link to the parsed state, in place (see the module docstring)."""
    check_additions(additions)
    cm, comp = root.find(_q("CircuitManager")), root.find(_q("CompartmentManager"))
    circuits = cm.findall(_q("FluidCircuit"))
    nodes = {n.text for c in circuits if c.findtext(_q("Name")) == CIRCUIT for n in c.findall(_q("Node"))}
    owner = {n.text: c.findtext(_q("Name")) for c in comp.findall(_q("LiquidCompartment"))
             for n in c.findall(_q("Node"))}
    graphs = {g.findtext(_q("Name")): g for g in comp.findall(_q("LiquidGraph"))}
    members = {name: {c.text for c in g.findall(_q("Compartment"))} for name, g in graphs.items()}
    vascular = members[TRANSPORT_GRAPH] & members[VASCULAR_GRAPH]
    taken = ({p.findtext(_q("Name")) for p in cm.findall(_q("FluidPath"))}
             | {link.findtext(_q("Name")) for link in comp.findall(_q("LiquidLink"))})

    for key, addition in additions.items():
        name = f"{PREFIX}{key}"
        source, target = addition["source"], addition["target"]
        if name in taken:
            raise ValueError(f"circuit addition {key!r}: {name!r} is already a path or link name in the state")
        missing = [n for n in (source, target) if n not in nodes]
        if missing:
            raise ValueError(f"circuit addition {key!r}: {missing} not nodes of {CIRCUIT}")
        outside = [f"{n} ({owner.get(n, 'no compartment')})" for n in (source, target) if owner.get(n) not in vascular]
        if outside:
            raise ValueError(f"circuit addition {key!r}: {outside} not in a vascular compartment, so blood "
                             "substances could not follow the path")
        if owner[source] == owner[target]:
            raise ValueError(f"circuit addition {key!r}: both nodes are in compartment {owner[source]!r}; "
                             "paths within one compartment are not supported")

        path = ET.Element(_q("FluidPath"))
        for tag, text in (("Name", name), ("SourceNode", source), ("TargetNode", target)):
            ET.SubElement(path, _q(tag)).text = text
        value = repr(float(addition["resistance_mmHg_s_per_mL"]))
        for tag in ("Resistance", "NextResistance", "ResistanceBaseline"):
            ET.SubElement(path, _q(tag), {"readOnly": "false", "unit": "mmHg s/mL", "value": value})
        # A flow, so the path reads 0 (not NaN) until BioGears' first step solves it.
        for tag in ("Flow", "NextFlow"):
            ET.SubElement(path, _q(tag), {"readOnly": "true", "unit": "mL/s", "value": "0"})
        cm.insert(list(cm).index(cm.findall(_q("FluidPath"))[-1]) + 1, path)
        for c in circuits:
            if {source, target} <= {n.text for n in c.findall(_q("Node"))}:
                el = ET.Element(_q("Path"))
                el.text = name
                c.insert(list(c).index(c.findall(_q("Path"))[-1]) + 1, el)

        link = ET.Element(_q("LiquidLink"))
        for tag, text in (("Name", name), ("Path", name), ("SourceCompartment", owner[source]),
                          ("TargetCompartment", owner[target])):
            ET.SubElement(link, _q(tag)).text = text
        comp.insert(list(comp).index(comp.findall(_q("LiquidLink"))[-1]) + 1, link)
        for g_name, g in graphs.items():
            if {owner[source], owner[target]} <= members[g_name]:
                el = ET.Element(_q("Link"))
                el.text = name
                links = g.findall(_q("Link"))
                g.insert(list(g).index(links[-1]) + 1 if links else len(g), el)
        taken.add(name)


def added_state(source: Path, additions: dict[str, Any]) -> Path:
    """``source`` with ``additions``, written once to ``<cache>/additions/`` and reused."""
    from ..patients import cache_dir

    check_additions(additions)
    content = Path(source).read_bytes()
    key = hashlib.sha256(content + json.dumps(additions, sort_keys=True).encode()).hexdigest()[:24]
    stem = Path(source).name.split("@")[0]
    directory = cache_dir().parent / "additions"
    out = directory / f"{stem}-{'-'.join(sorted(additions))}-{key}@{Path(source).name.split('@', 1)[-1]}"
    if out.is_file():
        return out
    ET.register_namespace("", _NS)
    ET.register_namespace("xsi", _XSI)
    # Keep comments: pybiogears stores the blood lost so far in one.
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.ElementTree(ET.fromstring(content, parser=parser))
    add_paths(tree.getroot(), additions)
    directory.mkdir(parents=True, exist_ok=True)
    fd, partial = tempfile.mkstemp(dir=directory, prefix=".", suffix=".xml")
    os.close(fd)
    try:
        tree.write(partial, xml_declaration=True, encoding="UTF-8")
        os.replace(partial, out)
    finally:
        Path(partial).unlink(missing_ok=True)
    return out
