import pandas as pd

# Match the settings in your storage script
battery_capacity = 100          # MWh
starting_battery = 100           # MWh
starting_hydrogen = 0           # L

battery_charge_eff = 0.9
battery_discharge_eff = 0.85
electrolysis_eff = 0.7
hydrogen_fuel_eff = 0.6
liters_per_mwh = 1000

filename = "Calculations-Efficiencies-new.xlsx"
source_sheet = "Elctric-NoGas"

df = pd.read_excel(filename, sheet_name=source_sheet, header=9)

renewable = pd.to_numeric(
    df["Total Renewable Supply  (kWh)"], errors="coerce"
)
demand = pd.to_numeric(
    df["Total Demand (kWh) for all houses"], errors="coerce"
)

if renewable.isna().any() or demand.isna().any():
    raise ValueError(
        "The source workbook has blank formula results. "
        "Recalculate and save it in Excel or LibreOffice first."
    )

# Each row represents one hour. kWh per hour / 1000 = MW.
net_power = ((renewable - demand) / 1000).to_numpy()
starting_energy = starting_battery + starting_hydrogen / liters_per_mwh


def simulate(hydrogen_capacity):
    batt = starting_battery
    h2 = starting_hydrogen
    unmet_demand = 0.0

    for net in net_power:
        if net > 0:
            charge = min(
                net,
                (battery_capacity - batt) / battery_charge_eff,
            )
            batt += charge * battery_charge_eff
            net -= charge

            h2_prod = min(
                net * liters_per_mwh * electrolysis_eff,
                hydrogen_capacity - h2,
            )
            h2 += h2_prod

        else:
            net = -net

            discharge = min(net, batt * battery_discharge_eff)
            batt -= discharge / battery_discharge_eff
            net -= discharge

            h2_use = min(
                net * liters_per_mwh / hydrogen_fuel_eff,
                h2,
            )
            h2 -= h2_use
            net -= h2_use * hydrogen_fuel_eff / liters_per_mwh

            unmet_demand += max(0, net)

    final_energy = batt + h2 / liters_per_mwh
    return final_energy, batt, h2, unmet_demand


# This upper bound can hold all hydrogen the year's surplus could produce.
max_capacity = max(
    starting_hydrogen,
    sum(max(0, net) for net in net_power)
    * liters_per_mwh
    * electrolysis_eff,
)

low = starting_hydrogen
high = max_capacity

low_result = simulate(low)
high_result = simulate(high)

low_difference = low_result[0] - starting_energy
high_difference = high_result[0] - starting_energy

if low_difference > 0:
    print(
        "Even the smallest tank ends above the starting energy. "
        "No tank capacity will make the energies equal."
    )
elif high_difference < 0:
    print(
        "Even a tank large enough to hold all producible hydrogen "
        "ends below the starting energy. No tank capacity can "
        "make up this energy shortfall."
    )
else:
    # Find a capacity that ends within 0.01 MWh of the starting energy.
    for _ in range(80):
        mid = (low + high) / 2
        result = simulate(mid)
        difference = result[0] - starting_energy

        if abs(difference) < 0.01:
            break

        if difference < 0:
            low = mid
        else:
            high = mid

    final_energy, final_batt, final_h2, unmet = result

    print(f"Hydrogen tank capacity: {mid:,.0f} L")
    print(f"Starting stored energy: {starting_energy:,.2f} MWh")
    print(f"Ending stored energy: {final_energy:,.2f} MWh")
    print(f"  Final battery: {final_batt:,.2f} MWh")
    print(f"  Final hydrogen: {final_h2:,.0f} L")
    print(f"Unmet demand: {unmet:,.2f} MWh")