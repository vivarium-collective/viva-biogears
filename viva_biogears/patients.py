"""Stabilized states for any patient file (and chronic conditions), stabilized once and cached.

A patient file (``<runtime>/patients/*.xml``) describes a person: sex, age, weight,
height, body fat and resting baselines. BioGears can't simulate from it directly;
``InitializeEngine`` first builds the body and runs it at rest until it settles
(*stabilization*), optionally applying chronic conditions. That takes minutes
(``workspace/experiments/stabilization-2026-11-03``); loading the saved state takes
well under a second. BioGears ships stabilized states for most of its own patients,
but not for a patient file you write or for any patient with conditions.
``stabilized_state`` stabilizes once and keeps the result in a cache directory, so
every later run loads it directly.

**Conditions** are BioGears' chronic conditions, applied during stabilization so
the patient starts with them in place: a map from condition name to its fields,

    {"ChronicAnemia": {"ReductionFactor": 0.3},
     "Starvation": {"TimeSinceMeal": "72 hr"}}

A field's value is a number (unitless) or a ``"<value> <unit>"`` string. The names
are BioGears' ``<Name>Data`` condition types (``CONDITIONS``); their fields are
those of ``share/xsd/cdm/PatientConditions.xsd``. BioGears rejects a wrong field,
which raises. The result is a different patient, not a perturbation of a running
one.

The cache key covers everything the stabilized state depends on: the patient
file's bytes, the conditions, and the BioGears install (``install_identity``: the
BioGears version, the SHA-256 of the pybiogears extension and of the BioGears
libraries next to the runtime, and of the data files stabilization reads).
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import platformdirs

from .runtime import import_pybiogears

#: Environment variable that overrides the cache directory.
CACHE_ENV_VAR = "VIVA_BIOGEARS_CACHE_DIR"

#: BioGears 8.2.0's patient conditions (PatientConditions.xsd), by name without "Data".
CONDITIONS = ("ChronicAnemia", "ChronicHeartFailure", "ChronicVentricularSystolicDysfunction",
              "ChronicObstructivePulmonaryDisease", "ChronicPericardialEffusion", "ChronicRenalStenosis",
              "Dehydration", "ImpairedAlveolarExchange", "LobarPneumonia", "Starvation")

#: Runtime files and directories BioGears reads when it stabilizes a patient.
DATA_ENTRIES = ("BioGearsConfiguration.xml", "config", "environments", "nutrition", "substances", "ecg",
                "xsd")


def cache_dir() -> Path:
    """``$VIVA_BIOGEARS_CACHE_DIR`` if set, else ``states/`` in the user cache directory."""
    override = os.environ.get(CACHE_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return platformdirs.user_cache_path("viva-biogears") / "states"


def resolve_patient_file(patient_file: str, runtime: Path) -> Path:
    """A bare name is a file in ``<runtime>/patients/``; anything else is a path."""
    separators = {os.sep, os.altsep} - {None}
    if any(sep in patient_file for sep in separators):
        path = Path(patient_file).expanduser().resolve()
    else:
        path = runtime / "patients" / patient_file
    if not path.is_file():
        raise FileNotFoundError(f"BioGears patient file not found: {path}")
    return path


_SCALAR = re.compile(r"^\s*([-+0-9.eE]+)\s*(.*?)\s*$")


def conditions_xml(conditions: dict) -> str:
    """BioGears ``<Condition>`` elements for ``conditions`` (see the module docstring)."""
    out = []
    for name, fields in sorted(conditions.items()):
        if name not in CONDITIONS:
            raise ValueError(f"unknown condition {name!r}; BioGears 8.2.0 has {CONDITIONS}")
        if not isinstance(fields, dict) or not fields:
            raise ValueError(f"condition {name} needs its fields, e.g. {{'ReductionFactor': 0.3}}")
        parts = []
        for field_name, value in fields.items():
            if not re.fullmatch(r"[A-Za-z]+", str(field_name)):
                raise ValueError(f"condition {name}: bad field name {field_name!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValueError(f"condition {name}.{field_name}: give a number or '<value> <unit>', got {value!r}")
            if isinstance(value, str):
                m = _SCALAR.match(value)
                if not m:
                    raise ValueError(f"condition {name}.{field_name}: give a number or '<value> <unit>', got {value!r}")
                number, unit = float(m.group(1)), m.group(2)
            else:
                number, unit = float(value), ""
            if not math.isfinite(number):
                raise ValueError(f"condition {name}.{field_name} must be finite, got {value!r}")
            unit_attr = f" unit={quoteattr(unit)}" if unit else ""
            parts.append(f'<{field_name} value="{number!r}"{unit_attr}/>')
        out.append(f'<Condition xsi:type="{escape(name)}Data">{"".join(parts)}</Condition>')
    return "\n".join(out)


def _update(digest, data: bytes) -> None:
    digest.update(len(data).to_bytes(8, "big"))
    digest.update(data)


@functools.cache
def _file_digest(path: str, mtime: float) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(path: Path) -> str:
    return _file_digest(str(path), path.stat().st_mtime)


@functools.cache
def _data_digest(runtime: str) -> str:
    digest = hashlib.sha256()
    root = Path(runtime)
    files = []
    for entry in DATA_ENTRIES:
        p = root / entry
        files += [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file())
    for path in files:
        _update(digest, path.relative_to(root).as_posix().encode())
        _update(digest, path.read_bytes())
    return digest.hexdigest()


def _libraries(runtime: Path) -> list[Path]:
    """The BioGears shared libraries of the install the runtime belongs to
    (``<prefix>/lib`` or ``<prefix>/bin``, with ``<prefix>/share/biogears/runtime``)."""
    prefix = runtime.parent.parent.parent
    libs = []
    for d in ("lib", "lib64", "bin"):
        libs += sorted(p for p in (prefix / d).glob("libbiogears*") if p.is_file() and not p.is_symlink())
    return libs


def install_identity(runtime: Path) -> str:
    """``<version>-<sha256 of the binaries>-<sha256 of the data>`` for this BioGears install."""
    pb = import_pybiogears()
    from pybiogears import _pybiogears  # the compiled extension
    binaries = hashlib.sha256()
    for path in [Path(_pybiogears.__file__), *_libraries(runtime)]:
        _update(binaries, path.name.encode())
        _update(binaries, _digest(path).encode())
    return f"{pb.biogears_version()}-{binaries.hexdigest()}-{_data_digest(str(runtime))}"


def stabilized_state(patient_file: str, runtime: Path, conditions: dict | None = None) -> Path:
    """The path of a stabilized state for ``patient_file`` with ``conditions``.

    Looked up in ``cache_dir()`` by its cache key. On a miss, BioGears stabilizes
    the patient (minutes), the state is saved to a temporary file in the cache
    directory, checked to load, and moved into place atomically, so a concurrent
    run never sees a partial file. Two runs that miss at once both stabilize and
    write equivalent files; the last one wins.
    """
    runtime = Path(runtime)
    patient_path, content, state_path = _cache_entry(patient_file, runtime, conditions)
    if state_path.is_file():
        return state_path
    conditions = dict(conditions or {})
    state_path.parent.mkdir(parents=True, exist_ok=True)
    _stabilize(runtime, patient_path, content, conditions_xml(conditions) if conditions else "", state_path,
               conditions)
    return state_path


def cache_path(patient_file: str, runtime: Path, conditions: dict | None = None) -> Path:
    """Where ``stabilized_state`` keeps (or will keep) this patient's state; nothing is stabilized."""
    return _cache_entry(patient_file, Path(runtime), conditions)[2]


