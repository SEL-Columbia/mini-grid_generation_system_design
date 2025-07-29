import numpy as np
import pandas as pd
from utils import load_timeseries, get_cap_cost
import datetime


def results_retrieval(m, T_hours):

    node_df = pd.DataFrame()
    node_df['solar_cap_kw'] = [m.getVarByName('solar_cap').X]
    node_df['diesel_cap_kw'] = [m.getVarByName('diesel_cap').X]
    node_df['batt_la_energy_cap_kwh'] = [m.getVarByName('batt_la_energy_cap').X]
    node_df['batt_la_power_cap_kw'] = [m.getVarByName('batt_la_power_cap').X]
    node_df['batt_li_energy_cap_kwh'] = [m.getVarByName('batt_li_energy_cap').X]
    node_df['batt_li_power_cap_kw'] = [m.getVarByName('batt_li_power_cap').X]

    # get the ts data
    variable_names = [
        'solar_util[{}]', 'diesel_gen[{}]', 'batt_la_level[{}]',
        'batt_la_charge[{}]', 'batt_la_discharge[{}]', 'batt_li_level[{}]',
        'batt_li_charge[{}]', 'batt_li_discharge[{}]', 'pue_load[{}]',
        'supply_deficit[{}]', 'curtailed_loads[{}]'
    ]
    ts_col_names = [
        'solar_util_kw', 'diesel_util_kw',
        'batt_la_level_kwh', 'batt_la_charge_kw', 'batt_la_discharge_kw',
        'batt_li_level_kwh', 'batt_li_charge_kw', 'batt_li_discharge_kw',
        'commercial_load_kw', 'supply_deficit_kw', 'curtailed_load_kw'
    ]
    num_vars = len(variable_names)
    system_ts_df = pd.DataFrame(index=range(T_hours), columns=ts_col_names)
    for j in range(T_hours):
        for var_name, col_name in zip(variable_names, ts_col_names):
            system_ts_df.at[j, col_name] = m.getVarByName(var_name.format(j)).X

    return node_df, system_ts_df


def process_results(args, caps_results, ts_results):

    # Retrieve necessary model parameters
    T = args.num_hour_fixed_load
    solar_region = args.solar_region
    solar_pot_hourly = load_timeseries(args, solar_region)

    # Calculate demand, generation, solar uncurtailed / actual CF
    avg_total_demand = np.mean(ts_results.commercial_load_kw + ts_results.fixed_load_kw)
    peak_total_demand = np.max(ts_results.commercial_load_kw + ts_results.fixed_load_kw)

    avg_solar_gen = np.mean(ts_results.solar_util_kw)
    avg_diesel_gen = np.mean(ts_results.diesel_util_kw)
    avg_total_gen = avg_solar_gen + avg_diesel_gen
    solar_uncurtailed_cf = np.mean(solar_pot_hourly)
    solar_actual_cf = avg_solar_gen / np.sum(caps_results.solar_cap_kw)

    # total capital cost and operation cost
    solar_cap_cost, battery_la_cap_cost_kwh, battery_li_cap_cost_kwh, \
        battery_inverter_cap_cost_kw, diesel_cap_cost_kw = get_cap_cost(args, args.num_year_fixed_load)
    total_solar_cost = np.sum(caps_results.solar_cap_kw) * solar_cap_cost
    total_diesel_cost = np.sum(caps_results.diesel_cap_kw) * diesel_cap_cost_kw
    total_battery_la_cost = np.sum(caps_results.batt_la_energy_cap_kwh) * battery_la_cap_cost_kwh + \
                            np.sum(caps_results.batt_la_power_cap_kw) * battery_inverter_cap_cost_kw
    total_battery_li_cost = np.sum(caps_results.batt_li_energy_cap_kwh) * battery_li_cap_cost_kwh + \
                            np.sum(caps_results.batt_li_power_cap_kw) * battery_inverter_cap_cost_kw
    total_diesel_fuel_cost = avg_diesel_gen * T * args.diesel_cost_liter * args.liter_per_kwh / args.diesel_eff

    total_gen_cost = total_solar_cost + total_battery_la_cost + total_battery_li_cost + \
                     total_diesel_cost + total_diesel_fuel_cost

    # Create arrays to store energy output & costs
    data_for_export = pd.DataFrame()

    data_for_export['solar_cap_kw'] = [np.sum(caps_results.solar_cap_kw)]
    data_for_export['diesel_cap_kw'] = [np.sum(caps_results.diesel_cap_kw)]
    data_for_export['battery_la_energy_cap_kwh'] = [np.sum(caps_results.batt_la_energy_cap_kwh)]
    data_for_export['battery_la_power_cap_kw'] = [np.sum(caps_results.batt_la_power_cap_kw)]
    data_for_export['battery_li_energy_cap_kwh'] = [np.sum(caps_results.batt_li_energy_cap_kwh)]
    data_for_export['battery_li_power_cap_kw'] = [np.sum(caps_results.batt_li_power_cap_kw)]

    data_for_export['peak_load_kw'] = [peak_total_demand]
    data_for_export['avg_load_kw'] = [avg_total_demand]
    data_for_export['avg_gen_kw'] = [avg_total_gen]
    data_for_export['avg_solar_gen_kw'] = [avg_solar_gen]
    data_for_export['avg_diesel_gen_kw'] = [avg_diesel_gen]
    data_for_export['solar_unc_cf'] = [solar_uncurtailed_cf]
    data_for_export['solar_act_cf'] = [solar_actual_cf]

    data_for_export['solar_cost'] = [total_solar_cost]
    data_for_export['diesel_cost'] = [(total_diesel_cost + total_diesel_fuel_cost)]
    data_for_export['diesel_cap_cost'] = [total_diesel_cost]
    data_for_export['diesel_fuel_cost'] = [total_diesel_fuel_cost]
    data_for_export['battery_la_cost'] = [total_battery_la_cost]
    data_for_export['battery_li_cost'] = [total_battery_li_cost]
    data_for_export['generation_cost'] = [total_gen_cost]
    data_for_export['LCOE'] = [total_gen_cost / (T*avg_total_demand)]

    return data_for_export