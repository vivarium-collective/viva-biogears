"""The compose-api image's contract (docs/design/prebuilt-image.md), against the real BioGears engine; nothing is mocked.

What is exercised is docker/compose-entrypoint.sh + the vendored docker/runner.py (compose-api 0.7.102's generic runner)
+ viva_biogears, in the interpreter running the tests. The image itself (Docker/Apptainer, process-bigraph 1.11.1) is
checked by .github/workflows/compose-image.yml. Each test names the proposition it would falsify.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from viva_biogears.runtime import runtime_dir

DOCKER = Path(__file__).resolve().parents[1] / "docker"
ENTRYPOINT = DOCKER / "compose-entrypoint.sh"
RUNNER = DOCKER / "runner.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, DOCKER / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_document = _load("make_document").make_document
# The composites compose-api can be given: the default hemorrhage, and a sepsis slice from the shipped 44 h infection state.
DOCUMENTS = [("hemorrhage", {}), ("sepsis", {"state_file": "StandardMale@severe-infection-44h.xml"})]
BY_COMPOSITE = pytest.mark.parametrize("composite, parameters", DOCUMENTS, ids=[d[0] for d in DOCUMENTS])
check_results = _load("check_results").check


def _job(entry, *args, runtime, tmp_path, check=True):
    """compose-api's job command, `<entry> run <doc> -o <out> -n <t>`, with a runtime directory and a scratch TMPDIR."""
    doc, out = tmp_path / "doc.pbg", tmp_path / "output"
    doc.write_text(json.dumps(make_document()))
    tmp = tmp_path / "tmp"
    tmp.mkdir(exist_ok=True)
    env = {**os.environ, "BIOGEARS_RUNTIME": str(runtime), "COMPOSE_RUNNER": str(RUNNER), "COMPOSE_PYTHON": sys.executable,
           "TMPDIR": str(tmp)}
    cmd = [*entry, "run", str(doc), "-o", str(out), "-n", "10", *args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300), out, tmp


