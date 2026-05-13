"""Task generation and local orchestration for synthesis workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from timeit import default_timer as timer
from typing import Any, Mapping, Protocol, Sequence

from .classes import HeatExchangerNetworkProblem
from .domain import (
    NetworkSolution,
    SolverRun,
    SynthesisStudy,
    SynthesisTask,
    TaskOutcome,
    TaskNumericalSettings,
    TaskRestrictions,
)
from .logger import openhens_log as logger
from .utils.branching import run_parallel_solution_results


ESM_ATTEMPT_WEIGHT = 11


@dataclass(frozen=True)
class TaskTopology:
    """Transient topology used to spawn downstream tasks during local solves."""

    stages: int | None = None
    recovery_heat_duties: tuple[tuple[tuple[float, ...], ...], ...] | None = None

    def restrictions(self) -> TaskRestrictions:
        return TaskRestrictions(recovery_heat_duties=self.recovery_heat_duties)


SynthesisTaskOutcome = TaskOutcome


class SynthesisExecutor(Protocol):
    """Executor protocol shared by the local and fake workflow executors."""

    def execute(
        self,
        tasks: Sequence[SynthesisTask],
        *,
        parent_outcomes: Mapping[str, SynthesisTaskOutcome],
        max_parallel: int,
        print_output: bool,
    ) -> tuple[SynthesisTaskOutcome, ...]:
        ...


@dataclass(frozen=True)
class SynthesisWorkflowResult:
    """Result of a task-oriented synthesis workflow run."""

    tasks: tuple[SynthesisTask, ...]
    outcomes: tuple[SynthesisTaskOutcome, ...]
    total_run_time: float

    @property
    def attempted_solver_jobs(self) -> int:
        return sum(ESM_ATTEMPT_WEIGHT if task.method == "ESM" else 1 for task in self.tasks)

    @property
    def successful_problems(self) -> list[HeatExchangerNetworkProblem]:
        return [outcome.problem for outcome in self.outcomes if outcome.success and outcome.problem is not None]


class WorkflowContractError(ValueError):
    """Raised when a successful upstream task lacks data required for downstream tasks."""


class LocalSynthesisExecutor:
    """Execute workflow tasks with the existing local multiprocessing solver path."""

    def execute(
        self,
        tasks: Sequence[SynthesisTask],
        *,
        parent_outcomes: Mapping[str, SynthesisTaskOutcome],
        max_parallel: int,
        print_output: bool,
    ) -> tuple[SynthesisTaskOutcome, ...]:
        if not tasks:
            return ()

        built: list[tuple[SynthesisTask, HeatExchangerNetworkProblem]] = []
        failed: dict[str, SynthesisTaskOutcome] = {}
        for task in tasks:
            try:
                problem = self._build_problem(task, parent_outcomes)
            except Exception as exc:
                failed[task.task_id] = SynthesisTaskOutcome(
                    task=task,
                    success=False,
                    solver=SolverRun(name=task.solver, failure_reason=str(exc)),
                    failure_reason=str(exc),
                )
                continue
            problem.synthesis_task_id = task.task_id
            built.append((task, problem))

        results_by_task_id = {}
        if built:
            solved_results = run_parallel_solution_results(
                problems=[problem for _, problem in built],
                max_parallel=max_parallel,
                print_output=print_output,
                evolution=any(task.evolution_enabled for task, _ in built),
            )
            results_by_task_id = {
                getattr(result.problem, "synthesis_task_id"): result
                for result in solved_results
                if getattr(result.problem, "synthesis_task_id", None) is not None
            }

        outcomes: list[SynthesisTaskOutcome] = []
        for task, problem in built:
            run_result = results_by_task_id.get(task.task_id)
            if run_result is None:
                reason = "solver worker did not return a result"
                outcomes.append(
                    SynthesisTaskOutcome(
                        task=task,
                        success=False,
                        solver=SolverRun(name=task.solver, failure_reason=reason),
                        failure_reason=reason,
                        problem=problem,
                    )
                )
            elif not run_result.success:
                outcomes.append(
                    SynthesisTaskOutcome(
                        task=task,
                        success=False,
                        solver=extract_solver_run(run_result.problem, task),
                        failure_reason=run_result.failure_reason,
                        verification_failures=run_result.verification_failures,
                        problem=run_result.problem,
                    )
                )
            else:
                solution = extract_network_solution(
                    run_result.problem,
                    task=task,
                    verification_failures=run_result.verification_failures,
                )
                outcomes.append(
                    SynthesisTaskOutcome(
                        task=task,
                        success=True,
                        solver=solution.solver,
                        solution=solution,
                        problem=run_result.problem,
                        topology=extract_topology(run_result.problem),
                    )
                )

        return tuple(failed.get(task.task_id) or next(outcome for outcome in outcomes if outcome.task_id == task.task_id) for task in tasks)

    def _build_problem(
        self,
        task: SynthesisTask,
        parent_outcomes: Mapping[str, SynthesisTaskOutcome],
    ) -> HeatExchangerNetworkProblem:
        if task.parent_task_ids:
            missing_parents = [task_id for task_id in task.parent_task_ids if task_id not in parent_outcomes]
            if missing_parents:
                raise ValueError(f"Missing parent outcomes for task {task.task_id}: {missing_parents}")
            failed_parents = [task_id for task_id in task.parent_task_ids if not parent_outcomes[task_id].success]
            if failed_parents:
                raise ValueError(f"Cannot build task {task.task_id} with failed parents: {failed_parents}")

        return HeatExchangerNetworkProblem(
            name=task.legacy_name,
            framework=task.method,
            solver=task.solver,
            dTmin=task.dTmin,
            import_file=task.case_reference,
            min_dqda=task.min_dqda,
            z_restriction=task.restrictions.to_legacy_z_restriction(),
            minimisation_goal=task.objective,
            non_isothermal_model=task.non_isothermal_model,
            integers=task.integers,
            parent=None,
            tol=task.numerical_settings.tolerance,
            stage_selection=_legacy_stage_selection(task.stage_selection),
            stages=task.stages,
        )


def run_synthesis_workflow(
    study: SynthesisStudy,
    *,
    executor: SynthesisExecutor | None = None,
    print_output: bool = False,
) -> SynthesisWorkflowResult:
    """Build and execute PDM, TDM, then ESM tasks for a synthesis study."""

    executor = executor or LocalSynthesisExecutor()
    start_time = timer()

    pdm_tasks = build_pdm_tasks(study)
    pdm_outcomes = executor.execute(
        pdm_tasks,
        parent_outcomes={},
        max_parallel=study.solving.max_parallel,
        print_output=print_output,
    )
    logger.warning(f"PDM Completed: {sum(outcome.success for outcome in pdm_outcomes)} solutions found")

    pdm_outcome_map = {outcome.task_id: outcome for outcome in pdm_outcomes}
    tdm_tasks = build_tdm_tasks(study, pdm_outcomes)
    tdm_outcomes = executor.execute(
        tdm_tasks,
        parent_outcomes=pdm_outcome_map,
        max_parallel=study.solving.max_parallel,
        print_output=print_output,
    )
    logger.warning(f"TDM Completed: {sum(outcome.success for outcome in tdm_outcomes)} solutions found")

    upstream_outcomes = pdm_outcome_map | {outcome.task_id: outcome for outcome in tdm_outcomes}
    esm_tasks = build_esm_tasks(study, tdm_outcomes)
    esm_outcomes = executor.execute(
        esm_tasks,
        parent_outcomes=upstream_outcomes,
        max_parallel=study.solving.max_parallel,
        print_output=print_output,
    )
    logger.warning(f"ESM Completed: {sum(outcome.success for outcome in esm_outcomes)} solutions found")

    total_run_time = timer() - start_time
    logger.warning(f"Total run time: {total_run_time}s")

    return SynthesisWorkflowResult(
        tasks=tuple(pdm_tasks + tdm_tasks + esm_tasks),
        outcomes=tuple(pdm_outcomes + tdm_outcomes + esm_outcomes),
        total_run_time=total_run_time,
    )


def build_pdm_tasks(study: SynthesisStudy) -> tuple[SynthesisTask, ...]:
    """Generate initial PDM tasks from a study design space."""

    tasks: list[SynthesisTask] = []
    for min_dT in study.design_space.approach_temperatures:
        fields = _task_fields(
            study,
            method="PDM",
            parent_task_ids=(),
            solver=study.methods.pdm_solver,
            objective="hot utility",
            dTmin=min_dT,
            min_dqda=0,
            approach_temperature=min_dT,
            derivative_threshold=None,
            stages=None,
            legacy_name=f"P-+--PDM-{min_dT}",
            restrictions=TaskRestrictions(),
            non_isothermal_model=False,
            integers=True,
            evolution_enabled=False,
        )
        tasks.append(SynthesisTask(task_id=_task_id(fields), **fields))
    return tuple(tasks)


def build_tdm_tasks(
    study: SynthesisStudy,
    pdm_outcomes: Sequence[SynthesisTaskOutcome],
) -> tuple[SynthesisTask, ...]:
    """Generate TDM tasks from successful PDM outcomes."""

    tasks: list[SynthesisTask] = []
    for outcome in pdm_outcomes:
        if not _is_successful_method(outcome, "PDM"):
            continue
        topology = required_topology_from_outcome(outcome, "TDM")
        stages = topology.stages
        restrictions = topology.restrictions()
        for min_dqda in study.design_space.derivative_thresholds:
            fields = _task_fields(
                study,
                method="TDM",
                parent_task_ids=(outcome.task_id,),
                solver=study.methods.tdm_solver,
                objective="hot utility",
                dTmin=0.1,
                min_dqda=min_dqda,
                approach_temperature=outcome.task.approach_temperature,
                derivative_threshold=min_dqda,
                stages=stages,
                legacy_name=f"P-S{stages if stages is not None else 'unknown'}--TDM-{min_dqda}",
                restrictions=restrictions,
                non_isothermal_model=False,
                integers=True,
                evolution_enabled=False,
            )
            tasks.append(SynthesisTask(task_id=_task_id(fields), **fields))
    return tuple(tasks)


def build_esm_tasks(
    study: SynthesisStudy,
    tdm_outcomes: Sequence[SynthesisTaskOutcome],
) -> tuple[SynthesisTask, ...]:
    """Generate ESM tasks from successful TDM outcomes."""

    tasks: list[SynthesisTask] = []
    for outcome in tdm_outcomes:
        if not _is_successful_method(outcome, "TDM"):
            continue
        topology = required_topology_from_outcome(outcome, "ESM")
        stages = topology.stages
        restrictions = topology.restrictions()
        fields = _task_fields(
            study,
            method="ESM",
            parent_task_ids=(outcome.task_id,),
            solver=study.methods.esm_solver,
            objective="variable total cost",
            dTmin=outcome.task.dTmin,
            min_dqda=outcome.task.min_dqda,
            approach_temperature=outcome.task.approach_temperature,
            derivative_threshold=outcome.task.derivative_threshold,
            stages=stages,
            legacy_name=f"P-S{stages if stages is not None else 'unknown'}-Synheat-Iso-NLP",
            restrictions=restrictions,
            non_isothermal_model=True,
            integers=False,
            evolution_enabled=True,
        )
        tasks.append(SynthesisTask(task_id=_task_id(fields), **fields))
    return tuple(tasks)


def extract_topology(problem: HeatExchangerNetworkProblem) -> TaskTopology:
    case = problem.case
    return TaskTopology(
        stages=getattr(case, "stages", None),
        recovery_heat_duties=_extract_recovery_heat_duties(getattr(case, "Q_r", None)),
    )


def extract_network_solution(
    problem: HeatExchangerNetworkProblem,
    *,
    task: SynthesisTask | None = None,
    verification_failures: Sequence[str] = (),
) -> NetworkSolution:
    """Convert a solved legacy problem into a durable JSON-compatible record."""

    case = getattr(problem, "case", problem)
    solver = extract_solver_run(problem, task)
    method = task.method if task is not None else getattr(problem, "framework", getattr(case, "framework", None))
    task_id = task.task_id if task is not None else getattr(problem, "synthesis_task_id", None)

    return NetworkSolution(
        name=str(getattr(problem, "name", getattr(case, "name", ""))),
        task_id=task_id,
        method=method,
        solver=solver,
        parent_task_ids=task.parent_task_ids if task is not None else (),
        dTmin=_optional_float(getattr(problem, "dTmin", getattr(case, "dTmin", None))),
        min_dqda=_optional_float(getattr(problem, "min_dqda", getattr(case, "min_dqda", None))),
        approach_temperature=task.approach_temperature if task is not None else None,
        derivative_threshold=task.derivative_threshold if task is not None else None,
        stages=getattr(case, "S", getattr(case, "stages", None)),
        recovery_heat_duties=_extract_3d_values(getattr(case, "Q_r", None)),
        hot_utility_duties=_extract_1d_values(getattr(case, "Q_h", None)),
        cold_utility_duties=_extract_1d_values(getattr(case, "Q_c", None)),
        hot_stream_temperatures=_extract_2d_values(getattr(case, "T_h", None)),
        cold_stream_temperatures=_extract_2d_values(getattr(case, "T_c", None)),
        hot_recovery_outlet_temperatures=_extract_3d_values(getattr(case, "T_h_out_x", None)),
        cold_recovery_outlet_temperatures=_extract_3d_values(getattr(case, "T_c_out_y", None)),
        recovery_areas=_extract_3d_values(getattr(case, "area_r", None)),
        hot_utility_areas=_extract_1d_values(getattr(case, "area_hu", None)),
        cold_utility_areas=_extract_1d_values(getattr(case, "area_cu", None)),
        dqda=_extract_3d_values(getattr(case, "dqda", None)),
        utility_loads={
            "hot": _optional_float(getattr(case, "Q_hu_total", None)),
            "cold": _optional_float(getattr(case, "Q_cu_total", None)),
        },
        unit_counts={
            "total": _optional_int(getattr(case, "n_units", None)),
            "recovery": _optional_int(getattr(case, "n_recovery_units", None)),
            "hot_utility": _optional_int(getattr(case, "n_hu_units", None)),
            "cold_utility": _optional_int(getattr(case, "n_cu_units", None)),
        },
        total_annual_cost=_optional_float(getattr(case, "TAC", None)),
        model_objective_value=solver.objective_value
        if solver.objective_value is not None
        else _optional_float(getattr(case, "TAC_model", None)),
        method_lineage=_method_lineage(problem, task),
        verification_failures=tuple(str(reason) for reason in verification_failures),
    )


def extract_solver_run(
    problem: HeatExchangerNetworkProblem,
    task: SynthesisTask | None = None,
) -> SolverRun:
    case = getattr(problem, "case", problem)
    solver_run = getattr(case, "solver_run", None)
    solver_name = task.solver if task is not None else getattr(problem, "solver", getattr(case, "solver", "unknown"))
    if isinstance(solver_run, SolverRun):
        return solver_run.model_copy(
            update={
                "name": solver_run.name or solver_name,
                "status": solver_run.status if solver_run.status is not None else getattr(case, "mSuccess", None),
                "objective_value": solver_run.objective_value
                if solver_run.objective_value is not None
                else _optional_float(getattr(case, "TAC_model", getattr(case, "TAC", None))),
                "solve_time": solver_run.solve_time
                if solver_run.solve_time is not None
                else _optional_float(getattr(case, "solve_time", None)),
            }
        )

    model = getattr(case, "m", None)
    options = getattr(model, "options", None)
    return SolverRun(
        name=str(solver_name),
        extension=getattr(options, "SOLVER_EXTENSION", None),
        status=getattr(options, "SOLVESTATUS", getattr(case, "mSuccess", None)),
        objective_value=_optional_float(getattr(options, "objfcnval", getattr(case, "TAC_model", getattr(case, "TAC", None)))),
        solve_time=_optional_float(getattr(case, "solve_time", None)),
        failure_reason=getattr(problem, "solution_failure_reason", None),
    )


def required_topology_from_outcome(outcome: SynthesisTaskOutcome, downstream_method: str) -> TaskTopology:
    topology = outcome.topology
    if topology is None and outcome.solution is not None:
        topology = TaskTopology(
            stages=outcome.solution.stages,
            recovery_heat_duties=outcome.solution.recovery_heat_duties,
        )
    if topology is None:
        raise WorkflowContractError(
            f"Successful {outcome.task.method} task {outcome.task_id} cannot spawn {downstream_method} "
            "tasks without extracted topology"
        )
    if topology.stages is None:
        raise WorkflowContractError(
            f"Successful {outcome.task.method} task {outcome.task_id} cannot spawn {downstream_method} "
            "tasks without stage count"
        )
    if topology.recovery_heat_duties is None:
        raise WorkflowContractError(
            f"Successful {outcome.task.method} task {outcome.task_id} cannot spawn {downstream_method} "
            "tasks without recovery heat-duty restrictions"
        )
    return topology


def _task_fields(
    study: SynthesisStudy,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "case_reference": study.case.source,
        "stage_selection": study.design_space.stage_selection,
        "numerical_settings": TaskNumericalSettings(tolerance=study.solving.tolerance),
        **fields,
    }


def _task_id(fields: Mapping[str, Any]) -> str:
    payload = _jsonable_task_payload(fields)
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
    method = str(fields["method"]).lower()
    return f"{method}-{digest}"


def _jsonable_task_payload(fields: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in fields.items():
        if key == "numerical_settings":
            payload[key] = value.model_dump(mode="json")
        elif key == "restrictions":
            payload[key] = value.model_dump(mode="json")
        elif key == "case_reference":
            payload[key] = str(value)
        else:
            payload[key] = value
    return payload


def _is_successful_method(outcome: SynthesisTaskOutcome, method: str) -> bool:
    return outcome.success and outcome.task.method == method


def _legacy_stage_selection(stage_selection):
    if stage_selection == "automated":
        return stage_selection
    return list(stage_selection)


def _extract_recovery_heat_duties(values) -> tuple[tuple[tuple[float, ...], ...], ...] | None:
    if values is None:
        return None
    return tuple(
        tuple(tuple(_as_float(value) for value in cold_stream) for cold_stream in hot_stream)
        for hot_stream in values
    )


def _extract_3d_values(values) -> tuple[tuple[tuple[float | None, ...], ...], ...] | None:
    if values is None:
        return None
    return tuple(tuple(tuple(_optional_float(value) for value in row) for row in plane) for plane in values)


def _extract_2d_values(values) -> tuple[tuple[float | None, ...], ...] | None:
    if values is None:
        return None
    return tuple(tuple(_optional_float(value) for value in row) for row in values)


def _extract_1d_values(values) -> tuple[float | None, ...] | None:
    if values is None:
        return None
    return tuple(_optional_float(value) for value in values)


def _as_float(value) -> float:
    try:
        return float(value[0])
    except (TypeError, IndexError, KeyError):
        return float(value)


def _optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        return _as_float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(round(_as_float(value)))
    except (TypeError, ValueError):
        return None


def _method_lineage(
    problem: HeatExchangerNetworkProblem,
    task: SynthesisTask | None,
) -> tuple[dict[str, str | int | float | bool | None], ...]:
    if task is None:
        return (
            {
                "task_id": getattr(problem, "synthesis_task_id", None),
                "method": getattr(problem, "framework", None),
                "solver": getattr(problem, "solver", None),
                "dTmin": _optional_float(getattr(problem, "dTmin", None)),
                "min_dqda": _optional_float(getattr(problem, "min_dqda", None)),
            },
        )
    return (
        {
            "task_id": task.task_id,
            "method": task.method,
            "solver": task.solver,
            "dTmin": task.dTmin,
            "min_dqda": task.min_dqda,
            "approach_temperature": task.approach_temperature,
            "derivative_threshold": task.derivative_threshold,
            "non_isothermal_model": task.non_isothermal_model,
            "integers": task.integers,
        },
    )
