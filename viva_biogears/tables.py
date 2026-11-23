"""Patients and substances from BioGears' spreadsheet templates, and BioGears' patient check.

BioGears describes patients and substances in XML files, which it can generate from
spreadsheet templates (``Patients.csv``, ``Substances.csv``, ``Compounds.csv``, the
layout of ``<runtime>/templates``; one column per item). pybiogears runs BioGears' own
converters on any such CSV (``pybiogears.generate_data``); this module puts them behind
three process settings:

- ``patient_table`` + ``patient``: a column of a Patients.csv, by its Name. The patient
  file is generated from the CSV, then stabilized and cached like a ``patient_file``
  (``viva_biogears.patients``).
- ``substance_table``: a Substances.csv, or a folder holding Substances.csv and/or
  Compounds.csv. The engine then runs on a copy of the runtime whose ``substances/``
  also holds the generated files (BioGears loads every file there at start), so the
  new substances and compounds can be infused and are known to the treatment checks.

Generated files are cached under ``cache_dir()/tables``, keyed by the CSV bytes and the
pybiogears converters, so a CSV is converted once and a changed CSV is converted again.

Every patient (a ``patient_file`` or a table's) is checked with BioGears' own patient
rules (``pybiogears.check_patient``) before anything runs: a patient BioGears would
refuse raises ``ValueError``; a patient whose values BioGears changes (a weight above
BMI 30 lowered to BMI 30, a heart rate above 109 /min set to 109, defaults filled in)
emits a ``PatientAdjustedWarning`` with the full report.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

from .patients import _digest, _update, cache_dir, resolve_patient_file
from .runtime import BASE_MARKER, BioGearsNotFoundError, import_pybiogears, runtime_dir

#: Patients.csv / Substances.csv / Compounds.csv kinds of pybiogears.generate_data.
_SUBSTANCE_KINDS = {"Substances.csv": "substances", "Compounds.csv": "compounds"}


class PatientAdjustedWarning(UserWarning):
    """BioGears accepts the patient but changes some of its values (see the message)."""


def _pybiogears(feature: str):
    pb = import_pybiogears()
    if not hasattr(pb, feature):
        raise BioGearsNotFoundError(
            f"the installed pybiogears has no {feature} (added in pybiogears 2026-11); reinstall it from its main "
            "branch: CMAKE_PREFIX_PATH=<biogears prefix> pip install <path to pybiogears>")
    return pb


def tables_dir() -> Path:
    return cache_dir() / "tables"


def _converter_identity() -> str:
    pb = import_pybiogears()
    from pybiogears import _pybiogears
    return f"{pb.biogears_version()}-{_digest(Path(_pybiogears.__file__))}"


def _table_path(table: str | os.PathLike, what: str) -> Path:
    path = Path(table).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"{what} not found: {path}")
    return path


def _generated(sources: dict[str, Path], label: str) -> Path:
    """pybiogears.generate_data's output for ``sources`` ({kind: csv}), converted once."""
    pb = _pybiogears("generate_data")
    key = hashlib.sha256()
    for kind in sorted(sources):
        _update(key, kind.encode())
        _update(key, sources[kind].read_bytes())
    _update(key, _converter_identity().encode())
    out = tables_dir() / f"{label}-{key.hexdigest()[:24]}"
    if out.is_dir():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=out.parent, prefix=f".{label}-"))
    try:
        try:
            pb.generate_data(sources, work / "data")
        except pb.DataGenerationError as error:
            raise ValueError(f"BioGears could not convert {', '.join(str(p) for p in sources.values())}: {error}") \
                from error
        try:
            os.replace(work / "data", out)
        except OSError:
            if not out.is_dir():         # not a concurrent run that got there first
                raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def patients_from_table(table: str | os.PathLike) -> dict[str, Path]:
    """{patient name: generated patient file} for a Patients.csv (BioGears' template layout)."""
    csv = _table_path(table, "patient_table")
    if not csv.is_file():
        raise ValueError(f"patient_table must be a CSV file (BioGears' Patients.csv layout), got the folder {csv}")
    folder = _generated({"patients": csv}, f"patients-{csv.stem}") / "patients"
    names = {}
    for f in sorted(folder.glob("*.xml")):
        name = ET.parse(f).getroot().findtext("{uri:/mil/tatrc/physiology/datamodel}Name")
        names[name or f.stem] = f
    return names


