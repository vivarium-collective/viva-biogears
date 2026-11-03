import sys
sys.argv=["x","none"]
exec(open("probe_actions.py").read().split("case=sys.argv[1]")[0])
def TA(hW,hf,cW,cf,on,T,af):
    return (f'<Action xsi:type="ThermalApplicationData" AppendToPrevious="false">'
            f'<ActiveHeating><Power value="{hW}" unit="W"/><SurfaceAreaFraction value="{hf}"/></ActiveHeating>'
            f'<ActiveCooling><Power value="{cW}" unit="W"/><SurfaceAreaFraction value="{cf}"/></ActiveCooling>'
            f'<AppliedTemperature><State>{on}</State><Temperature value="{T}" unit="degC"/><SurfaceAreaFraction value="{af}"/></AppliedTemperature></Action>')
e=eng()
act(e,TA(500,1,0,1,"Off",22,1),"heat 500",300)
act(e,TA(0,1,0,1,"Off",22,1),"all off",60)
act(e,TA(0,1,300,1,"Off",22,1),"cool 300",300)
act(e,TA(0,1,0,1,"On",40,1),"applied 40",300)
act(e,TA(0,1,0,1,"Off",40,1),"applied off",60)
e2=eng(); 
for i in range(10): e2.advance(60)
show("control 10 min",e2)
print("--- partial actions")
e3=eng()
act(e3,'<Action xsi:type="ThermalApplicationData" AppendToPrevious="false"><ActiveHeating><Power value="500" unit="W"/><SurfaceAreaFraction value="1.0"/></ActiveHeating></Action>',"heat only 500",300)
