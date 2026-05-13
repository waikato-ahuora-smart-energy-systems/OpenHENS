'''
__author__ = 'Keegan Hall and Tim Walmsley'
__credits__ = ['tbc']
'''

from dataclasses import dataclass
import multiprocessing
from ..logger import openhens_log as logger
from ..classes import HeatExchangerNetworkProblem


@dataclass(frozen=True)
class ProblemRunResult:
    """Multiprocessing-safe envelope for one attempted legacy problem solve."""

    problem: HeatExchangerNetworkProblem
    success: bool
    failure_reason: str | None = None
    verification_failures: tuple[str, ...] = ()


def run_single_solution(
        problem: HeatExchangerNetworkProblem,            
        print_output: bool,
        evolution: True | False = False,
    ) -> HeatExchangerNetworkProblem | None:
    """Compatibility wrapper returning the old ``[problem]``/``None`` shape."""

    result = run_single_solution_result(problem, print_output=print_output, evolution=evolution)
    return [problem] if result.success else None


def run_single_solution_result(
        problem: HeatExchangerNetworkProblem,
        print_output: bool,
        evolution: True | False = False,
    ) -> ProblemRunResult:
    """Solve one problem and preserve success or failure details."""

    problem.solution_failure_reason = None
    problem.verification_failures = ()
    try:
        solution = problem.get_solution(print_output=print_output, evolution=evolution)
    except Exception as exc:
        reason = str(exc) or exc.__class__.__name__
        problem.solution_failure_reason = reason
        return ProblemRunResult(problem=problem, success=False, failure_reason=reason)

    if not solution:
        reason = getattr(problem, "solution_failure_reason", None) or "model failed to load or solve"
        problem.solution_failure_reason = reason
        return ProblemRunResult(problem=problem, success=False, failure_reason=reason)

    if not getattr(solution, "mSuccess", 0):
        solver_run = getattr(solution, "solver_run", None)
        # Prefer the structured failure reason from the solver wrapper when it
        # exists; older models only expose the GEKKO success flag.
        reason = getattr(solver_run, "failure_reason", None) or f"solver status {getattr(solution, 'mSuccess', None)}"
        problem.solution_failure_reason = reason
        return ProblemRunResult(problem=problem, success=False, failure_reason=reason)

    is_valid, reasons = solution.verify()
    if not is_valid:
        verification_failures = tuple(str(reason) for reason in reasons)
        reason = "verification failed: " + ", ".join(verification_failures)
        problem.solution_failure_reason = reason
        problem.verification_failures = verification_failures
        logger.warning(f"[VerifyFail] {problem.name} failed checks: {', '.join(verification_failures)}")

        parent = getattr(problem, "parent", None)
        if parent:
            logger.info(f"Problem parent: {parent}")
            grandparent = getattr(parent, "parent", None)
            if grandparent:
                logger.info(f"Problem grandparent: {grandparent}")
        return ProblemRunResult(
            problem=problem,
            success=False,
            failure_reason=reason,
            verification_failures=verification_failures,
        )

    return ProblemRunResult(problem=problem, success=True)


def run_parallel_solutions(
        problems: list[HeatExchangerNetworkProblem],
        max_parallel: int = 1,
        print_output: bool = False,
        evolution: True | False = False
    ) -> list[HeatExchangerNetworkProblem]:
    """Solve problems in parallel and return only successful legacy objects."""

    solved_cases = []
    with multiprocessing.Pool(processes=max_parallel) as pool:
        running_processes = [
            pool.apply_async(
                run_single_solution, args=(p, print_output, evolution)
            ) for p in problems
        ]

        while running_processes:
            for p in running_processes:
                if p.ready():
                    solved_case = p.get()
                    if solved_case:
                        solved_cases.extend(solved_case)
                    running_processes.remove(p)  # Remove the completed process

    return solved_cases


def run_parallel_solution_results(
        problems: list[HeatExchangerNetworkProblem],
        max_parallel: int = 1,
        print_output: bool = False,
        evolution: True | False = False
    ) -> list[ProblemRunResult]:
    """Solve cases in parallel and return one result record per attempted problem.

    The task workflow uses this richer form so failed solver jobs still appear
    in ``TaskOutcome`` records and artifacts.
    """

    results = []
    with multiprocessing.Pool(processes=max_parallel) as pool:
        running_processes = [
            pool.apply_async(
                run_single_solution_result, args=(p, print_output, evolution)
            ) for p in problems
        ]

        while running_processes:
            for p in running_processes:
                if p.ready():
                    results.append(p.get())
                    running_processes.remove(p)

    return results
