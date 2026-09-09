import pandas as pd
import numpy as np
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows

battery_capacity = 100          # MWh
hydrogen_capacity = 600000000         # Liters
starting_battery = 100          # MWh
starting_hydrogen = 0          # Liters
battery_charge_eff = 0.9
battery_discharge_eff = 0.85
electrolysis_eff = 0.7
hydrogen_fuel_eff = 0.6

filename = "Calculations-Efficiencies-new.xlsx"
source_sheet = "Elctric-NoGas"  # <-- CHANGE THIS to your source sheet name
output_sheet = "Python Storage Results"  # <-- Name of the new sheet

# Load the workbook to preserve formatting
wb = load_workbook(filename)

# Read data with pandas for calculations
df = pd.read_excel(filename, header=9, sheet_name=source_sheet)

solar_column = 'Total Renewable Supply  (kWh)'
demand_column = 'Total Demand (kWh) for all houses'

# Calculate power values
df['Renewable Power (MW)'] = df[solar_column] / 1000
df['Demand (MW)'] = df[demand_column] / 1000
df['Net (MW)'] = df['Renewable Power (MW)'] - df['Demand (MW)']

# Storage logic
batt = starting_battery
h2 = starting_hydrogen
batt_power = []
h2_power = []
batt_soc = []
h2_level = []
hourly_deficit = []

for net in df['Net (MW)']:
    if net > 0:  # Excess power
        # Charge battery first
        charge = min(net, (battery_capacity - batt) / battery_charge_eff)
        batt += charge * battery_charge_eff
        net -= charge
        
        # Make hydrogen with remaining
        h2_prod = min(net * 233 * electrolysis_eff, hydrogen_capacity - h2)
        h2 += h2_prod
        net -= h2_prod / (233 * electrolysis_eff)
        
        batt_power.append(charge)
        h2_power.append(h2_prod)
        hourly_deficit.append(0)  # No deficit when there's excess
        
    else:  # Deficit
        net = abs(net)
        initial_deficit = net
        
        # Discharge battery first
        discharge = min(net, batt * battery_discharge_eff)
        batt -= discharge / battery_discharge_eff
        net -= discharge
        
        # Use hydrogen if still deficit
        h2_use = min(net / (0.0899 * 33.3 * hydrogen_fuel_eff), h2)
        h2 -= h2_use
        h2_power_out = h2_use * 0.0899 * 33.3 * hydrogen_fuel_eff
        net -= h2_power_out
        
        batt_power.append(-discharge)
        h2_power.append(-h2_power_out)
        hourly_deficit.append(net)  # Remaining deficit after storage
    
    batt_soc.append(batt)
    h2_level.append(h2)

# Create a results dataframe with all the information
results_df = pd.DataFrame({
    'Hour': range(1, len(df) + 1),
    'Renewable Power (MW)': df['Renewable Power (MW)'],
    'Demand (MW)': df['Demand (MW)'],
    'Net (MW)': df['Net (MW)'],
    'Battery Power (MW)': batt_power,
    'Battery Level (MWh)': batt_soc,
    'Hydrogen Power (MW)': h2_power,
    'Hydrogen Stored (L)': h2_level,
    'Remaining Deficit (MW)': hourly_deficit
})

# Check if output sheet already exists and remove it
if output_sheet in wb.sheetnames:
    std = wb[output_sheet]
    wb.remove(std)
    print(f"Removed existing sheet '{output_sheet}'")

# Create new sheet
ws = wb.create_sheet(title=output_sheet)

# Write the dataframe to the new sheet
for r in dataframe_to_rows(results_df, index=False, header=True):
    ws.append(r)

# Auto-adjust column widths (optional)
for column in ws.columns:
    max_length = 0
    column_letter = column[0].column_letter
    for cell in column:
        try:
            if len(str(cell.value)) > max_length:
                max_length = len(str(cell.value))
        except:
            pass
    adjusted_width = min(max_length + 2, 30)  # Cap at 30 characters
    ws.column_dimensions[column_letter].width = adjusted_width

# Save the workbook (preserves all formatting in original sheets)
wb.save(filename)
print(f"Done! Created new sheet '{output_sheet}' with all storage data in {filename}")
print(f"Columns included: {list(results_df.columns)}")