"""Can a path be added to BioGears 8.2.0's cardiovascular circuit by editing a state?

    python probe.py OUTDIR
Adds an aorta -> vena cava shunt (Aorta1 -> VenaCava, R mmHg s/mL, default 20) to StandardMale@0s:
(a) the path alone, (b) the path plus a liquid link between the two compartments.
Runs each 5 min against an unedited control and reports MAP, HR, CO, the shunt's flow,
and vena cava O2 partial pressure (substances follow only links).
"""
import os, sys
import xml.etree.ElementTree as ET
from pathlib import Path
import pybiogears as pb

RT = Path(os.environ["BIOGEARS_RUNTIME"]); OUT = Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
R = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
NS = "uri:/mil/tatrc/physiology/datamodel"; XSI = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", NS); ET.register_namespace("xsi", XSI)
q = lambda t: f"{{{NS}}}{t}"


def edit(link: bool) -> Path:
    tree = ET.parse(RT / "states" / "StandardMale@0s.xml"); root = tree.getroot()
    cm = root.find(q("CircuitManager")); comp = root.find(q("CompartmentManager"))
    paths = cm.findall(q("FluidPath"))
    new = ET.Element(q("FluidPath"))
    for tag, text in (("Name", "VivaAddedShunt"), ("SourceNode", "Aorta1"), ("TargetNode", "VenaCava")):
        ET.SubElement(new, q(tag)).text = text
    for tag in ("Resistance", "NextResistance", "ResistanceBaseline"):
        ET.SubElement(new, q(tag), {"readOnly": "false", "unit": "mmHg s/mL", "value": str(R)})
    cm.insert(list(cm).index(paths[-1]) + 1, new)
    for c in cm.findall(q("FluidCircuit")):
        nodes = {n.text for n in c.findall(q("Node"))}
        if {"Aorta1", "VenaCava"} <= nodes:
            last = c.findall(q("Path"))[-1]
            el = ET.Element(q("Path")); el.text = "VivaAddedShunt"
            c.insert(list(c).index(last) + 1, el)
    if link:
        links = comp.findall(q("LiquidLink"))
        new = ET.Element(q("LiquidLink"))
        for tag, text in (("Name", "VivaAddedShunt"), ("Path", "VivaAddedShunt"),
                          ("SourceCompartment", "Aorta"), ("TargetCompartment", "VenaCava")):
            ET.SubElement(new, q(tag)).text = text
        comp.insert(list(comp).index(links[-1]) + 1, new)
        for g in comp.findall(q("LiquidGraph")):
            cs = {c.text for c in g.findall(q("Compartment"))}
            if {"Aorta", "VenaCava"} <= cs:
                el = ET.Element(q("Link")); el.text = "VivaAddedShunt"
                ls = g.findall(q("Link"))
                g.insert(list(g).index(ls[-1]) + 1 if ls else len(g), el)
    out = OUT / f"shunt-{'link' if link else 'path'}@0s.xml"
    tree.write(out, xml_declaration=True, encoding="UTF-8")
    return out


REQ = [pb.DataRequest("Physiology", p, u) for p, u in [("MeanArterialPressure", "mmHg"), ("HeartRate", "1/min"),
       ("CardiacOutput", "L/min")]] + [pb.DataRequest("FluidPath", "Flow", "mL/min", "VivaAddedShunt"),
       pb.DataRequest("LiquidCompartment", "PartialPressure", "mmHg", "VenaCava", "Oxygen"),
       pb.DataRequest("LiquidCompartment", "PartialPressure", "mmHg", "Aorta", "Oxygen")]
for tag, path in [("control", RT / "states" / "StandardMale@0s.xml"), ("path only", edit(False)), ("path+link", edit(True))]:
    e = pb.BioGearsEngine(RT); e.set_requests(REQ)
    try:
        e.load_state(path)
    except Exception as ex:
        print(tag, "LOAD FAILED", ex); continue
    print(tag, "unconnected:", [r.compartment for r in e.unconnected])
    for minute, step in ((0, 0), (0.05, 3), (1, 57), (5, 240)):
        try:
            if step: e.advance(step)
        except pb.IrreversibleStateError as ex:
            print("  ", ex); break
        v = e.pull()[1:]
        print(f"  t={minute:g} min  MAP {v[0]:.1f}  HR {v[1]:.1f}  CO {v[2]:.2f}  shunt {v[3]:.0f} mL/min  "
              f"PvO2 {v[4]:.1f}  PaO2 {v[5]:.1f}", flush=True)
