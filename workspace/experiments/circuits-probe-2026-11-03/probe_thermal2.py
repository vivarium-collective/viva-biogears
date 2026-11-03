import sys
sys.argv=["x","none"]
exec(open("probe_actions.py").read().split("case=sys.argv[1]")[0])
variants={
 "ex_btu": '<Action xsi:type="ThermalApplicationData" AppendToPrevious="true"><ActiveHeating><Power value="340" unit="BTU/hr"/><SurfaceAreaFraction value="1.0" unit="unitless"/></ActiveHeating></Action>',
 "W_unitless": '<Action xsi:type="ThermalApplicationData" AppendToPrevious="false"><ActiveHeating><Power value="500" unit="W"/><SurfaceAreaFraction value="1.0" unit="unitless"/></ActiveHeating></Action>',
 "W_nofrac": '<Action xsi:type="ThermalApplicationData" AppendToPrevious="false"><ActiveHeating><Power value="500" unit="W"/></ActiveHeating></Action>',
 "applied": '<Action xsi:type="ThermalApplicationData" AppendToPrevious="false"><AppliedTemperature><State>On</State><Temperature value="40" unit="degC"/><SurfaceAreaFraction value="1.0"/></AppliedTemperature></Action>',
}
for k,x in variants.items():
    e=eng(); act(e,x,k,120)
