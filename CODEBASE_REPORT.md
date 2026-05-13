# OpenHENS Codebase Report

## Purpose and current behavior

OpenHENS is a Python package for synthesis and optimisation of heat exchanger networks (HENs) from CSV case data. The user-facing entry point is `OpenHENS` in `openhens/main.py`, with an example script in `run.py`.

At a high level, a run does the following:

1. Reads a case CSV containing hot streams, cold streams, utility data, and exchanger cost parameters.
2. Builds a family of HEN optimisation problems over a sweep of `dTmin` values.
3. Solves those problems with a pinch decomposition method (PDM) to identify utility-optimal stage structures.
4. Expands each PDM solution into a family of thermal-derivative method (TDM) problems over a sweep of `(dQ/dA)min` values.
5. Expands each TDM solution into an evolutionary synthesis method (ESM) problem that relaxes integrality and optimises variable total annual cost.
6. Saves the best solutions as pickles and generates run metrics and HTML/PNG plots.

The intended workflow is therefore not a single solve, but a coordinated search over a design space:

- `dTmin` controls the pinch decomposition instances.
- `(dQ/dA)min` controls screening/refinement of exchanger matches.
- The final ESM step refines network economics and optionally evolves the topology.

This is a sensible workflow for engineers and scientists because it balances thermodynamic structure, screening heuristics, and economic refinement instead of relying on one monolithic MINLP from the start.

## How the code currently works

### Top-level orchestration

`openhens/main.py` owns the main run pipeline.

- `OpenHensOptions` stores user options as mutable attributes populated from keyword arguments.
- `OpenHENS.solve()` resolves input and output paths, runs `_get_optimal_network()`, ranks solutions by TAC, and persists the top `n` solutions as pickle files.
- `display_run_metrics()`, `display_best_from_run()`, and `display_n_best_from_file()` handle reporting and visualisation.

The central control flow is `_get_optimal_network()`:

1. Create one `HeatExchangerNetworkProblem` per `dTmin` for the PDM layer.
2. Solve those in parallel with `run_parallel_solutions()`.
3. For every successful PDM solution, create one TDM problem per `min_dqda`.
4. Solve those in parallel.
5. For every successful TDM solution, create one ESM problem.
6. Solve those in parallel, optionally running network evolution.
7. Combine solved problems, save summary metrics, and return the solved objects.

This means the current parallelism is coarse-grained and embarrassingly parallel at the problem level, but stage-to-stage coordination is still performed in one local process.

### Problem abstraction

`openhens/classes/HEN_problem.py` provides `HeatExchangerNetworkProblem`, which is the bridge between orchestration and specific model implementations.

Its responsibilities are:

- Hold the problem metadata and solver settings.
- Decide whether the requested framework is `PDM`, `TDM`, or `ESM`.
- Build either a `PinchDecompModel` or a `StageWiseModel`.
- Solve the model, optionally reduce unused stages, optionally run evolution, and return the solved case.

This object currently acts as both:

- A job specification.
- A mutable container for parents, solved models, arguments, and post-processed results.

That dual role is one of the main architectural pressure points in the codebase.

### Solver/model layer

The numerical model logic is concentrated in three classes.

`openhens/classes/generic_model.py`

- Abstract base class for GEKKO-backed models.
- Configures the solver backend (`couenne`, `ipopt-pyomo`, `apopt`, `ipopt-GEKKO`).
- Loads case data from CSV.
- Applies match restrictions.
- Calls `m.solve()` and then triggers post-processing.

`openhens/classes/pinch_decomp_model.py`

- Specialises the generic model for pinch decomposition.
- Computes pinch location using the `pinch_classes` package.
- Splits the case into above-pinch and below-pinch submodels.
- Selects stages automatically or from user input.
- Solves subproblems and amalgamates them back into one stage-wise representation.

`openhens/classes/stage_wise_model.py`

- Implements the stage-wise superstructure for TDM and ESM.
- Creates recovery, utility, temperature, and binary variables.
- Supports both isothermal and non-isothermal formulations.
- Builds objectives for utility, heat recovery, or cost.
- Computes post-processed areas, unit counts, TAC, `dQ/dA`, `alpha`, and evolution heuristics.
- Contains logic to remove unused stages and perform plus/minus-one network evolution.

