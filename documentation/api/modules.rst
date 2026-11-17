Modules
=======

The declarative registry ``BioGearsModularProcess`` builds its ports from. A module
computes nothing: it names BioGears data requests (outputs) and the BioGears actions its
setpoints drive (inputs).

.. automodule:: viva_biogears.modules
   :members: MODULES

.. automodule:: viva_biogears.modules.base
   :members: Request, ActionBinding, CircuitModule

.. automodule:: viva_biogears.modules.vitals

.. automodule:: viva_biogears.modules.cardiovascular

.. automodule:: viva_biogears.modules.respiratory

.. automodule:: viva_biogears.modules.thermal

.. automodule:: viva_biogears.modules.supplemental_oxygen

.. automodule:: viva_biogears.modules.points

.. automodule:: viva_biogears.modules.substances
   :members: every_substance_output, LIQUID_PROPERTIES, GAS_PROPERTIES, BODY_PROPERTIES, TISSUE_PROPERTIES, TISSUE_FLUID_PROPERTIES

.. automodule:: viva_biogears.modules.lymph

.. automodule:: viva_biogears.modules.sepsis

.. automodule:: viva_biogears.modules.treatment

.. automodule:: viva_biogears.modules.additions
   :members: add_paths, check_additions, added_state

.. automodule:: viva_biogears.modules.state
   :members: read_state
