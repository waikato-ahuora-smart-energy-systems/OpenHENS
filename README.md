# OpenHENS

Open-source, equation-based synthesis and optimisation of heat exchanger networks 
Models apply the Gekko modelling language (https://github.com/BYU-PRISM/GEKKO) and solve using the open-source APOPT solver (https://apopt.com/) or COIN-OR solvers (https://www.coin-or.org)

The current version is 0.5. Active refactor work is focused on
- improved usability through a typed public API
- pytest coverage for fast checks and solver regressions
- user guides and documentation
- packaging through pip
- integration into the Ahuora Platform
- safer durable result artifacts


## Installation

The preferred development install uses `uv`, which reads `pyproject.toml` and creates a managed environment from the lockfile.

### 1. Clone the Repository

```bash
git clone https://github.com/waikato-ahuora-smart-energy-systems/OpenHENS.git
cd OpenHENS
```

### 2. Install uv

Install `uv` using the official instructions:
https://docs.astral.sh/uv/getting-started/installation/

### 3. Create the Environment

```bash
uv sync --dev
```

### 4. Run Fast Tests

```bash
uv run pytest -m "not solver"
```

Solver binaries are still installed separately from the Python environment. The
optional benchmark regressions run the mathematical solvers against the saved
Four-stream and Nine-stream baselines:

```bash
uv run pytest -m solver
```

---

## 5. Installation of COIN-OR solvers
COIN-OR solvers must be installed independently of the Python environment. This can be done by downloading the binaries for the desired solvers
from the COIN-OR website https://www.coin-or.org/download/binary. 

Once the binaries are downloaded, extract and save them to a local file e.g User\Documents\Solvers. The solver .exe path must then be added to the PATH which is done through the 'Environment Variables' program native to Windows systems. 

More detailed instructions can be found here: https://www.jdhp.org/docs/notebook/python_pyomo_getting_started_0_installation_instructions_pyomo_and_solvers.html


## Usage
Build a study from the public API objects, then pass it to `OpenHENS.solve()`:

```python
from pathlib import Path

from openhens import (
    CaseStudy,
    DesignSpace,
    MethodSequence,
    OpenHENS,
    SolveSetup,
    StudyOutputs,
    SynthesisStudy,
)

study = SynthesisStudy(
    case=CaseStudy.from_csv("examples/cases/Four-stream-Yee-and-Grossmann-1990-1.csv"),
    design_space=DesignSpace(
        approach_temperatures=(2, 4, 6, 8, 10, 12, 14, 16, 18, 20),
        derivative_thresholds=(0.5, 0.9, 1.3, 1.7, 2.1, 2.4, 2.8, 3.2, 3.6, 4.0),
    ),
    methods=MethodSequence.standard_pdm_tdm_esm(),
    solving=SolveSetup.local(tolerance=1e-3, max_parallel=10),
    outputs=StudyOutputs(
        folder=Path("examples/results/Four-stream-Yee-and-Grossmann-1990-1"),
        run_id="example-run",
        formats=("json", "csv"),
        include_excel=False,
        include_plots=False,
    ),
)

outcome = OpenHENS(study).solve()
print(outcome.manifest.run_id)
```

The fast test suite excludes solver regressions by default:

```bash
uv run pytest -m "not solver"
```

To reproduce the saved benchmark workbooks, run the optional solver tests:

```bash
uv run pytest -m solver
```


## Removing the uv Environment

To remove the local virtual environment:

```bash
rm -rf .venv
```

---

# Citation

Please cite this work as:

```shell
openHENS v0.5
Ahuora Centre for Smart Energy Systems https://www.waikato.ac.nz/research/institutes-centres-entities/centres/ahuora-centre-for-smart-energy-systems/
https://github.com/waikato-ahuora-smart-energy-systems/OpenHENS
```

## 💡 Notes

- If using **VSCode**, make sure to install the **Python extension by Microsoft**, and select the `.venv` interpreter created by `uv`.
- `uv run ...` runs commands inside the managed environment.

---
