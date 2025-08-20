from typing import Literal
from gekko import GEKKO, gk_variable
import numpy as np
import pandas as pd
from pathlib import Path
from abc import ABC, abstractmethod
from pyomo.environ import SolverFactory
import logging
from ..logger import openhens_log as logger
import time

class GenericHENModel(ABC):
    def __init__(
            self,
            name: str,
            framework: Literal["PDM", "TDM", "ESM"],
            solver: Literal["couenne", "ipopt"],
            import_file: Path,
            dTmin: float,
            z_restriction: list[float],
            min_dqda: float,
            minimisation_goal: Literal["hot utility", "total utility", "utility costs", "heat recovery", "total cost", "variable total cost"],
            non_isothermal_model: bool,
            integers: bool,
            tol: float,
            solver_options: list[str] = [],
        ) -> None:
        self.name = name
        self.framework = framework
        self.solver = solver
        self.import_file = import_file
        self.dTmin = dTmin
        self.z_restriction = z_restriction
        self.min_dqda = min_dqda
        self.minimisation_goal = minimisation_goal
        self.non_isothermal_model = non_isothermal_model
        self.integers = integers
        self.tol = tol
        self.solver_options = solver_options
        
        self.solve_time = None

        self.setup_model()
        self.setup()


    def setup_model(self) -> None:
        self.m = GEKKO(remote=False)
        self.mSuccess: int = 0
        
        # Set up solver options
        if self.solver in ['couenne', 'ipopt-pyomo']:
            self.m.options.SOLVER_EXTENSION = "pyomo"
        elif self.solver in ['ipopt-GEKKO', 'apopt']:
            self.m.options.SOLVER_EXTENSION = 0
        
        self.m.options.SOLVER = self.solver.split('-')[0]
       
        if self.solver in ['ipopt-GEKKO', ]:
            self.m.solver_options = [
                'tol 1e-3',                            # Overall optimality tolerance
                'acceptable_tol 1e-2',                # IPOPT will stop here if no better solution is found
                'constr_viol_tol 1e-2',               # Allow constraints to be violated up to this much
                'acceptable_constr_viol_tol 1e-1',    # Allow larger violation temporarily
                'compl_inf_tol 1e-2',                 # Tolerance for complementary constraints (e.g. bounds)
                'max_iter 1000',                      # Increase iterations if needed
                'print_level 5',                      # Optional: more verbose IPOPT output
            ]
        if self.solver in ['apopt', ]:    
            self.m.options.MAX_ITER = 1000
            self.m.options.RTOL = 1e-2
            self.m.options.OTOL = 1e-2
            
        # check solver is available
        try:
            if self.m.options.SOLVER_EXTENSION == "pyomo":
                SolverFactory(self.m.options.SOLVER).available()
            else:
                pass
        except:
            raise Exception(f"{self.solver} solver not found. Please check the solver is installed and the path is correct.")
    

    @abstractmethod
    def setup(self) -> None:
        """
        Defines the order of setup methods to create the model
        Implemented in the subclass
        """
        pass

    @abstractmethod
    def set_preprocessing(self) -> None:
        pass


    @abstractmethod
    def set_stage_wise_superstructure(self) -> None:
        pass

    def set_blank_input_parameters(self):
        #INPUT PARAMETERS
        #   Hot streams
        self.T_h_in = np.array([], dtype=float)         #supply temp. of hot stream i
        self.T_h_out = np.array([], dtype=float)        #target temp. of hot stream i
        self.f_h = np.array([], dtype=float)            #heat capacity flowrate of hot stream i
        self.htc_h = np.array([], dtype=float)          #stream-individual film coefficient hot i
        self.h_cost =  np.array([], dtype=float)        #hot stream cost
        self.hot_names = np.array([], dtype=str)        #hot stream names
        self.T_h_cont = np.array([], dtype=float)       #hot stream temperature contribution

        #   Cold streams
        self.T_c_in = np.array([], dtype=float)         #supply temp. of cold stream j
        self.T_c_out = np.array([], dtype=float)        #target temp. of cold stream j
        self.f_c = np.array([], dtype=float)            #heat capacity flowrate of cold stream j
        self.htc_c = np.array([], dtype=float)          #stream-individual film coefficient cold j
        self.c_cost =  np.array([], dtype=float)        #cold stream cost
        self.cold_names = np.array([], dtype=str)       #cold stream names
        self.T_c_cont = np.array([], dtype=float)       #cold stream temperature contribution

        #   Hot utility
        self.hu_cost = np.array([], dtype=float)        #hot utility prices
        self.hu_unit_cost = np.array([], dtype=float)   #fixed charge for heater
        self.hu_coeff = np.array([], dtype=float)       #area cost coefficient for heaters
        self.T_hu_in = np.array([], dtype=float)        #supply temp. of hot utility j
        self.T_hu_out = np.array([], dtype=float)       #target temp. of hot utility j
        self.htc_hu = np.array([], dtype=float)         #heat transfer coefficient for hot utility j
        self.hu_exp = np.array([], dtype=float)         #area cost exponent

        #   Cold utility
        self.cu_cost = np.array([], dtype=float)        #cold utility prices
        self.cu_unit_cost = np.array([], dtype=float)   #fixed charge for cooler
        self.cu_coeff = np.array([], dtype=float)       #area cost coefficient for coolers
        self.T_cu_in = np.array([], dtype=float)        #supply temp. of cold utility i
        self.T_cu_out = np.array([], dtype=float)       #target temp. of cold utility i
        self.htc_cu = np.array([], dtype=float)         #heat transfer coefficient for cold utility i
        self.cu_exp = np.array([], dtype=float)         #area cost exponent

        #   Heat exchange
        self.unit_cost = np.array([], dtype=float)      #fixed charge for exchanger
        self.A_coeff = np.array([], dtype=float)        #area cost coefficient for exchangers
        self.A_exp = np.array([], dtype=float)          #area cost exponent
    

    def get_model_parameters_from_file(self):   
        try:               
            df = pd.read_csv(self.import_file, sep=None, engine='python') # save csv to pandas dataframe using the python engine to detect what the file seperator is
            df_a = df.to_numpy(na_value=None)  # Convert to array where each row is a nested array
            
            stream_designation = 3  # Column of the stream designation

            for row in df_a:  # Iterate across each variable
                if row[stream_designation] in ["Hot", "hot"]:  # Append variables to hot stream arrays
                    self.hot_names = np.append(self.hot_names, str(row[2]))
                    self.T_h_in = np.append(self.T_h_in, float(row[4]))
                    self.T_h_out = np.append(self.T_h_out, float(row[5]))
                    self.f_h = np.append(self.f_h, float(row[6]))
                    self.htc_h = np.append(self.htc_h, float(row[7]))
                    self.h_cost = np.append(self.h_cost, float(row[8]))
                    if len(row) == 10: # if Tcont is given in data import it 
                        self.T_h_cont = np.append(self.T_h_cont, float(row[9]))
                    else:
                        self.T_h_cont = np.append(self.T_h_cont, self.dTmin/2)
                    

                elif row[stream_designation] in ["Cold", "cold"]:  # Append variables to hot stream arrays
                    self.cold_names = np.append(self.cold_names, str(row[2]))
                    self.T_c_in = np.append(self.T_c_in, float(row[4]))
                    self.T_c_out = np.append(self.T_c_out, float(row[5]))
                    self.f_c = np.append(self.f_c, float(row[6]))
                    self.htc_c = np.append(self.htc_c, float(row[7]))
                    self.c_cost = np.append(self.c_cost, float(row[8]))
                    if len(row) == 10:
                        self.T_c_cont = np.append(self.T_c_cont, float(row[9]))
                    else: 
                        self.T_c_cont = np.append(self.T_c_cont, self.dTmin/2)

                elif row[stream_designation] in ["Hot Utility", "Hot utility", "hot utility"]:  # Append variables to hot utility stream arrays
                    self.T_hu_in = np.append(self.T_hu_in, float(row[4]))
                    self.T_hu_out = np.append(self.T_hu_out, float(row[5]))
                    self.htc_hu = np.append(self.htc_hu, float(row[7]))
                    self.hu_cost = np.append(self.hu_cost, float(row[8]))

                elif row[stream_designation] in ["Cold Utility", "Cold utility", "cold utility"]: # Append variables to cold utility stream arrays
                    self.T_cu_in = np.append(self.T_cu_in, float(row[4]))
                    self.T_cu_out = np.append(self.T_cu_out, float(row[5]))
                    self.htc_cu = np.append(self.htc_cu, float(row[7]))
                    self.cu_cost = np.append(self.cu_cost, float(row[8]))

                elif row[stream_designation] in ["Exchange", "exchange"]: # Append variables to process HX arrays
                    self.unit_cost = np.append(self.unit_cost, float(row[4]))
                    self.A_coeff = np.append(self.A_coeff, float(row[5]))
                    self.A_exp = np.append(self.A_exp, float(row[6]))

                elif row[stream_designation] in ["Heating", "heating"]: # Append variables to heating HX arrays
                    self.hu_unit_cost = np.append(self.hu_unit_cost, float(row[4]))
                    self.hu_coeff = np.append(self.hu_coeff, float(row[5]))
                    self.hu_exp = np.append(self.hu_exp, float(row[6]))

                elif row[stream_designation] in ["Cooling", "cooling"]: # Append variables to cooling HX arrays
                    self.cu_unit_cost = np.append(self.cu_unit_cost, float(row[4]))
                    self.cu_coeff = np.append(self.cu_coeff, float(row[5]))
                    self.cu_exp = np.append(self.cu_exp, float(row[6]))
                
                else:  # blank rows
                    pass
                
        except:
            logger.error("Case file not found in directory.")  # TODO: need to throw an error either here or before


    def set_match_restrictions(self, restrictions):
        # Unpack restrictions for recovery, hu and cu matches 
        z_restriction, zhu_restriction, zcu_restriction = restrictions[0], restrictions[1], restrictions[2]
        
        # Apply restrictions if provided otherwise set to feasible
        if z_restriction is not None: # remove matches based on init_solution  
            if isinstance(z_restriction[0][0][0], int): # # 3d matrix so don't need to index 4th pos 
                self.z_allowed = [[[1 if z_restriction[i][j][k] > self.tol else 0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
            elif isinstance(z_restriction[0][0][0], list): # need to reference 4th index since gekko puts a [] around each variable after being solved
                self.z_allowed = [[[1 if z_restriction[i][j][k][0] > self.tol else 0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] # remove matches from init_solution if Q<tol or z=0
            elif type(z_restriction[0][0][0]).__name__ in  ["GKVariable", "GKParameter"]: # need to reference 4th index since gekko puts a [] around each variable after being solved :  
                self.z_allowed = [[[1 if z_restriction[i][j][k][0] > self.tol else 0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            else:
                raise ValueError("Invalid restriction type")
                
        else: # set to feasible
            self.z_allowed = self.z_feasible

        if zhu_restriction is not None:
            if isinstance(zhu_restriction[0], int): 
                self.z_hu_allowed = [1 if zhu_restriction[j] > self.tol else 0 for j in range(self.J)]  
            else:
                self.z_hu_allowed = [1 if zhu_restriction[j][0] > self.tol else 0 for j in range(self.J)]  
        else:
            self.z_hu_allowed = self.z_hu_feasible 
        
        if zcu_restriction is not None:
            if isinstance(zcu_restriction[0], int):
                self.z_cu_allowed = [1 if zcu_restriction[i] > self.tol else 0 for i in range(self.I)]
            else:
                self.z_cu_allowed = [1 if zcu_restriction[i][0] > self.tol else 0 for i in range(self.I)]
        else: 
            self.z_cu_allowed = self.z_cu_feasible
    

    @abstractmethod
    def set_obj(self, obj) -> None:
        pass


    @abstractmethod
    def get_post_process(self) -> None:
        pass

    def optimise(self, print_output) -> None:
        """
        Solve the model
        """
        try:
            start = time.time()
            self.m.solve(disp=False, debug=0) #
            self.solve_time = time.time() - start
            
            if self.m.options.SOLVESTATUS == 1:  
                if self.m.options.objfcnval + self.tol < 0: # double check that we have a positive objective function value
                    self.mSuccess = 0
                    logger.error(f"[Failed] [model: {self.name}] [path: {self.m._path}]")
                else:
                    self.mSuccess = self.m.options.SOLVESTATUS
                    logger.info(f"[Success] [model: {self.name}] [path: {self.m._path}]")
            else:
                self.mSuccess = self.m.options.SOLVESTATUS
                logger.error(f"[Failed] [model: {self.name}] [path: {self.m._path}] [status: {self.m.options.SOLVESTATUS}]")
            
                    
        except Exception as e:
            self.mSuccess = 0
            logger.error(f"[Failed] [model: {self.name}] [path: {self.m._path}]")

        if self.mSuccess:
            self.get_post_process()
            if print_output: # logger.info output shows model solution e.g duties, temperatures 
                self.output_to_cmd_line()
    

    def get_alpha_values(self) -> list[float]:
        '''
        Calculate alpha values for each HX

        Solves optimised model as a simulation but with additional equations to calculate alpha as part of post processing
        ''' 
        if self.alpha != []:
            return self.alpha
        else:
            model = GEKKO(remote=False)
            model.options.IMODE = 1
            model.options.SOLVER = 1
            self.set_alpha_dqda_equations(m=model, postoptimisation=True) 
            try:
                model.solve(disp=False)
            except:
                pass
            
            return self.alpha
    

    def set_alpha_dqda_equations(self, m=None, postoptimisation=False):
        '''
        Calculate the flow on effect 'alpha' for isothermal mixing

        Adds aditional equations and variables to calculate alpha and applies the minmax objective approach to ensure that the ...?
        ''' 
        if postoptimisation:
            m = m
            #Temperature effectiveness of all heat exchangers from both hot and cold stream perspectives
            if self.non_isothermal_model: # outlet temps remain stage temps
                self.P_h = [[[(self.T_h[i][k][0] - self.T_h_out_x[i][j][k][0]  ) / (self.T_h[i][k][0] - self.T_c[j][k+1][0]) if self.T_h[i][k][0] > self.T_c[j][k+1][0] else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
                self.P_c = [[[(self.T_c_out_y[j][i][k][0] - self.T_c[j][k+1][0]) / (self.T_h[i][k][0] - self.T_c[j][k+1][0]) if self.T_h[i][k][0] > self.T_c[j][k+1][0] else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
            else:
                self.P_h = [[[(self.T_h[i][k][0] - self.T_h[i][k+1][0]) / (self.T_h[i][k][0] - self.T_c[j][k+1][0]) if self.T_h[i][k][0] > self.T_c[j][k+1][0] else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
                self.P_c = [[[(self.T_c[j][k][0] - self.T_c[j][k+1][0]) / (self.T_h[i][k][0] - self.T_c[j][k+1][0]) if self.T_h[i][k][0] > self.T_c[j][k+1][0] else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
            
            #Total recovery duty within a stage
            self.Sum_Qr_is  = [[[sum([self.Q_r[i][j][k][0] for j in range(self.J)])] for k in range(self.S)] for i in range(self.I)]
            self.Sum_Qr_js  = [[[sum([self.Q_r[i][j][k][0] for i in range(self.I)])] for k in range(self.S)] for j in range(self.J)]

            #Effective split ratios between each heat exchanger within the same stage
            self.beta_h = [[[self.Q_r[i][j][k][0] / self.Sum_Qr_is[i][k][0] if self.Sum_Qr_is[i][k][0] > 0.0 else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
            self.beta_c = [[[self.Q_r[i][j][k][0] / self.Sum_Qr_js[j][k][0] if self.Sum_Qr_js[j][k][0] > 0.0 else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 

            self.z_i = [[sum([self.z[i][j][k][0] for i in range(self.I)]) / (sum([self.z[i][j][k][0] for i in range(self.I)]) + 1e-9) for k in range(self.S)] for j in range(self.J)]
            self.z_j = [[sum([self.z[i][j][k][0] for j in range(self.J)]) / (sum([self.z[i][j][k][0] for j in range(self.J)]) + 1e-9) for k in range(self.S)] for i in range(self.I)]

        else:
            m = self.m
            #Temperature effectiveness of all heat exchangers from both hot and cold stream perspectives
            if self.non_isothermal_model: # outlet temps remain stage temps
                self.P_h = [[[m.Intermediate((self.T_h[i][k] - self.T_h_out_x[i][j][k]  ) * self.z[i][j][k] / ((self.T_h[i][k] - self.T_c[j][k+1] - 1) * self.z[i][j][k] + 1)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
                self.P_c = [[[m.Intermediate((self.T_c_out_y[j][i][k] - self.T_c[j][k+1]) * self.z[i][j][k] / ((self.T_h[i][k] - self.T_c[j][k+1] - 1) * self.z[i][j][k] + 1)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            else:
                self.P_h = [[[m.Intermediate((self.T_h[i][k] - self.T_h[i][k+1]) * self.z[i][j][k] / ((self.T_h[i][k] - self.T_c[j][k+1] - 1) * self.z[i][j][k] + 1)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
                self.P_c = [[[m.Intermediate((self.T_c[j][k] - self.T_c[j][k+1]) * self.z[i][j][k] / ((self.T_h[i][k] - self.T_c[j][k+1] - 1) * self.z[i][j][k] + 1)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            
            #Total recovery duty within a stage
            self.Sum_Qr_j  = [[m.Intermediate(sum([self.Q_r[i][j][k] for j in range(self.J)]) ) for k in range(self.S)] for i in range(self.I)]
            self.Sum_Qr_i  = [[m.Intermediate(sum([self.Q_r[i][j][k] for i in range(self.I)]) ) for k in range(self.S)] for j in range(self.J)]

            #Effective split ratios between each heat exchanger within the same stage
            self.beta_h = [[[m.Intermediate(self.Q_r[i][j][k] / (self.Sum_Qr_j[i][k] + 1 - self.z[i][j][k])) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            self.beta_c = [[[m.Intermediate(self.Q_r[i][j][k] / (self.Sum_Qr_i[j][k] + 1 - self.z[i][j][k])) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            
            self.z_i = [[m.Intermediate(sum([self.z[i][j][k] for i in range(self.I)]) / (sum([self.z[i][j][k] for i in range(self.I)]) + 1e-9)) for k in range(self.S)] for j in range(self.J)]
            self.z_j = [[m.Intermediate(sum([self.z[i][j][k] for j in range(self.J)]) / (sum([self.z[i][j][k] for j in range(self.J)]) + 1e-9)) for k in range(self.S)] for i in range(self.I)]
            
        #Estimate alpha and gamma
        self.alpha = [[[m.Var(value=0.0, ub=1.0, lb=-1.0, name='alpha_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
        self.alpha_eqn = []

        self.gamma_h = [[[m.Var(value=0.5, ub=1.0, lb=-1.0, name='gamma_h_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
        self.gamma_c = [[[m.Var(value=0.5, ub=1.0, lb=-1.0, name='gamma_c_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 

        self.gamma_h_eqn = []
        self.gamma_c_eqn = []
        for k in range(self.S): 
            for j in range(self.J): 
                for i in range(self.I):
                    if k + 1 >= self.S: # final stage so no hot utility flow-on
                        self.gamma_h_eqn.append([m.Equation(self.gamma_h[i][j][k] == 0.0)])
                        self.gamma_c_eqn.append([m.Equation(self.gamma_c[i][j][k] == sum([self.beta_c[i0][j][k-1] * self.P_c[i0][j][k-1] * self.alpha[i0][j][k-1] for i0 in range(self.I)]) + (1 - self.z_i[j][k-1]) *  self.gamma_c[i][j][k-1] )])
                    elif k - 1 < 0: # first stage so no cold utility flow-on
                        self.gamma_h_eqn.append([m.Equation(self.gamma_h[i][j][k] == sum([self.beta_h[i][j0][k+1] * self.P_h[i][j0][k+1] * self.alpha[i][j0][k+1] for j0 in range(self.J)]) + (1 - self.z_j[i][k+1]) *  self.gamma_h[i][j][k+1] )])
                        self.gamma_c_eqn.append([m.Equation(self.gamma_c[i][j][k] == 0.0)])
                    else:
                        self.gamma_h_eqn.append([m.Equation(self.gamma_h[i][j][k] == sum([self.beta_h[i][j0][k+1] * self.P_h[i][j0][k+1] * self.alpha[i][j0][k+1] for j0 in range(self.J)]) + (1 - self.z_j[i][k+1]) *  self.gamma_h[i][j][k+1] )])
                        self.gamma_c_eqn.append([m.Equation(self.gamma_c[i][j][k] == sum([self.beta_c[i0][j][k-1] * self.P_c[i0][j][k-1] * self.alpha[i0][j][k-1] for i0 in range(self.I)]) + (1 - self.z_i[j][k-1]) *  self.gamma_c[i][j][k-1] )])      
                        
        # Estimate alpha (the heat duty flow-on factor through the network) and apply the alpha dQ/dA constraint
        if postoptimisation:
            self.alpha_eqn =  [m.Equation(self.alpha[i][j][k] == (1 - 0.5 * (self.gamma_h[i][j][k] + self.gamma_c[i][j][k]))) for k in range(self.S) for j in range(self.J) for i in range(self.I)]
        else:
            self.alpha_eqn =  [m.Equation(self.alpha[i][j][k] == (1 - 0.5 * (self.gamma_h[i][j][k] + self.gamma_c[i][j][k]))) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
            self.alpha_dQ_dA_eqn =  [m.Equation((self.min_dqda * (self.T_h[i][k] - self.T_c[j][k + 1]) - self.alpha[i][j][k] * self.theta_1[i][j][k] * self.theta_2[i][j][k] * self.U_r[i][j] ) * self.z[i][j][k] <= 0.0) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
        
    def output_to_cmd_line(self) -> None:
        if not self.mSuccess == 1:
            return
        #Output optimised values to the cmd line
        logger.info(f'Successful Solve.Path {self.m._path} name {self.name}')
        logger.info(f'Objective 0: {self.m.options.objfcnval}')
        logger.info(f'Objective 1: {self.TAC}')
        logger.info(f'Total Units: {self.n_units}')
        logger.info(f'Total Recovery Units: {self.n_recovery_units}')
        logger.info(f'T hot: {self.T_h}')
        logger.info(f'T cold: {self.T_c}')
        logger.info(f'theta 1: {self.theta_1}')
        logger.info(f'theta 2: {self.theta_2}')
        logger.info('')  
        logger.info('Heat recovery')
        logger.info(f'Q: {self.Q_r}')
        logger.info(f'self.z: {self.z}')
        logger.info(f'LMTD: {self.LMTD_r}')
        logger.info(f'A: {self.area_r}')
        logger.info(f"Q_r total: {self.Q_r_total}")
        logger.info('')  
        logger.info('Cold utility')
        logger.info(f'Q: {self.Q_c}')
        logger.info(f'self.z: {self.z_cu}')
        logger.info(f'LMTD: {self.LMTD_cu}')
        logger.info(f'A: {self.area_cu}')
        logger.info(f"Q_cu total: {self.Q_cu_total}")
        logger.info('')  
        logger.info('Hot utility')
        logger.info(f'Q: {self.Q_h}')
        logger.info(f'self.z: {self.z_hu}')
        logger.info(f'LMTD: {self.LMTD_hu}')
        logger.info(f'A: {self.area_hu}')
        logger.info(f"Q_hu total: {self.Q_hu_total}")

        if self.non_isothermal_model: # show non-isothermal variables
            for i in range(self.I):
                for j in range(self.J):
                    for k in range(self.S):
                        if self.Q_r[i][j][k][0] > self.tol:
                            logger.info(f"name {self.Q_r[i][j][k].name} binary {self.z[i][j][k][0]} "
                            f"heat exchange {self.Q_r[i][j][k][0]:.3f} ub 1 {self.Q_r[i][j][k].UPPER:.3f} "
                            f"Th in {self.T_h[i][k][0] - 273.15:.3f} Th out {self.T_h_out_x[i][j][k][0] - 273.15:.3f} "
                            f"Tc in {self.T_c[j][k+1][0] - 273.15:.3f} Tc out {self.T_c_out_y[j][i][k][0] - 273.15:.3f} "
                            f"X {self.X[i][j][k][0]:.3f} Y {self.Y[j][i][k][0]:.3f} allowed {self.z_allowed[i][j][k]} "
                            f"theta 1 {self.theta_1[i][j][k][0]:.3f} theta 2 {self.theta_2[i][j][k][0]:.3f}")
                            
        else: # show isothermal variables
            for i in range(self.I):
                for j in range(self.J):
                    for k in range(self.S):
                        if self.Q_r[i][j][k][0] > self.tol:
                            logger.info(f"name {self.Q_r[i][j][k].name} binary {self.z[i][j][k][0]} allowed {self.z_allowed[i][j][k]} "
                            f"heat exchange {self.Q_r[i][j][k][0]:.3f} "
                            f"Th in {self.T_h[i][k][0] - 273.15:.3f} Th out {self.T_h[i][k+1][0] - 273.15:.3f} "
                            f"Tc in {self.T_c[j][k+1][0] - 273.15:.3f} Tc out {self.T_c[j][k][0] - 273.15:.3f} "
                            f"theta 1 {self.theta_1[i][j][k][0]:.3f} theta 2 {self.theta_2[i][j][k][0]:.3f} "
                            f"theta 1 calc {self.T_h[i][k][0] - self.T_c[j][k][0]:.3f} theta 2 calc {self.T_h[i][k+1][0] - self.T_c[j][k+1][0]:.3f}")

    
        
                