def _cache_entry(patient_file, runtime, conditions):
    patient_path = resolve_patient_file(patient_file, runtime)
    content = patient_path.read_bytes()
    conditions = dict(conditions or {})
    if conditions:
        conditions_xml(conditions)  # validate before anything is stabilized
    key = hashlib.sha256()
    for part in (content, install_identity(runtime).encode(),
                 json.dumps(conditions, sort_keys=True, default=str).encode()):
        _update(key, part)
    tag = "-".join(sorted(conditions))
    name = f"{patient_path.stem}{'-' + tag if tag else ''}-{key.hexdigest()[:24]}@0s.xml"
    return patient_path, content, cache_dir() / name


def _stabilize(runtime: Path, patient_path: Path, content: bytes, xml: str, state_path: Path,
               conditions: dict) -> None:
    pb = import_pybiogears()

    def temporary(suffix: str) -> str:
        fd, path = tempfile.mkstemp(dir=state_path.parent, prefix=f".{patient_path.stem}.", suffix=suffix)
        os.close(fd)
        return path

    # Stabilize the exact bytes that were hashed, even if the file changes meanwhile.
    patient_copy, partial = temporary(".patient.xml"), temporary(".xml")
    try:
        Path(patient_copy).write_bytes(content)
        engine = pb.BioGearsEngine(runtime)
        try:
            engine.initialize(patient_copy, xml)
        except pb.BioGearsError as error:
            raise RuntimeError(f"BioGears failed to stabilize {patient_path}"
                               + (f" with conditions {conditions}" if conditions else "") + f": {error}") from error
        engine.save_state(partial)
        check = pb.BioGearsEngine(runtime)
        check.load_state(partial)
        os.replace(partial, state_path)
    finally:
        for path in (patient_copy, partial):
            Path(path).unlink(missing_ok=True)
