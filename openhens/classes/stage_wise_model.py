'''
__author__ = 'Keegan Hall & Tim Walmsley'
__credits__ = [Yee & Grossmann 1990]

Parent class for HEN synthesis that creates either an MINLP or NLP isothermal mixing superstructure
'''

import numpy as np
import math
import logging
import copy
from .generic_model import GenericHENModel
from ..analysis import solution_verification
import matplotlib.pyplot as plt
from .grid_diagram import Grid_Diagram
from ..logger import openhens_log as logger, logging


class StageWiseModel(GenericHENModel):
    def __init__(
            self,
            name,
            framework,
            solver,
            import_file,
            stages,
            dTmin,
            z_restriction,
            min_dqda,
            minimisation_goal,
            non_isothermal_model,
            integers,
            tol,
        ) -> None:
        self.stages = stages
        # ipopt solver options
        solver_options = [
            # "max_iter 10000",
            # "tol 1e-3",
            # "print_level 5",
        ]
        super().__init__(
            name,
            framework,
            solver,
            import_file,
            dTmin,
            z_restriction,
            min_dqda,
            minimisation_goal,
            non_isothermal_model,
            integers,
            tol,
            solver_options=solver_options,
        )
    
    def setup(self) -> None:
        self.set_blank_input_parameters()
        self.get_model_parameters_from_file()
        self.set_preprocessing()
        self.set_match_restrictions(self.z_restriction)
        self.set_stage_wise_superstructure()
        if self.framework == 'TDM':
            self.set_dqda_equations()
        self.set_obj()
    
    def set_preprocessing(self):
        '''
        Pre-process parameters for superstructure

        Calculates parameters for the synHEAT superstructure, applies constraints on the allowed HX matches 
        '''
        #CALCULATED PARAMETERS
        #    Superstructure parameters
        self.S = self.stages # number of stages is max of active hot or cold streams
        self.K = self.S + 1 
        self.I = len(self.f_h)  # number of hot streams
        self.J = len(self.f_c)  # number of cold streams 
        
        #    Hot stream parameters
        self.Qtot_sh = np.array([(self.T_h_in[i] - self.T_h_out[i]) * self.f_h[i] for i in range(self.I)]) # total heat content to be released from hot stream i 

        #    Cold stream parameters
        self.Qtot_sc = np.array([self.f_c[j] * (self.T_c_out[j] - self.T_c_in[j]) for j in range(self.J)]) # total heat content to be gained by cold stream j 

        #    Fixed parameters for heat exchanger matches
        self.U_r = np.array([[1 / ( 1 / self.htc_h[i]  + 1 / self.htc_c[j]) for j in range(self.J)] for i in range(self.I)]) #overall heat transfer coefficient between streams i, j
        self.U_hu = np.array([1 / ( 1 / self.htc_hu[0] + 1 / self.htc_c[j]) for j in range(self.J)]) #overall heat transfer coefficient for heaters to cold stream j
        self.U_cu = np.array([1 / ( 1 / self.htc_h[i] + 1 / self.htc_cu[0]) for i in range(self.I)]) #overall heat transfer coefficient for coolers to hot stream i
        self.Q_max = np.array([[max(self.T_h_in[i] - self.T_c_in[j] - self.dTmin, 0.0) * min(self.f_h[i], self.f_c[j]) for j in range(self.J)] for i in range(self.I)]) #maximum heat exchange between streams i, j
        
        # Big-M for approach temperatures
        self.M_ij = [[max(abs(self.T_h_in[i] - self.T_c_in[j]), 
                     abs(self.T_h_in[i] - self.T_c_out[j]), 
                     abs(self.T_h_out[i] - self.T_c_in[j]), 
                     abs(self.T_h_out[i] - self.T_c_out[j])
                     ) + self.dTmin
                for j in range(self.J)] for i in range(self.I)]
       
        #    Feasible matches    
        self.z_feasible =  [[[1 if self.Q_max[i][j] > self.tol else 0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]    
        self.z_hu_feasible = [1 for j in range(self.J)] 
        self.z_cu_feasible = [1 for i in range(self.I)] 
 
        
    def set_stage_wise_superstructure(self): 
        '''
        Creates common synHEAT model equations and variables

        Creates lists for variables and equations for the synHEAT model depending on whether there are integers, branch mixing type and evolution
        ''' 
        
        #   CONTINOUS VARIABLE DECLARATION 
        #       Heat recovery, cold utility and hot utility
        self.Q_r = [[[self.m.Var(value=self.Q_max[i][j]/3, ub=self.Q_max[i][j], lb=0.0, name='Q_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0.0, name='Q_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
        self.Q_c = [self.m.Var(value=0, ub=self.Qtot_sh[i], lb=0.0, name='Q_H{}_to_CU'.format(i)) if self.z_cu_allowed[i]> 0 else self.m.Param(value=0, name='Q_H{}_to_CU'.format(i)) for i in range(self.I)] 
        self.Q_h = [self.m.Var(value=0, ub=self.Qtot_sc[j], lb=0.0, name='Q_HU_to_C{}'.format(j)) if self.z_hu_allowed[j]> 0 else self.m.Param(value=0, name='Q_HU_to_C{}'.format(j)) for j in range(self.J)] 

        #       Stage-wise temperatures
        self.T_h = [[self.m.Var(value=self.T_h_in[i], ub=self.T_h_in[i],  lb=self.T_h_out[i], name='T_H{}_at_B{}'.format(i,k)) if k > 0 else self.m.Param(value=self.T_h_in[i], name='T_H{}_at_B{}'.format(i,k)) for k in range(self.K)] for i in range(self.I)] #Hot stream temperatures at the kth stageboundary            
        self.T_c = [[self.m.Var(value=self.T_c_in[j], ub=self.T_c_out[j], lb=self.T_c_in[j],  name='T_C{}_at_B{}'.format(j,k)) if k < self.S else self.m.Param(value=self.T_c_in[j], name='T_C{}_at_B{}'.format(j,k)) for k in range(self.K)] for j in range(self.J)] #Cold stream temperatures at the kth stage boundary
        
        #       Approach temperatures on the hot (1) and cold (2) sides of heat recovery exchangers
        self.theta_1 = [[[self.m.Var(value=self.dTmin, ub=abs(self.T_h_in[i] - self.T_c_in[j]), lb=self.dTmin, name='approach_T1_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=self.dTmin, name='approach_T1_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] #Approach temperature on the hot-side of each heat recovery exchanger
        self.theta_2 = [[[self.m.Var(value=self.dTmin, ub=abs(self.T_h_in[i] - self.T_c_in[j]), lb=self.dTmin, name='approach_T2_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=self.dTmin, name='approach_T2_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] #Approach temperature on the cold-side of each heat recovery exchanger    
        
        #   EQUATION DECLARATION 
        #       Energy balance for each stream
        _ = self.m.Equations([self.Qtot_sh[i] - self.m.sum([self.Q_r[i][j][k] for k in range(self.S) for j in range(self.J)]) - self.Q_c[i] == 0.0 for i in range(self.I)]) 
        _ = self.m.Equations([self.Qtot_sc[j] - self.m.sum([self.Q_r[i][j][k] for k in range(self.S) for i in range(self.I)]) - self.Q_h[j] == 0.0 for j in range(self.J)])
        
        #       Energy balance for each heat recovery stage
        _ = self.m.Equations([(self.T_h[i][k + 1] - self.T_h[i][k]) * self.f_h[i] + sum([self.Q_r[i][j][k] for j in range(self.J)]) == 0 for k in range(self.S) for i in range(self.I)]) 
        _ = self.m.Equations([(self.T_c[j][k + 1] - self.T_c[j][k]) * self.f_c[j] + sum([self.Q_r[i][j][k] for i in range(self.I)]) == 0 for k in range(self.S) for j in range(self.J)])

        #   INTEGER VARIABLE DECLARATION      
        if self.integers: # integers are variables    
            self.z =  [[[self.m.Var(value=1, ub=1, lb=0, integer=True, name='z_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0, name='z_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
            self.z_cu = [self.m.Var(value=1, ub=1, lb=0, integer=True, name='z_H{}_to_CU'.format(i)) if self.z_cu_allowed[i]> 0 else self.m.Param(value=0, name='z_H{}_to_CU'.format(i)) for i in range(self.I)]  
            self.z_hu = [self.m.Var(value=1, ub=1, lb=0, integer=True, name='z_HU_to_C{}'.format(j)) if self.z_hu_allowed[j]> 0 else self.m.Param(value=0, name='z_HU_to_C{}'.format(j)) for j in range(self.J)] 

            #       Logic equations
            _ = [self.m.Equation(self.Q_r[i][j][k] <= self.Q_max[i][j] * self.z[i][j][k]) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
            _ = [self.m.Equation(self.Q_c[i]       <= self.Qtot_sh[i]  * self.z_cu[i]) if self.z_cu_allowed[i]> 0     else None for i in range(self.I)]
            _ = [self.m.Equation(self.Q_h[j]       <= self.Qtot_sc[j]  * self.z_hu[j]) if self.z_hu_allowed[j]> 0     else None for j in range(self.J)]

        else: # integers are params hence network configuration is fixed and logic equations are not needed
            self.z =  [[[self.m.Param(value=1, name='z_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0, name='z_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
            self.z_hu = [self.m.Param(value=1, name='z_HU_to_C{}'.format(j)) if self.z_hu_allowed[j]> 0 else self.m.Param(value=0, name='z_HU_to_C{}'.format(j)) for j in range(self.J)] 
            self.z_cu = [self.m.Param(value=1, name='z_H{}_to_CU'.format(i)) if self.z_cu_allowed[i]> 0 else self.m.Param(value=0, name='z_H{}_to_CU'.format(i)) for i in range(self.I)]  

        # Different variables and equations for iso and non-iso     
        if self.non_isothermal_model:
            # Non-isothermal variables
            self.X =  [[[self.m.Var(value=0.5, ub=1.0, lb=0.0, name='X_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0.0, name='X_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] # stream split ratio for hot i with stream j in stage k
            self.Y =  [[[self.m.Var(value=0.5, ub=1.0, lb=0.0, name='Y_C{}_to_H{}_at_S{}'.format(j,i,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0.0, name='Y_C{}_to_H{}_at_S{}'.format(j,i,k)) for k in range(self.S)] for i in range(self.I)] for j in range(self.J)] # stream split ratio for cold j with stream i in stage k
            
            self.T_h_out_x = [[[self.m.Var(value=self.T_h_in[i], ub=self.T_h_in[i], lb=self.T_h_out[i], name='Thout_x_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0, name='Tx_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] # stream split oultet temperature for hot i with stream j in stage k    
            self.T_c_out_y = [[[self.m.Var(value=self.T_c_in[j], ub=self.T_c_out[j], lb=self.T_c_in[j], name='Tcout_y_C{}_to_H{}_at_S{}'.format(j,i,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0, name='Ty_C{}_to_H{}_at_S{}'.format(j,i,k)) for k in range(self.S)] for i in range(self.I)] for j in range(self.J)] # stream split oultet temperature for hot i with stream j in stage k          
            
            # Approach temperatures equations - can be inequality here since lower theta is penalised by higher area cost 
            _ = [self.m.Equation(self.theta_1[i][j][k] <= (self.T_h[i][k]     - self.T_c_out_y[j][i][k] ) + self.M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)] 
            _ = [self.m.Equation(self.theta_2[i][j][k] <= (self.T_h_out_x[i][j][k] - self.T_c[j][k + 1] ) + self.M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
            
            # Non-isothermal branch heat balance 
            _ = [self.m.Equation(self.Q_r[i][j][k] - self.X[i][j][k] * self.f_h[i] * (self.T_h[i][k]  -  self.T_h_out_x[i][j][k]) == 0.0) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
            _ = [self.m.Equation(self.Q_r[i][j][k] - self.Y[j][i][k] * self.f_c[j] * (self.T_c_out_y[j][i][k] - self.T_c[j][k+1]) == 0.0) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]

            # Non-isothermal split ratio logic 
            _ = [self.m.Equation(self.m.sum([self.X[i][j][k] for j in range(self.J)]) == 1.0 ) if sum([self.z_allowed[i][j][k] for j in range(self.J)]) > 0 else None for k in range(self.S) for i in range(self.I)]
            _ = [self.m.Equation(self.m.sum([self.Y[j][i][k] for i in range(self.I)]) == 1.0 ) if sum([self.z_allowed[i][j][k] for i in range(self.I)]) > 0 else None for k in range(self.S) for j in range(self.J)]

        else:
            # Approach temperatures equations - TDM needs equality since driving force is not enforced by area costs in the objectives
            _ = [self.m.Equation(self.theta_1[i][j][k] <= (self.T_h[i][k]     - self.T_c[j][k]    ) + self.M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
            _ = [self.m.Equation(self.theta_1[i][j][k] >= (self.T_h[i][k]     - self.T_c[j][k]    ) - self.M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
            
            _ = [self.m.Equation(self.theta_2[i][j][k] <= (self.T_h[i][k + 1] - self.T_c[j][k + 1]) + self.M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
            _ = [self.m.Equation(self.theta_2[i][j][k] >= (self.T_h[i][k + 1] - self.T_c[j][k + 1]) - self.M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
         
         
        self.dqda = []
        self.alpha = []
       

    def set_dqda_equations(self):
        '''
        Apply the min dQ/dA constraint 

        Adds a new equation that enforces the minimum efficiency of recovery area in reducing utility. Option to use a minmax objective ('maximum dQ/dA') approach to ...?
        ''' 
        #   dQ/dA minimum constraint
        self.min_dqda_int = [[[self.m.Intermediate(self.min_dqda * (self.T_h[i][k] - self.T_c[j][k + 1]) - self.theta_1[i][j][k] * self.theta_2[i][j][k] * self.U_r[i][j], name='dqda_calc_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
        self.min_dQ_dA_eqn = [self.m.Equation(self.min_dqda_int[i][j][k] <= self.min_dqda * self.M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
       
    
    def set_initial_values_for_variables(self, init_solution, brackets=False):
        def _initialise_value(var, val):
            if type(var).__name__ == "GKVariable": # ensure the initial value is within the bounds
                val = max(var.lower, min(var.upper, val))
                if brackets:
                    var.VALUE.value = [val]
                else:
                    var.VALUE.value = val
            elif type(var).__name__ == "GKParameter": # no bounds
                if brackets:
                    var.VALUE.value = [val]
                else:
                    var.VALUE.value = val
            else:
                if brackets:
                    var = [val]
                else:
                    var = val
                
            
        # Initialise recovery matches
        for k in range(self.S):
            for j in range(self.J):
                for i in range(self.I):
                    if self.z_allowed[i][j][k] > 0:
                        _initialise_value(self.Q_r[i][j][k], init_solution.Q_r[i][j][k].VALUE[0])
                        _initialise_value(self.z[i][j][k], init_solution.z[i][j][k][0])
                        _initialise_value(self.theta_1[i][j][k], init_solution.theta_1[i][j][k].VALUE[0])
                        _initialise_value(self.theta_2[i][j][k], init_solution.theta_2[i][j][k].VALUE[0])
                    else: # set to 0 if not allowed
                        _initialise_value(self.Q_r[i][j][k], 0.0) 
                        _initialise_value(self.z[i][j][k], 0)
                        _initialise_value(self.theta_1[i][j][k], self.dTmin) 
                        _initialise_value(self.theta_2[i][j][k], self.dTmin)

            
            
        # Initialise hot stream stage temperatures
        for i in range(self.I):
            for k in range(self.K):
                _initialise_value(self.T_h[i][k], init_solution.T_h[i][k].VALUE[0]) 
                    
    
        # Initialise cold stream stage temperatures
        for j in range(self.J):
            for k in range(self.K):
                _initialise_value(self.T_c[j][k], init_solution.T_c[j][k].VALUE[0])
      
        # Initialise utility variables
        for i in range(self.I):
            if self.z_cu_allowed[i] > 0:
                _initialise_value(self.Q_c[i], init_solution.Q_c[i].VALUE[0])
                _initialise_value(self.z_cu[i], init_solution.z_cu[i][0])
            else:
                _initialise_value(self.Q_c[i], 0.0)
                _initialise_value(self.z_cu[i], 0)  
        
        for j in range(self.J):
            if self.z_hu_allowed[j] > 0:
                _initialise_value(self.Q_h[j], init_solution.Q_h[j].VALUE[0])
                _initialise_value(self.z_hu[j], init_solution.z_hu[j][0])
            else:
                _initialise_value(self.Q_h[j], 0.0)   
                _initialise_value(self.z_hu[j], 0)
                
        # Initialise non-isothermal variables
        if self.non_isothermal_model:
            if init_solution.non_isothermal_model: # can initialise non-isothermal variables from non-isothermal init class
                for k in range(self.S):
                    for j in range(self.J):
                        for i in range(self.I):
                            if self.z_allowed[i][j][k] > 0:
                                _initialise_value(self.X[i][j][k], init_solution.X[i][j][k].VALUE[0])
                                _initialise_value(self.Y[j][i][k], init_solution.Y[j][i][k].VALUE[0])
                                _initialise_value(self.T_h_out_x[i][j][k], init_solution.T_h_out_x[i][j][k].VALUE[0])
                                _initialise_value(self.T_c_out_y[j][i][k], init_solution.T_c_out_y[j][i][k].VALUE[0])
                            else:
                                _initialise_value(self.X[i][j][k], 0.0)
                                _initialise_value(self.Y[j][i][k], 0.0)
                                _initialise_value(self.T_h_out_x[i][j][k], init_solution.T_h[i][k+1].VALUE[0])
                                _initialise_value(self.T_c_out_y[j][i][k], init_solution.T_c[j][k].VALUE[0])

            else:
                for k in range(self.S):
                    for j in range(self.J):
                        # Precompute sums for denominator reuse
                        sum_Q_r_j = sum(init_solution.Q_r[i][j][k].VALUE[0] for i in range(self.I))
                    for i in range(self.I):
                        sum_Q_r_i = sum(init_solution.Q_r[i][j][k].VALUE[0] for j in range(self.J))
                        
                        if self.z_allowed[i][j][k] > 0:
                            q_val = init_solution.Q_r[i][j][k].VALUE[0]
                            if q_val > 0.0:
                                _initialise_value(self.X[i][j][k], q_val / sum_Q_r_j if sum_Q_r_j else 0.0)
                                _initialise_value(self.Y[j][i][k], q_val / sum_Q_r_i if sum_Q_r_i else 0.0)
                            else:
                                _initialise_value(self.X[i][j][k], 0.0)
                                _initialise_value(self.Y[j][i][k], 0.0)

                            _initialise_value(self.T_h_out_x[i][j][k], init_solution.T_h[i][k+1].VALUE[0])
                            _initialise_value(self.T_c_out_y[j][i][k], init_solution.T_c[j][k].VALUE[0])
                        else:
                            # Inactive: zero init with consistent temperature defaulting
                            _initialise_value(self.X[i][j][k], 0.0)
                            _initialise_value(self.Y[j][i][k], 0.0)
                            _initialise_value(self.T_h_out_x[i][j][k], init_solution.T_h[i][k+1].VALUE[0])
                            _initialise_value(self.T_c_out_y[j][i][k], init_solution.T_c[j][k].VALUE[0])
                           

    def get_net_benefit_evolution(self, print_output, max_depth=5):
        """
        Evolves the current heat exchanger network by systematically adding and removing units.
        
        Constructs a decision tree by applying +/- HX modifications and selecting configurations 
        that reduce the Total Annual Cost (TAC). The process stops at the specified tree depth or 
        when no improvement is found.

        Args:
            print_output (bool): Whether to print solver output.
            max_depth (int): Maximum number of add/remove steps to attempt.

        Returns:
            best_model (object): The evolved model with lowest TAC found.
        """
        if self.mSuccess != 1:
            logger.warning("Initial model was not successful; skipping evolution.")
            return self

        model = self
        best_model = self

        for unit in range(max_depth):
            logger.debug(f"Evolution step {unit + 1}/{max_depth} — Current TAC: {model.TAC}")

            # Attempt evolution by removing or adding an HX
            model_minus_one = self.get_n_minus_one_evolution(print_output=print_output, unit=unit, prev_case=model)
            model_plus_one = self.get_n_plus_one_evolution(print_output=print_output, unit=unit, prev_case=model)

            # Prune: Select better model based on success and TAC
            model = self._select_best_candidate(model, model_minus_one, model_plus_one)
            if model is None:
                logger.debug("No viable model found; ending evolution.")
                break

            if model.TAC < best_model.TAC:
                best_model = model
                logger.debug(f"New best model: {model.name} found with TAC: {best_model.TAC:.2f}")

        # Final comparison: Is the best model actually better than the starting point?
        if best_model.mSuccess and best_model.TAC < self.TAC:
            logger.debug("Evolved model is better than initial. Updating state...")

            self._update_with_best_model(best_model)
            
        else:
            logger.debug("No improvement found over original model.")
        self.m.cleanup()

        

    def _select_best_candidate(self, current_model, model_minus_one, model_plus_one):
        """
        Selects the best candidate from plus/minus evolutions.

        Returns:
            model (object or None): Selected model or None if no improvement.
        """
        if not model_minus_one.mSuccess and not model_plus_one.mSuccess:
            return None
        elif model_minus_one.mSuccess and not model_plus_one.mSuccess:
            return model_minus_one
        elif not model_minus_one.mSuccess and model_plus_one.mSuccess:
            return model_plus_one
        else:
            logger.debug(f"TAC comparison -1: {model_minus_one.TAC:.2f}, +1: {model_plus_one.TAC:.2f}")
            return min([model_minus_one, model_plus_one], key=lambda m: m.TAC)

    def _update_with_best_model(self, best_model):
        """
        Update the current model (`self`) to adopt the configuration of the `best_model`.
        This avoids re-calling __init__, and manually transfers key solution attributes.
        """
        best_model.verify()
        # Deep copy alpha values (triple-nested list)
        self.alpha = [[[best_model.alpha[i][j][k] for k in range(self.S)] 
                    for j in range(self.J)] 
                    for i in range(self.I)]
        
        self.z_allowed = [[[best_model.z_allowed[i][j][k] for k in range(self.S)] 
                    for j in range(self.J)] 
                    for i in range(self.I)]
        # Set all continuous and discrete decision variables
        self.set_initial_values_for_variables(best_model, brackets=True)
        
        # Set solve obj intermediates
        self.hu_cost_total = copy.deepcopy(best_model.hu_cost_total)            
        self.cu_cost_total = copy.deepcopy(best_model.cu_cost_total)             
        self.recovery_area_cost_filtered = copy.deepcopy(best_model.recovery_area_cost_filtered)  
        self.hu_area_cost_total = copy.deepcopy(best_model.hu_area_cost_total)       
        self.cu_area_cost_total = copy.deepcopy(best_model.cu_area_cost_total)       
        
        # Post Process
        self.get_post_process()
               
    def get_n_minus_one_evolution(self, print_output, unit, prev_case):
        '''
        Evolve solution by removing lowest benefit HX

        Continue to evolve solution only if the next evolved solution is better than the last (or initial soln)
        '''  
       
       # Setup evolution model minus one by copying intial soln and emoving lowest benefit HX 
                
        # Remove low efficiency HX's matches from allowed z matrix
        low_pos = prev_case.get_lowest_benefit_HX() 
        z_allowed_removed = copy.deepcopy(prev_case.z) # need deep copy as self.z contains sublists
        for lp in low_pos:
            logger.debug(f'worst selected position i,j,k {lp}')
            i, j, k = lp
            if isinstance(z_allowed_removed[0][0][0], int): # 3d matrix so don't need to index 4th pos 
                z_allowed_removed[i][j][k] = 0 
            else:
                 z_allowed_removed[i][j][k][0] = 0 

        count_ones = 0
        for layer in z_allowed_removed:
            for row in layer:
                for element in row:
                    if isinstance(element, int): # 3d matrix so don't need to index 4th pos 
                        if element == 1:
                            count_ones += 1
                    else:                  
                        if element[0] == 1:
                            count_ones += 1
        logger.debug(f'number in z_allowed_removed {count_ones}')
        
        # Define model 
        model_minus_one = StageWiseModel(name=self.name+'-n_minus 1 evolution model {}'.format(unit), #!! add initial soln name here
                                framework=prev_case.framework,
                                solver='ipopt-pyomo',
                                import_file=prev_case.import_file,
                                stages=prev_case.stages,
                                dTmin=prev_case.dTmin,
                                z_restriction=[z_allowed_removed, None, None],
                                min_dqda=prev_case.min_dqda,
                                minimisation_goal=prev_case.minimisation_goal,
                                non_isothermal_model=prev_case.non_isothermal_model,
                                integers=False,
                                tol=1e-3) # integers should be false since anyway since initial soln is NLP 
        
      
        for lp in low_pos: # set continous variables from removed HX match to inactive i.e lower bound   
            i, j, k = lp         
            model_minus_one.Q_r[i][j][k].VALUE.value = 0.0
            model_minus_one.z[i][j][k].VALUE.value = 0    
            model_minus_one.theta_1[i][j][k].VALUE.value = self.dTmin
            model_minus_one.theta_2[i][j][k].VALUE.value = self.dTmin

        model_minus_one.optimise(print_output=print_output)

        return model_minus_one
                
    def get_n_plus_one_evolution(self, print_output, unit, prev_case):
        '''
        Evolve solution by allowing solver to add one more

        Continue to evolve solution only if the next evolved solution is better than the last (or initial soln)
        '''  
        # Setup evolution model minus +1 by copying evolved soln and adding back in HX with highest a-dQ/dA lowest benefit HX 
        
        # Add back highest a-dQ/dA HX's matches to allowed z matrix
        high_pos = prev_case.get_max_benefit_HX()
        z_allowed_added = copy.deepcopy(prev_case.z)   #copy.deepcopy(self.z) # need deep copy as self.z contains sublists
        
        for hp in high_pos:
            logger.debug(f'best non-selected position i,j,k {hp}')
            i, j, k = hp
            if isinstance(z_allowed_added[0][0][0], int): # 3d matrix so don't need to index 4th pos 
                z_allowed_added[i][j][k] = 1 
            else:
                z_allowed_added[i][j][k][0] = 1 
        
        count_ones = 0
        for layer in z_allowed_added:
            for row in layer:
                for element in row:
                    if isinstance(element, int): # 3d matrix so don't need to index 4th pos 
                        if element == 1:
                            count_ones += 1
                    else:                  
                        if element[0] == 1:
                            count_ones += 1
        logger.debug(f'number in z_allowed_removed {count_ones}')
        
        # Define model 
        model_plus_one = StageWiseModel(name=self.name+'-n_plus 1 evolution model {}'.format(unit), #!! add initial soln name here
                                framework=prev_case.framework,
                                solver='ipopt-pyomo',
                                import_file=prev_case.import_file,
                                stages=prev_case.stages,
                                dTmin=prev_case.dTmin,
                                z_restriction=[z_allowed_added, None, None],
                                min_dqda=prev_case.min_dqda,
                                minimisation_goal=prev_case.minimisation_goal,
                                non_isothermal_model=prev_case.non_isothermal_model,
                                integers=False,
                                tol=1e-3) # integers should be false since anyway since initial soln is NLP 
        
        for hp in high_pos: # set continous variables from removed HX match to inactive i.e lower bound   
            i, j, k = hp         
            model_plus_one.z[i][j][k].VALUE.value = 1    
            
        model_plus_one.optimise(print_output=print_output)
    
        return model_plus_one

    
    def set_obj(self):
        # logger.info('Minimise: ' + self.minimisation_goal)
        if self.minimisation_goal == 'hot utility':
            self.m.Minimize(self.m.sum([self.Q_h[j] for j in range(self.J)]))
        
        if self.minimisation_goal == 'cold utility':
            self.m.Minimize(self.m.sum([self.Q_c[i] for i in range(self.I)]))

        elif self.minimisation_goal == 'total utility':
            self.m.Minimize(self.m.sum([self.Q_h[j] for j in range(self.J)]) + self.m.sum([self.Q_c[i] for i in range(self.I)]))

        elif self.minimisation_goal ==  'utility costs':
            self.m.Minimize(self.hu_cost[0] * self.m.sum([self.Q_h[j] for j in range(self.J)]) + self.cu_cost[0] * self.m.sum([self.Q_c[i] for i in range(self.I)]))

        elif self.minimisation_goal == 'heat recovery':
            self.m.Maximize(self.m.sum([self.Q_r[i][j][k] for i in range(self.I) for j in range(self.J) for k in range(self.S)]))

        elif self.minimisation_goal == 'dQ/dA obj':
            self.m.Minimize(sum(self.Q_h) - self.HU_target)  
            #self.m.Equation(sum(self.Q_c) - self.CU_target == 0.0)  

        elif self.minimisation_goal == 'total cost' or self.minimisation_goal == 'variable total cost':
            #    NETWORK COST INTERMEDIATES
            self.hu_cost_total = self.m.Intermediate(self.hu_cost[0] * self.m.sum([self.Q_h[j] for j in range(self.J)]), name="Hot utility cost")
            self.cu_cost_total = self.m.Intermediate(self.cu_cost[0] * self.m.sum([self.Q_c[i] for i in range(self.I)]), name="Cold utility cost")
           
            self.recovery_area_cost_filtered  = [[0 for j in range(self.J)] for k in range(self.S)]                               
            for k in range(self.S): # sum area cost for each cold stream match in each stage with all hot streams then sum in obj function
                    for j in range(self.J):
                        allowed_hots = [] # empty list for saving allowed hot matches for stream j in stage
                        for i in range(self.I):
                            if self.z_allowed[i][j][k] > 0:
                                allowed_hots.append(i) # add the hot index to the list if its allowed
                        if sum([self.z_allowed[z][j][k] for z in range(self.I)]) > 0: # only add area cost to obj if a cold stream has a match with any i in that stage
                            self.recovery_area_cost_filtered[k][j] = self.m.Intermediate(self.A_coeff[0] * sum([(self.Q_r[n][j][k]/(self.U_r[n][j] * (self.theta_1[n][j][k] * self.theta_2[n][j][k] * (self.theta_1[n][j][k] + self.theta_2[n][j][k])/2 + 1e-3)**(1/3)) + 1e-3) ** self.A_exp[0] for n in allowed_hots]), name="Recovery HX area cost in stage {} cold {}".format(k,j)) # sum the area costs of all allowed i matches for j in stage k
                                
            self.hu_area_cost_total         = self.m.Intermediate(self.hu_coeff[0] * sum([(self.Q_h[j]/(self.U_hu[j] * ((self.T_hu_in[0] - self.T_c_out[j]) * (self.T_hu_out[0] - self.T_c[j][0])*((self.T_hu_in[0] - self.T_c_out[j]) + (self.T_hu_out[0] - self.T_c[j][0]))/2 + 1e-3)**(1/3)) + 1e-3) ** self.hu_exp[0] for j in range(self.J)]), name="Total hot utility HX area cost")
            self.cu_area_cost_total         = self.m.Intermediate(self.cu_coeff[0] * sum([(self.Q_c[i]/(self.U_cu[i] * ((self.T_h[i][self.S] - self.T_cu_out[0]) * (self.T_h_out[i] - self.T_cu_in[0])*((self.T_h[i][self.S] - self.T_cu_out[0]) + (self.T_h_out[i] - self.T_cu_in[0]))/2+ 1e-3)**(1/3))+ 1e-3) ** self.cu_exp[0] for i in range(self.I)]), name="Total cold utility HX area cost")
            
            #    OBJECTIVE FUNCTION DECLARATION
            if self.minimisation_goal == 'total cost':
                # Fixed costs
                self.utility_unit_cost_total = self.m.Intermediate(self.hu_unit_cost[0] * sum([self.z_hu[j] for j in range(self.J)]) + self.cu_unit_cost[0] * sum([self.z_cu[i] for i in range(self.I)]), name="Total utility base cost") 
                self.recovery_unit_cost      = [[0 for j in range(self.J)] for k in range(self.S)]
                for k in range(self.S): # sum  unit cost for each cold stream match in each stage with all hot streams then sum in obj function
                    for j in range(self.J):
                        self.recovery_unit_cost[k][j] = self.m.Intermediate(self.unit_cost[0] * sum([self.z[i][j][k] for i in range(self.I)]), name='Total recovery base cost in stage {} cold {}'.format(k,j))

                self.m.Minimize( #Total annual cost = utility energy costs + heat recovery exchanger capital costs + utility exchanger capital costs
                                self.hu_cost_total              # hot utility energy cost
                                + self.cu_cost_total            # cold utility energy cost
                                + self.utility_unit_cost_total  # fixed component of utility heat exchanger capital cost
                                + sum([self.recovery_unit_cost[k][j] for k in range(self.S) for j in range(self.J)])           # fixed component of recovery heat exchanger capital cost
                                + sum([self.recovery_area_cost_filtered[k][j] for k in range(self.S) for j in range(self.J)])  # heat recovery exchanger area cost
                                + self.hu_area_cost_total       # hot utility area cost
                                + self.cu_area_cost_total       # cold utility area cost
                                )

            elif self.minimisation_goal == 'variable total cost':
                self.m.Minimize( #Total annual cost = utility energy costs + heat recovery exchanger capital costs + utility exchanger capital costs
                                self.hu_cost_total              # hot utility energy cost
                                + self.cu_cost_total            # cold utility energy cost
                                #+ self.m.sum([self.recovery_area_cost[i][j][k] for k in range(self.S) for j in range(self.J) for i in range(self.I)])
                                + sum([self.recovery_area_cost_filtered[k][j] for k in range(self.S) for j in range(self.J)])  # heat recovery exchanger area cost
                                + self.hu_area_cost_total       # hot utility area cost
                                + self.cu_area_cost_total       # cold utility area cost
                                ) 


    def get_lowest_benefit_HX(self):
        '''
        Determine the lowest benefit/least efficient HX match

        Uses alpha to find the HX of a previous soln that has the least efficient reduction in utility for its area and returns the position in the z matrix
        ''' 
        #    Calculate duty and cost benefit of each HX (z>0) from previous network. (If set to non-active HX (Q<tol) then we could remove more than 1 HX per evolution so just remove matches that the NLP self.solver didn't 'select')
        self.net_benefit = np.array([[[0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)])
        smallest_net_benefit = float('inf') # lowest HX net cost
        low_pos = []
        for k in range(self.S):
            for j in range(self.J):
                for i in range(self.I):
                    if self.z[i][j][k][0] == 1:
                        self.net_benefit[i][j][k] = self.Q_r[i][j][k][0] * self.alpha[i][j][k][0] * (self.hu_cost[0] + self.cu_cost[0]) - (self.unit_cost[0] + self.A_coeff[0] * (self.area_r[i][j][k] ** self.A_exp[0]))
                        if self.net_benefit[i][j][k] < smallest_net_benefit: # only save the lowest net benefit 
                            smallest_net_benefit = self.net_benefit[i][j][k]
                            low_pos = [[i, j, k]]

        return low_pos

    def get_max_benefit_HX(self):
        '''
        Determine the best non-existing HX

        Uses alpha to find the HX of a previous soln that was not selected but has the highest alpha-dQ/dA and returns the position in the z matrix
        '''  
        self.net_benefit = np.array([[[0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)])
        highest_net_benefit = 0.0 #float('inf') # lowest HX net cost
        high_pos = []
        for k in range(self.S):
            for j in range(self.J):
                for i in range(self.I):
                        if self.alpha_dqda[i][j][k] > highest_net_benefit and self.z_feasible[i][j][k]: # only save the highest net benefit !!check if any non-feasible matches have positive alpha_dQ/dA
                            highest_net_benefit = self.alpha_dqda[i][j][k]
                            high_pos = [[i, j, k]]

        return high_pos

    def get_post_process(self):
        if self.mSuccess == 1:                
            #Post-processing analysis using more exact analysis, excludes costs for HX when z=1 but q=0

            # Calculate z matrix but as a parameter so that rest of code can function as it did with z as a solver variable. 
            self.z = [[[ [1] if self.Q_r[i][j][k][0] > self.tol else [0] for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            self.n_recovery_units = sum([self.z[i][j][k][0] if self.Q_r[i][j][k][0] > self.tol else 0 for k in range(self.S) for j in range(self.J) for i in range(self.I)])
            
            self.z_hu = [ [1] if self.Q_h[j][0] > self.tol else [0] for j in range(self.J)]
            self.n_hu_units = sum([self.z_hu[j][0] if self.Q_h[j][0] > self.tol else 0 for j in range(self.J)])
    
            self.z_cu = [ [1] if self.Q_c[i][0] > self.tol else [0] for i in range(self.I)]
            self.n_cu_units = sum([self.z_cu[i][0] if self.Q_c[i][0] > self.tol else 0 for i in range(self.I)])
                
            self.n_units = self.n_recovery_units + self.n_hu_units + self.n_cu_units
            
            # Calculate area cost metrics
            for k in range(self.S): 
                for j in range(self.J):
                    for i in range(self.I):
                        if self.Q_r[i][j][k][0] > 0:
                            try:
                                LMTD = self.z[i][j][k][0] * (self.theta_1[i][j][k][0] - self.theta_2[i][j][k][0]) / math.log(self.theta_1[i][j][k][0] / self.theta_2[i][j][k][0]) if (abs(self.theta_1[i][j][k][0] - self.theta_2[i][j][k][0]) > self.tol and  abs(self.theta_1[i][j][k][0] - self.dTmin) >= self.tol and abs(self.theta_2[i][j][k][0] - self.dTmin) >= self.tol) else self.theta_1[i][j][k][0] * self.z[i][j][k][0]
                            except:
                                print(f'Error calculating LMTD for i={i}, j={j}, k={k}. Qr: {self.Q_r[i][j][k][0]} Theta1: {self.theta_1[i][j][k][0]}, Theta2: {self.theta_2[i][j][k][0]}')
            
            self.LMTD_r = [[[self.z[i][j][k][0] * (self.theta_1[i][j][k][0] - self.theta_2[i][j][k][0]) / math.log(self.theta_1[i][j][k][0] / self.theta_2[i][j][k][0]) if (abs(self.theta_1[i][j][k][0] - self.theta_2[i][j][k][0]) > self.tol and  abs(self.theta_1[i][j][k][0] - self.dTmin) >= self.tol and abs(self.theta_2[i][j][k][0] - self.dTmin) >= self.tol) else self.theta_1[i][j][k][0] * self.z[i][j][k][0] for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            self.area_r = [[[self.Q_r[i][j][k][0] / self.U_r[i][j] / self.LMTD_r[i][j][k] if (self.LMTD_r[i][j][k] > self.tol and self.Q_r[i][j][k][0] > self.tol) else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            self.LMTD_hu = [self.z_hu[j][0] * ((self.T_hu_in[0] - self.T_c_out[j]) - (self.T_hu_out[0] - self.T_c[j][0][0])) / math.log((self.T_hu_in[0] - self.T_c_out[j]) / (self.T_hu_out[0] - self.T_c[j][0][0])) if (abs((self.T_hu_in[0] - self.T_c_out[j]) - (self.T_hu_out[0] - self.T_c[j][0][0])) > self.tol and (self.T_hu_in[0] - self.T_c_out[j] - self.dTmin) >= self.tol and (self.T_hu_out[0] - self.T_c[j][0][0] - self.dTmin) >= self.tol ) else (self.T_hu_in[0] - self.T_c_out[j]) * self.z_hu[j][0] for j in range(self.J)]
            self.area_hu = [self.Q_h[j][0] / self.U_hu[j] / self.LMTD_hu[j] if (self.LMTD_hu[j] > self.tol and self.Q_h[j][0] > self.tol) else 0.0 for j in range(self.J)]
            self.LMTD_cu = [self.z_cu[i][0] * ((self.T_h[i][self.S][0] - self.T_cu_out[0]) - (self.T_h_out[i] - self.T_cu_in[0])) / math.log((self.T_h[i][self.S][0] - self.T_cu_out[0]) / (self.T_h_out[i] - self.T_cu_in[0])) if (abs((self.T_h[i][self.S][0] - self.T_cu_out[0]) - (self.T_h_out[i] - self.T_cu_in[0])) > self.tol and (self.T_h[i][self.S][0] - self.T_cu_out[0] - self.dTmin) >= self.tol and (self.T_h_out[i] - self.T_cu_in[0] - self.dTmin) >= self.tol) else (self.T_h_out[i] - self.T_cu_in[0]) * self.z_cu[i][0] for i in range(self.I)]
            self.area_cu = [self.Q_c[i][0] / self.U_cu[i] / self.LMTD_cu[i] if (self.LMTD_cu[i] > self.tol and self.Q_c[i][0] > self.tol) else 0.0 for i in range(self.I)]
            self.Q_cu_total = sum(self.Q_c[i][0] for i in range(self.I))
            self.Q_hu_total =  sum(self.Q_h[j][0] for j in range(self.J)) 
            self.Q_r_total = sum([self.Q_r[i][j][k][0] for k in range(self.S) for j in range(self.J) for i in range(self.I)])
            self.alpha = self.get_alpha_values()
            self.dqda = [[[None for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            self.dtacda = [[[None for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            for k in range(self.S): 
                for j in range(self.J):
                    for i in range(self.I):
                        if self.Q_r[i][j][k][0] > 0 and (self.T_h[i][k][0] - self.T_c[j][k + 1][0]) > 0.0:
                            self.dqda[i][j][k] = (self.theta_1[i][j][k][0] * self.theta_2[i][j][k][0] * self.U_r[i][j]) / (self.T_h[i][k][0] - self.T_c[j][k + 1][0])
                        elif (self.T_h[i][k][0] - self.T_c[j][k + 1][0]) > 0.0: # feasible match but not currently selected
                            self.dqda[i][j][k] = self.U_r[i][j] * (self.T_h[i][k][0] - self.T_c[j][k + 1][0])
                        else: # infeasible match
                            self.dqda[i][j][k] = 0

                        if self.area_r[i][j][k] > 0.0:
                            self.dtacda[i][j][k] = self.dqda[i][j][k] * (self.hu_cost[0] + self.cu_cost[0]) - (self.A_coeff[0] * self.A_exp[0] * self.area_r[i][j][k] ** (self.A_exp[0] - 1)) 
                        else:
                            self.dtacda[i][j][k] = self.dqda[i][j][k] * (self.hu_cost[0] + self.cu_cost[0]) - (self.A_coeff[0] * self.A_exp[0]) 
            self.alpha_dqda = [[[self.alpha[i][j][k][0] * self.dqda[i][j][k] for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            
            #Recalculation of objective function
            self.TAC_model = self.m.options.objfcnval
            self.TAC =   (self.hu_cost[0]   * sum([self.Q_h[j][0] for j in range(self.J)]) # hot utility energy cost
                        + self.cu_cost[0]   * sum([self.Q_c[i][0] for i in range(self.I)]) # cold utility energy cost
                        + self.unit_cost[0] * self.n_units # fixed component of heat exchanger capital costs
                        + self.A_coeff[0]   * sum([self.area_r[i][j][k] ** self.A_exp[0] for k in range(self.S) for j in range(self.J) for i in range(self.I)]) # heat recovery exchanger area cost
                        + self.hu_coeff[0]  * sum([self.area_hu[j] ** self.A_exp[0] for j in range(self.J)]) # hot utility area cost
                        + self.cu_coeff[0]  * sum([self.area_cu[i] ** self.A_exp[0] for i in range(self.I)])) # cold utility area cost
            #print(self.name, self.TAC, self.TAC_model, self.mSuccess)
            
    def verify(self) -> tuple[bool, list[str]]:
        return solution_verification.verify_solution(self)
