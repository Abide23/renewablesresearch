import pandas as pd
from openpyxl.chart import BarChart, LineChart, Reference

# Storage settings
battery_capacity = 100          # MWh
hydrogen_capacity = 158035  # Liters
starting_battery = 100           # MWh
starting_hydrogen = 0           # Liters

battery_charge_eff = 0.9
battery_discharge_eff = 0.85
electrolysis_eff = 0.7
hydrogen_fuel_eff = 0.6
liters_per_mwh = 1000           # Your 500-bar approximation

filename = "Calculations-Efficiencies-new.xlsx"
output_filename = "Storage-Results.xlsx"
source_sheet = "Elctric-NoGas"

renewable_column = "Total Renewable Supply  (kWh)"
demand_column = "Total Demand (kWh) for all houses"

# Read the original workbook without changing it.
df = pd.read_excel(filename, sheet_name=source_sheet, header=9)

df["Renewable Power (MW)"] = df[renewable_column] / 1000
df["Demand (MW)"] = df[demand_column] / 1000
df["Net (MW)"] = df["Renewable Power (MW)"] - df["Demand (MW)"]

if df["Net (MW)"].isna().any():
    raise ValueError(
        "Source supply or demand values are blank. Recalculate and save "
        "the original workbook in Excel or LibreOffice first."
    )

batt = starting_battery
h2 = starting_hydrogen

batt_power = []
h2_power = []
batt_soc = []
h2_level = []
hourly_deficit = []

for net in df["Net (MW)"]:
    if net > 0:
        charge = min(net, (battery_capacity - batt) / battery_charge_eff)
        batt += charge * battery_charge_eff
        net -= charge

        h2_prod = min(
            net * liters_per_mwh * electrolysis_eff,
            hydrogen_capacity - h2,
        )
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
    "Hour": range(1, len(df) + 1),
    "Renewable Power (MW)": df["Renewable Power (MW)"],
    "Demand (MW)": df["Demand (MW)"],
    "Net (MW)": df["Net (MW)"],
    "Battery Power (MW)": batt_power,
    "Battery Level (MWh)": batt_soc,
    "Hydrogen Power (MW)": h2_power,
    "Hydrogen Stored (L)": h2_level,
    "Hydrogen Stored (MWh)": [
        level / liters_per_mwh for level in h2_level
    ],
    "Total Energy Stored (MWh)": [
        battery + hydrogen / liters_per_mwh
        for battery, hydrogen in zip(batt_soc, h2_level)
    ],
    "Remaining Deficit (MW)": hourly_deficit,
})

# Group consecutive sets of 24 hourly rows into days.
# Because each row is one hour, summing hourly MW deficits gives MWh.
results_df["Day"] = (results_df["Hour"] - 1) // 24 + 1

daily_df = results_df.groupby("Day", as_index=False).agg(
    **{
        "Minimum Battery (MWh)": ("Battery Level (MWh)", "min"),
        "Minimum Hydrogen (MWh)": ("Hydrogen Stored (MWh)", "min"),
        "Daily Unmet Demand (MWh)": ("Remaining Deficit (MW)", "sum"),
        "End-of-Day Total Storage (MWh)": (
            "Total Energy Stored (MWh)", "last"
        ),
    }
)

# Keep Day only in the daily sheet, not the hourly results.
results_df = results_df.drop(columns="Day")

with pd.ExcelWriter(output_filename, engine="openpyxl") as writer:
    results_df.to_excel(
        writer, sheet_name="Hourly Results", index=False
    )
    daily_df.to_excel(
        writer, sheet_name="Daily Summary", index=False
    )

    hourly_ws = writer.sheets["Hourly Results"]
    daily_ws = writer.sheets["Daily Summary"]

    hourly_ws.freeze_panes = "B2"
    daily_ws.freeze_panes = "B2"

    hourly_ws.column_dimensions["A"].width = 12
    for column in "BCDEFGHIJK":
        hourly_ws.column_dimensions[column].width = 27

    daily_ws.column_dimensions["A"].width = 12
    for column in "BCDE":
        daily_ws.column_dimensions[column].width = 34

    last_row = len(daily_df) + 1
    days = Reference(daily_ws, min_col=1, min_row=2, max_row=last_row)

    # Chart 1: lowest storage reached during each day.
    storage_chart = LineChart()
    storage_chart.title = "Daily Minimum Storage"
    storage_chart.x_axis.title = "Day of Year"
    storage_chart.y_axis.title = "Stored Energy (MWh)"
    storage_chart.width = 25
    storage_chart.height = 12
    storage_chart.legend.position = "b"

    storage_values = Reference(
        daily_ws,
        min_col=2,
        max_col=3,
        min_row=1,
        max_row=last_row,
    )
    storage_chart.add_data(storage_values, titles_from_data=True)
    storage_chart.set_categories(days)
    storage_chart.series[0].graphicalProperties.line.solidFill = "4472C4"
    storage_chart.series[1].graphicalProperties.line.solidFill = "ED7D31"
    daily_ws.add_chart(storage_chart, "G2")

    # Chart 2: how much demand could not be supplied each day.
    deficit_chart = BarChart()
    deficit_chart.title = "Daily Unmet Demand"
    deficit_chart.x_axis.title = "Day of Year"
    deficit_chart.y_axis.title = "Unmet Demand (MWh)"
    deficit_chart.width = 25
    deficit_chart.height = 12
    deficit_chart.legend = None

    deficit_values = Reference(
        daily_ws, min_col=4, min_row=1, max_row=last_row
    )
    deficit_chart.add_data(deficit_values, titles_from_data=True)
    deficit_chart.set_categories(days)
    deficit_chart.series[0].graphicalProperties.solidFill = "C00000"
    daily_ws.add_chart(deficit_chart, "G26")

    # Chart 3: longer-term change in total stored energy.
    total_chart = LineChart()
    total_chart.title = "End-of-Day Total Storage"
    total_chart.x_axis.title = "Day of Year"
    total_chart.y_axis.title = "Stored Energy (MWh)"
    total_chart.width = 25
    total_chart.height = 12
    total_chart.legend = None

    total_values = Reference(
        daily_ws, min_col=5, min_row=1, max_row=last_row
    )
    total_chart.add_data(total_values, titles_from_data=True)
    total_chart.set_categories(days)
    total_chart.series[0].graphicalProperties.line.solidFill = "70AD47"
    daily_ws.add_chart(total_chart, "G50")

final_energy = batt + h2 / liters_per_mwh
starting_energy = starting_battery + starting_hydrogen / liters_per_mwh

print(f"Starting stored energy: {starting_energy:.2f} MWh")
print(f"Ending stored energy: {final_energy:.2f} MWh")
print(f"Unmet demand: {sum(hourly_deficit):.2f} MWh")
print(f"Results and charts saved to: {output_filename}")