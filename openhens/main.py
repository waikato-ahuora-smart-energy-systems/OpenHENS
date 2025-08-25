'''
__author__ = 'Keegan Hall and Tim Walmsley'
__credits__ = ['tbc']

Simultaneous synthesis, design and optimization followed by network evolution
for process heat exchanger networks given input data
'''

from typing import Any, Literal
import os
from .classes import HeatExchangerNetworkProblem
from .utils import run_parallel_solutions, save_pickle, get_n_best_by_TAC, save_esm_metrics, save_run_summary, plot_metric_relationships, open_pickle
from timeit import default_timer as timer
import pickle
import matplotlib.pyplot as plt
from pathlib import Path


from openhens.logger import openhens_log as logger, add_handler
import logging
import sys


class OpenHensOptions:

    def __init__(self, **kwargs) -> None:
        # default options
        self.input_folder: str = f'examples/cases/Four-stream-Yee-and-Grossmann-1990-1.csv'
        self.output_folder: str = f'examples/results/Four-stream-Yee-and-Grossmann-1990-1'
        self.min_dT_list: list[float] = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20,]
        self.min_dqda_list: list[float] = [0.5, 0.9, 1.3, 1.7, 2.1, 2.4, 2.8, 3.2, 3.6, 4.0]
        self.stage_selection: str | list[float] = 'automated'
        self.tolerance: float = 1e-3
        self.max_parallel: int = 10
        self.best_solns_to_save: int = 10
        self.log_level: int = logging.WARNING
        
        # update options with kwargs passed in
        for k, v in kwargs.items():
            setattr(self, k, v)

