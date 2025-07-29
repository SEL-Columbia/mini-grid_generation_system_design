from fixed_load_model import create_fix_load_model
from flex_pue_model import create_flex_pue_model
from utils import get_args
import datetime
import os

if __name__ == '__main__':

    running_start_time = datetime.datetime.now()

    args = get_args()
    mg_list = ['agoro']

    for mg_no in range(len(mg_list)):
        mg_name = mg_list[mg_no]
        print(mg_name, 'name of mini-grid')

        if os.path.exists(os.path.join(args.results_dir, mg_name)):
            print(f"This scenario was already calculated. to rerun, delete the directory.")
            continue

        if args.fixed_load_sce:
            create_fix_load_model(args, mg_name)
        else:
            create_flex_pue_model(args, mg_name)

        # showing the time used
        running_end_time = datetime.datetime.now()
        print(running_end_time - running_start_time)