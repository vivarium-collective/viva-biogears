import sys, pybiogears as pb
from viva_biogears.runtime import runtime_dir
rt = runtime_dir(); ts=float(sys.argv[1]); rate=float(sys.argv[2])
e = pb.BioGearsEngine(rt)
req=[("Physiology","MeanArterialPressure","mmHg"),("Physiology","BloodVolume","mL"),("Physiology","HeartRate","1/min"),("Physiology","CardiacOutput","L/min")]
e.set_requests([pb.DataRequest(*r) for r in req])
e.load_state(rt/"states"/"StandardMale@0s.xml", configuration=pb.configuration(rt, TimeStep=(ts,"s")))
e.process_actions(pb.actions.hemorrhage("RightLeg", rate))
t=0
while t < float(sys.argv[3]):
    e.advance(1.0); t+=1
    pass
    if t%60==0: print(t, [round(x,2) for x in e.pull()[1:]], flush=True)
print("done")
