'''
__author__ = 'Keegan Hall and Tim Walmsley'
__credits__ = ['tbc']
'''


import multiprocessing
from ..logger import openhens_log as logger
from ..classes import HeatExchangerNetworkProblem


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
    solved_cases = []

    # Solve the most recently built case
    solution = problem.get_solution(print_output=print_output, evolution=evolution)
    if not solution or not getattr(solution, "mSuccess", 0):
        return None

    # Check feasibility of solution
    is_valid, reasons = solution.verify()
    if not is_valid:
        logger.warning(f"[VerifyFail] {problem.name} failed checks: {', '.join(reasons)}")

        # Log parent hierarchy (if present)
        parent = getattr(problem, "parent", None)
        if parent:
            logger.info(f"Problem parent: {parent}")
            grandparent = getattr(parent, "parent", None)
            if grandparent:
                logger.info(f"Problem grandparent: {grandparent}")
        return None

    solved_cases.append(problem)
    return solved_cases or None


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