class OpenHENS:
    """
    OpenHens class to solve HEN problems

    Methods:
    - solve: solve the problem
    - display_results: plots key results from the solved problem
    - _from_run: plots the best solution from the current solve
    - _from_run_from_file: plots the best solution from all solves

    Options:
    - see OpenHensOptions for available options
    """

    def __init__(self, **options) -> None:
        """
        - problem_file (str): path to csv problem file
        - options (dict): options for solving the problem (see OpenHensOptions)
        """
        self.options = OpenHensOptions(**options)
    
        self.set_log_level(self.options.log_level)
      
    def set_log_level(self, level: int) -> None:
        logger.setLevel(level)

        if not logger.handlers:
            stream_handler = logging.StreamHandler(sys.stdout)
            add_handler(stream_handler, level)
        else:
            for h in logger.handlers:
                h.setLevel(level)  # <- override even fallback INFO level
        
    def solve(self) -> None:
        """
        Solve the problem
        """
        self._problem_file = Path(self.options.input_folder)
        self._output_folder = Path(self.options.output_folder)
        self._output_folder.mkdir(parents=True, exist_ok=True)
        
        # Run 
        self.solutions = self._get_optimal_network(
            problem_file = self._problem_file, 
            min_dqda_list = self.options.min_dqda_list,
            min_dT_list = self.options.min_dT_list,
            stage_selection = self.options.stage_selection
        )

        # Save top n-best solutions to pickle
        # return n best where index 0 is best, index n is n best
        self._best_solns = get_n_best_by_TAC(self.solutions, self.options.best_solns_to_save)
        i=1 # start ranking as 1=best 2=next best
        for P_i in self._best_solns: # iterate across each best soln
            file_to_save = self._output_folder / '{} best.pkl'.format(i)
            # First check for existing file and only save if its better than the existing 
            if file_to_save.is_file() == True: # file exists
                n_best = pickle.load(open(file_to_save,'rb')) # load existing soln
                if P_i.case.TAC < n_best.case.TAC: # new soln is better so replace file
                    with open(file_to_save, 'wb') as model_file:
                        pickle.dump(P_i, model_file)
                else: # keep existing file
                    pass
            elif file_to_save.is_file() == False: # create new file
                with open(file_to_save, 'wb') as model_file:
                    pickle.dump(P_i, model_file)
            i=i+1 # add to i for next best
    

    def display_run_metrics(self) -> None:
        # Plot results from the current run
        if len(self.solutions) == 0:
            logger.warning("No solutions found, skipping display run metrics")
            return
        
        # Save and retrieve ESM metrics
        ESM_metrics = save_esm_metrics(P_list=self.solutions, path=self._output_folder)
      
        # Generate all standard plots
        try:
            plot_metric_relationships(metrics=ESM_metrics, path=self._output_folder)
        except Exception as e:
            logger.error(f"Plotting failed: {e}")
        
        # Save run summary
        
    def display_best_from_run(self) -> None:
        if len(self._best_solns) == 0:
            logger.warning("No solutions found, skipping display best from run")
            return
        logger.warning(f"best from current solve {self._best_solns[0].name} {self._best_solns[0].case.TAC}")
        self._best_solns[0].get_grid_diagram()
        plt.show()


    def display_n_best_from_file(self, n_best: int = 1) -> None:
        # Open best overall soln
        file_to_open = self._output_folder / '{} best.pkl'.format(n_best)
        if not os.path.exists(file_to_open):
            logger.warning(f"No overall best file found: `{file_to_open}`")
            return
        best = pickle.load(open(file_to_open, 'rb'))
        logger.warning(f"{n_best} best from file {best.name} {best.case.TAC}")
        best.get_grid_diagram()

    def _get_optimal_network(
            self, 
            problem_file,
            min_dqda_list,
            min_dT_list,
            stage_selection, 
        ) -> list[HeatExchangerNetworkProblem]:
        """
        Builds and solves different model types for a specific HEN synthesis problem
        
        For each model type the user specified model parameters are passed into the HEN problem class and returns a seperate list of the solved objects
        
        Args:
        - problem_file: filename of problem
        - stages_list: list containing the specified stages that the problem will be solved with
        - min_dqda_list: list containing the specified min dQ/dA that the problem will be with
        - min_dT_list: minimum dT for all problem objects created
        """
        start_tiem = timer()
        
        # Pinch Decomposition Method (PDM)
        pdm_problems: list[HeatExchangerNetworkProblem] = []
        for min_dT in min_dT_list:
                problem = HeatExchangerNetworkProblem(
                    name='P-+''--PDM-'+str(min_dT),
                    framework='PDM',
                    solver= 'couenne',
                    dTmin=min_dT, 
                    import_file=problem_file, 
                    z_restriction=[None,None,None], 
                    minimisation_goal='hot utility', 
                    non_isothermal_model=False,
                    integers=True, 
                    tol=self.options.tolerance,
                    parent=None,
                    stage_selection=stage_selection,
                )
                pdm_problems.append(problem)
        
        pdm_solutions = run_parallel_solutions(
            problems=pdm_problems,
            max_parallel=self.options.max_parallel,
            print_output=False,
            evolution=False
        )
        logger.warning(f"PDM Completed: {len(pdm_solutions)} solutions found")
       
        # Thermal Derivative Method (TDM)
        tdm_problems: list[HeatExchangerNetworkProblem] = []
        for pdm in pdm_solutions:
            for min_dqda in min_dqda_list:
                args = pdm.args.copy()
                args.update({
                    "name": 'P-S'+str(pdm.case.stages)+'--TDM-'+str(min_dqda),
                    "framework": 'TDM',
                    "solver": 'couenne',
                    "dTmin": 0.1,
                    "import_file": problem_file,
                    "non_isothermal_model": False,
                    "integers": True,
                    "min_dqda": min_dqda,
                    "minimisation_goal": 'hot utility',
                    "z_restriction": [pdm.case.Q_r, None, None]
                })
                tdm_problems.append(HeatExchangerNetworkProblem(**args, parent=pdm))
        
        tdm_solutions = run_parallel_solutions(
            problems=tdm_problems,
            max_parallel=self.options.max_parallel,
            print_output=False,
            evolution=False
        )

        tdm_ordered_solutions = get_n_best_by_TAC(tdm_solutions, 20)
        logger.warning(f"TDM Completed: {len(tdm_solutions)} solutions found")
       
        # Evolutionary Synthesis Method (ESM)
        esm_problems: list[HeatExchangerNetworkProblem] = []
        for tdm in tdm_solutions:
            args = tdm.args.copy()
            args.update({
                "name": 'P-S'+str(tdm.case.stages)+'-Synheat-Iso-NLP',
                "framework": 'ESM',
                "solver": 'ipopt-pyomo',
                "non_isothermal_model": True,
                "integers": False,
                "minimisation_goal": 'variable total cost',
                "z_restriction": [tdm.case.Q_r, None, None]
            })
            esm_problems.append(HeatExchangerNetworkProblem(**args, parent=tdm))
        
        esm_solutions = run_parallel_solutions(
            problems=esm_problems,
            max_parallel=self.options.max_parallel,
            print_output=False,
            evolution=True
        )
        logger.warning(f"ESM Completed: {len(esm_solutions)} solutions found")
        end_time = timer()
        total_run_time = end_time - start_tiem
        logger.warning(f"Total run time: {total_run_time}s")
        logger.debug(f"PDM: {pdm_solutions}")
        logger.debug(f"TDM: {tdm_solutions}")
        logger.debug(f"ESM: {esm_solutions}")

        combined_solutions = pdm_solutions + tdm_solutions + esm_solutions

        if len(combined_solutions) == 0:
            logger.warning("No solutions found")
            return []

        save_run_summary(
            path=self._output_folder,
            P_list=combined_solutions,
            attempted=len(min_dT_list) + len(min_dqda_list)*len(pdm_solutions) + len(tdm_solutions)*11,
            total_run_time=total_run_time
        )

        return combined_solutions
