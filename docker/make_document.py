"""Write a short, real BioGears document for compose-api's runner: ``make_document.py OUT.pbg [options]``.

``--composite hemorrhage`` (default; ``--rate R`` mL/min) or ``--composite sepsis`` (``--state-file F``, ``--severity S``,
``--treatment T``: the arguments of ``biogears_sepsis``). Every address is made portable (``local:<module>.<Class>``):
the runner's core is a plain ``allocate_core()``, so a bare ``local:BioGearsProcess`` would not resolve there. compose-api
admits only this form: its registry validation refuses ``local:!<module>.<Class>`` (it imports arbitrary modules).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from viva_biogears.composites.hemorrhage import biogears_hemorrhage
from viva_biogears.composites.sepsis import biogears_sepsis
from viva_biogears.core import build_core

COMPOSITES = {"hemorrhage": biogears_hemorrhage, "sepsis": biogears_sepsis}


def make_document(composite: str = "hemorrhage", **parameters: object) -> dict:
    """``{"state": ...}`` of the named composite with every address made portable."""
    core = build_core()
    state = COMPOSITES[composite](core, **parameters)
    document = {"state": _portable_addresses(state, core)}
    leftover = [a for a in _addresses(document) if not _portable(a)]
    if leftover:
        raise ValueError(f"addresses that are not a plain local:<module>.<Class> (bare ones only resolve in viva_biogears' own core, `local:!` is refused by compose-api): {leftover}")
    return document


def _portable_addresses(node: object, core: object) -> object:
    """``node`` with each bare ``local:<Name>`` address replaced by the ``local:<module>.<Class>`` of the class the core
    registers under that name."""
    if isinstance(node, dict):
        return {k: _portable_address(v, core) if k == "address" and isinstance(v, str) else _portable_addresses(v, core)
                for k, v in node.items()}
    if isinstance(node, list):
        return [_portable_addresses(v, core) for v in node]
    return node


def _portable_address(address: str, core: object) -> str:
    name = address.removeprefix("local:")
    cls = core.link_registry.get(name) if address.startswith("local:") and "." not in name else None
    return address if cls is None else f"local:{cls.__module__}.{cls.__qualname__}"


_PORTABLE = re.compile(r"local:[A-Za-z_]\w*(\.[A-Za-z_]\w*)+")


def _portable(address: str) -> bool:
    """``local:<module>.<Class>``: a dotted Python path, and not the ``local:!`` form."""
    return _PORTABLE.fullmatch(address) is not None


def _addresses(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        if isinstance(node.get("address"), str):
            found.append(node["address"])
        for value in node.values():
            found.extend(_addresses(value))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--composite", choices=sorted(COMPOSITES), default="hemorrhage")
    parser.add_argument("--rate", type=float, default=None, help="hemorrhage: rate, mL/min (the composite's default, 250, if omitted)")
    parser.add_argument("--state-file", default=None, help="sepsis: starting state (e.g. StandardMale@severe-infection-44h.xml)")
    parser.add_argument("--severity", default=None, help="sepsis: infection severity (the composite's default if omitted)")
    parser.add_argument("--treatment", default=None, help="sepsis: treatment protocol (the composite's default, none, if omitted)")
    args = parser.parse_args()
    given = {"rate_mL_per_min": args.rate, "state_file": args.state_file, "severity": args.severity, "treatment": args.treatment}
    parameters = {k: v for k, v in given.items() if v is not None}
    foreign = sorted(set(parameters) - {"hemorrhage": {"rate_mL_per_min"}, "sepsis": {"state_file", "severity", "treatment"}}[args.composite])
    if foreign:
        parser.error(f"{foreign} do not apply to --composite {args.composite}")
    args.output.write_text(json.dumps(make_document(args.composite, **parameters)))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