The mathematical modelling work is the strongest part of the repository. The abstractions are solver-oriented and reflect real HEN reasoning: feasible matches, stage superstructures, pinch decomposition, utility targeting, area-based costs, and heuristic topology evolution.

### Parallel execution

`openhens/utils/branching.py` runs local parallel solves using `multiprocessing.Pool`.

- `run_parallel_solutions()` launches one async task per `HeatExchangerNetworkProblem`.
- `run_single_solution()` solves one problem, verifies it, and returns the solved problem object if valid.

This is simple and effective for workstation-scale parameter sweeps, but it depends on Python object pickling and assumes shared local file system semantics.

### Analysis, persistence, and visualisation

Analysis and persistence are spread across:

- `openhens/analysis/analysis_tools.py` for ranking, metrics tables, and plot generation.
- `openhens/analysis/solution_verification.py` for temperature, area, and cost verification.
- `openhens/utils/solution_saver.py` and `solution_loader.py` for pickle persistence.
- `openhens/classes/grid_diagram.py` for grid-diagram visualisation.

Outputs currently include:

- Pickled best solutions.
- Excel workbooks with run and solution metrics.
- Plotly HTML and PNG charts.
- Matplotlib grid diagrams.

## Architectural assessment

### What is already good

- The core HEN workflow is aligned with engineering practice rather than generic optimisation boilerplate.
- The package exposes a simple top-level API for users.
- The PDM -> TDM -> ESM pipeline is explicit and understandable.
- Verification exists and is integrated into the solve path.
- The package can already exploit multi-core workstations through local multiprocessing.
- Example cases and saved outputs make the package easier to evaluate.

### Main architectural limitations

The main issues are not in the equations. They are in composition, data ownership, and runtime boundaries.

1. Orchestration, domain logic, solving, persistence, and plotting are tightly coupled.

`OpenHENS`, `HeatExchangerNetworkProblem`, and `StageWiseModel` collectively own too many concerns. A single solve object can contain configuration, parent lineage, solver model, solved variables, reporting metrics, and persistence-relevant state.

2. Runtime objects are being used as transport objects.

Parallel workers receive rich mutable objects, not compact immutable job specifications. That is acceptable locally with `multiprocessing`, but it becomes fragile for distributed execution, reproducibility, and versioned persistence.

3. The modelling layer mixes optimisation logic with post-processing and heuristic search.

`StageWiseModel` contains variable construction, objective construction, post-processing, stage reduction, alpha calculations, and evolutionary topology search. This makes the class hard to test and hard to change safely.

4. There is no formal data schema for inputs, options, results, or artifacts.

Engineers and scientists usually need reproducibility, auditability, and confidence in units and assumptions. At the moment, inputs are inferred from CSV layout and outputs are largely pickled Python objects plus spreadsheets.

5. Persistence is convenience-oriented rather than analysis-oriented.

Pickle is useful for quick local reuse, but it is brittle across code changes and poor for interoperability with other tools.

6. The codebase is light on automated tests.

There is a `tests` package, but essentially no implemented test suite. For scientific software, that is a material risk because numerical regressions can hide inside valid-looking solutions.

7. The concurrency model is local only.

The current implementation assumes one Python process can create and coordinate all tasks. There is no durable task queue, no artifact store abstraction, no retry model, and no notion of distributed dependency scheduling.

## Recommended module and architectural changes

The biggest improvement would be to separate the code by responsibility and by lifecycle.

### 1. Split configuration, jobs, models, and results

Introduce explicit data models, ideally with `dataclasses` or `pydantic` models:

- `CaseInput`: parsed stream and utility data from CSV.
- `RunConfig`: user options such as `dTmin` grid, `min_dqda` grid, solver choices, tolerances, and parallelism.
- `ProblemSpec`: immutable description of a single PDM, TDM, or ESM solve.
- `ProblemResult`: compact solved summary with objective values, status, timings, selected topology, and artifact references.
- `SolutionArtifactManifest`: references to plots, tables, diagrams, and any serialized detailed model state.

This change would make the system much easier to reason about, test, persist, and distribute.

