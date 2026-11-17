# Glossary

composite
: A process-bigraph simulation document: stores, processes wired to them, and an emitter.
  A *composite generator* (`biogears_hemorrhage`, ...) builds one from a few parameters.

setpoint
: An input port holding an intervention's value (a bleed rate, `connected`). It is sent to
  BioGears as an action only when it changes.

reading
: An output port holding a BioGears value, always equal to BioGears' own.

module
: A named set of readings and setpoints of one part of BioGears (`cardiovascular`, `lymph`,
  `infection`, ...), selected in `BioGearsModularProcess`'s `modules`. The engine always
  simulates every system; a module only chooses what becomes a port.

compartment
: A named group of circuit nodes that BioGears tracks volume, pressure and substances for
  (`Aorta`, `MuscleTissueExtracellular`).

node, path
: The elements of a circuit: a node holds a pressure (and volume, if compliant); a path
  between two nodes carries a flow through a resistance, compliance or source.

state, state file
: A saved BioGears engine (`StandardMale@0s.xml`). Every run starts from one.

stabilization
: BioGears' build of a body from a patient file, run at rest until it settles; its result is
  a state.

checkpoint, branch
: A state saved mid-run, and a run started from it.

MAP, CVP
: Mean arterial pressure, central venous pressure (mmHg).

irreversible state
: BioGears' declaration that the patient can't recover (at 50 % blood loss, for example);
  the engine stops advancing.
