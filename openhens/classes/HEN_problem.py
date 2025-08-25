'''
__author__ = 'Keegan Hall and Tim Walmsley'
__credits__ = ['tbc']
'''
from typing import Literal, List
from .stage_wise_model import StageWiseModel
from .grid_diagram import Grid_Diagram
from .pinch_decomp_model import PinchDecompModel
import matplotlib.pyplot as plt
from ..logger import openhens_log as logger



class HeatExchangerNetworkProblem: 
    def __init__(
            self,
            name: str = "",
            framework: str = "dQ/dA",
            solver: int = 1,
            dTmin: float = 0.1,
            import_file: str = "",
            min_dqda: float = 0,
            z_restriction: bool | None = None,
            minimisation_goal: str = "hot utility",
            non_isothermal_model: bool = False,
            integers: bool = True,
            parent: "HeatExchangerNetworkProblem" = None,
            tol: float = 1e-3,
            stage_selection: str | list[str] = "automated", 
        ):
        """
        Constructs arguements dictionary that contains the details for creating the model

        User provides the model details via strings which activate if statements in code to construct the specific model

        Args:
        - name: name of case and cut number
        - framework: specifies what model equations to comprise
        - solver: specifies the solver to use in GEKKO
        - dTmin: specifies minimum approach temperature for a recovery heat exchanger match
        - import_file: specifies case to solve via a string containing the filename in the 'cases' folder
        - min_dqda: specifies the minimum dQ/dA for a recovery heat exchanger match. Low value means 'low bar' for unit to be considered good
        - z_restriction: specifies wether the heat exchanger matches would be restricted from those in the init_solution (True) or any feasibloe match (False)
        - minimisation_goal: specifies the objective function type
        - non_isothermal_model: specifies wether non_isothermal model is created.
        - integers: specifies wether the model has integer variables (True) or not (False)
        - parent: solved HEN_problem instance object containing values for initialisation of current object
        - tol: tolerance for GEKKO solver
        - stage_selection: specifies the stage selection criteria for the PDM. If 'automated', stages are automatically selected based on the number of hot and cold streams in each submodel. If a list, stages are set to the specified values.
        """
        self.name = name
        self.framework = framework
        self.solver = solver
        self.dTmin = dTmin
        self.import_file = import_file
        self.min_dqda = min_dqda
        self.z_restriction = z_restriction
        self.minimisation_goal = minimisation_goal
        self.non_isothermal_model = non_isothermal_model
        self.integers = integers
        self.parent = parent
        self.tol = tol
        self.stage_selection = stage_selection


    def load_model(self) -> None:
        '''
        Constructs specific model from model arguments

        Extracts the framework and model type argument to call the appropriate model class. It then passes the argument dictionary with **  which extracts the dictionary arguments as positional arguments to the model class. 
        '''
        
        self.args = {
            'name' : self.name,
            'framework' : self.framework,             
            'solver' : self.solver,
            'dTmin' : self.dTmin,
            'import_file' : self.import_file,
            'min_dqda' : self.min_dqda,
            'z_restriction' : self.z_restriction,
            'minimisation_goal' : self.minimisation_goal,
            'non_isothermal_model' : self.non_isothermal_model,
            'integers' : self.integers, 
            'tol' : self.tol,
        }

        #  Construct model
        if self.framework == 'PDM':
            self._build_pdm()  # Construct above and below pinch models for PDM framework
        else:
            self._build_stage_wise() # Construct single stage-wise model for TDM or ESM framework
            
    def _build_pdm(self) -> None:
        """Constructs above and below pinch models for PDM framework."""
        base_args = self.args.copy()

        above_args = base_args | {
            'name': f'above pinch {self.dTmin}',
            'pinch_loc': 'above',
            'minimisation_goal': 'hot utility',
            'stage_selection': self.stage_selection, 
        }
        below_args = base_args | {
            'name': f'below pinch {self.dTmin}',
            'pinch_loc': 'below',
            'minimisation_goal': 'cold utility',
            'stage_selection': self.stage_selection, 
        }

        self.above = PinchDecompModel(**above_args)
        self.below = PinchDecompModel(**below_args)
    
    def _build_stage_wise(self) -> None:
        self.case = StageWiseModel(**self.args, stages=self.parent.case.stages) # single stage-wise model
        if self.parent is not None:
            self.case.set_initial_values_for_variables(self.parent.case)
    
    def _solve_pdm(self, print_output: bool = True) -> None:
        """Solves above and below pinch models and combines them for the PDM framework."""
        # Solve above and below pinch models unless they are threshold problems
        if self.above.HU_target > 0:
            self.above.optimise(print_output=print_output)
           
        if self.below.CU_target > 0:
            self.below.optimise(print_output=print_output)
           
        # Amalgamate networks and post-process
        self.case = self.above.amalgamate_networks(
            below_case=self.below,
            above_case=self.above
        )
        self.case.get_post_process()

        if print_output:
            self.case.output_to_cmd_line()

        self.args.update({
            'name': f'PDM amalgamated {self.dTmin}',
            'minimisation_goal': 'total utility',
            'tol': self.tol
        }) 

    def check_logger_levels(self):
        print(f"\n[LOG TEST] Logger level: {logger.level}")
        for i, h in enumerate(logger.handlers):
            print(f"[LOG TEST] Handler {i} level: {h.level}")

        logger.debug("Should appear if level is DEBUG or lower")
        logger.info("Should appear if level is INFO or lower")
        logger.warning("Should appear if level is WARNING or lower")
        logger.error("Should appear if level is ERROR or lower")
        logger.critical("Should always appear")

    def get_solution(self, print_output=True, evolution=None) -> StageWiseModel | None:
        """
        Solves the HEN synthesis proble, using the specified framework.

        Depending on the `framework` type ('PDM', 'TDM', or ESM), the method solves the model by optimising above and/or below pinch models, optionally post-processing and removing unused stages. 

        Args:
            print_output (bool): Whether to print solution output to the command line.
            evolution (optional): If provided, triggers evolution

        Returns:
            StageWiseModel: The solved model object if successful.
            None: If model loading or solving fails.
        """
        try:
            self.load_model()
            
            if self.framework == 'PDM': # solve above and below pinch models then amalgamte networks and post process
               self._solve_pdm(print_output=print_output)

            else: # solve single model
                self.case.optimise(print_output=print_output)
            
            if self.framework in ['PDM', 'TDM']:
                self.case = self.remove_unused_stages(case = self.case) 
            
            if self.framework in ['ESM', 'TDM']:
                #self.check_removed_matches() # debugging function to check if matches have been removed
                pass
           
            if evolution:
                self.case.get_net_benefit_evolution(print_output=print_output)
     
    
            return self.case
        
        except ValueError as e:
            logger.error(f'StageWiseModel failed to load or solve. Error: {e}')
            return None

    def check_removed_matches(self) -> None:
        for k in range(self.case.S):
            for j in range(self.case.J):
                for i in range(self.case.I):
                    if self.parent.case.Q_r[i][j][k][0] > self.tol and self.case.Q_r[i][j][k][0] < self.tol:
                        logger.warning(f"Match removed:  stream {i}->{j} stage {k},, duty {self.parent.case.Q_r[i][j][k][0]} -> {self.case.Q_r[i][j][k][0]}")
        

    def get_grid_diagram(self, draw_stages=False) -> Grid_Diagram:
        """
        Plots grid diagram

        Calls visualisation class to plot grid diagram of a particular case specified by case_index which is the position of the solved model in the case_list. Must be called seperately to class initialisation  
        """
        # Extact desired case from case list
        if self.case.mSuccess == 1:
            non_iso = True if self.case.non_isothermal_model else False # defines whether to plot branch (non-isothermal) or stage (isothermal) temperatures
            grid = Grid_Diagram(network=self.case, non_iso=non_iso, draw_stages=draw_stages)
        
        return grid # returns the grid diagram object
    
    def remove_unused_stages(self, case) -> StageWiseModel: 
        """
        Removes unused or underutilised stages and updates internal variables accordingly.
        
        Parameters:
            case (StageWiseModel): Original case.
        
        Returns:
            StageWiseModel: A modified case with reduced stages, or the original case if the reduced case solve was unsuccessful.
        """
        if case.mSuccess != 1:
            logger.warning("Initial model was not successful; skipping stage reduction.")
            return case
        
        def assign(var, val):
            if type(var).__name__ == "GKParameter": # parameters have no bounds
                pass
            else:
                val = max(var.lower, min(var.upper, val))
                 
            var.VALUE.value =  val

        def assign_bin(var, val):
            var.VALUE.value = 1 if val > case.tol else 0
                
           
        active_stages = self._get_active_stages(case)  # Identify active stages based on criteria
        if len(active_stages) == case.S:
            logger.info("All stages are active — no reduction needed.")
            return case
        
        # Determine z_allowed list under new number of stages
        active_locations = [[[None for _ in range(len(active_stages))] for _ in range(case.J)] for _ in range(case.I)]
        for new_k, old_k in enumerate(active_stages):
            for i in range(case.I):
                for j in range(case.J):
                    active_locations[i][j][new_k] = 1 if case.Q_r[i][j][old_k][0] > case.tol else 0 
        
        # Initialise new SWS with reduced stages
        f_case = StageWiseModel(
            name=f'reduced-{case.name}',
            framework=case.framework,
            solver= 'apopt', #case.solver,
            import_file=case.import_file,
            stages=len(active_stages),
            dTmin=case.dTmin,
            z_restriction=[active_locations, None, None], 
            min_dqda=case.min_dqda,
            minimisation_goal=case.minimisation_goal,
            non_isothermal_model=case.non_isothermal_model,
            integers=False,
            tol=case.tol,
        )
        
        # Copy recovery HX values
        for new_k, old_k in enumerate(active_stages):
            for i in range(case.I):
                for j in range(case.J):
                    q_val = case.Q_r[i][j][old_k][0] if case.Q_r[i][j][old_k][0] > case.tol else 0.0
                    assign(f_case.Q_r[i][j][new_k], q_val)
                    assign_bin(f_case.z[i][j][new_k], q_val)
                    assign(f_case.theta_1[i][j][new_k], case.theta_1[i][j][old_k][0])
                    assign(f_case.theta_2[i][j][new_k], case.theta_2[i][j][old_k][0])
            
                    if case.non_isothermal_model:
                        assign(f_case.X[i][j][new_k], case.X[i][j][old_k][0])
                        assign(f_case.Y[j][i][new_k], case.Y[j][i][old_k][0])
                        assign(f_case.T_h_out_x[i][j][new_k], case.T_h_out_x[i][j][old_k][0])
                        assign(f_case.T_c_out_y[j][i][new_k], case.T_c_out_y[j][i][old_k][0])

            # Copy temperature boundary values 
            for i in range(case.I):
                for new_k, old_k in enumerate([0] + [s + 1 for s in active_stages]):
                    assign(f_case.T_h[i][new_k], case.T_h[i][old_k][0])

            for j in range(case.J):
                for new_k, old_k in enumerate([0] + [s + 1 for s in active_stages]):
                    assign(f_case.T_c[j][new_k], case.T_c[j][old_k][0])

            # Copy utility variables
            for i in range(case.I):
                assign(f_case.Q_c[i], case.Q_c[i][0])
                assign_bin(f_case.z_cu[i], case.Q_c[i][0])

            for j in range(case.J):
                assign(f_case.Q_h[j], case.Q_h[j][0])
                assign_bin(f_case.z_hu[j], case.Q_h[j][0])
        
        # Metadata
        f_case.TAC_model = case.TAC_model
        f_case.TAC = case.TAC
        f_case.solve_time = case.solve_time
        f_case.mSuccess = case.mSuccess
   
        # Re-solve with reduced stages
        f_case.optimise(print_output=False)
        if f_case.mSuccess != 1: # return unreduced case if reduced model fails to solve
            logger.warning(f"Failed to solve reduced model {f_case.name}. Returning original case.")
            return case

        return f_case
    
    
    def _get_active_stages(self, case) -> List[int]:
        Q_total = sum(case.Q_r[i][j][k][0] for i in range(case.I) for j in range(case.J) for k in range(case.S))
        Q_per_stage = [
            sum(case.Q_r[i][j][k][0] for i in range(case.I) for j in range(case.J))
            for k in range(case.S)
        ]
        threshold = self._utilisation_threshold(case.S)
        return [k for k, Qk in enumerate(Q_per_stage) if Qk / Q_total * 100 >= threshold]
    
    def _utilisation_threshold(self, S) -> float :
        # could add check so that stages arent reduced by more than the max num of hot or cold streams
        if S <= 3:
            return 0.1
        elif S <= 5:
            return 5.0
        elif S <= 8:
            return 8.0
        elif S <= 10:
            return 10.0
        else:
            return 0
        
        
