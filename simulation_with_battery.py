import pandas as pd
import numpy as np
import os

# --- CONFIGURATION PARAMETERS ---
# Modify these values to change the simulation input
WIND_CAPACITY_KW = 10000   # 10 MW
BAT_CAP_KWH = 50000000     # 50,000,000 kWh
BAT_EFF_CH = 0.95          # Battery Charge Efficiency
BAT_EFF_DIS = 0.95         # Battery Discharge Efficiency
H2_ELEC_EFF = 0.75         # Hydrogen Electrolysis Efficiency
H2_FC_EFF = 0.60           # Hydrogen Fuel Cell Efficiency
# -------------------------------

def run_simulation(
    df,
    wind_capacity_kw,
    pv_area_m2,
    h2_start_kwh,
    bat_cap_kwh,
    bat_eff_ch,
    bat_eff_dis,
    h2_elec_eff,
    h2_fc_eff
):
    """
    Simulates the energy balance for 8760 hours.
    """
    # Column mapping based on file inspection
    idx_irradiance = df.columns.get_loc('Total Irradiance (Solar) (Wh/m2)')
    idx_pv_eff = df.columns.get_loc('PV Cell Efficiency')
    idx_wind_per_kw = df.columns.get_loc('Wind, kWh/kW')
    idx_demand = df.columns.get_loc('Total Demand (kWh) for all houses')

    # Initialize series for recording data
    wind_s_series = []
    solar_s_series = []
    net_series = []
    dissipation_step_series = []
    bat_soc_series = []
    h2_soc_series = []
    
    # Current state
    current_bat_kwh = 0.0
    current_h2_kwh = h2_start_kwh

    for i in range(len(df)):
        # 1. Calculate Supply
        wind_supply_kwh = df.iloc[i, idx_wind_per_kw] * wind_capacity_kw
        irradiance_wh_m2 = df.iloc[i, idx_irradiance]
        pv_eff = df.iloc[i, idx_pv_eff]
        solar_supply_kwh = (irradiance_wh_m2 * pv_area_m2 * pv_eff) / 1000.0
        
        total_supply_kwh = wind_supply_kwh + solar_supply_kwh
        demand_kwh = df.iloc[i, idx_demand]
        
        net_kwh = total_supply_kwh - demand_kwh
        
        wind_s_series.append(wind_supply_kwh)
        solar_s_series.append(solar_supply_kwh)
        net_series.append(net_kwh)
        
        dissipation_kwh = 0.0
        
        if net_kwh > 0:
            # Surplus: Charge Battery first, then H2
            charge_amount = min(net_kwh, (bat_cap_kwh - current_bat_kwh) / bat_eff_ch)
            current_bat_kwh += charge_amount * bat_eff_ch
            remaining_surplus = net_kwh - charge_amount
            
            h2_prod_kwh = remaining_surplus * h2_elec_eff
            current_h2_kwh += h2_prod_kwh
            
            dissipation_kwh = (charge_amount * (1 - bat_eff_ch)) + (remaining_surplus * (1 - h2_elec_eff))
            
        else:
            # Deficit: Discharge Battery first, then H2
            deficit_kwh = abs(net_kwh)
            
            discharge_amount = min(deficit_kwh, current_bat_kwh * bat_eff_dis)
            current_bat_kwh -= discharge_amount / bat_eff_dis
            remaining_deficit = deficit_kwh - discharge_amount
            
            if remaining_deficit > 0:
                h2_use_kwh = min(remaining_deficit / h2_fc_eff, current_h2_kwh)
                current_h2_kwh -= h2_use_kwh
                energy_from_h2 = h2_use_kwh * h2_fc_eff
                remaining_deficit -= energy_from_h2
                dissipation_kwh += (h2_use_kwh * (1 - h2_fc_eff))
            
            dissipation_kwh += (discharge_amount * (1 - bat_eff_dis))
            
        bat_soc_series.append(current_bat_kwh)
        h2_soc_series.append(current_h2_kwh)
        dissipation_step_series.append(dissipation_kwh)

    results_df = df.copy()
    results_df['Wind Supply (kWh)'] = wind_s_series
    results_df['Solar Supply (kWh)'] = solar_s_series
    results_df['Net Energy (kWh)'] = net_series
    results_df['Battery Energy (kWh)'] = bat_soc_series
    results_df['H2 Energy (kWh)'] = h2_soc_series
    results_df['H2 Volume (m³)'] = [h / 1000.0 for h in h2_soc_series]
    results_df['Hourly Dissipation (kWh)'] = dissipation_step_series
    
    return results_df

