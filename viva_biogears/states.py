"""Save BioGears engine states during a run, one state file per requested simulation time.

A saved state is an ordinary BioGears state file: ``state_file`` loads it as the start
of another run (``BioGearsProcess``, ``BioGearsModularProcess``), so a run can be
checkpointed at ``t`` and branched under several interventions. BioGears records the
whole engine in it, including the actions active at that time (a bleed, an infusion,
intubation, the ventilator, a thermal application, a changed environment), which keep
running after a reload. A process loading such a state reads them from it, so its
setpoints start at the state's values: a branch whose setpoints equal them sends
nothing and continues the run, and one that differs sends the change (a 0 rate stops
the bleed). This matters in BioGears in particular: resending a hemorrhage restarts it.

A reloaded state continues the run to about 1e-11 relative (probe
``workspace/experiments/save-states-2026-11-03``), with pybiogears' fixes for two
BioGears 8.2.0 save/load bugs: the anesthesia machine's empty chamber states (the
saved file did not reload), and ``TotalBloodVolumeLost``, which BioGears doesn't save
(pybiogears keeps it in a comment of the file).

Times are compared in BioGears steps, not seconds. The engine's clock is a floating-point
sum of its steps, so it reads off the exact time: 10 s is reached as 9.999999999999876,
12 h as 43199.999999 and 48 h as 172799.999987. The engine is at step ``round(t / step)``,
and a requested time is reached at the first step at or after it. Files are named
``<name>@<t>s.xml``, BioGears' convention for its shipped states, with ``t`` the engine's
clock rounded to the microsecond. An existing file is never overwritten.

``save_states`` drives the engine it is given (a pybiogears engine you hold, the
command line). A process in a running composite saves its own engine instead, through
its ``save_state_times_s`` config (``StateSaver``).

Command line, from a state file (a name in ``<runtime>/states`` or the package's
``states/``, or a path)::

    python -m viva_biogears.states StandardMale@0s.xml --times 60 120 --out states/
"""

from __future__ import annotations

import argparse
import glob
import math
from pathlib import Path
from typing import Sequence

#: Saved-state names use the engine's time rounded to this many decimals (1 µs).
TIME_DECIMALS = 6
#: A requested time within this fraction of a step of a step boundary is on it.
STEP_DECIMALS = 6
#: How far (in steps) the clock may read off its step grid: its own drift is far smaller.
OFF_GRID_STEPS = 0.01


def engine_step(engine) -> int:
    """The engine's step. Its clock is a floating-point sum of its steps and reads off the
    step's exact time, by 1.3e-5 s at 48 h of 0.02 s steps: far less than half a step.

    Steps count from time 0, so the clock must be on its step's grid. A state saved between
    two of this step's boundaries (at 60.02 s, then loaded with 0.04 s steps) is not, and
    raises: there, which step a time falls on is undefined."""
    step_s = engine.time_step_s
    steps = engine.sim_time_s / step_s
    if abs(steps - round(steps)) > OFF_GRID_STEPS:
        raise ValueError(f"BioGears' clock ({engine.sim_time_s} s) is not on its {step_s} s step grid, so "
                         "saved states and timed actions can't be placed on its steps; load this state with "
                         "a time step that divides its time")
    return round(steps)


def first_step_at_or_after(t: float, step_s: float) -> int:
    """The first step at or after time ``t`` (0.14 s / 0.02 s is 7.000000000000001 in
    floating point, and still step 7)."""
    return math.ceil(round(t / step_s, STEP_DECIMALS))


def _seconds(t: float) -> str:
    """``t`` in fixed point at TIME_DECIMALS, without trailing zeros: 10, 2.5, 86400.02."""
    return f"{t:.{TIME_DECIMALS}f}".rstrip("0").rstrip(".")


