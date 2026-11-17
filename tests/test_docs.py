"""The user documentation builds with no warnings, executing every tutorial.

The tutorials are notebooks run against the real engine during the build
(``nb_execution_mode = "force"``), so a code change that breaks an example or a renamed
port fails here, as it would fail ``make docs``. About ten minutes.

The Read the Docs build (``READTHEDOCS=True``) can't use BioGears, so it publishes the
tutorials as code only; ``test_hosted_build_needs_no_engine`` builds it that way with
BioGears unreachable.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _build(out: Path, env: dict | None = None) -> None:
    pytest.importorskip("myst_nb", reason="install the docs group: uv pip install --group docs")
    result = subprocess.run(
        [sys.executable, "-m", "sphinx", "-W", "--keep-going", "-b", "html", str(ROOT / "documentation"), str(out)],
        capture_output=True, text=True, cwd=ROOT, timeout=3600, env=env,
    )
    assert result.returncode == 0, result.stderr[-4000:]


def test_docs_build_without_warnings(tmp_path):
    """Falsifies: a tutorial cell raises, a cross-reference is broken, or a docstring the API
    pages render has invalid markup (``-W`` turns every warning into a failure)."""
    from viva_biogears.runtime import BioGearsNotFoundError, runtime_dir
    try:
        runtime_dir()
    except BioGearsNotFoundError:
        pytest.skip("BioGears build not available")
    out = tmp_path / "html"
    _build(out)
    for page in ("index", "tutorials/03-lymph-and-tissue-fluid", "concepts/modules", "api/modules"):
        assert (out / f"{page}.html").is_file(), page
    assert "cell_output" in (out / "tutorials/01-hemorrhage-and-resuscitation.html").read_text()
    shutil.rmtree(out)


def test_hosted_build_needs_no_engine(tmp_path):
    """Falsifies: the Read the Docs build executes a page that needs BioGears (with
    ``BIOGEARS_RUNTIME`` pointing nowhere, any engine load raises), or the hosted pages lose
    the note that the tutorials show code only."""
    out = tmp_path / "html"
    env = {**os.environ, "READTHEDOCS": "True", "BIOGEARS_RUNTIME": str(tmp_path / "no-biogears")}
    _build(out, env)
    tutorial = (out / "tutorials/01-hemorrhage-and-resuscitation.html").read_text()
    assert "show their code without its output" in tutorial
    assert "show their code without its output" in (out / "index.html").read_text()
    assert "cell_output" not in tutorial
    shutil.rmtree(out)
