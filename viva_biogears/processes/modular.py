"""BioGearsModularProcess: the whole BioGears engine, exposing the selected modules' readings and setpoints."""

from __future__ import annotations

import math
from typing import Any

from process_bigraph import Process

from ..modules import MODULES
from ..modules.base import check_outputs
from ..modules.state import read_state
from ..states import SAVE_CONFIG, engine_step, first_step_at_or_after, saver_from_config
from ._bridge import (
    START_CONFIG,
    advance,
    check_compound,
    check_start,
    load_engine,
    resolve_state,
)


def _config_schema() -> dict[str, Any]:
    schema: dict[str, Any] = {"modules": {"_type": "list[string]", "_default": []}, **START_CONFIG, **SAVE_CONFIG}
    for module in MODULES.values():
        for key, spec in module.params.items():
            if key in schema and schema[key] != spec:
                raise ValueError(f"circuit module {module.name!r} redefines config key {key!r}")
            schema[key] = spec
    return schema


def _nest(leaves) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for path, value in leaves:
        node = tree
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value
    return tree


class BioGearsModularProcess(Process):
    """Bridge to one real BioGears 8.2.0 engine, exposing the selected modules (every BioGears
    system is simulated every step; a module chooses only which readings and setpoints are ports).

    ``config.modules`` names entries of ``viva_biogears.modules.MODULES``. Each module
    contributes a port subtree named after it:

    - outputs: the module's BioGears data requests as ``overwrite[float]`` ports at the
      module's nested paths (e.g. ``cardiovascular/central/aorta/pressure_mmHg``);
    - inputs, under the single ``setpoints`` port: the module's setpoints as
      ``overwrite[float]`` ports whose schema default is the baseline value, sent to
      BioGears as actions only on change (e.g. ``setpoints/cardiovascular/hemorrhage_rate_mL_per_min``).

    Inputs and outputs use disjoint top-level port names on purpose: process-bigraph
    projects ``initial_state()`` through the input wires as well as the output wires,
    so a shared name would copy readings into the setpoint store.

    Outputs follow ``BioGearsProcess``'s contract: ``initial_state()`` seeds each store
    with the loaded state's reading and every update emits BioGears' current reading.
    ``irreversible_state`` turns True once BioGears reports its irreversible state; the
    engine is not advanced after that. Identical requests from different modules share
    one BioGears request. A request BioGears does not connect raises at load; a NaN
    reading raises, naming the request, unless the request allows it.

    All changed setpoint groups are validated before any action is sent, and so is the
    airway rule: at most one module's ``airway_device`` connected, and none connecting
    in the update in which another disconnects (BioGears would process the new device
    before the old one's removal and fail every step).

    The engine loads ``state_file`` (a name in ``<runtime>/states`` or the package's
    ``states/``, or an absolute path), or ``patient_file``/``conditions`` stabilized and
    cached (``viva_biogears.patients``). A state saved mid-run carries its actions; each
    setpoint group starts at the state's values (``ActionBinding.loaded``), so a branch
    with the same setpoints continues the run exactly and one that differs sends the
    change. A state whose airway is held by a device the process doesn't control is
    refused when the process can connect one. ``save_state_times_s`` saves the engine
    at those times (``viva_biogears.states``).
    """

    config_schema = _config_schema()

    def __init__(self, config=None, core=None):
        super().__init__(config=config, core=core)
        names = list(self.config["modules"])
        if not names:
            raise ValueError(f"modules is empty; choose from {sorted(MODULES)}")
        unknown = [n for n in names if n not in MODULES]
        if unknown:
            raise ValueError(f"unknown modules {unknown}; available: {sorted(MODULES)}")
        if len(set(names)) != len(names):
            raise ValueError(f"modules listed twice: {names}")
        self._modules = [MODULES[n] for n in names]
        check_start(self.config)
        if self.config["circuit_additions"]:
            resolve_state(self.config)  # edits the state now, so a bad addition fails at construction
        for module in self._modules:
            if module.check_config:
                module.check_config(self.config)
        # A module whose outputs depend on the state reads it now (it needs the runtime).
        outputs = {m.name: m.outputs for m in self._modules}
        if any(m.prepare for m in self._modules):
            _, path = resolve_state(self.config)
            state = read_state(path)
            for m in self._modules:
                if m.prepare:
                    outputs[m.name] = m.prepare(self.config, state, names)
                    check_outputs(m.name, outputs[m.name])
        self._requests = []
        index: dict[tuple, int] = {}
        self._slots: list[tuple[tuple[str, ...], int, bool]] = []
        for module in self._modules:
            for request in outputs[module.name]:
                key = request.key()
                if key not in index:
                    index[key] = len(self._requests)
                    self._requests.append(request)
                self._slots.append(((module.name, *request.path), index[key], request.negate))
        self._applied = {(m.name, i): dict(b.ports) for m in self._modules for i, b in enumerate(m.bindings)}
        self._engine = None
        self._alive = True
        self._saver = saver_from_config(self.config)
        # Timed one-shot actions of all modules, in time order: (time s, module, xml).
        self._schedule = sorted(((float(t), m.name, xml) for m in self._modules if m.schedule
                                 for t, xml in m.schedule(self.config)), key=lambda e: e[0])

    # -- ports -------------------------------------------------------------
    def inputs(self):
        return {"setpoints": {m.name: {port: {"_type": "overwrite[float]", "_default": default}
                                       for b in m.bindings for port, default in b.ports.items()}
                              for m in self._modules if m.bindings}}

    def outputs(self):
        ports = _nest([(path, "overwrite[float]") for path, _, _ in self._slots])
        ports["irreversible_state"] = "boolean"
        return ports

    def initial_state(self):
        state = self.read()
        state["irreversible_state"] = False
        return state

    # -- engine --------------------------------------------------------------
    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine
        runtime, path = resolve_state(self.config)
        if any(b.action_types == ("SubstanceCompoundInfusionData",) for m in self._modules for b in m.bindings):
            check_compound(runtime, self.config["iv_compound"])
        state = read_state(path)
        # A state saved mid-run carries its actions: start each setpoint group at the
        # state's values (None: unknown, sent on the first update whatever its value).
        for m in self._modules:
            for i, b in enumerate(m.bindings):
                values = b.loaded_values(state, self.config)
                self._applied[(m.name, i)] = None if values is None else {p: float(values[p]) for p in b.ports}
        if state.airway_mode != "Free" and any(m.airway_device for m in self._modules):
            ours = [m.name for m in self._modules if m.airway_device and self._device_connected(m)]
            if not ours:
                raise ValueError(f"the loaded state's airway is held by {state.airway_mode}, which this process "
                                 "doesn't control; BioGears allows one airway device, so connecting "
                                 f"{[m.name for m in self._modules if m.airway_device]} would fail every step")
        engine = load_engine(runtime, path, [r.key() for r in self._requests], self.config["time_step_s"])
        self._engine = engine
        # A run from a saved state skips the timed actions before its step. One due at its step
        # is kept: the saving run sent it at the start of the next update, after the save. (One
        # due between that run's last two updates was sent after the save too, but where its
        # updates fell isn't known here, so it is skipped.)
        if self._schedule:
            start, step_s = engine_step(engine), engine.time_step_s
            self._schedule = [e for e in self._schedule if first_step_at_or_after(e[0], step_s) >= start]
        if self._saver:
            self._saver(engine)
        values = self._pull()
        loaded = _nest([(path_, values[i]) for path_, i, _ in self._slots])
        for m in self._modules:
            if m.check_loaded:
                m.check_loaded(loaded[m.name])
        return engine

    def _pull(self) -> list[float]:
        """Current readings in request order (negated where the request says); an
        unexpected NaN raises, naming the request."""
        raw = [float(v) for v in self._engine.pull()[1:]]
        bad = [r.label() for r, v in zip(self._requests, raw) if math.isnan(v) and not r.allow_nan]
        if bad:
            raise ValueError("BioGears returned NaN for: " + ", ".join(bad))
        return raw

    def read(self) -> dict[str, Any]:
        """The current readings, nested per module."""
        self._ensure_engine()
        values = self._pull()
        return _nest([(path, -values[i] if neg else values[i]) for path, i, neg in self._slots])

    def _bleed_rate(self):
        for values in self._applied.values():
            if values and "hemorrhage_rate_mL_per_min" in values:
                return values["hemorrhage_rate_mL_per_min"]
        return None

    def _apply_setpoints(self, state):
        # Validate every changed group before sending any action, so an invalid
        # setpoint never leaves the engine with only part of an update applied.
        changed = []
        for m in self._modules:
            for i, b in enumerate(m.bindings):
                values = {port: float(state["setpoints"][m.name][port]) for port in b.ports}
                previous = self._applied[(m.name, i)]
                if values != previous:
                    if b.validate:
                        b.validate(values, self.config)
                    if b.check_transition:
                        b.check_transition(previous, values)
                    changed.append(((m.name, i), b, values))
        self._check_airway(state)
        for key, b, values in changed:
            self._engine.process_actions(b.build(values, self.config))
            self._applied[key] = values

    def events(self) -> list[tuple[float, str, bool]]:
        """BioGears' patient events so far (time s, event name, active), e.g.
        ``(98760.0, "SevereSepsis", True)``; the latest ones (pybiogears keeps a bounded log)."""
        if self._engine is None:
            return []
        return [(float(e.sim_time_s), str(e.event), bool(e.active)) for e in self._engine.events]

    def _send_due(self) -> None:
        """Send the timed actions due at the start of this update: those whose first step at
        or after their time has been reached (BioGears' clock drifts off the exact time)."""
        if not self._schedule:
            return
        now, step_s = engine_step(self._engine), self._engine.time_step_s
        due = [e for e in self._schedule if first_step_at_or_after(e[0], step_s) <= now]
        if due:
            self._engine.process_actions([xml for _, _, xml in due])
            self._schedule = self._schedule[len(due):]

    def _device_connected(self, m) -> bool:
        """Whether module ``m``'s airway device is connected as far as the process knows
        (an unknown group, None, counts as connected)."""
        i = next(i for i, b in enumerate(m.bindings) if m.airway_device in b.ports)
        applied = self._applied[(m.name, i)]
        return applied is None or applied[m.airway_device] == 1.0

    def _check_airway(self, state):
        devices = [(m.name, self._device_connected(m), float(state["setpoints"][m.name][m.airway_device]) == 1.0)
                   for m in self._modules if m.airway_device is not None]
        now = [name for name, _, connected in devices if connected]
        if len(now) > 1:
            raise ValueError(f"only one airway device can be connected at a time, got {now}")
        before = [name for name, connected, _ in devices if connected]
        for name in now:
            others = [o for o in before if o != name]
            if name not in before and others:
                raise ValueError(f"{name} cannot connect in the same update that {others[0]} disconnects; "
                                 f"disconnect {others[0]} one update earlier")

    def update(self, state, interval):
        self._ensure_engine()
        if not self._alive:
            return {}
        self._apply_setpoints(state)
        self._send_due()
        if not advance(self._engine, interval, self._bleed_rate()):
            self._alive = False
            return {"irreversible_state": True}
        if self._saver:
            self._saver(self._engine)
        return self.read()


class BioGearsCircuitProcess(BioGearsModularProcess):
    """Deprecated name of :class:`BioGearsModularProcess` (it runs the whole engine, not
    only its circuits); documents with ``address: local:BioGearsCircuitProcess`` still run."""

    def __init__(self, config=None, core=None):
        import warnings
        warnings.warn("BioGearsCircuitProcess is now BioGearsModularProcess", DeprecationWarning, stacklevel=2)
        super().__init__(config, core=core)