def _substance_sources(table: str | os.PathLike) -> dict[str, Path]:
    path = _table_path(table, "substance_table")
    if path.is_file():
        return {"substances": path}
    found = {kind: path / name for name, kind in _SUBSTANCE_KINDS.items() if (path / name).is_file()}
    if not found:
        raise FileNotFoundError(f"substance_table {path} holds neither Substances.csv nor Compounds.csv")
    return found


def substances_from_table(table: str | os.PathLike) -> list[Path]:
    """The substance and compound files generated from ``table`` (a Substances.csv, or a
    folder with Substances.csv and/or Compounds.csv)."""
    sources = _substance_sources(table)
    label = "substances-" + "-".join(p.stem for p in sources.values())
    return sorted((_generated(sources, label) / "substances").glob("*.xml"))


def runtime_with_substances(runtime: Path, table: str | os.PathLike) -> Path:
    """A runtime directory that is ``runtime`` plus the substances of ``table``.

    Every entry of ``runtime`` is linked except ``substances/``, which holds links to
    the runtime's substance files and copies of the generated ones (a generated file
    with the name of a shipped one replaces it). The base runtime is recorded in
    ``.viva-biogears-base`` (``runtime.base_runtime``). Built once per runtime and table.
    """
    runtime = Path(runtime)
    files = substances_from_table(table)
    key = hashlib.sha256(str(runtime).encode())
    for f in files:
        _update(key, f.name.encode())
        _update(key, f.read_bytes())
    out = tables_dir() / f"runtime-{key.hexdigest()[:24]}"
    if out.is_dir():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=out.parent, prefix=".runtime-"))
    try:
        for entry in runtime.iterdir():
            if entry.name != "substances":
                (work / entry.name).symlink_to(entry)
        (work / "substances").mkdir()
        for f in (runtime / "substances").iterdir():
            (work / "substances" / f.name).symlink_to(f)
        for f in files:
            target = work / "substances" / f.name
            if target.is_symlink():
                target.unlink()
            shutil.copyfile(f, target)
        (work / BASE_MARKER).write_text(str(runtime))
        try:
            os.replace(work, out)
        except OSError:
            if not out.is_dir():
                raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def engine_runtime(config) -> Path:
    """The runtime a process runs on: ``runtime_dir`` (``viva_biogears.runtime``), plus the
    substances of ``substance_table`` when it is set."""
    runtime = runtime_dir(config.get("runtime_dir", ""))
    table = config.get("substance_table", "")
    return runtime_with_substances(runtime, table) if table else runtime


def start_patient(config, runtime: Path | None = None) -> Path | None:
    """The patient file a process starts from: ``patient_file``, or ``patient`` from
    ``patient_table``; None when it starts from ``state_file`` (or only ``conditions``)."""
    if config.get("patient_table"):
        table = patients_from_table(config["patient_table"])
        name = config.get("patient", "")
        if name not in table:
            raise ValueError(f"patient {name!r} is not in patient_table {config['patient_table']}; "
                             f"it has {sorted(table)}")
        return table[name]
    if config.get("patient_file"):
        return resolve_patient_file(config["patient_file"], runtime or runtime_dir(config.get("runtime_dir", "")))
    return None


def check_patient(patient_file: str | os.PathLike):
    """``pybiogears.check_patient``: what BioGears 8.2.0 does with the patient when it sets
    it up (``.ok``, ``.errors``, ``.adjusted``, ``.warnings``, ``.values``, ``.report()``)."""
    return _pybiogears("check_patient").check_patient(Path(patient_file))


def require_acceptable(patient_file: Path) -> None:
    """Raise ``ValueError`` if BioGears would refuse the patient; warn
    (``PatientAdjustedWarning``) if it changes any of its values."""
    check = check_patient(patient_file)
    if not check.ok:
        raise ValueError(check.report())
    if check.adjusted:
        warnings.warn(check.report(), PatientAdjustedWarning, stacklevel=3)
