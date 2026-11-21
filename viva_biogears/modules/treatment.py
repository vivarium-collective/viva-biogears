"""``treatment``: timed IV treatment (fluid boluses, antibiotics, vasopressors), for
McDaniel et al. 2019's treatment experiments (Figs 9-13).

Config ``treatment_schedule``, a list of events sent at the first update at or after
their time (``Module.schedule``), each one of:

- a compound infusion (``SubstanceCompoundInfusion``):
  ``{"hour": h, "compound": "Saline", "bag_volume_mL": 500, "rate_mL_per_min": 50}``.
  A bag ends by itself when it is empty, so a bolus is one event; ``rate_mL_per_min``
  0 stops it early. The compound is a BioGears compound file (``Saline``,
  ``PiperacillinTazobactam``, ``RingersLactate``, ...).
- a substance infusion (``SubstanceInfusion``):
  ``{"hour": h, "substance": "Norepinephrine", "concentration_ug_per_mL": 14,
  "rate_mL_per_min": 1.0}``. It runs until a later event for the same substance changes
  its rate; rate 0 stops it.

BioGears keeps one infusion per compound and one per substance, so a later event for the
same one replaces it. Readings: ``antibiotic_activity_per_hr`` (BioGears'
``AntibioticActivity``: the reduction of the bacterial growth rate, 0 without an
antibiotic or an infection) and, for each substance in config ``treatment_readouts``
(e.g. ``["Piperacillin", "Norepinephrine"]``), its plasma and blood concentration and
the area under its plasma concentration curve, under ``<substance>/``. They read NaN in
the loaded state and 0 from the first update until the substance is given. (Asking for a substance before it is given activates it in
BioGears; results change at the 1e-13 level.)

Setpoint ``vasopressor_rate_ug_per_min``: a substance infusion of config
``vasopressor_substance`` (Norepinephrine) from a syringe of
``vasopressor_concentration_ug_per_mL`` (14, as in BioGears' sepsis treatment scenario),
for controllers that start, change and stop a vasopressor (``TreatmentController``).
Rate 0 stops it.

The cardiovascular module's ``iv_rate_mL_per_min`` setpoint infuses ``iv_compound`` too.
If the schedule infuses that same compound, the setpoint must stay 0 (one infusion per
compound: a setpoint change would replace the scheduled bolus), and a state saved
mid-bolus is handed to this module rather than to the setpoint (``loaded_infusion``). The
same holds for the vasopressor setpoint and a scheduled infusion of the same substance.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .base import ActionBinding, Module, Request, check_nonnegative, scalar
from .state import scalar as state_scalar
from .state import text as state_text

_COMPOUND_KEYS = {"hour", "compound", "bag_volume_mL", "rate_mL_per_min"}
_SUBSTANCE_KEYS = {"hour", "substance", "concentration_ug_per_mL", "rate_mL_per_min"}
_NAME = re.compile(r"<Name>\s*([^<]+?)\s*</Name>")


@lru_cache(maxsize=4)
def _substance_files(substances_dir: str) -> tuple[frozenset[str], frozenset[str]]:
    """(substance names, compound names) defined in ``<runtime>/substances``. A substance is
    named by its file's ``<Name>`` (Caffeine.xml defines "Caffine"), a compound by its file."""
    substances, compounds = set(), set()
    for p in Path(substances_dir).glob("*.xml"):
        head = p.read_text(errors="ignore")[:4000]
        if "<SubstanceCompound" in head:
            compounds.add(p.stem)
        elif "<Substance" in head and (m := _NAME.search(head)):
            substances.add(m.group(1))
    return frozenset(substances), frozenset(compounds)


def _known(config: dict[str, Any]) -> tuple[frozenset[str], frozenset[str]]:
    from ..tables import engine_runtime
    return _substance_files(str(engine_runtime(config) / "substances"))


def scheduled_compounds(config: dict[str, Any]) -> set[str]:
    """The compounds the treatment schedule infuses."""
    return {e["compound"] for e in config.get("treatment_schedule") or [] if isinstance(e, dict) and "compound" in e}


def compound_infusion_xml(compound: str, bag_volume_mL: float, rate_mL_per_min: float) -> str:
    return ('<Action xsi:type="SubstanceCompoundInfusionData">'
            f"<SubstanceCompound>{escape(compound)}</SubstanceCompound>"
            + scalar("BagVolume", bag_volume_mL, "mL") + scalar("Rate", rate_mL_per_min, "mL/min") + "</Action>")


def substance_infusion_xml(substance: str, concentration_ug_per_mL: float, rate_mL_per_min: float) -> str:
    return ('<Action xsi:type="SubstanceInfusionData">'
            f"<Substance>{escape(substance)}</Substance>"
            + scalar("Concentration", concentration_ug_per_mL, "ug/mL")
            + scalar("Rate", rate_mL_per_min, "mL/min") + "</Action>")


def _number(name, key, value, *, positive=False):
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if not ok or value < 0 or (positive and value == 0):
        raise ValueError(f"{name}: {key} must be a finite number {'> 0' if positive else '>= 0'}, got {value!r}")


