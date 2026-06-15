from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from openhens import (
    CaseStudy,
    DesignSpace,
    MethodSequence,
    OpenHENS,
    SolveSetup,
    StudyOutputs,
    SynthesisStudy,
)


pytestmark = [pytest.mark.solver, pytest.mark.slow]

# Tight tolerances catch meaningful TAC drift. The max constant is a guardrail:
# any future relaxation must remain below one percent.
TAC_REL_TOL = 1e-4
TAC_ABS_TOL = 1.0
MAX_REGRESSION_REL_TOL = 1e-2
# Bucket counts use this separate boundary check to allow one-count changes
# when solver tie-breaking places a solution exactly on a threshold.
THRESHOLD_TIE_REL_TOL = 1e-4

assert TAC_REL_TOL < MAX_REGRESSION_REL_TOL
assert THRESHOLD_TIE_REL_TOL < MAX_REGRESSION_REL_TOL

CASE_IDS = (
    "Four-stream-Yee-and-Grossmann-1990-1",
    "Nine-stream-Linnhoff-and-Ahmad-1999-1",
)


@dataclass(frozen=True)
class BaselineRun:
    """Workbook baseline slices for one historical case and one recorded run."""

    case_id: str
    run_metrics: pd.Series
    solution_metrics: pd.DataFrame


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_solver_regression_matches_saved_workbook_baselines(case_id: str, tmp_path: Path) -> None:
    """Compare fresh JSON/CSV artifacts against the latest workbook baseline."""
    baseline = _load_baseline(case_id)
    outcome = OpenHENS(
        SynthesisStudy(
            case=CaseStudy.from_csv(Path("examples/cases") / f"{case_id}.csv"),
            design_space=DesignSpace(),
            methods=MethodSequence.standard_pdm_tdm_esm(),
            solving=SolveSetup.local(),
            outputs=StudyOutputs(
                folder=tmp_path,
                run_id=case_id,
                formats=("json", "csv"),
                include_excel=False,
                include_plots=False,
            ),
        )
    ).solve()

    run_folder = tmp_path / case_id
    manifest_path = run_folder / "manifest.json"
    current_solutions = _current_esm_solution_metrics(run_folder)
    current_run = _single_row(pd.read_csv(run_folder / "metrics" / "run_summary.csv"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result_json_paths = [run_folder / path for path in manifest["result_paths"]]
    result_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in result_json_paths]
    current_esm_successes = [
        payload
        for payload in result_payloads
        if payload["success"] and payload["task"]["method"] == "ESM"
    ]

    _assert_artifacts_are_json_csv_only(manifest, run_folder, result_json_paths, outcome.attempted_solver_jobs)
    _assert_equal_metric(
        "attempted solver jobs",
        _int_metric(baseline.run_metrics, "Total Cases Attempted"),
        outcome.attempted_solver_jobs,
    )
    _assert_equal_metric(
        "run_summary.csv attempted solver jobs",
        _int_metric(baseline.run_metrics, "Total Cases Attempted"),
        _int_metric(current_run, "Total Cases Attempted"),
    )
    _assert_equal_metric(
        "weighted solved job count",
        _int_metric(baseline.run_metrics, "Total Cases Solved"),
        _weighted_success_count(result_payloads),
    )
    _assert_equal_metric(
        "run_summary.csv weighted solved job count",
        _int_metric(baseline.run_metrics, "Total Cases Solved"),
        _int_metric(current_run, "Total Cases Solved"),
    )
    _assert_equal_metric(
        "solved ESM count",
        len(baseline.solution_metrics),
        len(current_esm_successes),
    )
    _assert_equal_metric(
        "solution_metrics.csv solved ESM count",
        len(baseline.solution_metrics),
        len(current_solutions),
    )

    _assert_run_summary_matches_baseline(baseline, current_run, current_solutions)
    _assert_solution_metrics_match_baseline(baseline, current_solutions)


def _load_baseline(case_id: str) -> BaselineRun:
    """Load the newest baseline run from the saved workbook exports."""
    baseline_folder = Path("examples/results") / case_id
    run_path = baseline_folder / "Run Metrics.xlsx"
    solution_path = baseline_folder / "Solution Metrics.xlsx"
    run_metrics = pd.read_excel(run_path, engine="openpyxl")
    solution_metrics = pd.read_excel(solution_path, engine="openpyxl")

    if run_metrics.empty:
        raise AssertionError(f"{case_id}: baseline Run Metrics.xlsx has no rows")
    if solution_metrics.empty:
        raise AssertionError(f"{case_id}: baseline Solution Metrics.xlsx has no rows")

    run_row = _latest_run_row(run_metrics)
    # Prefer solution rows stamped with the same run date; older workbooks may
    # contain multiple historical runs in one sheet.
    run_solutions = solution_metrics[solution_metrics["Date"].astype(str) == str(run_row["Date"])]
    if run_solutions.empty:
        run_solutions = _latest_solution_rows(solution_metrics)

    return BaselineRun(
        case_id=case_id,
        run_metrics=run_row,
        solution_metrics=run_solutions.reset_index(drop=True),
    )


def _latest_run_row(run_metrics: pd.DataFrame) -> pd.Series:
    """Pick the newest run-summary row, falling back to append order if needed."""
    dates = pd.to_datetime(run_metrics["Date"], dayfirst=True, errors="coerce")
    if dates.notna().any():
        return run_metrics.loc[dates.idxmax()]
    return run_metrics.iloc[-1]


def _latest_solution_rows(solution_metrics: pd.DataFrame) -> pd.DataFrame:
    """Return solution rows for the newest dated run in the workbook."""
    dates = pd.to_datetime(solution_metrics["Date"], dayfirst=True, errors="coerce")
    if dates.notna().any():
        latest = dates.max()
        return solution_metrics.loc[dates == latest]
    return solution_metrics


def _current_esm_solution_metrics(run_folder: Path) -> pd.DataFrame:
    """Read the current solution metrics and keep only solved ESM rows."""
    metrics = pd.read_csv(run_folder / "metrics" / "solution_metrics.csv")
    if "Method" in metrics:
        metrics = metrics[metrics["Method"] == "ESM"]
    if metrics.empty:
        raise AssertionError("current solution_metrics.csv has no solved ESM rows")
    return metrics.reset_index(drop=True)


def _assert_artifacts_are_json_csv_only(
    manifest: dict,
    run_folder: Path,
    result_json_paths: list[Path],
    attempted_solver_jobs: int,
) -> None:
    """Confirm the regression fixture only emitted the requested artifact types."""
    _assert_equal_metric("manifest attempted solver jobs", attempted_solver_jobs, manifest["attempted_solver_jobs"])
    _assert_equal_metric("manifest result JSON count", len(result_json_paths), len(manifest["result_paths"]))
    for path in result_json_paths:
        assert path.exists(), f"missing result JSON artifact: {path}"

    artifact_suffixes = {Path(path).suffix for path in manifest["artifacts"]}
    assert ".xlsx" not in artifact_suffixes, "include_excel=False should not create workbook artifacts"
    assert ".png" not in artifact_suffixes, "include_plots=False should not create PNG artifacts"
    assert ".html" not in artifact_suffixes, "include_plots=False should not create HTML artifacts"
    assert (run_folder / "metrics" / "solution_metrics.csv").exists(), "missing solution_metrics.csv artifact"
    assert (run_folder / "metrics" / "run_summary.csv").exists(), "missing run_summary.csv artifact"


def _assert_run_summary_matches_baseline(
    baseline: BaselineRun,
    current_run: pd.Series,
    current_solutions: pd.DataFrame,
) -> None:
    """Validate the aggregate run summary against the workbook baseline."""
    baseline_costs = _finite_metric_values(baseline.solution_metrics, "ESM TAC")
    current_costs = _finite_metric_values(current_solutions, "ESM TAC")
    baseline_best_tac = float(baseline.run_metrics["Best Solution"])
    current_best_tac = float(current_run["Best Solution"])
    _assert_close_metric(
        "run_summary.csv best ESM TAC",
        baseline_best_tac,
        current_best_tac,
    )
    for label in ("Quartile 1", "Quartile 2", "Quartile 3"):
        _assert_close_metric(
            f"run_summary.csv {label}",
            float(baseline.run_metrics[label]),
            float(current_run[label]),
        )
    for threshold in (0.02, 0.05, 0.10):
        label = f"Within {int(threshold * 100)}%"
        _assert_threshold_count(
            f"run_summary.csv {label}",
            baseline=_int_metric(baseline.run_metrics, label),
            current=_int_metric(current_run, label),
            baseline_costs=baseline_costs,
            current_costs=current_costs,
            baseline_best_tac=baseline_best_tac,
            current_best_tac=current_best_tac,
            threshold=threshold,
        )


def _assert_solution_metrics_match_baseline(baseline: BaselineRun, current: pd.DataFrame) -> None:
    """Compare the solved ESM population against the baseline workbook rows."""
    baseline_costs = _finite_metric_values(baseline.solution_metrics, "ESM TAC")
    current_costs = _finite_metric_values(current, "ESM TAC")
    baseline_best_tac = float(baseline.run_metrics["Best Solution"])
    current_best_tac = float(current_costs.min())

    _assert_close_metric("best ESM TAC", baseline_best_tac, current_best_tac)

    for quantile, label in ((0.25, "Quartile 1"), (0.5, "Quartile 2"), (0.75, "Quartile 3")):
        baseline_value = float(baseline.run_metrics[label])
        current_value = float(np.quantile(current_costs, quantile))
        _assert_close_metric(label, baseline_value, current_value)

    for threshold in (0.02, 0.05, 0.10):
        label = f"Within {int(threshold * 100)}%"
        baseline_count = _int_metric(baseline.run_metrics, label)
        current_count = int((current_costs <= current_best_tac * (1 + threshold)).sum())
        _assert_threshold_count(
            label,
            baseline=baseline_count,
            current=current_count,
            baseline_costs=baseline_costs,
            current_costs=current_costs,
            baseline_best_tac=baseline_best_tac,
            current_best_tac=current_best_tac,
            threshold=threshold,
        )

    baseline_best = _best_solution_row(baseline.solution_metrics, baseline_best_tac)
    current_best = _best_solution_row(current, current_best_tac)
    _assert_equal_metric("best solution stage count", _int_metric(baseline_best, "Stages"), _int_metric(current_best, "Stages"))
    _assert_equal_metric(
        "best solution recovery unit count",
        _int_metric(baseline_best, "N Recovery Units"),
        _int_metric(current_best, "N Recovery Units"),
    )
    _assert_equal_metric("best solution CU unit count", _int_metric(baseline_best, "N CU Units"), _int_metric(current_best, "N CU Units"))
    _assert_equal_metric("best solution HU unit count", _int_metric(baseline_best, "N HU Units"), _int_metric(current_best, "N HU Units"))
    _assert_equal_metric("best solution dTmin", float(baseline_best["dTmin"]), float(current_best["dTmin"]))
    _assert_equal_metric("best solution derivative_threshold", float(baseline_best["min_dQ"]), float(current_best["min_dQ"]))


def _best_solution_row(metrics: pd.DataFrame, best_tac: float) -> pd.Series:
    """Return a stable representative row for the best-TAC solution cluster."""
    costs = pd.to_numeric(metrics["ESM TAC"], errors="coerce")
    actual_best = float(costs.min())
    _assert_close_metric("best-row ESM TAC", best_tac, actual_best)
    best_rows = metrics[costs == actual_best]
    if best_rows.empty:
        raise AssertionError(f"best solution row missing for TAC {best_tac}")
    return best_rows.sort_values(["ESM TAC", "dTmin", "min_dQ"]).iloc[0]


def _finite_metric_values(metrics: pd.DataFrame, metric: str) -> np.ndarray:
    """Extract finite numeric metric values, dropping workbook noise."""
    values = pd.to_numeric(metrics[metric], errors="coerce").dropna().to_numpy(dtype=float)
    return values[np.isfinite(values)]


def _assert_close_metric(metric: str, baseline: float, current: float) -> None:
    if not math.isclose(current, baseline, rel_tol=TAC_REL_TOL, abs_tol=TAC_ABS_TOL):
        raise AssertionError(
            f"{metric} drifted: baseline={baseline!r}, current={current!r}, "
            f"rel_tol={TAC_REL_TOL}, abs_tol={TAC_ABS_TOL}"
        )


def _assert_equal_metric(metric: str, baseline, current) -> None:
    if current != baseline:
        raise AssertionError(f"{metric} drifted: baseline={baseline!r}, current={current!r}")


def _assert_threshold_count(
    metric: str,
    *,
    baseline: int,
    current: int,
    baseline_costs: np.ndarray,
    current_costs: np.ndarray,
    baseline_best_tac: float,
    current_best_tac: float,
    threshold: float,
) -> None:
    """Allow a one-count drift when costs land on the threshold boundary."""
    if current == baseline:
        return
    baseline_limit = baseline_best_tac * (1 + threshold)
    current_limit = current_best_tac * (1 + threshold)
    # Solver ordering can flip which near-tied solution lands exactly on the
    # threshold, changing the bucket count by one without changing TAC quality.
    has_near_threshold_tie = _has_near_threshold_tie(
        baseline_costs,
        baseline_limit,
    ) or _has_near_threshold_tie(current_costs, current_limit)
    if abs(current - baseline) == 1 and has_near_threshold_tie:
        return
    raise AssertionError(f"{metric} count drifted: baseline={baseline!r}, current={current!r}")


def _has_near_threshold_tie(costs: np.ndarray, threshold: float) -> bool:
    """Detect costs that are effectively equal to a threshold within test tolerances."""
    return bool(np.isclose(costs, threshold, rtol=THRESHOLD_TIE_REL_TOL, atol=TAC_ABS_TOL).any())


def _single_row(frame: pd.DataFrame) -> pd.Series:
    if len(frame) != 1:
        raise AssertionError(f"expected one run summary row, got {len(frame)}")
    return frame.iloc[0]


def _int_metric(row: pd.Series, metric: str) -> int:
    value = row[metric]
    if pd.isna(value):
        raise AssertionError(f"{metric} is missing")
    return int(value)


def _weighted_success_count(result_payloads: list[dict]) -> int:
    """Mirror the production weighted ESM counting used in run summaries."""
    total = 0
    for payload in result_payloads:
        if not payload["success"]:
            continue
        total += 11 if payload["task"]["method"] == "ESM" else 1
    return total
