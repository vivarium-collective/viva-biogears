import os, sys
from pathlib import Path
import pybiogears as pb
RT = Path(os.environ["BIOGEARS_RUNTIME"])
REQ=[("Physiology","RespirationRate","1/min",""),("Physiology","TidalVolume","mL",""),("Physiology","OxygenSaturation","",""),
     ("Physiology","ArterialOxygenPressure","mmHg",""),("Physiology","CoreTemperature","degC",""),("Physiology","SkinTemperature","degC",""),
     ("Environment","Conditions-AmbientTemperature","degC",""),("Environment","Conditions-RelativeHumidity","",""),
     ("Equipment","VentilatorPressure","cmH2O",""),("GasCompartment","Pressure","cmH2O","Trachea"),
     ("Physiology","HeartRate","1/min",""),("Physiology","MeanArterialPressure","mmHg","")]
NAMES=["RR","VT","SpO2","PaO2","Tcore","Tskin","Tamb","RH","Vp","Ptrach","HR","MAP"]
def eng():
    e=pb.BioGearsEngine(RT); e.set_requests([pb.DataRequest(*r) for r in REQ]); e.load_state(RT/"states"/"StandardMale@0s.xml"); return e
def show(tag,e):
    v=e.pull()[1:]; print(f"{tag:40s}", " ".join(f"{n}={x:.4g}" for n,x in zip(NAMES,v)), "| airway:", getattr(e,'airway_mode',None))
def act(e,xml,tag,secs=60):
    try:
        e.process_actions(xml)
    except Exception as ex:
        print(tag,"process_actions raised",type(ex).__name__,ex); return
    n=len(e.log)
    try:
        e.advance(secs)
    except Exception as ex:
        print(tag,"advance raised",type(ex).__name__,str(ex)[:200])
    errs=[m.text[:160] for m in list(e.log)[n:] if m.level in ("Error","Fatal")] if hasattr(list(e.log)[0] if e.log else None,'level') else [str(m)[:160] for m in list(e.log)[n:]][:3]
    show(tag,e); 
    if errs: print("   log:",errs[:3])
AM=lambda conn,vp=12,peep=1,rr=12,o2=0.21: f'<Action xsi:type="AnesthesiaMachineConfigurationData"><Configuration><Connection>{conn}</Connection><InletFlow value="5" unit="L/min"/><InspiratoryExpiratoryRatio value="0.5"/><OxygenFraction value="{o2}"/><OxygenSource>Wall</OxygenSource><PositiveEndExpiredPressure value="{peep}" unit="cmH2O"/><PrimaryGas>Nitrogen</PrimaryGas><RespiratoryRate value="{rr}" unit="1/min"/><VentilatorPressure value="{vp}" unit="cmH2O"/></Configuration></Action>'
NC=lambda f: f'<Action xsi:type="NasalCannulaData"><FlowRate value="{f}" unit="L/min"/></Action>'
INT=lambda t: f'<Action xsi:type="IntubationData" Type="{t}"/>'
case=sys.argv[1]
e=eng(); show("loaded",e)
if case=="vent":
    act(e,INT("Tracheal"),"intubate")
    act(e,AM("Tube",vp=15,peep=5,rr=16,o2=0.5),"AM tube 15/5 rr16 o2 .5",120)
    act(e,AM("Off"),"AM off",60)
    act(e,INT("Off"),"extubate",60)
    act(e,AM("Mask",vp=15,peep=5,rr=16,o2=0.5),"AM mask",60)
elif case=="o2":
    act(e,NC(4),"cannula 4",120)
    act(e,AM("Mask"),"AM mask while cannula",10)
    act(e,NC(0),"cannula 0",60)
    act(e,NC(6),"cannula 6",60)
elif case=="o2b":
    act(e,NC(4),"cannula 4",60)
    act(e,NC(0),"cannula 0",60)
    act(e,NC(6),"cannula 6",60)
    act(e,NC(0),"cannula 0",30)
    act(e,AM("Mask",o2=0.6),"AM mask after cannula",60)
    act(e,AM("Off"),"AM off",30)
    act(e,NC(3),"cannula 3 after AM",60)
elif case=="swap":
    act(e,AM("Mask",o2=0.6),"AM mask",30)
    e.process_actions(AM("Off")); e.process_actions(NC(4)); act(e,NC(4),"AM off + cannula same step",30)
elif case=="thermal":
    act(e,'<Action xsi:type="EnvironmentChangeData"><Conditions><AmbientTemperature value="5" unit="degC"/></Conditions></Action>',"amb 5C partial",300)
    act(e,'<Action xsi:type="ThermalApplicationData" AppendToPrevious="false"><ActiveHeating><Power value="500" unit="W"/><SurfaceAreaFraction value="1.0"/></ActiveHeating></Action>',"heat 500W",300)
    act(e,'<Action xsi:type="ThermalApplicationData" AppendToPrevious="false"><ActiveHeating><Power value="0" unit="W"/><SurfaceAreaFraction value="1.0"/></ActiveHeating></Action>',"heat 0W",60)
    act(e,'<Action xsi:type="ThermalApplicationData" AppendToPrevious="false"><AppliedTemperature State="On"><Temperature value="40" unit="degC"/><SurfaceAreaFraction value="1.0"/></AppliedTemperature></Action>',"applied 40C",300)
    act(e,'<Action xsi:type="ThermalApplicationData" AppendToPrevious="false"><AppliedTemperature State="Off"><Temperature value="40" unit="degC"/><SurfaceAreaFraction value="1.0"/></AppliedTemperature></Action>',"applied off",60)
