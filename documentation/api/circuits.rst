Circuit modules
===============

The declarative registry ``BioGearsCircuitProcess`` builds its ports from. A module
computes nothing: it names BioGears data requests (outputs) and the BioGears actions its
setpoints drive (inputs).

.. automodule:: viva_biogears.circuits
   :members: MODULES

.. automodule:: viva_biogears.circuits.base
   :members: Request, ActionBinding, CircuitModule

.. automodule:: viva_biogears.circuits.vitals

.. automodule:: viva_biogears.circuits.cardiovascular

.. automodule:: viva_biogears.circuits.respiratory

.. automodule:: viva_biogears.circuits.thermal

.. automodule:: viva_biogears.circuits.supplemental_oxygen

.. automodule:: viva_biogears.circuits.points

.. automodule:: viva_biogears.circuits.substances
   :members: every_substance_output, LIQUID_PROPERTIES, GAS_PROPERTIES, BODY_PROPERTIES, TISSUE_PROPERTIES, TISSUE_FLUID_PROPERTIES

.. automodule:: viva_biogears.circuits.lymph

.. automodule:: viva_biogears.circuits.sepsis

.. automodule:: viva_biogears.circuits.additions
   :members: add_paths, check_additions, added_state

.. automodule:: viva_biogears.circuits.state
   :members: read_state
