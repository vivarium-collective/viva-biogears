"""Registry of BioGears circuit modules available to ``BioGearsCircuitProcess``.

A module is declarative (``base.CircuitModule``): the BioGears data requests that
become its output ports and the BioGears actions its setpoints drive. Modules
compute nothing. viva-pulse's ``viva_pulse.circuits`` is the model.
"""

from .base import ActionBinding, CircuitModule, Request
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

#: Every circuit module, by name: the values ``BioGearsCircuitProcess`` accepts in ``config.modules``.
MODULES: dict[str, CircuitModule] = {
    m.name: m for m in (VITALS_MODULE, CARDIOVASCULAR, RESPIRATORY, MECHANICAL_VENTILATOR, THERMAL,
                        SUPPLEMENTAL_OXYGEN, CARDIOVASCULAR_POINTS, RESPIRATORY_POINTS, SUBSTANCES,
                        TISSUE_READINGS, LYMPH, TISSUE_FLUID, INFECTION, NUTRITION, TREATMENT)
}

__all__ = ["ActionBinding", "CircuitModule", "HEMORRHAGE_COMPARTMENTS", "MODULES", "Request", "TISSUES", "VITALS"]
