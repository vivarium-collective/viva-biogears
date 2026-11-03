import json, os
from pathlib import Path
import pybiogears as pb
RT = Path(os.environ["BIOGEARS_RUNTIME"])
LIQ = ["Aorta","Heart","LeftHeart","RightHeart","LeftAtrium","LeftVentricle","RightAtrium","RightVentricle",
       "MyocardiumVasculature","Pericardium","VenaCava","PulmonaryArteries","PulmonaryCapillaries","PulmonaryVeins",
       "LungsVasculature","KidneyVasculature","LeftKidneyVasculature","RightKidneyVasculature","LeftRenalArtery","RightRenalArtery",
       "LeftGlomerularCapillaries","RightGlomerularCapillaries","LeftRenalVein","RightRenalVein",
       "BrainVasculature","CerebralArteries","CerebralCapillaries","CerebralVeins","NeckArteries","NeckVeins",
       "MuscleVasculature","SkinVasculature","FatVasculature","BoneVasculature","LiverVasculature","SpleenVasculature",
       "GutVasculature","SplanchnicVasculature","SmallIntestineVasculature","LargeIntestineVasculature",
       "LeftArmVasculature","RightArmVasculature","LeftLegVasculature","RightLegVasculature","Lymph","CerebralSpinalFluid","Bladder"]
GAS = ["Mouth","Trachea","LeftBronchi","RightBronchi","LeftLungPulmonary","RightLungPulmonary","PulmonaryLungs",
       "LeftAlveoli","RightAlveoli","LeftPleuralCavity","RightPleuralCavity","PleuralCavity","Stomach"]
TH = ["InternalCore","InternalTorsoSkin","InternalHeadSkin","ExternalCore","ExternalTorsoSkin","Clothing","Enclosure","Ambient","Active","ExternalGround","InternalGround"]
reqs=[]
for c in LIQ:
    for p,u in [("Pressure","mmHg"),("Volume","mL"),("InFlow","mL/min"),("OutFlow","mL/min")]: reqs.append(("LiquidCompartment",p,u,c))
for c in GAS:
    for p,u in [("Pressure","cmH2O"),("Volume","mL"),("InFlow","L/min"),("OutFlow","L/min")]: reqs.append(("GasCompartment",p,u,c))
for c in TH:
    for p,u in [("Temperature","degC"),("Heat","kJ"),("HeatTransferRateIn","W"),("HeatTransferRateOut","W")]: reqs.append(("ThermalCompartment",p,u,c))
env=["ConvectiveHeatLoss","ConvectiveHeatTranferCoefficient","EvaporativeHeatLoss","EvaporativeHeatTranferCoefficient","RadiativeHeatLoss","RadiativeHeatTranferCoefficient","RespirationHeatLoss","SkinHeatLoss"]
for p in env: reqs.append(("Environment",p,"W" if "Loss" in p else "W/m^2 K",""))
for p,u in [("AmbientTemperature","degC"),("MeanRadiantTemperature","degC"),("RespirationAmbientTemperature","degC"),("RelativeHumidity",""),("AirVelocity","m/s"),("ClothingResistance","clo"),("AtmosphericPressure","mmHg"),("Emissivity",""),("AirDensity","kg/m^3")]:
    reqs.append(("Environment","Conditions-"+p,u,""))
for p,u in [("InletFlow","L/min"),("InspiratoryExpiratoryRatio",""),("OxygenFraction",""),("PositiveEndExpiredPressure","cmH2O"),("ReliefValvePressure","cmH2O"),("RespiratoryRate","1/min"),("VentilatorPressure","cmH2O")]:
    reqs.append(("Equipment",p,u,""))
for p in ["InflammatoryResponse-TissueIntegrity","InflammatoryResponse-Interleukin6","InflammatoryResponse-LocalPathogen"]:
    reqs.append(("Physiology",p,"",""))
e=pb.BioGearsEngine(RT); e.set_requests([pb.DataRequest(*r) for r in reqs]); e.load_state(RT/"states"/"StandardMale@0s.xml"); e.advance(2.0)
v=e.pull()[1:]; unc={(r.category,r.compartment,r.property) for r in e.unconnected}
res=[]
for r,x in zip(reqs,v):
    res.append([*r, None if (r[0],r[3],r[1]) in unc else float(x)])
json.dump(res,open("compartments.json","w"),indent=0)
for r in res:
    if r[-1] is None or r[-1]!=r[-1] or abs(r[-1])==float("inf"): print("BAD",r)
