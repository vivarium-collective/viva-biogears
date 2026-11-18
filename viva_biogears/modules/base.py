"""Declarative description of one BioGears circuit family as process-bigraph ports.

A ``Module`` names the BioGears data requests that become its output ports
and the BioGears actions that its setpoint input ports drive. It computes nothing:
``BioGearsModularProcess`` turns the selected modules into ports, requests and
actions against one real BioGears engine. Circuit nodes and paths are read directly,
so no module edits the state, and actions are BioGears scenario XML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

# Top-level port names of BioGearsModularProcess that a module name must not shadow.
RESERVED_NAMES = frozenset({"setpoints", "irreversible_state"})

#: pybiogears DataRequest categories (pybiogears ``BioGearsThunk::set_requests``).
CATEGORIES = frozenset({"Physiology", "Patient", "Environment", "Equipment", "Substance",
                        "LiquidCompartment", "GasCompartment", "TissueCompartment",
                        "ThermalCompartment", "FluidPath", "FluidNode"})


@dataclass(frozen=True)
class Request:
    """One BioGears data request, emitted at ``path`` inside its module's port tree.

    ``category`` is a pybiogears DataRequest category (``CATEGORIES``); ``unit`` is
    BioGears' unit string ("" for unitless). ``compartment`` is a compartment,
    circuit node or circuit path name; ``substance`` a substance name.

    ``negate`` reports the negative (BioGears stores some pressures as negative
    sources). ``allow_nan`` marks a value BioGears leaves NaN in some states (total
    blood volume lost before the first bleed); any other NaN raises, naming the request.
    """

    path: tuple[str, ...]
    category: str
    property: str
    unit: str = ""
    compartment: str = ""
    substance: str = ""
    negate: bool = False
    allow_nan: bool = False

    def __post_init__(self):
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown data request category {self.category!r}")

    def key(self) -> tuple:
        """Identity of the underlying BioGears request; equal keys share one request."""
        return (self.category, self.property, self.unit, self.compartment, self.substance)

    def as_tuple(self) -> tuple:
        return self.key()

    def label(self) -> str:
        where = ".".join(x for x in (self.compartment, self.substance) if x)
        return f"{self.category}:{where + '.' if where else ''}{self.property}"


@dataclass(frozen=True)
class ActionBinding:
    """A group of setpoint ports forwarded to BioGears as one action.

    ``ports`` maps each port name to its baseline value (the value at which no
    action is needed). Whenever any port in the group changes, ``build`` is called
    with every port's current value plus the process config and returns the
    BioGears action XML (one ``<Action>``, or several concatenated). ``validate``
    raises ``ValueError`` on bad values; ``check_transition(previous, values)``
    raises ``ValueError`` on a change BioGears cannot make. ``action_types`` are the
    BioGears action types (``xsi:type``) ``build`` sends.

    ``loaded(state, config)`` reads, from the parsed starting state
    (``viva_biogears.modules.state.StateInfo``), the values the group already has
    there: a state saved mid-run carries its bleed, infusion, ventilator, ... So a
    branch whose setpoints equal them sends nothing and continues the run exactly, and
    one that differs sends the change. It returns the values (the baselines when
    nothing is active), None when the state's values can't be read (the group is then
    sent on the first update whatever its value), or raises ``ValueError`` for an active
    action the group can't address (a bleed in another compartment). A group without
    ``loaded`` whose action type is active in the state is treated as None.
    """

    ports: dict[str, float]
    build: Callable[[dict[str, float], dict[str, Any]], str]
    action_types: tuple[str, ...]
    validate: Callable[[dict[str, float], dict[str, Any]], None] | None = None
    check_transition: Callable[[dict[str, float], dict[str, float]], None] | None = None
    loaded: Callable[[Any, dict[str, Any]], dict[str, float] | None] | None = None

    def loaded_values(self, state, config) -> dict[str, float] | None:
        if self.loaded is not None:
            return self.loaded(state, config)
        if set(self.action_types) & set(state.active_actions):
            return None
        return dict(self.ports)


def check_outputs(module: str, outputs: tuple[Request, ...]) -> None:
    """Output paths must be unique, and none may be a prefix of another."""
    paths = [r.path for r in outputs]
    if len(set(paths)) != len(paths):
        raise ValueError(f"{module}: duplicate output paths")
    ordered = sorted(paths)
    for a, b in zip(ordered, ordered[1:]):
        if b[: len(a)] == a:
            raise ValueError(f"{module}: output path {a} is a prefix of {b}")


def validate_switch(port: str, value: float) -> None:
    """A 0/1 setpoint."""
    if value not in (0.0, 1.0):
        raise ValueError(f"{port} must be 0 or 1, got {value}")


def check_fraction(port: str, value: float, *, zero: bool = False) -> None:
    lo_ok = value >= 0.0 if zero else value > 0.0
    if not (lo_ok and value <= 1.0):
        raise ValueError(f"{port} must be in {'[' if zero else '('}0, 1], got {value}")


def check_nonnegative(port: str, value: float) -> None:
    if not (value >= 0.0 and value != float("inf")):
        raise ValueError(f"{port} must be a finite number >= 0, got {value}")


@dataclass(frozen=True)
class Module:
    """One part of BioGears exposed as ports: its outputs, its setpoint bindings, its config params.

    ``params`` are ``config_schema`` entries that ``BioGearsModularProcess`` exposes,
    and ``check_config`` validates them, raising ``ValueError``. ``check_loaded``
    receives the module's readings (nested like its outputs) once the engine is
    loaded, and raises ``ValueError`` if the loaded state contradicts the module's
    setpoint baselines. ``airway_device`` names the module's 0/1 setpoint that is 1
    while its equipment occupies BioGears' airway: BioGears allows one airway device
    at a time (``BioGears::SetAirwayMode``).

    ``schedule(config)`` returns timed actions, ``(simulation time in s, action XML)``:
    one-shot actions such as a meal, which no setpoint can describe. The process sends
    each at the first update that starts at or after its time; a run starting from a
    saved state skips the ones before its own time (they happened before the save).

    A module whose outputs depend on the starting state or the config sets
    ``prepare`` instead of ``outputs``: ``prepare(config, state, modules)`` gets the
    parsed state (``viva_biogears.modules.state.StateInfo``) and the names of all
    modules on the process, and returns the outputs. Nothing is edited.
    """

    name: str
    description: str = ""
    outputs: tuple[Request, ...] = ()
    bindings: tuple[ActionBinding, ...] = ()
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    check_config: Callable[[dict[str, Any]], None] | None = None
    check_loaded: Callable[[dict[str, Any]], None] | None = None
    airway_device: str | None = None
    prepare: Callable[[dict[str, Any], Any, list[str]], tuple[Request, ...]] | None = None
    schedule: Callable[[dict[str, Any]], list[tuple[float, str]]] | None = None

    def __post_init__(self):
        if self.name in RESERVED_NAMES:
            raise ValueError(f"circuit module name {self.name!r} is reserved")
        if self.prepare is not None and self.outputs:
            raise ValueError(f"{self.name}: a module with prepare declares no static outputs")
        check_outputs(self.name, self.outputs)
        ports = [p for b in self.bindings for p in b.ports]
        if len(set(ports)) != len(ports):
            raise ValueError(f"{self.name}: duplicate setpoint ports")
        if self.airway_device is not None and self.airway_device not in ports:
            raise ValueError(f"{self.name}: airway_device {self.airway_device!r} is not a setpoint port")

    @property
    def requests(self) -> tuple[Request, ...]:
        """Static outputs (empty for a ``prepare`` module)."""
        return self.outputs


def port_units(unit: str) -> str | None:
    """The bigraph-schema (pint) units for a BioGears unit string, or None if pint has
    no such unit (e.g. BioGears' ``clo``) or the request is unitless.

    The two grammars differ: BioGears puts everything after the ``/`` in the
    denominator (``L/min m^2`` is L/(min m^2)) and writes counts as ``ct``, while pint
    reads left to right (``L/min m^2`` would be L m^2/min) and ``ct`` is the carat. The
    type grammar (``float[...]``) has no parentheses, so the denominator is chained:
    ``L/min/m^2``.
    """
    if not unit:
        return None
    from bigraph_schema.units import units as registry

    num, slash, den = re.sub(r"\bct\b", "count", unit).partition("/")
    translated = f"{num}/{'/'.join(den.split())}" if slash else num
    try:
        registry.Unit(translated)
    except Exception:  # noqa: BLE001 - not a pint unit: leave the port without units
        return None
    return translated


def scalar(tag: str, value: float, unit: str = "") -> str:
    """``<tag value=".." unit=".."/>``, BioGears' scalar XML."""
    u = f' unit="{unit}"' if unit else ""
    return f'<{tag} value="{float(value)!r}"{u}/>'


def __getattr__(name):
    if name == "CircuitModule":           # the class's former name
        import warnings
        warnings.warn("CircuitModule is now Module", DeprecationWarning, stacklevel=2)
        return Module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
