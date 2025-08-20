# OpenHENS

Open-source, equation-based synthesis and optimisation of heat exchanger networks 
Models apply the Gekko modelling language (https://github.com/BYU-PRISM/GEKKO) and solve using the open-source APOPT solver (https://apopt.com/) or COIN-OR solvers (https://www.coin-or.org)

The current version is 0.5. The full release will come by March 2026 and will involve 
- Code refactor for improved useability
- Pytests
- User guides & documentation
- Package through pip
- Integration into the Ahuora Platform
- Safety of saving solutions


## 🚀 Installation (via Conda + setup.py)

Follow these steps to install and run OpenHENS using a Conda environment.

### 1. Clone the Repository

```bash
git clone https://github.com/waikato-ahuora-smart-energy-systems/OpenHENS.git
cd OpenHENS
```

### 2. Install Miniconda (if not already installed)

Download and install **Miniconda** from:  
https://docs.conda.io/en/latest/miniconda.html

> During setup, check the box to "Add Miniconda to my PATH environment variable" if you want to use it from any terminal.

Once installed, open **Anaconda Prompt** (Windows) or terminal (macOS/Linux). Do not use virtual environments as they dont work with packages outside of Python

---

### 3. Create and Activate a Conda Environment

```bash
conda create -n openhens-env python=3.12
conda activate openhens-env
```

### 4. Install the Package (Using setup.py)

From the project root:

```bash
pip install -e .
```

This installs the `OpenHENS` package in **editable mode** and uses `requirements.txt` automatically.

---

## 5. Installation of COIN-OR solvers to virtual environment'
COIN-OR solvers must be installed independently of  `openhens-env`. This can be done by downloading the binaries for the desired solvers
from the COIN-OR website https://www.coin-or.org/download/binary. 

Once the binaries are downloaded, extract and save them to a local file e.g User\Documents\Solvers. The solver .exe path must then be added to the PATH which is done through the 'Environment Variables' program native to Windows systems. 

More detailed instructions can be found here: https://www.jdhp.org/docs/notebook/python_pyomo_getting_started_0_installation_instructions_pyomo_and_solvers.html


## Usage
Import the OpenHENS class. The user can specify their own parameters as demonstrated in run.py

```shell
from openhens import OpenHENS
options = { 'input_folder': f'examples/cases/Four-stream-Yee-and-Grossmann-1990-1.csv', 
            'output_folder': f'examples/results/Four-stream-Yee-and-Grossmann-1990-1', 
            'min_dT_list': [10],
            'min_dqda_list': [1,2,3],
            'stage_selection': 'automated'
            'tolerance': 1e-3, 
            'max_parallel': 10, 
            'best_solns_to_save': 10, 
            'log_level': logging.WARNING, 
            } 
            
model = OpenHens(**options) 
model.solve()
```


## Deleting the Conda Environment

To delete the environment:

```bash
conda deactivate
conda remove -n openhens-env --all
```

This will **not affect** any other Conda environments or your base Python install.

---

# Citation

Please cite this work as:

```shell
openHENS v0.5
Ahuora Centre for Smart Energy Systems https://www.waikato.ac.nz/research/institutes-centres-entities/centres/ahuora-centre-for-smart-energy-systems/
https://github.com/waikato-ahuora-smart-energy-systems/OpenHENS
```

## 💡 Notes

- If using **VSCode**, make sure to install the **Python extension by Microsoft**, and select the `openhens-env` interpreter.
- If you modify the codebase, the `-e .` install ensures changes are reflected automatically without re-installing.

---