### 2. Create a pipeline/orchestrator module

Move the PDM -> TDM -> ESM coordination out of `OpenHENS` into a dedicated orchestration layer, for example:

- `pipeline/builders.py`: generate downstream `ProblemSpec` objects from upstream results.
- `pipeline/executor.py`: run a batch using a pluggable executor.
- `pipeline/workflow.py`: manage stage ordering, retries, and aggregation.

Then `OpenHENS` becomes a thin facade over that workflow.

### 3. Isolate solver adapters from mathematical model definitions

Keep the equations, but separate them from backend concerns.

Suggested split:

- `models/pdm.py` and `models/stagewise.py` for framework logic.
- `solvers/gekko_backend.py` for GEKKO setup and solve lifecycle.
- `solvers/pyomo_backend.py` if the codebase later grows direct Pyomo formulations.

This makes it easier to compare backends, capture solver metadata, and add remote execution wrappers.

### 4. Extract post-processing and verification into pure functions

Move the numerical reporting logic out of model classes where possible:

- `postprocess/areas.py`
- `postprocess/economics.py`
- `postprocess/topology.py`
- `verification/checks.py`

Pure functions that consume a solved state and return derived metrics are much easier to test than methods that mutate large model objects.

### 5. Formalise artifact storage

Replace ad hoc output writes with a simple repository abstraction:

- `artifacts/local_fs.py`
- `artifacts/manifest.py`

The repository should know how to save:

- tabular metrics as CSV or Parquet
- plots as HTML/PNG
- detailed network topologies as JSON
- optional full solver snapshots as pickle for local debugging only

For engineering users, JSON plus tabular outputs are much safer and easier to integrate than opaque Python pickles.

### 6. Add a proper CLI and batch-run interface

For scientific users, a script is not enough. Add a CLI such as:

`openhens solve case.csv --config config.yaml`

and optionally:

`openhens batch run-manifest.yaml`

This would improve reproducibility, help cluster execution, and reduce the need to edit Python files for every run.

### 7. Add tests at three levels

Recommended test layers:

- Unit tests for CSV parsing, match restriction logic, stage reduction, and post-processing.
- Regression tests on a few canonical case studies checking utility targets, unit counts, and TAC ranges.
- Workflow tests ensuring the PDM -> TDM -> ESM pipeline produces expected numbers of jobs and artifacts.

For scientific code, regression fixtures around a small number of benchmark problems would provide high value quickly.

## Changes that especially help engineers and scientists

Because the intended users are engineers and scientists rather than software specialists, the most useful improvements are not only technical. They should reduce ambiguity and support repeatable studies.

Priority changes:

1. Add explicit input validation with clear error messages for missing fields, units, and impossible stream data.
2. Add configuration files in YAML or TOML so studies are self-documenting.
3. Export results in stable, analysis-friendly formats such as CSV, JSON, and Parquet.
4. Record provenance for every solve: code version, solver version, case file hash, options, timestamps, machine info.
5. Add benchmark comparison reports against literature examples in `examples/cases`.
6. Separate publication-quality reporting from internal debug output.
7. Add unit conventions and a documented case schema.

These changes would make OpenHENS more credible as a research and engineering platform, not just a useful codebase.

## High-level path to distributed coordinated solving

### What should be distributed

The most natural distributed unit is not the internal linear algebra of a single GEKKO solve. It is the solve jobs themselves.

In this repository, the strongest opportunities for distribution are:

- all PDM solves across `dTmin`
- all TDM solves across `(parent PDM, min_dqda)`
- all ESM solves across TDM parents
- potentially the plus/minus-one evolution branches for a candidate network

These are mostly independent tasks with clear upstream dependencies, which makes them well suited to distributed workflow execution.

### Recommended target architecture

Use a coordinator-worker model with explicit job specifications and durable artifacts.

Core components:

- `WorkflowCoordinator`: builds the dependency graph and releases jobs whose parents are complete.
- `Executor`: submits jobs to either local multiprocessing or a distributed backend.
- `Worker`: fetches a `ProblemSpec`, reconstructs the model, solves it, verifies it, and writes a `ProblemResult` plus artifacts.
- `ArtifactStore`: shared output store, local or remote.
- `ResultIndex`: lightweight metadata store tracking job status, parent-child lineage, timings, and objective summaries.

