"""BioGearsCircuitProcess: one BioGears engine exposing the selected circuit modules."""

from __future__ import annotations

import math
from typing import Any

from process_bigraph import Process

from ..circuits import MODULES
from ..circuits.base import check_outputs
from ..circuits.state import read_state
from ._bridge import advance, check_compound, load_engine, resolve_state


def _config_schema() -> dict[str, Any]:
    schema: dict[str, Any] = {
        "modules": {"_type": "list[string]", "_default": []},
        "state_file": {"_type": "string", "_default": "StandardMale@0s.xml"},
        "runtime_dir": {"_type": "string", "_default": ""},
    }
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


class BioGearsCircuitProcess(Process):
    """Bridge to one real BioGears 8.2.0 engine, exposing the selected circuit modules.

    ``config.modules`` names entries of ``viva_biogears.circuits.MODULES``. Each module
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
    ``states/``, or an absolute path). A state holding an active action that one of the
    process's setpoint groups sends is refused, and so is one whose airway is already
    held by a device while the process can connect one.
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
        sent = {t for m in self._modules for b in m.bindings for t in b.action_types}
        active = sorted(set(state.active_actions) & sent)
        if active:
            raise ValueError(f"state {path.name} has active {', '.join(active)}, which this process's "
                             "setpoints also drive, so their stores wouldn't describe it; start from a state "
                             "without them")
        if "IntubationData" in sent and state.intubation != "Off":
            raise ValueError(f"state {path.name} is intubated ({state.intubation}) while the respiratory "
                             "module's intubated setpoint starts at 0")
        if state.airway_mode != "Free" and any(m.airway_device for m in self._modules):
            raise ValueError(f"the loaded state's airway is held by {state.airway_mode}; BioGears allows one "
                             f"airway device, so connecting "
                             f"{[m.name for m in self._modules if m.airway_device]} would fail every step")
        engine = load_engine(runtime, path, [r.key() for r in self._requests])
        self._engine = engine
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
            if "hemorrhage_rate_mL_per_min" in values:
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

    def _check_airway(self, state):
        devices = []
        for m in self._modules:
            if m.airway_device is None:
                continue
            port = m.airway_device
            i = next(i for i, b in enumerate(m.bindings) if port in b.ports)
            devices.append((m.name, self._applied[(m.name, i)][port] == 1.0,
                            float(state["setpoints"][m.name][port]) == 1.0))
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
        if not advance(self._engine, interval, self._bleed_rate()):
            self._alive = False
            return {"irreversible_state": True}
        return self.read()
