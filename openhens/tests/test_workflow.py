from pathlib import Path
import json

from openhens import CaseStudy, DesignSpace, OpenHENS, SolveSetup, SolverRun, StudyOutputs, SynthesisStudy, SynthesisTask
from openhens.classes import HeatExchangerNetworkProblem
from openhens.workflow import (
    ESM_ATTEMPT_WEIGHT,
    SynthesisTaskOutcome,
    SynthesisWorkflowResult,
    TaskTopology,
    WorkflowContractError,
    build_esm_tasks,
    build_pdm_tasks,
    build_tdm_tasks,
    extract_network_solution,
    LocalSynthesisExecutor,
    run_synthesis_workflow,
)
from openhens.utils.branching import _pool_size


class FakeSynthesisExecutor:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.stage_order: list[str] = []
        self.executed_tasks = []

    def execute(self, tasks, *, parent_outcomes, max_parallel, print_output):
        if tasks:
            self.stage_order.append(tasks[0].method)
        outcomes = []
        for task in tasks:
            for parent_task_id in task.parent_task_ids:
                assert parent_task_id in parent_outcomes
                assert parent_outcomes[parent_task_id].success

            self.executed_tasks.append(task)
            outcomes.append(
                SynthesisTaskOutcome(
                    task=task,
                    success=task.task_id not in self.failures,
                    topology=_topology(),
                )
            )
        return tuple(outcomes)


def test_synthesis_task_ids_are_deterministic_and_serializable() -> None:
    study = _study(approach_temperatures=(2, 4), derivative_thresholds=(0.5,))

    first = build_pdm_tasks(study)
    second = build_pdm_tasks(study)

    assert [task.task_id for task in first] == [task.task_id for task in second]
    assert first[0].solver == "couenne"
    assert first[0].objective == "hot utility"
    assert first[0].parent_task_ids == ()

    roundtrip = SynthesisTask.model_validate_json(first[0].model_dump_json())
    assert roundtrip == first[0]


def test_failed_pdm_and_tdm_tasks_do_not_spawn_downstream_tasks() -> None:
    study = _study(approach_temperatures=(2, 4), derivative_thresholds=(0.5, 1.0))
    pdm_tasks = build_pdm_tasks(study)
    successful_pdm = SynthesisTaskOutcome(task=pdm_tasks[1], success=True, topology=_topology())
    tdm_tasks = build_tdm_tasks(study, [successful_pdm])

    executor = FakeSynthesisExecutor(failures={pdm_tasks[0].task_id, tdm_tasks[0].task_id})
    result = run_synthesis_workflow(study, executor=executor)

    generated_tdm_tasks = [task for task in result.tasks if task.method == "TDM"]
    generated_esm_tasks = [task for task in result.tasks if task.method == "ESM"]

    assert executor.stage_order == ["PDM", "TDM", "ESM"]
    assert len(generated_tdm_tasks) == 2
    assert {task.parent_task_ids for task in generated_tdm_tasks} == {(pdm_tasks[1].task_id,)}
    assert len(generated_esm_tasks) == 1
    assert generated_esm_tasks[0].parent_task_ids == (tdm_tasks[1].task_id,)
    assert result.attempted_solver_jobs == 2 + 2 + ESM_ATTEMPT_WEIGHT


def test_workflow_attempt_count_matches_current_formula_for_successful_design_space() -> None:
    study = _study(approach_temperatures=(2, 4), derivative_thresholds=(0.5, 1.0, 2.0))
    executor = FakeSynthesisExecutor()

    result = run_synthesis_workflow(study, executor=executor)

    pdm_count = 2
    tdm_count = pdm_count * 3
    esm_count = tdm_count
    assert len([task for task in result.tasks if task.method == "PDM"]) == pdm_count
    assert len([task for task in result.tasks if task.method == "TDM"]) == tdm_count
    assert len([task for task in result.tasks if task.method == "ESM"]) == esm_count
    assert result.attempted_solver_jobs == pdm_count + tdm_count + esm_count * ESM_ATTEMPT_WEIGHT


def test_parallel_pool_size_is_capped_by_submitted_jobs() -> None:
    assert _pool_size(max_parallel=10, job_count=3) == 3
    assert _pool_size(max_parallel=2, job_count=10) == 2


def test_successful_pdm_without_durable_topology_cannot_spawn_tdm_tasks() -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    pdm_task = build_pdm_tasks(study)[0]
    outcome = SynthesisTaskOutcome(task=pdm_task, success=True)

    try:
        build_tdm_tasks(study, [outcome])
    except WorkflowContractError as exc:
        assert "without extracted topology" in str(exc)
    else:
        raise AssertionError("expected missing topology to fail workflow contract")


