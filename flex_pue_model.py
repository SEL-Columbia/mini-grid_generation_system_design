from gurobipy import *
from utils import get_cap_cost, load_timeseries, get_flex_pue_ts, get_fixed_system_size, get_curtailable_load, get_motor_cap_limit
from results_processing import results_retrieval, process_results
import numpy as np
import pandas as pd
import os

def create_flex_pue_model(args, mg_name):
    print("flex pue load model building and solving")
    print("--------####################------------")

    T = args.num_hour_flex_pue
    trange = range(T)
    solar_region = args.solar_region
    solar_po_hourly = load_timeseries(args, solar_region)

    fixed_load, pue_daily_array = get_flex_pue_ts(args, mg_name)
    print(pue_daily_array, 'delete')
    if args.curtailable_load_sce:
        curtailable_load = get_curtailable_load(args, mg_name)

    # Retrieve capital prices for solar, battery, and diesel generators
    solar_cap_cost, battery_la_cap_cost_kwh, battery_li_cap_cost_kwh, \
        battery_inverter_cap_cost_kw, diesel_cap_cost_kw = get_cap_cost(args, args.num_year_flex_pue)

    # create the model
    m = Model("flex_pue_model")
    print('Flexible pue model building and solving')

    # Initialize capacity variables
    solar_cap = m.addVar(name='solar_cap', obj=solar_cap_cost)
    solar_binary = m.addVar(name='solar_cap_binary', vtype=GRB.BINARY)
    diesel_cap = m.addVar(obj=diesel_cap_cost_kw, name='diesel_cap')
    diesel_binary = m.addVar(name='diesel_cap_binary', vtype=GRB.BINARY)
    battery_la_cap_kwh = m.addVar(obj=battery_la_cap_cost_kwh, name='batt_la_energy_cap')
    battery_la_cap_kw = m.addVar(obj=battery_inverter_cap_cost_kw, name='batt_la_power_cap')
    battery_li_cap_kwh = m.addVar(obj=battery_li_cap_cost_kwh, name='batt_li_energy_cap')
    battery_li_cap_kw = m.addVar(obj=battery_inverter_cap_cost_kw, name='batt_li_power_cap')

    # constraints for technology availability
    if not args.solar_ava:
        m.addConstr(solar_cap == 0)
    else:
        m.addConstr(solar_cap - args.solar_min_cap * solar_binary >= 0)
        m.addConstr(solar_cap * (1 - solar_binary) == 0)
    if not args.battery_la_ava:
        m.addConstr(battery_la_cap_kwh == 0)
    if not args.battery_li_ava:
        m.addConstr(battery_li_cap_kwh == 0)
    if not args.diesel_ava:
        m.addConstr(diesel_cap == 0)
    else:
        m.addConstr(diesel_cap - args.diesel_min_cap * diesel_binary >= 0)
        m.addConstr(diesel_cap * (1 - diesel_binary) == 0)
        if args.diesel_vali_cond:
            m.addConstr(diesel_binary == 1)

    # three-phase motor capacity limits the battery inverter capacity
    motor_limit_cap = get_motor_cap_limit(args, mg_name)
    if args.motor_cap_limit:
        if args.flex_pue_dir == 'flex_pue_ts/sp_tp':
            m.addConstr(battery_la_cap_kw + battery_li_cap_kw >= motor_limit_cap)  # + diesel_cap

    # fixed generation system with solar, and LA battery and battery inverter
    if args.fixed_gen_caps:
        caps = get_fixed_system_size(args, mg_name)
        print('Solar capacity [kW]: ', caps[0], '\n',
              'Battery capacity [kWh]: ', caps[1], '\n',
              'Inverter capacity [kWh]: ', caps[2])
        m.addConstr(solar_cap == caps[0])
        m.addConstr(battery_la_cap_kwh == caps[1])
        # for inverter, choose the maximum of guided capacity and motor capacity if applicable.
        if args.motor_cap_limit:
            if args.fixed_load_dir not in [f'fixed_load_ts/{scenario}' for scenario in
                                           args.no_motor_cap_scenarios]:
                m.addConstr(battery_la_cap_kw == max(caps[2], motor_limit_cap))
            else:
                m.addConstr(battery_la_cap_kw == caps[2])
        else:
            m.addConstr(battery_la_cap_kw == caps[2])

    # battery capacity constraints
    m.addConstr(battery_la_cap_kwh * (1 - args.battery_la_min_soc) * float(args.battery_la_p2e_ratio_range[0]) <=
                battery_la_cap_kw)
    m.addConstr(battery_la_cap_kwh * (1 - args.battery_la_min_soc) * float(args.battery_la_p2e_ratio_range[1]) >=
                battery_la_cap_kw)
    m.addConstr(battery_li_cap_kwh * (1 - args.battery_li_min_soc) * float(args.battery_li_p2e_ratio_range[0]) <=
                battery_li_cap_kw)
    m.addConstr(battery_li_cap_kwh * (1 - args.battery_li_min_soc) * float(args.battery_li_p2e_ratio_range[1]) >=
                battery_li_cap_kw)
    m.update()

    # Initialize time-series variables
    solar_util = m.addVars(trange, name='solar_util')
    battery_la_charge = m.addVars(trange, name='batt_la_charge')
    battery_la_discharge = m.addVars(trange, obj=args.nominal_discharge_cost_kwh, name='batt_la_discharge')
    battery_la_level = m.addVars(trange, name='batt_la_level')
    battery_li_charge = m.addVars(trange, name='batt_li_charge')
    battery_li_discharge = m.addVars(trange, obj=args.nominal_discharge_cost_kwh, name='batt_li_discharge')
    battery_li_level = m.addVars(trange, name='batt_li_level')
    diesel_kwh_fuel_cost = args.diesel_cost_liter * args.liter_per_kwh / args.diesel_eff
    diesel_gen = m.addVars(trange, obj=diesel_kwh_fuel_cost, name="diesel_gen")

    supply_deficit = m.addVars(trange, obj=args.deficit_penalty, name='supply_deficit')
    supply_deficit_binary = m.addVars(trange, vtype=GRB.BINARY, name='supply_deficit_binary', obj=0.1)
    curtailed_loads = m.addVars(trange, obj=args.curtailment_nominal, name='curtailed_loads')

    # create commercial loads
    pue_load = m.addVars(trange, name='pue_load')
    m.update()

    # Add time-series Constraints
    for j in trange:
        # solar and diesel generation constraint
        m.addConstr(diesel_gen[j] <= diesel_cap)
        m.addConstr(solar_util[j] <= solar_cap * round(solar_po_hourly[j], 4))

        # Energy Balance
        m.addConstr(solar_util[j] + diesel_gen[j] - battery_la_charge[j] + battery_la_discharge[j] -
                    battery_li_charge[j] + battery_li_discharge[j] ==
                    fixed_load[j] + pue_load[j] - curtailed_loads[j] - supply_deficit[j])

        # curtailable load from those customers with high demand events. we tested how much impacts they have.
        if args.curtailable_load_sce:
            m.addConstr(curtailable_load[j] - curtailed_loads[j] == 0)
        else:
            m.addConstr(curtailed_loads[j] == 0)

        # Battery operation constraints
        m.addConstr(args.battery_la_eff * battery_la_charge[j] - battery_la_cap_kw <= 0)
        m.addConstr(battery_la_discharge[j] / args.battery_la_eff - battery_la_cap_kw <= 0)
        m.addConstr(battery_la_level[j] - battery_la_cap_kwh <= 0)
        m.addConstr(battery_la_level[j] - battery_la_cap_kwh * args.battery_la_min_soc >= 0)

        m.addConstr(args.battery_li_eff * battery_li_charge[j] - battery_li_cap_kw <= 0)
        m.addConstr(battery_li_discharge[j] / args.battery_li_eff - battery_li_cap_kw <= 0)
        m.addConstr(battery_li_level[j] - battery_li_cap_kwh <= 0)
        m.addConstr(battery_li_level[j] - battery_li_cap_kwh * args.battery_li_min_soc >= 0)

        # Battery control
        if j == 0:
            m.addConstr(
                battery_la_discharge[j] / args.battery_la_eff - args.battery_la_eff * battery_la_charge[j] ==
                battery_la_level[T - 1] - battery_la_level[j])
            m.addConstr(
                battery_li_discharge[j] / args.battery_li_eff - args.battery_li_eff * battery_li_charge[j] ==
                battery_li_level[T - 1] - battery_li_level[j])
        else:
            m.addConstr(
                battery_la_discharge[j] / args.battery_la_eff - args.battery_la_eff * battery_la_charge[j] ==
                battery_la_level[j - 1] - battery_la_level[j])
            m.addConstr(
                battery_li_discharge[j] / args.battery_li_eff - args.battery_li_eff * battery_li_charge[j] ==
                battery_li_level[j - 1] - battery_li_level[j])

        if args.supply_deficit_binary_sce:
            m.addConstr(supply_deficit[j] <= fixed_load[j] * supply_deficit_binary[j])
            if args.curtailable_load_sce:
                m.addConstr(supply_deficit[j] <= (fixed_load[j] - curtailed_loads[j]) * supply_deficit_binary[j])
            m.addConstr(supply_deficit[j] >= 0)


    m.update()

    # allowed supply deficit
    if args.supply_deficit_sce:
        m.addConstr(
            quicksum(supply_deficit[j] for j in trange) <= args.allowed_supply_deficit_frac *
            quicksum(fixed_load[j] + pue_load[j] for j in trange))
    else:
        m.addConstr(quicksum(supply_deficit[j] for j in trange) == 0)

    # Commercial load constraint / initialize variables for each commercial load
    pue_nums = int(pue_daily_array.shape[0])
    for pue_no in range(pue_nums):
        pue_load_single = m.addVars(trange, name=f'pue_load_{pue_no}')
        # for each pue, the daily sum and the daily max is limited
        for d in range(int(args.num_hour_flex_pue/24)):
            pue_load_single_daily = quicksum(pue_load_single[j] for j in range(d*24, (d+1)*24))
            m.addConstr(pue_load_single_daily == pue_daily_array[pue_no, d, 0])
            for hour in range(24):
                m.addConstr(pue_load_single[d * 24 + hour] <= pue_daily_array[pue_no, d, 1])

    m.update()

    # sum the pue load single to pue load
    for j in trange:
        pue_load_sums = quicksum(m.getVarByName(f'pue_load_{pue_no}[{j}]') for pue_no in range(pue_nums))
        m.addConstr(pue_load[j] == pue_load_sums)

    m.update()

    # Set model solver parameters
    m.setParam("FeasibilityTol", args.feasibility_tol)
    m.setParam("OptimalityTol", args.optimality_tol)
    m.setParam("Method", args.solver_method)
    m.setParam("TimeLimit", args.model_time_limit)
    m.setParam("OutputFlag", 1)
    # Solve the model
    m.optimize()

    ### ------------------------- Results Output ------------------------- ###
    # Process the model solution
    caps_results, ts_results = results_retrieval(m, T)
    ts_results['fixed_load_kw'] = fixed_load  # add the fixed load to the time series results

    # save results / get final processed results
    if not os.path.exists(os.path.join(args.results_dir, mg_name)):
        os.makedirs(os.path.join(args.results_dir, mg_name))

    processed_results = process_results(args, caps_results, ts_results)

    ts_results.round(decimals=3).to_csv(os.path.join(args.results_dir, mg_name, 'ts_results.csv'))
    processed_results.round(decimals=3).to_csv(os.path.join(args.results_dir, mg_name, 'processed_results.csv'))

    return None