"""Registry of BioGears modules available to ``BioGearsModularProcess``.

A module is declarative (``base.Module``): the BioGears data requests that
become its output ports and the BioGears actions its setpoints drive. Modules
compute nothing.
"""

from .base import ActionBinding, Module, Request
from .cardiovascular import CARDIOVASCULAR, HEMORRHAGE_COMPARTMENTS
from .lymph import LYMPH, TISSUE_FLUID
from .lymph import TISSUES as LYMPH_TISSUES
from .points import CARDIOVASCULAR_POINTS, RESPIRATORY_POINTS
from .respiratory import MECHANICAL_VENTILATOR, RESPIRATORY
from .sepsis import INFECTION, NUTRITION
from .substances import SUBSTANCES
from .substances import TISSUES as TISSUE_READINGS
from .supplemental_oxygen import SUPPLEMENTAL_OXYGEN
from .thermal import THERMAL
from .treatment import TREATMENT
from .vitals import VITALS, VITALS_MODULE

#: Tissues with a lymph drainage path, as port keys -> BioGears names.
TISSUES = LYMPH_TISSUES

#: Every module, by name: the values ``BioGearsModularProcess`` accepts in ``config.modules``.
MODULES: dict[str, Module] = {
    m.name: m for m in (VITALS_MODULE, CARDIOVASCULAR, RESPIRATORY, MECHANICAL_VENTILATOR, THERMAL,
                        SUPPLEMENTAL_OXYGEN, CARDIOVASCULAR_POINTS, RESPIRATORY_POINTS, SUBSTANCES,
                        TISSUE_READINGS, LYMPH, TISSUE_FLUID, INFECTION, NUTRITION, TREATMENT)
}

__all__ = ["HEMORRHAGE_COMPARTMENTS", "MODULES", "TISSUES", "VITALS", "ActionBinding", "Module", "Request"]


def __getattr__(name):
    if name == "CircuitModule":           # the module class's former name
        from . import base
        return base.CircuitModule
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