def _check_config(config: dict[str, Any]) -> None:
    schedule, readouts = config["treatment_schedule"], config["treatment_readouts"]
    substances, compounds = _known(config)
    if config["vasopressor_substance"] not in substances:
        raise ValueError(f"vasopressor_substance {config['vasopressor_substance']!r} is not a BioGears substance")
    for i, event in enumerate(schedule):
        name = f"treatment_schedule[{i}]"
        if not isinstance(event, dict) or set(event) not in (_COMPOUND_KEYS, _SUBSTANCE_KEYS):
            raise ValueError(f"{name} must have the keys {sorted(_COMPOUND_KEYS)} (a compound) or "
                             f"{sorted(_SUBSTANCE_KEYS)} (a substance), got {event!r}")
        _number(name, "hour", event["hour"])
        _number(name, "rate_mL_per_min", event["rate_mL_per_min"])
        if "compound" in event:
            if event["compound"] not in compounds:
                raise ValueError(f"{name}: {event['compound']!r} is not a BioGears compound; available: "
                                 f"{sorted(compounds)}")
            _number(name, "bag_volume_mL", event["bag_volume_mL"], positive=True)
        else:
            if event["substance"] not in substances:
                raise ValueError(f"{name}: {event['substance']!r} is not a BioGears substance")
            _number(name, "concentration_ug_per_mL", event["concentration_ug_per_mL"], positive=True)
    for s in readouts:
        if s not in substances:
            raise ValueError(f"treatment_readouts: {s!r} is not a BioGears substance")
    if len(set(readouts)) != len(readouts):
        raise ValueError(f"treatment_readouts lists a substance twice: {readouts}")
    _number("vasopressor", "vasopressor_concentration_ug_per_mL", config["vasopressor_concentration_ug_per_mL"],
            positive=True)


VASOPRESSOR_BASELINE = {"vasopressor_rate_ug_per_min": 0.0}


def scheduled_substances(config: dict[str, Any]) -> set[str]:
    return {e["substance"] for e in config.get("treatment_schedule") or [] if isinstance(e, dict) and "substance" in e}


def _validate_vasopressor(values, config):
    check_nonnegative("vasopressor_rate_ug_per_min", values["vasopressor_rate_ug_per_min"])
    if values["vasopressor_rate_ug_per_min"] != 0.0 and config["vasopressor_substance"] in scheduled_substances(config):
        raise ValueError(f"vasopressor_rate_ug_per_min must stay 0: the treatment schedule infuses "
                         f"{config['vasopressor_substance']!r} too, and BioGears keeps one infusion per substance")


def _build_vasopressor(values, config):
    conc = config["vasopressor_concentration_ug_per_mL"]
    return substance_infusion_xml(config["vasopressor_substance"], conc, values["vasopressor_rate_ug_per_min"] / conc)


def _loaded_vasopressor(state, config):
    """The vasopressor infusion the state carries, unless the schedule owns that substance."""
    sub = config["vasopressor_substance"]
    if sub in scheduled_substances(config):
        return dict(VASOPRESSOR_BASELINE)
    for kind, el in state.actions:
        if kind == "SubstanceInfusionData" and state_text(el, "Substance") == sub:
            rate, conc = state_scalar(el, "Rate", "mL/min"), state_scalar(el, "Concentration", "ug/mL")
            if rate is None or conc is None:
                return None
            return {"vasopressor_rate_ug_per_min": rate * conc}
    return dict(VASOPRESSOR_BASELINE)


def _schedule(config):
    out = []
    for e in config["treatment_schedule"]:
        if "compound" in e:
            xml = compound_infusion_xml(e["compound"], e["bag_volume_mL"], e["rate_mL_per_min"])
        else:
            xml = substance_infusion_xml(e["substance"], e["concentration_ug_per_mL"], e["rate_mL_per_min"])
        out.append((float(e["hour"]) * 3600.0, xml))
    return out


def _outputs(config, state, modules) -> tuple[Request, ...]:
    out = [Request(("antibiotic_activity_per_hr",), "Physiology", "AntibioticActivity")]
    for s in config["treatment_readouts"]:
        # NaN in the loaded state (the substance isn't active yet), then 0 until it is given.
        out += [Request((s, "plasma_concentration_ug_per_mL"), "Substance", "PlasmaConcentration", "ug/mL",
                        substance=s, allow_nan=True),
                Request((s, "blood_concentration_ug_per_mL"), "Substance", "BloodConcentration", "ug/mL",
                        substance=s, allow_nan=True),
                Request((s, "area_under_curve_s_ug_per_mL"), "Substance", "AreaUnderCurve", "s ug/mL",
                        substance=s, allow_nan=True)]
    return tuple(out)


TREATMENT = Module(
    name="treatment",
    description="Timed IV treatment (treatment_schedule): compound boluses and infusions (saline, antibiotics) and "
                "substance infusions; setpoint: a vasopressor infusion rate; readings: antibiotic activity and the "
                "treatment_readouts substances' concentrations.",
    bindings=(ActionBinding(ports=dict(VASOPRESSOR_BASELINE), build=_build_vasopressor,
                            action_types=("SubstanceInfusionData",), validate=_validate_vasopressor,
                            loaded=_loaded_vasopressor),),
    params={"treatment_schedule": {"_type": "list", "_default": []},
            "treatment_readouts": {"_type": "list[string]", "_default": []},
            "vasopressor_substance": {"_type": "string", "_default": "Norepinephrine"},
            "vasopressor_concentration_ug_per_mL": {"_type": "float", "_default": 14.0}},
    check_config=_check_config,
    prepare=_outputs,
    schedule=_schedule,
)

__all__ = ["TREATMENT", "VASOPRESSOR_BASELINE", "compound_infusion_xml", "scheduled_compounds",
           "scheduled_substances", "substance_infusion_xml"]
