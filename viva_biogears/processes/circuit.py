"""BioGearsCircuitProcess: BioGears with selectable readout modules (lymph, tissue fluid, vitals)."""

from __future__ import annotations

from typing import Any

from process_bigraph import Process

from ._bridge import (
    INTERVENTION_CONFIG,
    SETPOINTS,
    EngineBridge,
    check_intervention_config,
)


def _nest(paths_values) -> dict:
    out: dict[str, Any] = {}
    for path, value in paths_values:
        d = out
        for p in path[:-1]:
            d = d.setdefault(p, {})
        d[path[-1]] = value
    return out


class BioGearsCircuitProcess(Process):
    """BioGears 8.2.0 with the readout modules in ``config.modules``.

    The circuit sibling of ``BioGearsProcess``, as viva-pulse's ``PulseCircuitProcess`` is
    of ``PulseProcess``: the same engine handling, setpoints and output contract.

    Config
    ------
    modules : list[string]
        Names in ``viva_biogears.circuits.MODULES`` (``vitals``, ``lymph``,
        ``tissue_fluid``). An empty list raises: there is no sensible default.
    state_file, runtime_dir, hemorrhage_compartment, iv_compound, iv_bag_volume_L
        As ``BioGearsProcess``.

    Inputs
    ------
    interventions : {hemorrhage_rate_mL_per_min, iv_rate_mL_per_min} as overwrite[float]
        Setpoints, sent to BioGears only when they change (as ``BioGearsProcess``).

    Outputs
    -------
    One nested port per module, e.g. ``lymph/formation/muscle_mL_per_min``, every
    leaf ``overwrite[float]``: seeded with the loaded state's reading, then
    BioGears' current reading after each update. The only transformation is a
    sign: BioGears stores the plasma oncotic pressure as a negative pressure
    source, reported positive as ``plasma_oncotic_pressure_mmHg``.
    ``irreversible_state`` as ``BioGearsProcess``.
    """

    config_schema = {**INTERVENTION_CONFIG, "modules": {"_type": "list[string]", "_default": []}}

    def __init__(self, config=None, core=None):
        super().__init__(config=config, core=core)
        from ..circuits import MODULES
        check_intervention_config(self.config)
        mods = list(self.config["modules"])
        if not mods:
            raise ValueError(f"modules is empty; choose from {sorted(MODULES)}")
        unknown = [m for m in mods if m not in MODULES]
        if unknown:
            raise ValueError(f"unknown modules {unknown}; available: {sorted(MODULES)}")
        if len(set(mods)) != len(mods):
            raise ValueError(f"modules listed twice: {mods}")
        self._requests = [(name, req) for name in mods for req in MODULES[name].requests]
        self._bridge = EngineBridge(self.config, [req.as_tuple() for _, req in self._requests])

    def inputs(self):
        return {"interventions": {k: "overwrite[float]" for k in SETPOINTS}}

    def outputs(self):
        ports = _nest(((name, *req.path), "overwrite[float]") for name, req in self._requests)
        ports["irreversible_state"] = "boolean"
        return ports

    def initial_state(self):
        return {"interventions": {k: 0.0 for k in SETPOINTS}, **self.read(), "irreversible_state": False}

    def read(self) -> dict:
        """The current readings, nested per module."""
        values = self._bridge.values()
        return _nest(((name, *req.path), -v if req.negate else v)
                     for (name, req), v in zip(self._requests, values))

    def update(self, state, interval):
        if not self._bridge.alive:
            return {}
        self._bridge.apply(state["interventions"])
        if not self._bridge.advance(interval):
            return {"irreversible_state": True}
        return self.read()
