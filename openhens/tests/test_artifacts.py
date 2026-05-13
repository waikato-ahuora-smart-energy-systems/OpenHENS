import csv
import json
from pathlib import Path
import subprocess
import sys

from openhens import (
    CaseStudy,
    DesignSpace,
    NetworkSolution,
    SolutionPortfolio,
    SolverRun,
    StudyOutcome,
    StudyOutputs,
    SynthesisStudy,
    TaskOutcome,
)
from openhens.artifacts import RUN_SUMMARY_COLUMNS, SOLUTION_METRIC_COLUMNS, write_study_artifacts
from openhens.workflow import build_pdm_tasks


FIXED_TIME = "2026-01-02T03:04:05Z"


def test_write_artifacts_creates_json_csv_and_reconstructs(tmp_path: Path) -> None:
    study = _study(tmp_path)
    outcomes = _fake_outcomes(study)

    outcome = write_study_artifacts(
        study,
        outcomes,
        total_run_time_seconds=12.5,
        attempted_solver_jobs=13,
        created_at=FIXED_TIME,
        completed_at=FIXED_TIME,
    )

    run_folder = tmp_path / "fixed-run"
    manifest_path = run_folder / "manifest.json"
    result_paths = sorted((run_folder / "results").glob("*.json"))
    solution_metrics_path = run_folder / "metrics" / "solution_metrics.csv"
    run_summary_path = run_folder / "metrics" / "run_summary.csv"

    assert outcome.manifest.run_id == "fixed-run"
    assert manifest_path.exists()
    assert [path.name for path in result_paths] == sorted(f"{result.task_id}.json" for result in outcomes)
    assert solution_metrics_path.exists()
    assert run_summary_path.exists()
    assert list(run_folder.rglob("*.pkl")) == []
    assert list(run_folder.rglob("*.xlsx")) == []

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["case_hash"]
    assert manifest["result_paths"] == [f"results/{result.task_id}.json" for result in outcomes]
    assert "metrics/solution_metrics.csv" in manifest["artifacts"]
    assert "metrics/run_summary.csv" in manifest["artifacts"]

    metric_rows = _read_csv(solution_metrics_path)
    assert list(metric_rows[0].keys()) == list(SOLUTION_METRIC_COLUMNS)
    assert [row["Task ID"] for row in metric_rows] == [outcomes[0].task_id, outcomes[1].task_id]
    assert metric_rows[1]["ESM TAC"] == "150.0"
    assert metric_rows[1]["N Recovery Units"] == "2"

    summary_rows = _read_csv(run_summary_path)
    assert list(summary_rows[0].keys()) == list(RUN_SUMMARY_COLUMNS)
    assert summary_rows[0]["Best Solution"] == "150.0"
    assert summary_rows[0]["Best Task ID"] == outcomes[1].task_id
    assert summary_rows[0]["Total Cases Attempted"] == "13"

    reconstructed = StudyOutcome.from_artifacts(run_folder)
    assert len(reconstructed.task_outcomes) == 3
    assert reconstructed.solutions.best_by_total_annual_cost().name == "lower cost"
    assert reconstructed.manifest.case_hash == outcome.manifest.case_hash


def test_solution_portfolio_best_by_total_annual_cost_ignores_missing_costs() -> None:
    portfolio = SolutionPortfolio(
        solutions=(
            NetworkSolution(name="missing", total_annual_cost=None),
            NetworkSolution(name="expensive", total_annual_cost=300),
            NetworkSolution(name="cheap", total_annual_cost=100),
        )
    )

    assert portfolio.best_by_total_annual_cost().name == "cheap"
    assert SolutionPortfolio().best_by_total_annual_cost() is None


def test_excel_artifacts_are_written_only_when_requested(tmp_path: Path) -> None:
    study = _study(tmp_path, include_excel=True, run_id="excel-run")

    write_study_artifacts(
        study,
        _fake_outcomes(study),
        total_run_time_seconds=1.0,
        attempted_solver_jobs=2,
        created_at=FIXED_TIME,
        completed_at=FIXED_TIME,
    )

    run_folder = tmp_path / "excel-run"
    assert (run_folder / "metrics" / "Solution Metrics.xlsx").exists()
    assert (run_folder / "metrics" / "Run Metrics.xlsx").exists()


