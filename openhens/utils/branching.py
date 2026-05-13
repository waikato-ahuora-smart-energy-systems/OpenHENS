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
    problem: HeatExchangerNetworkProblem
    success: bool
    failure_reason: str | None = None
    verification_failures: tuple[str, ...] = ()


def run_single_solution(
        problem: HeatExchangerNetworkProblem,            
        print_output: bool,
        evolution: True | False = False,
    ) -> HeatExchangerNetworkProblem | None:
    """   
    Calls get_solution to solve model in GEKKO and loops for the specified number of networks. Must be called seperately to class initialisation

    Args:
    - problem: built but not yet solved single case
    - print_output: enable print output of network metrics and matches
    - evolution: evolution toggle, either True or False

    Returns:
    - the solved case
    """
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
    """
    Solves each case on a seperate CPU core
    
    Packages HEN problem into a tuple allowing it to be solved via parallel computing to make it faster
    
    Args:
    - problems: list of built but not yet solved cases
    - number_of_networks: number of networks to return i.e number of cuts + 1 so 2 networs will integer cut once
    - max_parallel: number of worker threads to be used for parallel execution
    - print_output: print output of network metrics and matches
    - evolution: evolution toggle, either True or False
    """

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
    """Solve cases in parallel and return one result record per attempted problem."""

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
