"""Locate the BioGears runtime and the pybiogears binding.

BioGears has no PyPI release: it is built from source and driven through
pybiogears (https://github.com/vivarium-collective/pybiogears, built against an installed BioGears 8.2.0
by its ``scripts/install_biogears.sh``). The *runtime* directory
holds BioGears' data (``xsd/``, ``substances/``, ``patients/``, ``states/``); the
install script assembles it at ``<prefix>/share/biogears/runtime``.

The runtime directory is the first of these that is set:
  1. the ``runtime_dir`` process config;
  2. ``$BIOGEARS_RUNTIME``;
  3. ``~/biogears-8.2.0-install/share/biogears/runtime`` (the install script's default).

A location that is given (1 or 2) but is not a valid runtime raises
``BioGearsNotFoundError``; it never falls back to another location.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_RUNTIME = Path("~/biogears-8.2.0-install/share/biogears/runtime").expanduser()
BIOGEARS_VERSION = "8.2.0"


class BioGearsNotFoundError(RuntimeError):
    """No usable BioGears runtime or pybiogears binding."""


def _check_runtime(path: Path, origin: str) -> Path:
    missing = [d for d in ("xsd", "substances", "patients", "states") if not (path / d).is_dir()]
    if missing:
        raise BioGearsNotFoundError(
            f"{origin} {path} is not a BioGears runtime directory (missing {', '.join(missing)}). "
            "Build one with pybiogears' scripts/install_biogears.sh; see README.md.")
    return path


def runtime_dir(configured: str = "") -> Path:
    """The BioGears runtime directory (see the module docstring for the order)."""
    if configured:
        return _check_runtime(Path(configured).expanduser().resolve(), "runtime_dir")
    env = os.environ.get("BIOGEARS_RUNTIME")
    if env:
        return _check_runtime(Path(env).expanduser().resolve(), "$BIOGEARS_RUNTIME")
    return _check_runtime(DEFAULT_RUNTIME, "the default runtime")


#: File in a runtime built by ``tables.runtime_with_substances`` naming the runtime it extends.
BASE_MARKER = ".viva-biogears-base"


def base_runtime(runtime: Path) -> Path:
    """The installed runtime ``runtime`` is (or extends, for a runtime with a substance table)."""
    marker = Path(runtime) / BASE_MARKER
    return Path(marker.read_text().strip()) if marker.is_file() else Path(runtime)


def import_pybiogears():
    """The pybiogears module, checked to drive BioGears 8.2.0."""
    try:
        import pybiogears
    except ImportError as ex:
        raise BioGearsNotFoundError(
            "pybiogears is not installed in this environment. Install it with "
            "CMAKE_PREFIX_PATH=<biogears prefix> pip install <path to pybiogears>; see README.md."
        ) from ex
    version = pybiogears.biogears_version()
    if not version.startswith(BIOGEARS_VERSION):
        raise BioGearsNotFoundError(f"pybiogears drives BioGears {version}; viva-biogears needs {BIOGEARS_VERSION}")
    return pybiogears


#: States shipped with viva-biogears (see viva_biogears/states/README.md).
PACKAGE_STATES = Path(__file__).parent / "states"
#: StandardMale@0s after 5 h at rest with 150 mL water/h (equilibration-2026-11-03).
EQUILIBRATED_STATE = "StandardMale@equilibrated.xml"


def state_path(runtime: Path, state_file: str) -> Path:
    """``state_file`` if absolute, else ``<runtime>/states/<state_file>``, else the
    package's ``states/<state_file>``; must exist."""
    p = Path(state_file)
    if not p.is_absolute():
        candidates = [runtime / "states" / state_file, PACKAGE_STATES / state_file]
        p = next((c for c in candidates if c.is_file()), candidates[0])
    if not p.is_file():
        raise FileNotFoundError(f"BioGears state file not found: {state_file} "
                                f"(looked in {runtime / 'states'} and {PACKAGE_STATES})")
    return p


def compound_names(runtime: Path) -> list[str]:
    """Substance compounds BioGears can infuse: files in ``<runtime>/substances`` that hold one."""
    return sorted(p.stem for p in (runtime / "substances").glob("*.xml")
                  if "<SubstanceCompound" in p.read_text(errors="ignore")[:2000])
