# Project Repository

This repository contains all the necessary files to run and customize a mini-grid electricity system model. Developed using linear programming, this model simulates and designs generation systems to meet annual electricity demands while minimizing costs by optimizing the mix of solar, battery, and diesel generators. It supports various scenarios by processing inputs of load and solar potential time series and outputs the Levelized Cost of Energy (LCOE) and system capacities. The model includes functions for load shedding and flexible productive load operations. Note that distribution/connection systems and maintenance costs are not included in this model. Below is an overview of the primary components and their functionalities.

## Files Description

- **main.py:** This is the main file used to run the model. It integrates all the components and executes the modeling process.
- **fixed_load_model.py:** Contains the fixed load model which is part of the broader system.
- **flex_pue_model.py:** Implements the Productive Use of Energy (PUE) model, allowing for flexibility within the load modeling.
- **results_processing.py:** Handles the creation and processing of results from the model execution.
- **utils.py:** Includes various utility functions that support model operations.
- **params.yaml:** This file stores parameters that can be customized depending on the specific requirements of the model you want to run.

- Two types of inputs. Parameters can be edited in the params.yaml file, while test inputs for loads, solar potential, and flexible productive load scenarios are located in the “data_uploads” folder.
- For model formulation and scenario details, refer to the paper “Leveraging Targeted Curtailment and Daytime Loads to Improve Mini-Grid Economics”.

## Running the Model

To use the model:
Navigate to the directory containing `main.py`. Run the command: 
```
python3 main.py