def _checked(times_s: Sequence[float], name: str) -> list[float]:
    """``times_s`` as floats, after checking it and ``name`` (shared by both entry points)."""
    if isinstance(times_s, (int, float)):
        raise ValueError(f"times_s must be a sequence of times, got the number {times_s}")
    if not name or "/" in name or "@" in name:
        raise ValueError(f"name must be non-empty, without '/' or '@', got {name!r}")
    times = [float(t) for t in times_s]
    if not times:
        raise ValueError("times_s is empty")
    if not all(math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError(f"times_s must be finite and strictly increasing, got {list(times_s)}")
    return times


class StateSaver:
    """Saves a process's engine at the first update boundary at or after each time.

    A process advances its engine by its own interval, so a save never steps the engine
    (stepping to an exact time inside an update would change the run). Called after the
    engine loads and after every update; when pending times have been reached, it saves
    once, named by the engine's time. Times past the end of the run are never saved.
    States of the same name already in ``out_dir`` raise at construction; two processes
    saving into one directory need different names.
    """

    def __init__(self, times_s: Sequence[float], out_dir: str | Path, name: str):
        self.pending = _checked(times_s, name)
        if not str(out_dir):
            raise ValueError("save_state_dir must be set when save_state_times_s is")
        self.out_dir, self.name = Path(out_dir), name
        existing = sorted(self.out_dir.glob(f"{glob.escape(name)}@*s.xml"))
        if existing:
            raise FileExistsError(f"{self.out_dir} already holds states named {name!r} ({existing[0].name}, ...); "
                                  "use another save_state_dir or save_state_name")
        self.saved: list[Path] = []

    def __call__(self, engine) -> None:
        if not self.pending:
            return
        now, step_s = engine_step(engine), engine.time_step_s
        if first_step_at_or_after(self.pending[0], step_s) <= now:
            while self.pending and first_step_at_or_after(self.pending[0], step_s) <= now:
                self.pending.pop(0)
            # The step's exact time, not the clock: a clock reading just past the step
            # would fall on the next step, and save_states would advance to it.
            self.saved += save_states(engine, self.out_dir, [now * step_s], self.name)


def save_states(engine, out_dir: str | Path, times_s: Sequence[float], name: str = "state") -> list[Path]:
    """Advance ``engine`` (a loaded pybiogears engine) to each simulation time in
    ``times_s`` and save its state there.

    ``times_s`` are absolute simulation times, increasing and not before the engine's
    current time. Each state is saved at the first BioGears step (0.02 s) at or after its
    time, so two times within one step raise; a time equal to the current one saves
    without advancing. An existing file raises instead of being overwritten. Returns the
    written paths, in order. Raises if BioGears fails to advance (an irreversible state)
    or to save; files written before the failure stay.
    """
    times = _checked(times_s, name)
    step_s = engine.time_step_s
    if first_step_at_or_after(times[0], step_s) < engine_step(engine):
        raise ValueError(f"times_s starts at {times[0]} s, before the engine's time {engine.sim_time_s} s")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for t in times:
        target = first_step_at_or_after(t, step_s)
        while engine_step(engine) < target:
            engine.advance_steps(1)
        now = engine.sim_time_s
        path = out / f"{name}@{_seconds(now)}s.xml"
        if path in paths:
            raise ValueError(f"times {t} s and an earlier one both fall on BioGears' step at {now} s")
        if path.exists():
            raise FileExistsError(f"{path} exists; save_states never overwrites a state")
        engine.save_state(path)
        paths.append(path)
    return paths


SAVE_CONFIG = {
    "save_state_times_s": {"_type": "list[float]", "_default": []},
    "save_state_dir": {"_type": "string", "_default": ""},
    "save_state_name": {"_type": "string", "_default": "state"},
}


def saver_from_config(config) -> StateSaver | None:
    if not config["save_state_times_s"]:
        return None
    return StateSaver(config["save_state_times_s"], config["save_state_dir"], config["save_state_name"])


def main(argv: Sequence[str] | None = None) -> list[Path]:
    """Load a state file and save the engine's state at each requested time."""
    from .processes._bridge import load_engine
    from .runtime import runtime_dir, state_path

    parser = argparse.ArgumentParser(prog="python -m viva_biogears.states", description=main.__doc__)
    parser.add_argument("state_file", help="a name in <runtime>/states (or the package's states/), or a path")
    parser.add_argument("--times", type=float, nargs="+", required=True,
                        help="absolute simulation times to save at, in seconds, increasing")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--name", default=None, help="file name stem (default: the state file's, before '@')")
    parser.add_argument("--runtime-dir", default="", help="BioGears runtime directory")
    args = parser.parse_args(argv)
    runtime = runtime_dir(args.runtime_dir)
    state = args.state_file
    if Path(state).name != state:
        state = str(Path(state).expanduser().resolve())
    engine = load_engine(runtime, state_path(runtime, state), [])
    name = args.name or Path(args.state_file).stem.split("@")[0]
    paths = save_states(engine, args.out, args.times, name)
    for path in paths:
        print(path)
    return paths


if __name__ == "__main__":
    main()
