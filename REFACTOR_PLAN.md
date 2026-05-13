# OpenHENS Phase-One Refactor Plan

## Summary
Refactor OpenHENS around safer local execution while preserving current mathematical behavior. Phase one will not add new HEN modeling features or distributed execution; it will introduce typed schemas, explicit job/result boundaries, strict validation, stable JSON/CSV artifacts, uv-based packaging, and automated guardrails.

## Key Changes
- Add `pyproject.toml` as the dependency source of truth, managed with `uv`, targeting Python 3.12 and adding `pydantic v2`. Generate `uv.lock` and remove `requirements.txt` and `setup.py`.
- Replace mutable `OpenHensOptions` with Pydantic domain entry objects: `SynthesisStudy`, `CaseStudy`, `DesignSpace`, `MethodSequence`, `SolveSetup`, and `StudyOutputs`.
- Keep an `OpenHENS` facade, but make the preferred API `OpenHENS(study: SynthesisStudy).solve() -> StudyOutcome`. Old `**kwargs` compatibility is not required.
- Add strict CSV parsing into a validated `CaseStudy`; fail fast with clear messages for missing fields, invalid numeric data, impossible stream temperatures, and unsupported schema shapes.
- Introduce `SynthesisTask`, `TaskOutcome`, `StudyOutcome`, `SolutionPortfolio`, `NetworkSolution`, and `StudyManifest`. Tasks describe PDM/TDM/ESM jobs; outcomes store status, timings, objective metrics, unit counts, topology, parent IDs, solver metadata, and artifact paths.
- Move PDM -> TDM -> ESM coordination out of `OpenHENS` into a pipeline/workflow module. Keep `StageWiseModel`, `PinchDecompModel`, and equations mostly intact in phase one.
- Centralize current GEKKO/Pyomo solver setup in a solver wrapper/helper: preserve current defaults, validate solver availability, apply options consistently, and record solver metadata.
- Replace pickle persistence with a per-run artifact directory containing `manifest.json`, per-problem result JSON, metrics CSVs, and optional Excel compatibility outputs. Pickle writing is removed.
- Keep plotting/reporting separate from solving; plots should consume stable metrics artifacts instead of solved Python objects.

## Public API
The public API should use domain-first names rather than generic configuration names.

```python
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
        approach_temperatures=[2, 4, 6, 8, 10],
        derivative_thresholds=[0.5, 1.0, 2.0, 4.0],
        stage_selection="automated",
    ),
    methods=MethodSequence.standard_pdm_tdm_esm(),
    solving=SolveSetup.local(
        tolerance=1e-3,
        max_parallel=10,
        pdm_solver="couenne",
        tdm_solver="couenne",
        esm_solver="ipopt-pyomo",
    ),
    outputs=StudyOutputs(
        folder="examples/results/Four-stream-Yee-and-Grossmann-1990-1",
        formats=["json", "csv"],
        include_excel=False,
        include_plots=False,
    ),
)

outcome = OpenHENS(study).solve()
best = outcome.solutions.best_by_total_annual_cost()
```

Name mapping for implementation:
- `SynthesisStudy`: top-level aggregate root for one HEN synthesis study.
- `CaseStudy`: validated process streams, utility streams, and exchanger economics.
- `DesignSpace`: approach-temperature grid, derivative-threshold grid, and stage selection.
- `MethodSequence`: ordered synthesis methods, initially standard PDM -> TDM -> ESM.
- `SolveSetup`: local solving controls such as solvers, tolerances, and parallelism.
- `StudyOutputs`: artifact location and requested output formats.
- `SynthesisTask`: one concrete PDM, TDM, or ESM solve generated from the study.
- `TaskOutcome`: result of one concrete synthesis task.
- `StudyOutcome`: overall result of a completed synthesis study.
- `SolutionPortfolio`: ranked collection of candidate HEN solutions.
- `NetworkSolution`: one solved heat exchanger network candidate.
- `StudyManifest`: durable provenance and artifact map.

## Artifact Layout
Use `output_folder/<run_id>/` for each run. If no `run_id` is provided, generate a timestamped ID; tests may provide a fixed ID.

Required artifacts:
- `manifest.json`
- `results/<problem_id>.json`
- `metrics/solution_metrics.csv`
- `metrics/run_summary.csv`

Optional artifacts:
- Excel workbooks when `StudyOutputs.include_excel=True`
- Plotly HTML/PNG reports when reporting is explicitly requested

## Implementation Steps
This refactor is split into reviewable steps. Each step has its own checklist, review criteria, and definition of done:

- [Step 1: Project Baseline and Public API](docs/refactor/01-project-baseline-and-public-api.md)
- [Step 2: Case Study Parsing and Validation](docs/refactor/02-case-study-parsing-and-validation.md)
- [Step 3: Synthesis Tasks and Workflow](docs/refactor/03-synthesis-tasks-and-workflow.md)
- [Step 4: Solver Wrapper and Task Outcomes](docs/refactor/04-solver-wrapper-and-task-outcomes.md)
- [Step 5: Study Artifacts and Reporting](docs/refactor/05-study-artifacts-and-reporting.md)
- [Step 6: Regression Tests and Documentation](docs/refactor/06-regression-tests-and-documentation.md)

## Test Plan
- Add fast default tests for config validation, CSV parsing, pipeline job generation, artifact writing, result serialization, and failure handling.
- Add fake-executor workflow tests proving only successful PDM results spawn TDM jobs, only successful TDM results spawn ESM jobs, and failed jobs are recorded without corrupting downstream artifacts.
- Add marked optional solver regression tests using the two cases that already have saved result workbooks:
  - `examples/cases/Four-stream-Yee-and-Grossmann-1990-1.csv`
  - `examples/cases/Nine-stream-Linnhoff-and-Ahmad-1999-1.csv`
- Treat the existing `Run Metrics.xlsx` and `Solution Metrics.xlsx` files for those cases as the phase-one numerical baselines. The tests should load those workbooks, run the same study inputs, and compare the newly generated JSON/CSV metrics against the saved baseline values.
- Regression tests must confirm that each benchmark reproduces the same scientific result within reasonable numerical tolerance:
  - Best ESM TAC is within less than 1% relative error from the workbook baseline.
  - Quartile TAC values are within less than 1% relative error from the workbook baseline.
  - Within-2%/5%/10% solution counts are exact where deterministic, or differ by no more than one solution when solver tie-breaking changes near a threshold.
  - Total attempted jobs and solved ESM solution counts match expectations unless a solver failure is explicitly captured and explained.
  - The best solution's stage count and recovery/CU/HU unit counts match the baseline.
  - The `(dTmin, derivative_threshold)` coordinates of the best solution match the baseline, or the test documents a tie when several solutions are numerically equivalent.
- Ignore non-scientific run fields in regression comparisons: date, wall-clock solve time, generated run ID, artifact paths, and plot file metadata.
- Use tolerance constants in the tests rather than inline numbers. Start with `TAC_REL_TOL = 1e-4` and `TAC_ABS_TOL = 1.0`; any future widening must remain below `MAX_REGRESSION_REL_TOL = 1e-2`.
- Default CI runs `uv run pytest -m "not solver"`. Solver regressions run manually with `uv run pytest -m solver`.

## Assumptions
- Phase one is behavior-preserving: no forced utility matrix, no multiple utility-level support, no changed solver defaults, and no equation refactor unless required for boundaries.
- Strict validation still supports the current example CSV shape, including optional temperature-contribution data.
- Results persist enough summary and topology data for analysis, but not full GEKKO model state.
- Distributed execution remains a later phase, after specs/results/artifacts are stable locally.
