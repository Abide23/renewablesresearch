import pandas as pd
import numpy as np

battery_capacity = 100          # MWh
hydrogen_capacity = 600         # Liters
starting_battery = 100          # MWh
starting_hydrogen = 50          # Liters
battery_charge_eff = 0.9
battery_discharge_eff = 0.85
electrolysis_eff = 0.7
hydrogen_fuel_eff = 0.6

df = pd.read_excel("powerdata.xlsx", header=9)

solar_column = 'Avg Solar Supply kwh'
demand_column = 'Total Demand (kWh) for all houses'

df['Solar Power'] = df[solar_column] / 1000
df['Demand'] = df[demand_column] / 1000
df['Net'] = df['Solar Power'] - df['Demand']

# Storage logic
batt = starting_battery
h2 = starting_hydrogen
batt_power = []
h2_power = []
batt_soc = []
h2_level = []

for net in df['Net']:
    if net > 0:  # Excess power
        # 1. Charge battery first
        charge = min(net, (battery_capacity - batt) / battery_charge_eff)
        batt += charge * battery_charge_eff
        net -= charge
        
        # 2. Make hydrogen with remaining
        h2_prod = min(net * 233 * electrolysis_eff, hydrogen_capacity - h2)
        h2 += h2_prod
        net -= h2_prod / (233 * electrolysis_eff)
        
        batt_power.append(charge)
        h2_power.append(h2_prod)
        
    else:  # Deficit
        net = abs(net)
        
        # 1. Discharge battery first
        discharge = min(net, batt * battery_discharge_eff)
        batt -= discharge / battery_discharge_eff
        net -= discharge
        
        # 2. Use hydrogen if still deficit
        h2_use = min(net / (0.0899 * 33.3 * hydrogen_fuel_eff), h2)
        h2 -= h2_use
        net -= h2_use * 0.0899 * 33.3 * hydrogen_fuel_eff
        
        batt_power.append(-discharge)
        h2_power.append(-h2_use * 0.0899 * 33.3 * hydrogen_fuel_eff)
    
    batt_soc.append(batt)
    h2_level.append(h2)

# Add results to dataframe
df['Battery Consumed (MW)'] = batt_power
df['Battery Level (MWh)'] = batt_soc
df['Hydrogen Power (MW)'] = h2_power
df['Hydrogen Stored (L)'] = h2_level

# Save new file
df.to_excel("output_with_storage.xlsx", index=False)
print("Done")