### Execution model

Represent the solve pipeline as a DAG:

- PDM jobs have no parents.
- TDM jobs depend on one PDM result.
- ESM jobs depend on one TDM result.
- Evolution jobs depend on one ESM result and possibly previous evolution depth.

The coordinator should:

1. Submit all PDM jobs.
2. Wait for completions.
3. Generate TDM jobs only from successful PDM results.
4. Generate ESM jobs only from successful TDM results.
5. Aggregate results continuously instead of only at the end.

This gives fault tolerance and makes long studies observable while they are still running.

### Technology options

There are several viable options, depending on how tightly coupled the distributed environment needs to be.

#### Option 1: Executor abstraction with local plus distributed backends

This is the best starting point.

Implement an executor interface and support:

- `LocalProcessExecutor` using current multiprocessing.
- `DaskExecutor` for cluster-scale Python task execution.
- `RayExecutor` for flexible remote Python workers.
- `CeleryExecutor` if job queuing and durability are more important than low-latency scheduling.

This option preserves current model code and mainly changes orchestration.

#### Option 2: MPI for HPC environments

MPI is appropriate if the target environment is a cluster where users already submit jobs through Slurm or similar systems.

Recommended MPI usage here is not fine-grained equation parallelism. It is rank-based distribution of independent solve jobs.

Example pattern:

- rank 0 acts as coordinator
- worker ranks request the next available `ProblemSpec`
- workers solve locally and send back compact `ProblemResult` records
- artifacts are written to a shared filesystem or object store

MPI is a good fit if users already work on HPC systems, but it imposes more operational complexity than Dask or Ray.

#### Option 3: Async event-driven coordination

An async architecture can help the coordinator side, especially if the system grows into a service.

Useful roles for async processing:

- submit jobs without blocking
- consume completion events
- stream intermediate metrics and logs
- trigger downstream job creation as events arrive

However, the solver work itself remains CPU-bound and external-process heavy, so async should coordinate tasks, not replace worker execution.

### Practical migration sequence

The cleanest path is incremental.

1. Introduce `ProblemSpec` and `ProblemResult` and stop sending rich mutable model objects across process boundaries.
2. Create an `Executor` interface and reimplement the current multiprocessing logic behind it.
3. Move output writing behind an artifact repository abstraction.
4. Add a coordinator that can release dependent jobs stage by stage.
5. Add one distributed backend, most likely Dask or Ray first.
6. Add MPI only if HPC deployment is a real target and the operational model justifies it.

### Important design constraints for distributed support

To make distributed solving reliable, OpenHENS should also adopt these rules:

- Jobs must be reconstructible from serialized specs alone.
- Results must be valid without loading pickled Python objects from worker memory.
- Every artifact path must be deterministic and collision-safe.
- Verification must run on the worker before the result is accepted.
- Failed jobs should be retryable without corrupting shared outputs.
- Logs and solver traces should be attached to job IDs.
- Downstream jobs should depend on explicit upstream result manifests, not in-memory parent objects.

## Recommended near-term roadmap

### Phase 1: Stabilise the local architecture

- Add input schemas, config files, and a CLI.
- Introduce `ProblemSpec` and `ProblemResult`.
- Extract post-processing and artifact writing from model classes.
- Add regression tests for benchmark cases.

### Phase 2: Make orchestration pluggable

- Build executor and coordinator abstractions.
- Keep the current local multiprocessing backend as the default.
- Replace direct pickle-based handoff with explicit serialized inputs and outputs.

### Phase 3: Add distributed execution

- Start with Dask or Ray for multi-machine studies.
- Add live run-state tracking and resumable workflows.
- Add MPI only if the project specifically targets HPC cluster users.

## Bottom line

OpenHENS already contains a meaningful HEN optimisation workflow with a clear scientific structure: pinch decomposition, derivative-based screening, and economic refinement. The core opportunity is not to redesign the equations, but to redesign the software boundaries around them.

If the repository is refactored around immutable job specs, compact result records, pluggable execution, and stable artifacts, it can become much stronger for its intended users and can support distributed coordinated solving without rewriting the mathematical core.