@pytest.fixture(scope="module")
def read_only_runtime(tmp_path_factory):
    """A copy of the BioGears runtime that nothing can write into: the image's filesystem, as seen by the engine."""
    copy = tmp_path_factory.mktemp("ro") / "runtime"
    shutil.copytree(runtime_dir(), copy)
    for path in [copy, *copy.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    yield copy
    for path in [copy, *copy.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


def test_vendored_runner_is_compose_apis_file():
    """Falsified if docker/runner.py is edited (or re-pinned) without docker/runner.sha256: the image must carry
    exactly the release file compose-api's cluster contract was written against."""
    expected = (DOCKER / "runner.sha256").read_text().split()[0]
    assert hashlib.sha256(RUNNER.read_bytes()).hexdigest() == expected


# The runner's plain core (`allocate_core()`) finds classes through `importlib.metadata.packages_distributions()`, which
# lists no editable package, so `local:<module>.<Class>` resolves only when viva-biogears is installed normally, as in
# the image. biogears-engine-ci installs it that way; workspace-ci (generated from viva-template) installs `-e`.
import importlib.metadata  # noqa: E402

discoverable = pytest.mark.skipif("viva_biogears" not in importlib.metadata.packages_distributions(),
                                  reason="viva_biogears is an editable install; install it without -e (README.md)")


def test_portable_address_check_accepts_only_plain_dotted_local_paths():
    """Falsified if the check in make_document.py lets through the `local:!` form (compose-api refuses it), a bare
    `local:Name` (the runner's plain core cannot resolve it) or a malformed path."""
    portable = _load("make_document")._portable
    assert portable("local:viva_biogears.processes.biogears.BioGearsProcess")
    assert portable("local:process_bigraph.emitter.RAMEmitter")
    for bad in ["local:!viva_biogears.processes.biogears.BioGearsProcess", "local:BioGearsProcess", "local:.", "local:a.",
                "local:.C", "local:a.!b", "python:a.B", "local:", ""]:
        assert not portable(bad), bad


@discoverable
@BY_COMPOSITE
def test_document_resolves_in_the_runners_plain_core(composite, parameters):
    """Falsified if the document uses a bare `local:Name` address: the runner's core is a plain allocate_core(),
    where a bare name does not resolve, so compose-api would fail with 'no link found at address'."""
    from bigraph_schema.protocols import unresolvable_addresses
    from process_bigraph import allocate_core
    assert unresolvable_addresses(make_document(composite, **parameters), allocate_core()) == []


@BY_COMPOSITE
def test_document_addresses_are_the_form_compose_api_admits(composite, parameters):
    """Falsified if any address is the `local:!module.Class` form: compose-api's registry validation refuses it
    (compose_api/registry/validation.py, "imports arbitrary modules"), even for a prebuilt image, so the document would be
    rejected at admission however well it runs. Every address must be `local:<module>.<Class>`."""
    def addresses(node):
        if isinstance(node, dict):
            if isinstance(node.get("address"), str):
                yield node["address"]
            for value in node.values():
                yield from addresses(value)
    found = list(addresses(make_document(composite, **parameters)))
    assert found, "the document has no addresses"
    assert [a for a in found if a.startswith("local:!")] == []
    assert all(a.startswith("local:") and "." in a.removeprefix("local:") for a in found), found


@discoverable
def test_job_command_runs_the_engine_on_a_read_only_runtime(read_only_runtime, tmp_path):
    """Falsified if the job command fails, the engine does not advance, a vital is not finite, or the hemorrhage
    does not lower blood volume, with the BioGears runtime directory not writable (the image under Apptainer)."""
    done, out, _ = _job(["bash", str(ENTRYPOINT)], runtime=read_only_runtime, tmp_path=tmp_path)
    assert done.returncode == 0, done.stderr[-2000:]
    summary = check_results(out)
    assert summary["t_end"] == 10.0 and summary["rows"] == 11


def test_engine_alone_cannot_use_a_read_only_runtime(read_only_runtime, tmp_path):
    """Falsified if BioGears/pybiogears stop writing into the runtime directory. Then the scratch runtime in the
    entrypoint is unnecessary and should be removed: this test is the reason it exists (pybiogears writes its
    action/condition/configuration files into the engine's working directory = the runtime)."""
    doc = tmp_path / "doc.pbg"
    doc.write_text(json.dumps(make_document()))
    env = {**os.environ, "BIOGEARS_RUNTIME": str(read_only_runtime)}
    done = subprocess.run([sys.executable, str(RUNNER), "run", str(doc), "-o", str(tmp_path / "out"), "-n", "10"],
                          env=env, capture_output=True, text=True, timeout=300)
    assert done.returncode != 0


@discoverable
def test_entrypoint_leaves_nothing_in_tmp(read_only_runtime, tmp_path):
    """Falsified if the per-job scratch directory survives the run: compose-api puts TMPDIR on the node's disk, and a
    leaked directory per job fills it."""
    done, _, tmp = _job(["bash", str(ENTRYPOINT)], runtime=read_only_runtime, tmp_path=tmp_path)
    assert done.returncode == 0, done.stderr[-2000:]
    assert list(tmp.iterdir()) == []


def test_entrypoint_passes_the_runners_failure_through(read_only_runtime, tmp_path):
    """Falsified if a failing run exits 0: compose-api would record a failed simulation as complete."""
    env = {**os.environ, "BIOGEARS_RUNTIME": str(read_only_runtime), "COMPOSE_RUNNER": str(RUNNER),
           "COMPOSE_PYTHON": sys.executable, "TMPDIR": str(tmp_path)}
    done = subprocess.run(["bash", str(ENTRYPOINT), "run", str(tmp_path / "missing.pbg"), "-o", str(tmp_path / "o"), "-n", "1"],
                          env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode != 0
