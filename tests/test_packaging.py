"""Packaging: viva-biogears is also a library other workspaces install (inflect-sim-core pins
it from git), so its core dependencies are what the library itself needs, and no more.

Regression: ``vivarium-workbench==0.3.92`` was a core dependency, so a project that brings its
own workbench (inflect-sim-core, 0.5.3 from git) could not resolve viva-biogears at all ("your
project's requirements are unsatisfiable"). And ``viva_superpowers``, which ``core.build_core()``
imports, came only through the workbench, so moving the workbench to an extra alone would have
broken the import.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

LIBRARY_IMPORT = """
import importlib, importlib.util, inspect, json, pkgutil
import viva_biogears
import viva_biogears.composites as composites
from process_bigraph import Composite
from viva_biogears.core import build_core
from viva_biogears.runtime import BioGearsNotFoundError
names = [m.name for m in pkgutil.walk_packages(viva_biogears.__path__, "viva_biogears.")
         if not m.name.startswith("viva_biogears.cli")]  # the CLI is the `cli` extra
for name in names:
    importlib.import_module(name)
core = build_core()
# Every composite generator runs until it needs the engine: imports inside a generator's body
# run too. Without pybiogears (the `engine` extra) the only allowed failure is the engine's.
generators = {}
for m in pkgutil.iter_modules(composites.__path__, "viva_biogears.composites."):
    module = importlib.import_module(m.name)
    for name, make in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("biogears_") and make.__module__ == module.__name__:
            try:
                Composite({"state": make(build_core())}, core=build_core())
                generators[name] = "built"
            except BioGearsNotFoundError:
                generators[name] = "needs the engine"
print(json.dumps({"module": viva_biogears.__file__,
                  "registered": "BioGearsModularProcess" in core.link_registry,
                  "generators": generators,
                  "workbench": importlib.util.find_spec("vivarium_workbench") is not None}))
"""


def test_core_dependencies_have_no_exact_pins():
    """Falsifies: a core dependency pinned to one version. A project that installs viva-biogears
    as a library resolves these together with its own requirements, and an exact pin
    (``vivarium-workbench==0.3.92``) left it no solution. Exact pins belong in extras."""
    import tomllib

    from packaging.requirements import Requirement

    core = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    pinned = [d for d in core if any(s.operator in ("==", "===") for s in Requirement(d).specifier)]
    assert pinned == []


def test_library_installs_and_imports_without_extras(tmp_path):
    """Falsifies: installing viva-biogears without extras pulls in the workbench (whose exact pin
    made a project with its own workbench unresolvable), or leaves the library unable to import
    every module, build its core, and run each composite generator up to the engine
    (core.py's viva_superpowers came only through the workbench). No engine is needed:
    pybiogears is the `engine` extra and is imported only when an engine loads."""
    uv = shutil.which("uv")
    assert uv, "uv is required to develop viva-biogears (see README.md)"
    venv = tmp_path / "venv"
    python = venv / "bin" / "python"
    for cmd in ([uv, "venv", "--python", sys.executable, str(venv)],
                [uv, "pip", "install", "--python", str(python), str(ROOT)]):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        assert result.returncode == 0, result.stderr
    result = subprocess.run([str(python), "-I", "-c", LIBRARY_IMPORT], capture_output=True,
                            text=True, timeout=300, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.splitlines()[-1])
    assert Path(out["module"]).is_relative_to(venv)
    assert out["workbench"] is False
    assert out["registered"]
    assert {"biogears_hemorrhage", "biogears_sepsis", "biogears_lymph"} <= set(out["generators"])
