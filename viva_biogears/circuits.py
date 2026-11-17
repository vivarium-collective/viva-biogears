"""Deprecated: the module declarations moved to :mod:`viva_biogears.modules`.

``import viva_biogears.circuits`` and ``from viva_biogears.circuits.<module> import ...``
keep working (each name is the same object as in ``viva_biogears.modules``) and warn.
"""
import importlib
import pkgutil
import sys
import warnings

from . import modules as _modules

warnings.warn("viva_biogears.circuits is now viva_biogears.modules", DeprecationWarning, stacklevel=2)

for _info in pkgutil.iter_modules(_modules.__path__):
    sys.modules[f"{__name__}.{_info.name}"] = importlib.import_module(f"{_modules.__name__}.{_info.name}")
sys.modules[__name__] = _modules
