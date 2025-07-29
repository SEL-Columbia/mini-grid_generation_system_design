import os, re, argparse, yaml
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
import pytz

def get_args():
    # Store all parameters for easy retrieval
    parser = argparse.ArgumentParser(description='fixed&flexible')
    parser.add_argument('--params_filename',
                        type=str,
                        default='params.yaml',
                        help='Loads model parameters')
    args = parser.parse_args()
    config = yaml.load(open(args.params_filename), Loader=yaml.FullLoader)
    for k,v in config.items():
        args.__dict__[k] = v
    return args

def get_fixed_load(args, mg_name):
    fixed_load = np.array(pd.read_csv(f'{args.data_dir}/{args.fixed_load_dir}/{mg_name}_fixed_loads.csv', index_col=0))[:, 0]
    return fixed_load

def get_motor_cap_limit(args, mg_name):
    caps = pd.read_csv(f'{args.data_dir}/{args.motor_cap_dir}')
    caps = caps[caps['mg_name'] == mg_name]
    return caps['motor_capacity'].values[0]

def get_fixed_system_size(args, mg_name):
    caps = pd.read_csv(f'{args.data_dir}/{args.system_capacity}')
    caps = caps[caps['mg_name'] == mg_name]
    return [caps['solar_cap_kw'].values[0], caps['batt_cap_kwh'].values[0], caps['inv_cap_kw'].values[0]]

def get_curtailable_load(args, mg_name):
    curtailable_load = np.array(pd.read_csv(f'{args.data_dir}/{args.curtailment_dir}/{mg_name}_curtailable_loads.csv', index_col=0))[:, 0]
    return curtailable_load

def get_flex_pue_ts(args, mg_name):
    source_dir = f'{args.data_dir}/{args.flex_pue_dir}/{mg_name}'
    fixed_load = np.array(pd.read_csv(f'{source_dir}/fixed_loads.csv').iloc[:, 1])

    # read the PUE daily loads
    pue_list = [name.rstrip('.csv') for name in os.listdir(f'{source_dir}') if name.startswith('pue_daily')]
    pue_daily_list = []
    for pue_id in pue_list:
        pue_daily_ts = np.array(pd.read_csv(f'{source_dir}/{pue_id}.csv'))
        pue_daily_list.append(pue_daily_ts)
    if pue_daily_list:
        pue_daily_array = np.stack(pue_daily_list, axis=0)
    else:
        pue_daily_array = np.zeros((1, len(fixed_load), 2))

    return fixed_load, pue_daily_array

def annualization_rate(i, years):
    return (i*(1+i)**years)/((1+i)**years-1)

def get_cap_cost(args, years):
    # Annualize capacity costs for model
    annualization_solar = annualization_rate(args.i_rate, args.annualize_years_solar)
    annualization_battery_la = annualization_rate(args.i_rate, args.annualize_years_battery_la)
    annualization_battery_li = annualization_rate(args.i_rate, args.annualize_years_battery_li)
    annualization_battery_inverter = annualization_rate(args.i_rate, args.annualize_years_battery_inverter)
    annualization_diesel = annualization_rate(args.i_rate, args.annualize_years_diesel)

    solar_cap_cost = years * annualization_solar * float(args.solar_cost_kw)
    battery_la_cap_cost_kwh = years * annualization_battery_la * float(args.battery_la_cost_kwh)
    battery_li_cap_cost_kwh = years * annualization_battery_li * float(args.battery_li_cost_kwh)
    battery_inverter_cap_cost_kw = years * annualization_battery_inverter * float(args.battery_inverter_cost_kw)
    diesel_cap_cost_kw = years * annualization_diesel  * float(args.diesel_cap_cost_kw) * args.reserve_req
    return solar_cap_cost, battery_la_cap_cost_kwh, battery_li_cap_cost_kwh, battery_inverter_cap_cost_kw, \
        diesel_cap_cost_kw

def load_timeseries(args, solar_region):
    solar_region = solar_region.lower()
    solar_po = pd.read_csv(f'{args.data_dir}/uganda_solar_ts/{solar_region}_solar_2019.csv')
    solar_po = get_solar_ts(solar_po, args)
    solar_po_hourly = np.array(solar_po)[:, 0]
    return solar_po_hourly

def get_solar_ts(solar_po, args):
    solar_po.time = [datetime.strptime(k, "%Y%m%d:%H%M") for k in solar_po.time]
    solar_po.time = solar_po.time.dt.tz_localize('UTC')
    solar_po.time = solar_po.time.dt.tz_convert('Africa/Kampala')

    solar_po = solar_po[["time", "P"]]
    solar_po["P"] = solar_po["P"] / 1000
    solar_po.columns = ["time", "solar_po"]

    # create a DataFrame with the new times
    new_times = pd.DataFrame({
        'time': [
            datetime(2019, 1, 1, 0, 30, tzinfo=pytz.timezone('Etc/GMT-3')),
            datetime(2019, 1, 1, 1, 30, tzinfo=pytz.timezone('Etc/GMT-3')),
            datetime(2019, 1, 1, 2, 30, tzinfo=pytz.timezone('Etc/GMT-3')),
        ],
        'solar_po': [0, 0, 0]
    })
    solar_po = pd.concat([new_times, solar_po], ignore_index=True)
    solar_po.set_index('time', inplace=True)

    period1 = solar_po[(solar_po.index >= pd.Timestamp("2019-03-01 00:00", tzinfo=pytz.timezone('Etc/GMT-3'))) &
                       (solar_po.index <= pd.Timestamp("2019-12-31 23:59", tzinfo=pytz.timezone('Etc/GMT-3')))]
    period2 = solar_po[(solar_po.index >= pd.Timestamp("2019-01-01 00:00", tzinfo=pytz.timezone('Etc/GMT-3'))) &
                       (solar_po.index <= pd.Timestamp("2019-02-28 23:59", tzinfo=pytz.timezone('Etc/GMT-3')))]

    solar_po_sorted = pd.concat([period1, period2])
    solar_po_sorted = solar_po_sorted.reset_index(drop=True)

    return solar_po_sorted