def test_successful_pdm_with_only_live_problem_still_cannot_spawn_tdm_tasks() -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    pdm_task = build_pdm_tasks(study)[0]
    live_problem = type("Problem", (), {"case": type("Case", (), {"stages": 2, "Q_r": ((([10.0],),),)})()})()
    outcome = SynthesisTaskOutcome(task=pdm_task, success=True, problem=live_problem)

    try:
        build_tdm_tasks(study, [outcome])
    except WorkflowContractError as exc:
        assert "without extracted topology" in str(exc)
    else:
        raise AssertionError("expected live problem fallback to fail workflow contract")


def test_successful_tdm_without_restrictions_cannot_spawn_esm_tasks() -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    pdm_task = build_pdm_tasks(study)[0]
    pdm_outcome = SynthesisTaskOutcome(task=pdm_task, success=True, topology=_topology())
    tdm_task = build_tdm_tasks(study, [pdm_outcome])[0]
    outcome = SynthesisTaskOutcome(task=tdm_task, success=True, topology=TaskTopology(stages=2))

    try:
        build_esm_tasks(study, [outcome])
    except WorkflowContractError as exc:
        assert "without recovery heat-duty restrictions" in str(exc)
    else:
        raise AssertionError("expected missing restrictions to fail workflow contract")


def test_downstream_tasks_include_required_topology_and_restrictions_in_json() -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    pdm_task = build_pdm_tasks(study)[0]
    pdm_outcome = SynthesisTaskOutcome(task=pdm_task, success=True, topology=_topology())
    tdm_task = build_tdm_tasks(study, [pdm_outcome])[0]
    tdm_roundtrip = SynthesisTask.model_validate_json(tdm_task.model_dump_json())

    assert tdm_roundtrip.stages == 2
    assert tdm_roundtrip.restrictions.recovery_heat_duties == _topology().recovery_heat_duties

    tdm_outcome = SynthesisTaskOutcome(task=tdm_task, success=True, topology=_topology())
    esm_task = build_esm_tasks(study, [tdm_outcome])[0]
    esm_roundtrip = SynthesisTask.model_validate_json(esm_task.model_dump_json())

    assert esm_roundtrip.stages == 2
    assert esm_roundtrip.restrictions.recovery_heat_duties == _topology().recovery_heat_duties


def test_local_executor_builds_downstream_problem_with_parent_problem_object() -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    pdm_task = build_pdm_tasks(study)[0]
    parent_problem = HeatExchangerNetworkProblem(name="parent", framework="PDM")
    pdm_outcome = SynthesisTaskOutcome(
        task=pdm_task,
        success=True,
        topology=_topology(),
        problem=parent_problem,
    )
    tdm_task = build_tdm_tasks(study, [pdm_outcome])[0]
    problem = LocalSynthesisExecutor()._build_problem(
        tdm_task,
        parent_outcomes={pdm_task.task_id: pdm_outcome},
    )

    assert problem.parent is parent_problem
    assert problem.stages == 2
    assert problem.framework == "TDM"


def test_downstream_task_defaults_preserve_legacy_solver_settings() -> None:
    study = _study(approach_temperatures=(10,), derivative_thresholds=(1.5,))
    executor = FakeSynthesisExecutor()

    result = run_synthesis_workflow(study, executor=executor)
    tasks_by_method = {task.method: task for task in result.tasks}

    assert tasks_by_method["PDM"].solver == "couenne"
    assert tasks_by_method["TDM"].solver == "couenne"
    assert tasks_by_method["TDM"].dTmin == 0.1
    assert tasks_by_method["ESM"].solver == "ipopt-pyomo"
    assert tasks_by_method["ESM"].objective == "variable total cost"
    assert tasks_by_method["ESM"].non_isothermal_model is True
    assert tasks_by_method["ESM"].integers is False
    assert tasks_by_method["ESM"].evolution_enabled is True


def test_task_outcome_serializes_fake_network_solution_without_live_problem() -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    task = build_pdm_tasks(study)[0]
    problem = _fake_solved_problem(task)

    solution = extract_network_solution(problem, task=task)
    outcome = SynthesisTaskOutcome(
        task=task,
        success=True,
        solver=solution.solver,
        solution=solution,
        problem=problem,
        topology=_topology(),
    )

    payload = outcome.model_dump(mode="json")
    json.dumps(payload)

    assert payload["success"] is True
    assert "problem" not in payload
    assert "topology" not in payload
    assert payload["solution"]["solver"]["name"] == "couenne"
    assert payload["solution"]["recovery_heat_duties"] == [[[10.0, 5.0]]]
    assert payload["solution"]["hot_recovery_outlet_temperatures"] == [[[375.0, 365.0]]]
    assert payload["solution"]["cold_recovery_outlet_temperatures"] == [[[315.0, 325.0]]]
    assert payload["solution"]["utility_loads"] == {"hot": 3.0, "cold": 4.0}
    assert payload["solution"]["unit_counts"] == {
        "total": 3,
        "recovery": 1,
        "hot_utility": 1,
        "cold_utility": 1,
    }


