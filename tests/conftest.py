import pytest
from process_bigraph import Composite, gather_emitter_results

from viva_biogears.core import build_core
from viva_biogears.runtime import BioGearsNotFoundError, import_pybiogears, runtime_dir


def _biogears_available() -> bool:
    """True when pybiogears and a BioGears runtime can be found (see viva_biogears.runtime)."""
    try:
        import_pybiogears()
        runtime_dir()
        return True
    except BioGearsNotFoundError:
        return False


BIOGEARS_AVAILABLE = _biogears_available()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Engine-free CI: skip (don't fail) tests that need the real BioGears build.

    BioGears has no PyPI release, so CI without a build raises BioGearsNotFoundError
    in engine-driving tests; convert that to a skip. With a build present, nothing is
    converted and every engine test runs for real. (Same scheme as viva-pulse.)
    """
    outcome = yield
    if BIOGEARS_AVAILABLE:
        return
    report = outcome.get_result()
    if call.excinfo is not None and call.excinfo.errisinstance(BioGearsNotFoundError):
        report.outcome = "skipped"
        report.longrepr = (str(item.fspath), None, "BioGears build not available")


@pytest.fixture
def run_composite():
    """Run a composite generator for `seconds`; returns (sim, emitted rows)."""
    def run(generator, seconds, **kwargs):
        core = build_core()
        sim = Composite({"state": generator(core, **kwargs)}, core=core)
        sim.run(seconds)
        return sim, gather_emitter_results(sim)[("emitter",)]
    return run


@pytest.fixture
def direct_engine():
    """A pybiogears engine driven directly (the oracle for BioGearsProcess)."""
    def make(state_file="StandardMale@0s.xml"):
        from viva_biogears.processes.biogears import VITALS
        pb = import_pybiogears()
        rt = runtime_dir()
        e = pb.BioGearsEngine(rt)
        e.set_requests([pb.DataRequest("Physiology", p, u) for p, u in VITALS.values()])
        e.load_state(rt / "states" / state_file)
        return e
    return make