def optimize_pv_and_h2(df, wind_capacity_kw, bat_cap_kwh, bat_eff_ch, bat_eff_dis, h2_elec_eff, h2_fc_eff):
    """
    Bisection-based optimization for PV Area and H2 Storage.
    Incorporates the 240-hour hydrogen buffer requirement from the research paper.
    """
    print("Starting Bisection Optimization (with 240h buffer)...")
    
    # Pre-calculate the 240-hour demand buffer requirement (in kWh of H2 energy)
    # At any hour i, we must have enough H2 to cover the next 240 hours of demand.
    demand_series = df['Total Demand (kWh) for all houses'].values
    n = len(demand_series)
    buffer_kwh = np.zeros(n)
    
    # Calculate rolling sum for the next 240 hours
    for i in range(n):
        # Look ahead 240 hours (or until end of array)
        end_idx = min(i + 241, n)
        # Sum demand and divide by fuel cell efficiency to get required H2 energy
        buffer_kwh[i] = np.sum(demand_series[i+1:end_idx]) / h2_fc_eff

    # Stage 1: Find min PV Area such that the system is feasible with a large H2 buffer
    def is_pv_feasible(pv_area):
        # Use a very large H2 buffer for the feasibility check
        res = run_simulation(df, wind_capacity_kw, pv_area, 1e8, bat_cap_kwh, bat_eff_ch, bat_eff_dis, h2_elec_eff, h2_fc_eff)
        return res['Battery Energy (kWh)'].min() >= 0

    pv_low, pv_high = 0.0, 2000000.0
    best_pv = pv_high
    for _ in range(20):
        mid_pv = (pv_low + pv_high) / 2
        if is_pv_feasible(mid_pv):
            best_pv = mid_pv
            pv_high = mid_pv
        else:
            pv_low = mid_pv
            
    opt_pv = best_pv

    # Stage 2: Find min H2 volume for that PV area such that SOC >= buffer
    def find_min_h2(pv_area):
        h2_low, h2_high = 0.0, 1e9 # 1 TWh
        best_h2 = h2_high
        for _ in range(25): # Increased iterations for precision
            mid_h2 = (h2_low + h2_high) / 2
            res = run_simulation(df, wind_capacity_kw, pv_area, mid_h2, bat_cap_kwh, bat_eff_ch, bat_eff_dis, h2_elec_eff, h2_fc_eff)
            
            # Check if H2 SOC is always >= the 240h buffer AND battery is always >= 0
            h2_soc = res['H2 Energy (kWh)'].values
            if (h2_soc >= buffer_kwh).all() and res['Battery Energy (kWh)'].min() >= 0:
                best_h2 = mid_h2
                h2_high = mid_h2
            else:
                h2_low = mid_h2
        return best_h2

    opt_h2 = find_min_h2(opt_pv)
    
    # Run final simulation with optimized values
    final_res = run_simulation(df, wind_capacity_kw, opt_pv, opt_h2, bat_cap_kwh, bat_eff_ch, bat_eff_dis, h2_elec_eff, h2_fc_eff)
    
    return opt_pv, opt_h2, final_res

if __name__ == "__main__":
    filename = "Calculations-Efficiencies-new.xlsx"
    if not os.path.exists(filename):
        print(f"Error: {filename} not found.")
    else:
        df = pd.read_excel(filename, sheet_name="Elctric-NoGas", header=9)
        
        # Perform full optimization
        opt_pv, opt_h2, results = optimize_pv_and_h2(
            df,
            WIND_CAPACITY_KW,
            BAT_CAP_KWH,
            BAT_EFF_CH,
            BAT_EFF_DIS,
            H2_ELEC_EFF,
            H2_FC_EFF
        )

        print("\n" + "="*30)
        print("   OPTIMIZATION RESULTS")
        print("="*30)
        print(f"Optimized PV Area:    {opt_pv:12.2f} m2")
        print(f"Optimized H2 Volume:  {opt_h2/1000.0:12.2f} m3")
        print(f"Optimized H2 Energy:  {opt_h2:12.2f} kWh")
        print("-" * 30)
        print(f"Min Battery Energy:   {results['Battery Energy (kWh)'].min():12.2f} kWh")
        print(f"Min H2 Energy:        {results['H2 Energy (kWh)'].min():12.2f} kWh")
        print("="*30)

        output_filename = "Simulation_Results.xlsx"
        with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
            results.to_excel(writer, sheet_name='Results', index=False)
            workbook  = writer.book
            worksheet = writer.sheets['Results']
            for i, col in enumerate(results.columns):
                column_len = max(results[col].astype(str).str.len().max(), len(col)) + 2
                worksheet.set_column(i, i, min(column_len, 50))

        print(f"\nSimulation complete. Results saved to {output_filename}")
