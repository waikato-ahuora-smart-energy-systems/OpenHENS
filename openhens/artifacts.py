"""Write and reload the durable JSON/CSV artifacts for a study run."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .domain import (
    NetworkSolution,
    SolutionPortfolio,
    StudyManifest,
    StudyOutcome,
    StudyOutputs,
    SynthesisStudy,
    TaskOutcome,
)


ESM_ATTEMPT_WEIGHT = 11
SOLUTION_METRIC_COLUMNS = (
    "Date",
    "Task ID",
    "Name",
    "Method",
    "dTmin",
    "min_dQ",
    "Solve Time",
    "ESM TAC",
    "Stages",
    "N Recovery Units",
    "N CU Units",
    "N HU Units",
    "Total Annual Cost",
    "Model Objective Value",
    "Solver",
    "Solver Status",
    "Verification Failures",
)
RUN_SUMMARY_COLUMNS = (
    "Date",
    "Run ID",
    "Study Name",
    "Best Solution",
    "Best Task ID",
    "Total Cases Attempted",
    "Total Cases Solved",
    "Total Run Time (s)",
    "Quartile 1",
    "Quartile 2",
    "Quartile 3",
    "Within 2%",
    "Within 5%",
    "Within 10%",
)


def write_study_artifacts(
    study: SynthesisStudy,
    task_outcomes: Sequence[TaskOutcome],
    *,
    total_run_time_seconds: float | None,
    attempted_solver_jobs: int,
    outputs: StudyOutputs | None = None,
    run_id: str | None = None,
    created_at: datetime | str | None = None,
    completed_at: datetime | str | None = None,
) -> StudyOutcome:
    """Persist one run's artifacts and return a reconstructable outcome.

    The on-disk layout is intentionally stable:

    - ``manifest.json`` describes the run and lists every emitted artifact.
    - ``results/<task_id>.json`` stores one serialized ``TaskOutcome`` per task.
    - ``metrics/*.csv`` stores the summary tables that downstream tooling reads.

    Optional workbook and plot exports extend that layout without changing the
    JSON/CSV contract used by tests and reload paths.
    """

    outputs = outputs or study.outputs
    run_id = run_id or outputs.run_id or _default_run_id()
    run_folder = outputs.folder / run_id
    results_folder = run_folder / "results"
    metrics_folder = run_folder / "metrics"
    # Keep the artifact tree predictable so manifests can use relative paths.
    results_folder.mkdir(parents=True, exist_ok=True)
    metrics_folder.mkdir(parents=True, exist_ok=True)

    created_at_text = _timestamp(created_at)
    completed_at_text = _timestamp(completed_at) if completed_at is not None else _timestamp(None)

    result_paths: list[Path] = []
    for outcome in task_outcomes:
        result_path = Path("results") / f"{outcome.task_id}.json"
        _write_json(run_folder / result_path, outcome.model_dump(mode="json"))
        result_paths.append(result_path)

    portfolio = SolutionPortfolio(
        solutions=tuple(
            outcome.solution for outcome in task_outcomes if outcome.success and outcome.solution is not None
        )
    )
    manifest = StudyManifest(
        run_id=run_id,
        study_name=study.name,
        study=study,
        case_hash=_case_hash(study),
        package_version=_package_version(),
        solver_metadata=_solver_metadata(task_outcomes),
        created_at=created_at_text,
        completed_at=completed_at_text,
        total_run_time_seconds=total_run_time_seconds,
        attempted_solver_jobs=attempted_solver_jobs,
        manifest_path=Path("manifest.json"),
        result_paths=tuple(result_paths),
        solution_metrics_path=Path("metrics/solution_metrics.csv"),
        run_summary_path=Path("metrics/run_summary.csv"),
    )
    outcome = StudyOutcome(
        study=study,
        solutions=portfolio,
        manifest=manifest,
        task_outcomes=tuple(task_outcomes),
        total_run_time_seconds=total_run_time_seconds,
        attempted_solver_jobs=attempted_solver_jobs,
    )

    solution_metrics = solution_metric_rows(portfolio.solutions, date=completed_at_text)
    run_summary = run_summary_rows(outcome, date=completed_at_text)
    _write_csv(run_folder / manifest.solution_metrics_path, SOLUTION_METRIC_COLUMNS, solution_metrics)
    _write_csv(run_folder / manifest.run_summary_path, RUN_SUMMARY_COLUMNS, run_summary)

    excel_paths: tuple[Path, ...] = ()
    if outputs.include_excel:
        # Workbook export stays opt-in because it pulls in the pandas/openpyxl
        # stack and is not required for round-tripping study outcomes.
        excel_paths = _write_excel_artifacts(run_folder, solution_metrics, run_summary)

    plot_paths: tuple[Path, ...] = ()
    if outputs.include_plots and solution_metrics:
        # Plot generation is also optional and only meaningful once there are
        # solved rows to visualise.
        plot_paths = _write_plot_artifacts(run_folder, solution_metrics)

    manifest = manifest.model_copy(
        update={
            "excel_paths": excel_paths,
            "plot_paths": plot_paths,
            "artifacts": _artifact_paths(manifest, excel_paths=excel_paths, plot_paths=plot_paths),
        }
    )
    outcome = outcome.model_copy(update={"manifest": manifest})
    _write_json(run_folder / "manifest.json", manifest.model_dump(mode="json"))
    return outcome


def load_study_outcome(manifest: str | Path | StudyManifest) -> StudyOutcome:
    """Reconstruct a ``StudyOutcome`` from a manifest and its result payloads.

    Relative paths in ``manifest.json`` are resolved from the manifest's parent
    folder so copied run directories remain self-contained. When a
    ``StudyManifest`` object is passed directly, no source folder is available;
    relative paths are resolved from the current working directory.
    """

    if isinstance(manifest, StudyManifest):
        manifest_model = manifest
        base_folder = Path(".")
    else:
        manifest_path = Path(manifest)
        if manifest_path.is_dir():
            manifest_path = manifest_path / "manifest.json"
        base_folder = manifest_path.parent
        manifest_model = StudyManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))

    if manifest_model.study is None:
        raise ValueError("manifest does not contain a reconstructable study payload")

    task_outcomes = tuple(
        TaskOutcome.model_validate(json.loads(_resolve_artifact_path(base_folder, path).read_text(encoding="utf-8")))
        for path in manifest_model.result_paths
    )
    portfolio = SolutionPortfolio(
        solutions=tuple(outcome.solution for outcome in task_outcomes if outcome.success and outcome.solution is not None)
    )
    return StudyOutcome(
        study=manifest_model.study,
        solutions=portfolio,
        manifest=manifest_model,
        task_outcomes=task_outcomes,
        total_run_time_seconds=manifest_model.total_run_time_seconds,
        attempted_solver_jobs=manifest_model.attempted_solver_jobs,
    )


def solution_metric_rows(
    solutions: Iterable[NetworkSolution],
    *,
    date: str | None,
) -> list[dict[str, object]]:
    """Project solved network models into the stable solution-metrics schema."""
    rows: list[dict[str, object]] = []
    for solution in solutions:
        unit_counts = solution.unit_counts
        solver = solution.solver
        rows.append(
            {
                "Date": date or "",
                "Task ID": solution.task_id or "",
                "Name": solution.name,
                "Method": solution.method or "",
                "dTmin": solution.approach_temperature
                if solution.approach_temperature is not None
                else solution.dTmin,
                "min_dQ": solution.derivative_threshold
                if solution.derivative_threshold is not None
                else solution.min_dqda,
                "Solve Time": solver.solve_time if solver is not None else None,
                "ESM TAC": solution.total_annual_cost,
                "Stages": solution.stages,
                "N Recovery Units": unit_counts.get("recovery"),
                "N CU Units": unit_counts.get("cold_utility"),
                "N HU Units": unit_counts.get("hot_utility"),
                "Total Annual Cost": solution.total_annual_cost,
                "Model Objective Value": solution.model_objective_value,
                "Solver": solver.name if solver is not None else "",
                "Solver Status": solver.status if solver is not None else "",
                "Verification Failures": "; ".join(solution.verification_failures),
            }
        )
    return rows


def run_summary_rows(outcome: StudyOutcome, *, date: str | None) -> list[dict[str, object]]:
    """Build the single-row run summary consumed by regression baselines."""
    solutions = [
        solution
        for solution in outcome.solutions.solutions
        if solution.total_annual_cost is not None and np.isfinite(solution.total_annual_cost)
    ]
    costs = [solution.total_annual_cost for solution in solutions]
    quartiles = np.quantile(costs, [0.25, 0.5, 0.75]) if costs else [0, 0, 0]
    best = outcome.solutions.best_by_total_annual_cost()
    best_tac = best.total_annual_cost if best is not None else 0
    thresholds = {
        f"Within {int(threshold * 100)}%": sum(
            solution.total_annual_cost <= best_tac * (1 + threshold) for solution in solutions
        )
        if best is not None
        else 0
        for threshold in (0.02, 0.05, 0.10)
    }

    return [
        {
            "Date": date or "",
            "Run ID": outcome.manifest.run_id or "",
            "Study Name": outcome.study.name or "",
            "Best Solution": best_tac,
            "Best Task ID": best.task_id if best is not None else "",
            "Total Cases Attempted": outcome.attempted_solver_jobs,
            # Historical spreadsheets count one successful ESM sweep as eleven
            # attempted cases, so the CSV summary preserves that convention.
            "Total Cases Solved": _weighted_success_count(outcome.task_outcomes),
            "Total Run Time (s)": outcome.total_run_time_seconds,
            "Quartile 1": quartiles[0],
            "Quartile 2": quartiles[1],
            "Quartile 3": quartiles[2],
            **thresholds,
        }
    ]


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, columns: Sequence[str], rows: Sequence[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_excel_artifacts(
    run_folder: Path,
    solution_metrics: Sequence[dict[str, object]],
    run_summary: Sequence[dict[str, object]],
) -> tuple[Path, ...]:
    """Write the legacy workbook exports expected by older result bundles."""
    solution_path = Path("metrics") / "Solution Metrics.xlsx"
    summary_path = Path("metrics") / "Run Metrics.xlsx"
    pd.DataFrame(solution_metrics, columns=SOLUTION_METRIC_COLUMNS).to_excel(run_folder / solution_path, index=False)
    pd.DataFrame(run_summary, columns=RUN_SUMMARY_COLUMNS).to_excel(run_folder / summary_path, index=False)
    return (solution_path, summary_path)


def _write_plot_artifacts(run_folder: Path, solution_metrics: Sequence[dict[str, object]]) -> tuple[Path, ...]:
    """Generate Plotly-derived study plots and return only the new artifact paths."""
    from .analysis.analysis_tools import plot_metric_relationships

    metrics = pd.DataFrame(solution_metrics, columns=SOLUTION_METRIC_COLUMNS)
    before = set(run_folder.glob("*.html")) | set(run_folder.glob("*.png"))
    plot_metric_relationships(metrics=metrics, path=run_folder, show=False)
    after = set(run_folder.glob("*.html")) | set(run_folder.glob("*.png"))
    return tuple(sorted((path.relative_to(run_folder) for path in after - before), key=str))


def _artifact_paths(
    manifest: StudyManifest,
    *,
    excel_paths: Sequence[Path],
    plot_paths: Sequence[Path],
) -> tuple[Path, ...]:
    """Return the manifest's complete artifact inventory in stable display order."""
    paths: list[Path] = [manifest.manifest_path, *manifest.result_paths]
    if manifest.solution_metrics_path is not None:
        paths.append(manifest.solution_metrics_path)
    if manifest.run_summary_path is not None:
        paths.append(manifest.run_summary_path)
    paths.extend(excel_paths)
    paths.extend(plot_paths)
    return tuple(paths)


def _solver_metadata(task_outcomes: Sequence[TaskOutcome]) -> tuple[dict[str, object], ...]:
    """Capture lightweight per-task solver details for later inspection."""
    records = []
    for outcome in task_outcomes:
        solver = outcome.solver or (outcome.solution.solver if outcome.solution is not None else None)
        records.append(
            {
                "task_id": outcome.task_id,
                "method": outcome.task.method,
                "solver": solver.name if solver is not None else outcome.task.solver,
                "status": solver.status if solver is not None else None,
                "solve_time": solver.solve_time if solver is not None else None,
                "failure_reason": outcome.failure_reason,
            }
        )
    return tuple(records)


def _weighted_success_count(task_outcomes: Sequence[TaskOutcome]) -> int:
    """Count solved tasks using the workbook-era weighting for ESM sweeps."""
    return sum(
        ESM_ATTEMPT_WEIGHT if outcome.task.method == "ESM" else 1
        for outcome in task_outcomes
        if outcome.success
    )


def _case_hash(study: SynthesisStudy) -> str:
    source = study.case.source
    if source.exists():
        return hashlib.sha256(source.read_bytes()).hexdigest()
    payload = json.dumps(study.case.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _package_version() -> str:
    try:
        return metadata.version("openhens")
    except metadata.PackageNotFoundError:
        return "unknown"


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _timestamp(value: datetime | str | None) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_artifact_path(base_folder: Path, path: Path) -> Path:
    return path if path.is_absolute() else base_folder / path