def test_top_level_artifact_imports_do_not_load_solver_or_plotting_modules() -> None:
    script = "\n".join(
        [
            "import sys",
            "import openhens",
            "import openhens.open_best",
            "import openhens.artifacts",
            "loaded = {name: name in sys.modules for name in ('gekko', 'plotly', 'openhens.main', 'openhens.utils.solution_loader', 'openhens.utils.solution_saver')}",
            "print(loaded)",
            "raise SystemExit(any(loaded.values()))",
        ]
    )

    subprocess.run([sys.executable, "-c", script], check=True)


def test_display_run_metrics_reads_existing_artifact_paths_without_exporting(tmp_path: Path) -> None:
    from openhens import OpenHENS

    study = _study(tmp_path)
    outcome = write_study_artifacts(
        study,
        _fake_outcomes(study),
        total_run_time_seconds=1.0,
        attempted_solver_jobs=2,
        created_at=FIXED_TIME,
        completed_at=FIXED_TIME,
    )
    run_folder = tmp_path / "fixed-run"
    before = {path.relative_to(run_folder) for path in run_folder.rglob("*") if path.is_file()}

    facade = OpenHENS.__new__(OpenHENS)
    facade.study_outcome = outcome
    facade._run_folder = run_folder

    facade.display_run_metrics()

    after = {path.relative_to(run_folder) for path in run_folder.rglob("*") if path.is_file()}
    assert after == before
    assert list(run_folder.rglob("*.xlsx")) == []
    assert list(run_folder.rglob("*.html")) == []
    assert list(run_folder.rglob("*.png")) == []


def _study(
    folder: Path,
    *,
    include_excel: bool = False,
    run_id: str = "fixed-run",
) -> SynthesisStudy:
    return SynthesisStudy(
        case=CaseStudy(source=Path("missing-case.csv"), name="Artifact Study"),
        design_space=DesignSpace(approach_temperatures=(2,), derivative_thresholds=(0.5,)),
        outputs=StudyOutputs(folder=folder, run_id=run_id, include_excel=include_excel),
    )


def _fake_outcomes(study: SynthesisStudy) -> tuple[TaskOutcome, ...]:
    first_task = build_pdm_tasks(study)[0]
    second_task = first_task.model_copy(update={"task_id": "esm-fixed", "method": "ESM", "stages": 2})
    failed_task = first_task.model_copy(update={"task_id": "failed-fixed"})
    return (
        TaskOutcome(
            task=first_task,
            success=True,
            solver=SolverRun(name="couenne", status=1, solve_time=2.0, objective_value=200.0),
            solution=_solution(first_task.task_id, "PDM", "higher cost", 200.0, 1),
        ),
        TaskOutcome(
            task=second_task,
            success=True,
            solver=SolverRun(name="ipopt-pyomo", status=1, solve_time=3.0, objective_value=150.0),
            solution=_solution(second_task.task_id, "ESM", "lower cost", 150.0, 2),
        ),
        TaskOutcome(
            task=failed_task,
            success=False,
            solver=SolverRun(name="couenne", status=0, solve_time=0.2, failure_reason="failed"),
            failure_reason="failed",
        ),
    )


def _solution(task_id: str, method: str, name: str, tac: float, recovery_units: int) -> NetworkSolution:
    return NetworkSolution(
        name=name,
        task_id=task_id,
        method=method,
        solver=SolverRun(name="couenne", status=1, solve_time=1.0, objective_value=tac),
        approach_temperature=2.0,
        derivative_threshold=0.5,
        stages=2,
        unit_counts={"recovery": recovery_units, "cold_utility": 1, "hot_utility": 1},
        total_annual_cost=tac,
        model_objective_value=tac,
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
