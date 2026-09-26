import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows

battery_capacity = 100          # MWh
hydrogen_capacity = 200000   # Liters
starting_battery = 100          # MWh
starting_hydrogen = 0          # Liters
battery_charge_eff = 0.9
battery_discharge_eff = 0.85
electrolysis_eff = 0.7
hydrogen_fuel_eff = 0.6

liters_per_mwh = 1000          # Your approximation: 1 MWh = 1 m³ H2

filename = "Calculations-Efficiencies-new.xlsx"
source_sheet = "Elctric-NoGas"
output_sheet = "Python Storage Results"

wb = load_workbook(filename)

if output_sheet in wb.sheetnames:
    del wb[output_sheet]
    wb.save(filename)
    
df = pd.read_excel(filename, header=9, sheet_name=source_sheet)

renewable_column = 'Total Renewable Supply  (kWh)'
demand_column = 'Total Demand (kWh) for all houses'

df['Renewable Power (MW)'] = df[renewable_column] / 1000
df['Demand (MW)'] = df[demand_column] / 1000
df['Net (MW)'] = df['Renewable Power (MW)'] - df['Demand (MW)']

batt = starting_battery
h2 = starting_hydrogen
batt_power = []
h2_power = []
batt_soc = []
h2_level = []
hourly_deficit = []

for net in df['Net (MW)']:
    if net > 0:
        charge = min(net, (battery_capacity - batt) / battery_charge_eff)
        batt += charge * battery_charge_eff
        net -= charge

        h2_prod = min(net * liters_per_mwh * electrolysis_eff,
                      hydrogen_capacity - h2)
        h2 += h2_prod
        h2_input = h2_prod / (liters_per_mwh * electrolysis_eff)

        batt_power.append(charge)
        h2_power.append(h2_input)
        hourly_deficit.append(0)
    else:
        net = abs(net)

        discharge = min(net, batt * battery_discharge_eff)
        batt -= discharge / battery_discharge_eff
        net -= discharge

        h2_use = min(net * liters_per_mwh / hydrogen_fuel_eff, h2)
        h2 -= h2_use
        h2_power_out = h2_use * hydrogen_fuel_eff / liters_per_mwh
        net -= h2_power_out

        batt_power.append(-discharge)
        h2_power.append(-h2_power_out)
        hourly_deficit.append(max(0, net))

    batt_soc.append(batt)
    h2_level.append(h2)

results_df = pd.DataFrame({
    'Hour': range(1, len(df) + 1),
    'Renewable Power (MW)': df['Renewable Power (MW)'],
    'Demand (MW)': df['Demand (MW)'],
    'Net (MW)': df['Net (MW)'],
    'Battery Power (MW)': batt_power,
    'Battery Level (MWh)': batt_soc,
    'Hydrogen Power (MW)': h2_power,
    'Hydrogen Stored (L)': h2_level,
    'Total Energy Stored (MWh)': [
        battery + hydrogen / liters_per_mwh
        for battery, hydrogen in zip(batt_soc, h2_level)
    ],
    'Remaining Deficit (MW)': hourly_deficit
})

ws = wb.create_sheet(output_sheet)

for row in dataframe_to_rows(results_df, index=False, header=True):
    ws.append(row)

for column in ws.columns:
    width = min(max(len(str(cell.value)) for cell in column) + 2, 30)
    ws.column_dimensions[column[0].column_letter].width = width


wb.save(filename)

final_energy = batt + h2 / liters_per_mwh
starting_energy = starting_battery + starting_hydrogen / liters_per_mwh
print(f"Starting stored energy: {starting_energy:.2f} MWh")
print(f"Ending stored energy: {final_energy:.2f} MWh")
print(f"Unmet demand: {sum(hourly_deficit):.2f} MWh")