def test_failed_task_outcome_serializes_failure_reason_and_verification_failures() -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    task = build_pdm_tasks(study)[0]

    outcome = SynthesisTaskOutcome(
        task=task,
        success=False,
        solver=SolverRun(
            name=task.solver,
            extension="pyomo",
            status=0,
            objective_value=None,
            solve_time=0.25,
            failure_reason="verification failed: temperature",
        ),
        failure_reason="verification failed: temperature",
        verification_failures=("temperature",),
        problem=object(),
        topology=_topology(),
    )

    payload = outcome.model_dump(mode="json")
    json.dumps(payload)

    assert payload["success"] is False
    assert payload["failure_reason"] == "verification failed: temperature"
    assert payload["verification_failures"] == ["temperature"]
    assert "problem" not in payload
    assert "topology" not in payload


def test_legacy_error_field_populates_failure_reason() -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    task = build_pdm_tasks(study)[0]

    outcome = SynthesisTaskOutcome(task=task, success=False, error="missing parent")

    assert outcome.failure_reason == "missing parent"


def test_facade_delegates_orchestration_to_workflow(monkeypatch, tmp_path) -> None:
    study = _study(approach_temperatures=(2,), derivative_thresholds=(0.5,))
    study = study.model_copy(update={"outputs": StudyOutputs(folder=tmp_path, run_id="workflow-test")})
    model = OpenHENS(study)
    model._output_folder = tmp_path
    called = {}

    def fake_run_synthesis_workflow(study_arg, *, print_output):
        called["study"] = study_arg
        called["print_output"] = print_output
        return SynthesisWorkflowResult(tasks=(), outcomes=(), total_run_time=0.0)

    monkeypatch.setattr("openhens.main.run_synthesis_workflow", fake_run_synthesis_workflow)

    solutions = model._get_optimal_network(
        problem_file=Path("ignored.csv"),
        min_dqda_list=[0.5],
        min_dT_list=[2],
        stage_selection="automated",
    )

    assert solutions == []
    assert called == {"study": study, "print_output": False}


def _study(
    *,
    approach_temperatures: tuple[float, ...],
    derivative_thresholds: tuple[float, ...],
) -> SynthesisStudy:
    return SynthesisStudy(
        case=CaseStudy(source=Path("case.csv"), name="Workflow Test"),
        design_space=DesignSpace(
            approach_temperatures=approach_temperatures,
            derivative_thresholds=derivative_thresholds,
        ),
        solving=SolveSetup.local(tolerance=1e-3, max_parallel=4),
    )


def _topology() -> TaskTopology:
    return TaskTopology(stages=2, recovery_heat_duties=(((10.0, 0.0), (0.0, 5.0)),))


def _fake_solved_problem(task: SynthesisTask):
    options = type("Options", (), {"SOLVER_EXTENSION": "pyomo", "SOLVESTATUS": 1, "objfcnval": 123.4})()
    model = type("Model", (), {"options": options})()
    case = type(
        "Case",
        (),
        {
            "name": "fake solved case",
            "framework": task.method,
            "solver": task.solver,
            "m": model,
            "mSuccess": 1,
            "S": 2,
            "stages": 2,
            "dTmin": task.dTmin,
            "min_dqda": task.min_dqda,
            "solve_time": 1.5,
            "Q_r": ((([10.0], [5.0]),),),
            "Q_h": ([3.0],),
            "Q_c": ([4.0],),
            "T_h": (([400.0], [350.0], [300.0]),),
            "T_c": (([280.0], [320.0], [360.0]),),
            "T_h_out_x": ((([375.0], [365.0]),),),
            "T_c_out_y": ((([315.0], [325.0]),),),
            "area_r": ((([1.25], [0.75]),),),
            "area_hu": ([0.5],),
            "area_cu": ([0.25],),
            "dqda": ((([2.5], [1.5]),),),
            "Q_hu_total": 3.0,
            "Q_cu_total": 4.0,
            "n_units": 3,
            "n_recovery_units": 1,
            "n_hu_units": 1,
            "n_cu_units": 1,
            "TAC": 125.0,
            "TAC_model": 123.4,
            "solver_run": SolverRun(
                name=task.solver,
                extension="pyomo",
                status=1,
                objective_value=123.4,
                solve_time=1.5,
            ),
        },
    )()
    return type(
        "Problem",
        (),
        {
            "name": "fake problem",
            "framework": task.method,
            "solver": task.solver,
            "dTmin": task.dTmin,
            "min_dqda": task.min_dqda,
            "synthesis_task_id": task.task_id,
            "case": case,
        },
    )()
