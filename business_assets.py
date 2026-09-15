"""Business asset catalog. Acquisition and accounting schedules are not configured."""
from __future__ import annotations

BUSINESSES = (
    ('farm', 'Greenfield Farm', ('Irrigation system', 'Greenhouse equipment', 'Crop-management software licence')),
    ('fish_stall', 'Harbor Fish Stall', ('Refrigerated display counter', 'Ice-making machine', 'Cold-chain tracking software licence')),
    ('roastery', 'Copper Kettle Roastery', ('Coffee roasting machine', 'Commercial espresso machine', 'Exclusive coffee-blend licence')),
    ('garage', 'Tinker’s Garage', ('Vehicle lift', 'Diagnostic equipment', 'Vehicle-diagnostics software licence')),
    ('workshop', 'Ironworks Shop', ('Hydraulic metal press', 'Industrial welding equipment', 'Metalworking design licence')),
    ('solar_coop', 'Rooftop Solar Co-op', ('Rooftop solar panels', 'Battery storage bank', 'Energy-management software licence')),
    ('cannery', 'Meridian Cannery', ('Automated canning line', 'Sterilisation equipment', 'Food-preservation process licence')),
    ('machine_works', 'Bluecollar Machine Works', ('CNC milling machine', 'Precision testing equipment', 'Precision-tooling patent rights')),
    ('turbine_field', 'Windward Turbine Field', ('Wind turbines', 'Power conversion equipment', 'Wind-forecasting software licence')),
    ('generator', 'North Grid Plant', ('Generator unit', 'Heat-recovery equipment', 'Fixed-term electricity-generation rights')),
    ('relay_station', 'Signal Relay Station', ('Signal repeaters', 'Transmission antennas', 'Fixed-term spectrum-use rights')),
    ('freight_terminal', 'Atlas Freight Terminal', ('Container crane', 'Cargo sorting conveyor', 'Fixed-term terminal operating concession')),
    ('data_center', 'Node-7 Data Hub', ('Server racks', 'Cooling system', 'Acquired cloud-platform software')),
    ('solar_array', 'Helios Solar Array', ('Solar tracking equipment', 'Utility-scale inverters', 'Fixed-term grid-connection rights')),
    ('uplink_center', 'Orbital Uplink Center', ('Satellite dish array', 'Ground-control equipment', 'Fixed-term satellite bandwidth rights')),
)


def catalog():
    return [dict(id='asset_' + business_id + '_' + str(slot + 1), name=name,
                 businessId=business_id, businessName=business_name,
                 assetType='intangible' if slot == 2 else 'tangible',
                 accounting='Amortization' if slot == 2 else 'Depreciation',
                 iconIndex=index * 3 + slot, canCraft=False,
                 acquisition='Not configured', usefulLife=None, recordedValue=None)
            for index, (business_id, business_name, names) in enumerate(BUSINESSES)
            for slot, name in enumerate(names)]
