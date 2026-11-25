"""Write a short, real BioGears document for compose-api's runner: ``make_document.py OUT.pbg [--rate R]``.

The document is the ``biogears_hemorrhage`` composite with portable addresses (``local:<module>.<Class>``): the
runner's core is a plain ``allocate_core()``, so a bare ``local:BioGearsProcess`` would not resolve there. compose-api
admits only this form: its registry validation refuses ``local:!<module>.<Class>`` (it imports arbitrary modules).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from process_bigraph.emitter import RAMEmitter

from viva_biogears.composites.hemorrhage import biogears_hemorrhage
from viva_biogears.core import build_core
from viva_biogears.processes.biogears import BioGearsProcess

PORTABLE = {
    "local:BioGearsProcess": f"local:{BioGearsProcess.__module__}.{BioGearsProcess.__name__}",
    "local:RAMEmitter": f"local:{RAMEmitter.__module__}.{RAMEmitter.__name__}",
}


def make_document(**parameters: object) -> dict:
    """``{"state": ...}`` of ``biogears_hemorrhage(**parameters)`` with every address made portable."""
    state = biogears_hemorrhage(build_core(), **parameters)
    text = json.dumps(state)
    for bare, portable in PORTABLE.items():
        text = text.replace(f'"{bare}"', f'"{portable}"')
    document = {"state": json.loads(text)}
    leftover = [a for a in _addresses(document) if not _portable(a)]
    if leftover:
        raise ValueError(f"addresses that are not a plain local:<module>.<Class> (bare ones only resolve in viva_biogears' own core, `local:!` is refused by compose-api): {leftover}")
    return document


def _portable(address: str) -> bool:
    """``local:<module>.<Class>``: dotted, and not the ``local:!`` form."""
    module_class = address.removeprefix("local:")
    return address.startswith("local:") and not module_class.startswith("!") and "." in module_class


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
    parser.add_argument("--rate", type=float, default=None, help="hemorrhage rate, mL/min; the composite's default (250) if omitted")
    args = parser.parse_args()
    parameters = {} if args.rate is None else {"rate_mL_per_min": args.rate}
    args.output.write_text(json.dumps(make_document(**parameters)))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
