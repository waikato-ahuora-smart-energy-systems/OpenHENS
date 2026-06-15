# Step 5: Study Artifacts and Reporting

## Goal
Replace pickle-centered persistence with stable per-run study artifacts and make reporting consume those artifacts.

## Scope
- Introduce `StudyManifest`, `StudyOutcome`, and `SolutionPortfolio`.
- Write JSON and CSV artifacts under a per-run directory.
- Keep Excel and plots optional through `StudyOutputs`.
- Remove default pickle persistence from the workflow.

## Checklist
- [x] Create the per-run output layout: `manifest.json`, `results/<task_id>.json`, `metrics/solution_metrics.csv`, and `metrics/run_summary.csv`.
- [x] Implement `StudyManifest` with study metadata, case hash, package version, solver metadata, timestamps, and artifact paths.
- [x] Implement `SolutionPortfolio.best_by_total_annual_cost()`.
- [x] Generate solution metrics CSV from `NetworkSolution` records.
- [x] Generate run summary CSV from `StudyOutcome`.
- [x] Add optional Excel export when `StudyOutputs.include_excel=True`.
- [x] Add optional Plotly HTML/PNG generation when `StudyOutputs.include_plots=True`.
- [x] Remove default writing of `N best.pkl` files.
- [x] Update `open_best.py` or replace it with an artifact-based example.

## Review Criteria
- JSON and CSV are the primary durable outputs.
- Artifacts are deterministic enough for tests when a fixed run ID is supplied.
- Plotting and Excel generation do not run unless requested.
- Pickle is not required to inspect the best solution or metrics.

## Definition of Done
- A completed study writes all required artifacts to `output_folder/<run_id>/`.
- `StudyOutcome` can be reconstructed from the manifest and result JSON files.
- Existing metric columns needed by the benchmark workbooks are preserved in CSV form.

## Implementation Record
- Implemented durable artifact writing/loading in `openhens/artifacts.py`.
- Added artifact domain models and `StudyOutcome.from_artifacts()`.
- Updated `OpenHENS.solve()` to return `StudyOutcome` and stop writing default pickle files.
- Replaced `open_best.py` with an artifact-based best-solution reader.
- Kept Excel and Plotly generation behind `StudyOutputs.include_excel` and `StudyOutputs.include_plots`.
- Made artifact inspection imports lightweight by lazy-loading `OpenHENS`, removing pickle/analysis re-exports from `openhens.utils`, and importing Plotly only inside optional plot artifact generation.
- Reworked `OpenHENS.display_run_metrics()` to report existing manifest CSV paths without creating Excel, plots, or browser-visible output.

## Review Record
- Reviewer: Step 5 reviewer agent `019e1faa-24e9-7031-b138-a922528f45c4`.
- Result: PASS.
- Findings: none blocking.
- Verification: `rtk uv run pytest openhens/tests/test_artifacts.py -q` passed with 5 tests, import subprocess checks confirmed artifact inspection does not import `gekko`, `plotly`, `openhens.main`, or pickle helper modules, and `rtk uv run pytest -m "not solver" -q` passed with 53 tests.
- Decision: The reviewer confirmed the Step 5 findings were resolved and cleared the plan to move to Step 6.
