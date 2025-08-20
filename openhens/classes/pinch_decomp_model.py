'''
__author__ = 'Keegan Hall & Tim Walmsley'
__credits__ = [Yee & Grossmann 1990]

Parent class for HEN synthesis that decomposes the SynHEAT model into above and below the pinch to synthesis a minimum utility use HEN
'''

import numpy as np
import math
from .stage_wise_model import StageWiseModel
from .pinch_classes.stream import Stream
from .pinch_classes.process import Process
from ..analysis import solution_verification
from .generic_model import GenericHENModel
import logging
from ..logger import openhens_log as logger


class PinchDecompModel(GenericHENModel):
    def __init__(self,
            *args, 
            pinch_loc=None, 
            stage_selection=None, 
            **kwargs
        ) -> None:
        self.pinch_loc = pinch_loc
        self.stage_selection = stage_selection
        solver_options = [
            # "max_iter 10000",
            # "tol 1e-1"
        ]

        super().__init__(*args, **kwargs)

    
    def setup(self) -> None:
        self.set_blank_input_parameters()
        self.get_model_parameters_from_file()
        self.calculate_pinch()
        self.set_preprocessing()
        self.set_match_restrictions(self.z_restriction)
        self.set_stage_wise_superstructure()
        self.set_obj()
    

    def get_model_parameters_from_file(self):
        super().get_model_parameters_from_file()
        self.T_h_in_OG, self.T_h_out_OG = self.T_h_in.copy(), self.T_h_out.copy()
        self.T_c_in_OG, self.T_c_out_OG = self.T_c_in.copy(), self.T_c_out.copy()
    
    def set_preprocessing(self):
        '''
        Pre-process parameters for superstructure

        Calculates parameters for the synHEAT superstructure, applies constraints on the allowed HX matches 
        '''
        #CALCULATED PARAMETERS
        #   Number of hot and cold streams
        self.I = len(self.f_h)  # number of hot streams
        self.J = len(self.f_c)  # number of cold streams 
        
        #   Change temps depending on pinch location
        if self.pinch_loc == 'above': # hot target is Tpinch if Ttarget < Tpinch, cold supply is Tpinch if Ttarget > Tpinch
            self.z_i_active = [1 if i > self.T_pinch + self.dTmin/2 else 0 for i in self.T_h_in] # hot stream exists above pinch if supply is higher than Tpinch
            self.z_j_active = [1 if j > self.T_pinch - self.dTmin/2 else 0 for j in self.T_c_out] # cold stream exists above pinch if target is higher than Tpinch
            for i in range(self.I):
                if self.z_i_active[i] > 0: # active
                    if self.T_h_out[i] < self.T_pinch + self.dTmin/2: # crosses pinch
                        self.T_h_out[i] = self.T_pinch + self.dTmin/2 # change to Tpinch 
                else: # not active
                    self.T_h_in[i] = 0
                    self.T_h_out[i] = 0

            for j in range(self.J):
                if self.z_j_active[j] > 0: # active
                    if self.T_c_in[j] < self.T_pinch - self.dTmin/2: # crosses pinch
                        self.T_c_in[j] = self.T_pinch - self.dTmin/2 # change to Tpinch 
                else: # not active
                    self.T_c_in[j] = 0
                    self.T_c_out[j] = 0
            
         
            
        elif self.pinch_loc == 'below': # hot supply is Tpinch if Ttarget < Tpinch, cold target is Tpinch if Ttarget > Tpinch
            self.z_i_active = [1 if i < self.T_pinch + self.dTmin/2 else 0 for i in self.T_h_out] # hot stream exists below pinch if target is lower than Tpinch
            self.z_j_active = [1 if j < self.T_pinch - self.dTmin/2 else 0 for j in self.T_c_in] # cold stream exists below pinch if supply is lower than Tpinch
            for i in range(self.I):
                if self.z_i_active[i] > 0: # active
                    if self.T_h_in[i] > self.T_pinch + self.dTmin/2: # crosses pinch
                        self.T_h_in[i] = self.T_pinch + self.dTmin/2 # change to Tpinch 
                else: # not active
                    self.T_h_in[i] = 0
                    self.T_h_out[i] = 0

            for j in range(self.J):
                if self.z_j_active[j] > 0: # active
                    if self.T_c_out[j] > self.T_pinch - self.dTmin/2: # crosses pinch
                        self.T_c_out[j] = self.T_pinch - self.dTmin/2 # change to Tpinch 
                else: # not active
                    self.T_c_in[j] = 0
                    self.T_c_out[j] = 0
        
        #    Superstructure stage parameters
        if self.stage_selection == 'automated':
            self.S = max(sum(self.z_i_active), sum(self.z_j_active))
        else:
            if self.pinch_loc == 'above':
                self.S = self.stage_selection[0]
            elif self.pinch_loc == 'below':
                self.S = self.stage_selection[1]             
        self.K = self.S + 1 
        
        #    Hot stream parameters
        self.Qtot_sh = np.array([(self.T_h_in[i] - self.T_h_out[i]) * self.f_h[i] * self.z_i_active[i] for i in range(self.I)]) # total heat content to be released from hot stream i 

        #    Cold stream parameters
        self.Qtot_sc = np.array([self.f_c[j] * (self.T_c_out[j] - self.T_c_in[j]) * self.z_j_active[j] for j in range(self.J)]) # total heat content to be gained by cold stream j 

        #    Fixed parameters for heat exchanger matches
        self.U_r = np.array([[1 / ( 1 / self.htc_h[i]  + 1 / self.htc_c[j]) for j in range(self.J)] for i in range(self.I)]) #overall heat transfer coefficient between streams i, j
        self.U_hu = np.array([1 / ( 1 / self.htc_hu[0] + 1 / self.htc_c[j]) for j in range(self.J)]) #overall heat transfer coefficient for heaters to cold stream j
        self.U_cu = np.array([1 / ( 1 / self.htc_h[i] + 1 / self.htc_cu[0]) for i in range(self.I)]) #overall heat transfer coefficient for coolers to hot stream i
        self.Q_max = np.array([[max(self.T_h_in[i] - self.T_c_in[j] - self.dTmin, 0.0) * min(self.f_h[i] * self.z_i_active[i], self.f_c[j] * self.z_j_active[j]) for j in range(self.J)] for i in range(self.I)]) #maximum heat exchange between streams i, j
        
        #    Feasible matches    
        self.z_feasible =  [[[1 if self.Q_max[i][j] > self.tol else 0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]    
        self.z_hu_feasible = [1 if self.pinch_loc =='above' and self.z_j_active[j] > 0 else 0 for j in range(self.J)] # only feasible to have hu aboce the pinch
        self.z_cu_feasible = [1 if self.pinch_loc =='below' and self.z_i_active[i] > 0 else 0 for i in range(self.I)] # only feasible to have cu below the pinch

        
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
        self.T_h = [[self.m.Var(value=self.T_h_in[i], ub=self.T_h_in[i],  lb=self.T_h_out[i], name='T_H{}_at_B{}'.format(i,k)) if k > 0 and self.z_i_active[i] > 0  else self.m.Param(value=self.T_h_in[i], name='T_H{}_at_B{}'.format(i,k)) for k in range(self.K)] for i in range(self.I)] #Hot stream temperatures at the kth stageboundary            
        self.T_c = [[self.m.Var(value=self.T_c_in[j], ub=self.T_c_out[j], lb=self.T_c_in[j],  name='T_C{}_at_B{}'.format(j,k)) if k < self.S and self.z_j_active[j] > 0 else self.m.Param(value=self.T_c_in[j], name='T_C{}_at_B{}'.format(j,k)) for k in range(self.K)] for j in range(self.J)] #Cold stream temperatures at the kth stage boundary
        
        #   EQUATION DECLARATION 
        #       Energy balance for each stream
        _ = [self.m.Equation(self.Qtot_sh[i] - sum([self.Q_r[i][j][k] for k in range(self.S) for j in range(self.J)]) - self.Q_c[i] == 0.0) if self.z_i_active[i] > 0 else None for i in range(self.I)]
        _ = [self.m.Equation(self.Qtot_sc[j] - sum([self.Q_r[i][j][k] for k in range(self.S) for i in range(self.I)]) - self.Q_h[j] == 0.0) if self.z_j_active[j] > 0 else None for j in range(self.J)]
        
        #       Energy balance for each heat recovery stage
        _ = [self.m.Equation((self.T_h[i][k + 1] - self.T_h[i][k]) * self.f_h[i] + sum([self.Q_r[i][j][k] for j in range(self.J)]) == 0) if self.z_i_active[i] > 0 else None for k in range(self.S) for i in range(self.I)]
        _ = [self.m.Equation((self.T_c[j][k + 1] - self.T_c[j][k]) * self.f_c[j] + sum([self.Q_r[i][j][k] for i in range(self.I)]) == 0) if self.z_j_active[j] > 0 else None for k in range(self.S) for j in range(self.J)]

        #   INTEGER VARIABLE DECLARATION      
        if self.integers: # integers are variables    
            self.z =  [[[self.m.Var(value=1, ub=1, lb=0, integer=True, name='z_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0, name='z_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
            self.z_cu = [self.m.Var(value=1, ub=1, lb=0, integer=True, name='z_H{}_to_CU'.format(i)) if self.z_cu_allowed[i]> 0 else self.m.Param(value=0, name='z_H{}_to_CU'.format(i)) for i in range(self.I)]  
            self.z_hu = [self.m.Var(value=1, ub=1, lb=0, integer=True, name='z_HU_to_C{}'.format(j)) if self.z_hu_allowed[j]> 0 else self.m.Param(value=0, name='z_HU_to_C{}'.format(j)) for j in range(self.J)] 
            
            #       Logic equations
            ## check what happens to utility binaries above and below, maybe try just biug-m on Q_r
            _ = [self.m.Equation(self.Q_r[i][j][k] * (1 - self.z[i][j][k]) == 0.0) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
            _ = [self.m.Equation(self.Q_c[i]       * (1 - self.z_cu[i]) == 0.0) if self.z_cu_allowed[i]> 0     else None for i in range(self.I)]
            _ = [self.m.Equation(self.Q_h[j]       * (1 - self.z_hu[j]) == 0.0) if self.z_hu_allowed[j]> 0     else None for j in range(self.J)]
          
        else: # integers are params hence network configuration is fixed and logic equations are not needed
            self.z =  [[[self.m.Param(value=1, name='z_H{}_to_C{}_at_S{}'.format(i,j,k)) if self.z_allowed[i][j][k] > 0 else self.m.Param(value=0, name='z_H{}_to_C{}_at_S{}'.format(i,j,k)) for k in range(self.S)] for j in range(self.J)] for i in range(self.I)] 
            self.z_hu = [self.m.Param(value=1, name='z_HU_to_C{}'.format(j)) if self.z_hu_allowed[j]> 0 else self.m.Param(value=0, name='z_HU_to_C{}'.format(j)) for j in range(self.J)] 
            self.z_cu = [self.m.Param(value=1, name='z_H{}_to_CU'.format(i)) if self.z_cu_allowed[i]> 0 else self.m.Param(value=0, name='z_H{}_to_CU'.format(i)) for i in range(self.I)]  

        # Approach temperatures isothermal equations
        
        M_ij = [[max(abs(self.T_h_in[i] - self.T_c_in[j]), 
                     abs(self.T_h_in[i] - self.T_c_out[j]), 
                     abs(self.T_h_out[i] - self.T_c_in[j]), 
                     abs(self.T_h_out[i] - self.T_c_out[j])
                     ) + self.dTmin
                for j in range(self.J)] for i in range(self.I)]
                          
        _ = [self.m.Equation((self.T_h[i][k]     - self.T_c[j][k]    ) >= self.dTmin - M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
        _ = [self.m.Equation((self.T_h[i][k+1]     - self.T_c[j][k+1]    ) >= self.dTmin - M_ij[i][j] * (1 - self.z[i][j][k])) if self.z_allowed[i][j][k] > 0 else None for k in range(self.S) for j in range(self.J) for i in range(self.I)]
          
        self.dqda = []
        self.alpha = []
        
      
    def set_obj(self):
        # print('Minimise: ' + self.minimisation_goal)
        
        if self.minimisation_goal == 'hot utility':    
            self.m.Equation(sum(self.Q_h) - self.HU_target >= 0.0)   
            self.m.Minimize(sum(self.Q_h))

        elif self.minimisation_goal == 'cold utility':
            self.m.Equation(sum(self.Q_c) - self.CU_target >= 0.0)  
            self.m.Minimize(sum(self.Q_c))

        elif self.minimisation_goal == 'total utility':
            self.m.Minimize(sum(self.Q_h) + sum(self.Q_c))   

        elif self.minimisation_goal == 'heat recovery':
            self.m.Maximize(self.m.sum([self.Q_r[i][j][k] for i in range(self.I) for j in range(self.J) for k in range(self.S)]))
        
        elif self.minimisation_goal == 'min units':
            self.m.Minimize(self.m.sum([self.z[i][j][k] for k in range(self.S) for j in range(self.J) for i in range(self.I)]))

        elif self.minimisation_goal == 'total cost' or self.minimisation_goal == 'variable total cost':
            #    NETWORK COST INTERMEDIATES
            # Variable costs
            self.hu_cost_total = self.m.Intermediate(self.hu_cost[0] * self.m.sum([self.Q_h[j] for j in range(self.J)]), name="Hot utility cost")
            self.cu_cost_total = self.m.Intermediate(self.cu_cost[0] * self.m.sum([self.Q_c[i] for i in range(self.I)]), name="Cold utility cost")
            self.recovery_area_cost_filtered  = [[0 for j in range(self.J)] for k in range(self.S)]                               
            for k in range(self.S): # sum area cost for each cold stream match in each stage with all hot streams then sum in obj function
                    for j in range(self.J):
                        allowed_hots = [] # empty list for saving allowed hot matches for stream j in stage
                        for i in range(self.I):
                            if self.z_allowed[i][j][k] > 0:
                                allowed_hots.append(i) # add the hot index to the list if its allowed
                        self.recovery_area_cost_filtered[k][j] = self.m.Intermediate(self.A_coeff[0] * self.m.sum([(self.Q_r[n][j][k]/(self.U_r[n][j] * (self.theta_1[n][j][k] * self.theta_2[n][j][k] * (self.theta_1[n][j][k] + self.theta_2[n][j][k])/2 + 1e-3)**(1/3))) ** self.A_exp[0] for n in allowed_hots]), name="Recovery HX area cost in stage {} cold {}".format(k,j)) # sum the area costs of all allowed i matches for j in stage k
                                
            self.hu_area_cost_total         = self.m.Intermediate(self.hu_coeff[0] * self.m.sum([(self.Q_h[j]/(self.U_hu[j] * ((self.T_hu_in[0] - self.T_c_out[j]) * (self.T_hu_out[0] - self.T_c[j][0])*((self.T_hu_in[0] - self.T_c_out[j]) + (self.T_hu_out[0] - self.T_c[j][0]))/2 + 1e-6)**(1/3)) + 1e-6) ** self.hu_exp[0] for j in range(self.J)]), name="Total hot utility HX area cost")
            self.cu_area_cost_total         = self.m.Intermediate(self.cu_coeff[0] * self.m.sum([(self.Q_c[i]/(self.U_cu[i] * ((self.T_h[i][self.S] - self.T_cu_out[0]) * (self.T_h_out[i] - self.T_cu_in[0])*((self.T_h[i][self.S] - self.T_cu_out[0]) + (self.T_h_out[i] - self.T_cu_in[0]))/2+ 1e-6)**(1/3))+ 1e-6) ** self.cu_exp[0] for i in range(self.I)]), name="Total cold utility HX area cost")
            
            #    OBJECTIVE FUNCTION DECLARATION
            if self.minimisation_goal == 'total cost':
                # Fixed costs
                self.utility_unit_cost_total = self.m.Intermediate(self.hu_unit_cost[0] * self.m.sum([self.z_hu[j] for j in range(self.J)]) + self.cu_unit_cost[0] * self.m.sum([self.z_cu[i] for i in range(self.I)]), name="Total utility base cost") 
                self.recovery_unit_cost      = [[0 for j in range(self.J)] for k in range(self.S)]
                for k in range(self.S): # sum  unit cost for each cold stream match in each stage with all hot streams then sum in obj function
                    for j in range(self.J):
                        self.recovery_unit_cost[k][j] = self.m.Intermediate(self.unit_cost[0] * self.m.sum([self.z[i][j][k] for i in range(self.I)]), name='Total recovery base cost in stage {} cold {}'.format(k,j))

                self.m.Minimize( #Total annual cost = utility energy costs + heat recovery exchanger capital costs + utility exchanger capital costs
                                self.hu_cost_total              # hot utility energy cost
                                + self.cu_cost_total            # cold utility energy cost
                                + self.utility_unit_cost_total  # fixed component of utility heat exchanger capital cost
                                + self.m.sum([self.recovery_unit_cost[k][j] for k in range(self.S) for j in range(self.J)])           # fixed component of recovery heat exchanger capital cost
                                + self.m.sum([self.recovery_area_cost_filtered[k][j] for k in range(self.S) for j in range(self.J)])  # heat recovery exchanger area cost
                                + self.hu_area_cost_total       # hot utility area cost
                                + self.cu_area_cost_total       # cold utility area cost
                                )

            elif self.minimisation_goal == 'variable total cost':
                self.m.Minimize( #Total annual cost = utility energy costs + heat recovery exchanger capital costs + utility exchanger capital costs
                                self.hu_cost_total              # hot utility energy cost
                                + self.cu_cost_total            # cold utility energy cost
                                + self.m.sum([self.recovery_area_cost_filtered[k][j] for k in range(self.S) for j in range(self.J)])  # heat recovery exchanger area cost
                                + self.hu_area_cost_total       # hot utility area cost
                                + self.cu_area_cost_total       # cold utility area cost
                                ) 

        
    def get_post_process(self):
        if self.mSuccess == 1:                
            #Post-processing analysis using more exact analysis, excludes costs for HX when z=1 but q=0
            self.n_units = sum([self.z[i][j][k][0] if self.Q_r[i][j][k][0] > self.tol else 0 for k in range(self.S) for j in range(self.J) for i in range(self.I)]) + sum([self.z_cu[i][0] if self.Q_c[i][0] > self.tol else 0 for i in range(self.I)]) + sum([self.z_hu[j][0] if self.Q_h[j][0] > self.tol else 0 for j in range(self.J)])
            self.n_recovery_units = sum([self.z[i][j][k][0] if self.Q_r[i][j][k][0] > self.tol else 0 for k in range(self.S) for j in range(self.J) for i in range(self.I)])
            
            # Post process approach temperatures if objective did not have area cost since it is not enforced to the actual theta in the model
            if self.minimisation_goal not in ['total cost', 'variable total cost']:
                if self.non_isothermal_model:
                    self.theta_1 = [[[ [self.T_h_out_x[i][j][k][0] - self.T_c[j][k][0]] if self.z[i][j][k][0] > 0 else [self.dTmin] for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
                    self.theta_2 = [[[ [self.T_h[i][k+1][0] - self.T_c_out_y[j][i][k][0]] if self.z[i][j][k][0] > 0 else [self.dTmin] for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
                else: 
                    self.theta_1 = [[[ [self.T_h[i][k][0] - self.T_c[j][k][0]] if self.z[i][j][k][0] > 0 else [self.dTmin] for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
                    self.theta_2 = [[[ [self.T_h[i][k+1][0] - self.T_c[j][k + 1][0]] if self.z[i][j][k][0] > 0 else [self.dTmin] for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            
            
            self.LMTD_r = [[[self.z[i][j][k][0] * (self.theta_1[i][j][k][0] - self.theta_2[i][j][k][0]) / math.log(self.theta_1[i][j][k][0] / self.theta_2[i][j][k][0]) if (abs(self.theta_1[i][j][k][0] - self.theta_2[i][j][k][0]) > self.tol and self.theta_1[i][j][k][0] >= self.dTmin and self.theta_2[i][j][k][0] >= self.dTmin) else self.theta_1[i][j][k][0] * self.z[i][j][k][0] for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            self.area_r = [[[self.Q_r[i][j][k][0] / self.U_r[i][j] / self.LMTD_r[i][j][k] if (self.LMTD_r[i][j][k] > self.tol and self.Q_r[i][j][k][0] > self.tol) else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            self.LMTD_hu = [self.z_hu[j][0] * ((self.T_hu_in[0] - self.T_c_out[j]) - (self.T_hu_out[0] - self.T_c[j][0][0])) / math.log((self.T_hu_in[0] - self.T_c_out[j]) / (self.T_hu_out[0] - self.T_c[j][0][0])) if (abs((self.T_hu_in[0] - self.T_c_out[j]) - (self.T_hu_out[0] - self.T_c[j][0][0])) > self.tol and self.T_hu_in[0] - self.T_c_out[j] >= self.dTmin and self.T_hu_out[0] - self.T_c[j][0][0] >= self.dTmin) else (self.T_hu_in[0] - self.T_c_out[j]) * self.z_hu[j][0] for j in range(self.J)]
            self.area_hu = [self.Q_h[j][0] / self.U_hu[j] / self.LMTD_hu[j] if (self.LMTD_hu[j] > self.tol and self.Q_h[j][0] > self.tol) else 0.0 for j in range(self.J)]
            self.LMTD_cu = [self.z_cu[i][0] * ((self.T_h[i][self.S][0] - self.T_cu_out[0]) - (self.T_h_out[i] - self.T_cu_in[0])) / math.log((self.T_h[i][self.S][0] - self.T_cu_out[0]) / (self.T_h_out[i] - self.T_cu_in[0])) if (abs((self.T_h[i][self.S][0] - self.T_cu_out[0]) - (self.T_h_out[i] - self.T_cu_in[0])) > self.tol and self.T_h[i][self.S][0] - self.T_cu_out[0] >= self.dTmin and self.T_h_out[i] - self.T_cu_in[0] >= self.dTmin) else (self.T_h_out[i] - self.T_cu_in[0]) * self.z_cu[i][0] for i in range(self.I)]
            self.area_cu = [self.Q_c[i][0] / self.U_cu[i] / self.LMTD_cu[i] if (self.LMTD_cu[i] > self.tol and self.Q_c[i][0] > self.tol) else 0.0 for i in range(self.I)]
            self.Q_cu_total = sum(self.Q_c[i][0] for i in range(self.I))
            self.Q_hu_total =  sum(self.Q_h[j][0] for j in range(self.J)) 
            self.Q_r_total = sum([self.Q_r[i][j][k][0] for k in range(self.S) for j in range(self.J) for i in range(self.I)])
            self.dqda = [[[(self.theta_1[i][j][k][0] * self.theta_2[i][j][k][0] * self.U_r[i][j]) / (self.T_h[i][k][0] - self.T_c[j][k + 1][0]) * self.z[i][j][k][0] if (self.T_h[i][k][0] - self.T_c[j][k + 1][0]) > 0.0 else 0.0 for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            self.alpha = self.get_alpha_values()
            self.dtacda = [[[None for k in range(self.S)] for j in range(self.J)] for i in range(self.I)]
            for k in range(self.S): 
                for j in range(self.J):
                    for i in range(self.I):
                        if self.area_r[i][j][k] > 0.0:
                            self.dtacda[i][j][k] = self.dqda[i][j][k] * (self.hu_cost[0] + self.cu_cost[0]) - (self.A_coeff[0] * self.A_exp[0] * self.area_r[i][j][k] ** (self.A_exp[0] - 1)) 
                        else:
                            self.dtacda[i][j][k] = self.dqda[i][j][k] * (self.hu_cost[0] + self.cu_cost[0]) - (self.A_coeff[0] * self.A_exp[0]) 

            #Recalculation of objective function
            self.TAC_model = self.m.options.objfcnval
            self.TAC =   (self.hu_cost[0]   * sum([self.Q_h[j][0] for j in range(self.J)]) # hot utility energy cost
                        + self.cu_cost[0]   * sum([self.Q_c[i][0] for i in range(self.I)]) # cold utility energy cost
                        + self.unit_cost[0] * self.n_units # fixed component of heat exchanger capital costs
                        + self.A_coeff[0]   * sum([self.area_r[i][j][k] ** self.A_exp[0] for k in range(self.S) for j in range(self.J) for i in range(self.I)]) # heat recovery exchanger area cost
                        + self.hu_coeff[0]  * sum([self.area_hu[j] ** self.A_exp[0] for j in range(self.J)]) # hot utility area cost
                        + self.cu_coeff[0]  * sum([self.area_cu[i] ** self.A_exp[0] for i in range(self.I)])) # cold utility area cost
                                

    def amalgamate_networks(self, below_case, above_case) -> StageWiseModel:
        '''Amalgamates soln above and below pinch into one network'''
        amalgamated = StageWiseModel(name='amalgamated', 
                                                    framework=self.framework,
                                                    solver=self.solver,
                                                    import_file=self.import_file,
                                                    stages=(above_case.S if above_case.HU_target > 0 else 0) + (below_case.S if below_case.CU_target > 0 else 0),  # total number of stages is sum of above and below pinch stages
                                                    dTmin=self.dTmin,
                                                    z_restriction=self.z_restriction,
                                                    min_dqda=self.min_dqda,
                                                    minimisation_goal='total utility',
                                                    non_isothermal_model=self.non_isothermal_model,
                                                    integers=True,
                                                    tol=1e-3)
        try:
            if (above_case.HU_target > 0 and above_case.mSuccess == 0) or (below_case.CU_target > 0 and below_case.mSuccess == 0): # Check for threshold problem and set amalgamated to either above or below case
                raise ValueError(f'Pinch Decomposition failed: Above {above_case.mSuccess} Below {below_case.mSuccess} dTmin {self.dTmin}') 
            else: 
                # Amalgamate above pinch (LHS)
                if above_case.HU_target > 0 and above_case.mSuccess == 1:
                    amalgamated.mSuccess = above_case.mSuccess
                    amalgamated.TAC = above_case.TAC
                    amalgamated.solve_time = above_case.solve_time 
                    
                    for i in range(self.I):
                        for j in range(self.J):
                            for k in range(above_case.S):
                                amalgamated.z[i][j][k].VALUE.value = [above_case.z[i][j][k][0]]
                                amalgamated.Q_r[i][j][k].VALUE.value = [above_case.Q_r[i][j][k][0]]
                                amalgamated.theta_1[i][j][k].VALUE.value = [above_case.theta_1[i][j][k][0]]
                                amalgamated.theta_2[i][j][k].VALUE.value = [above_case.theta_2[i][j][k][0]]
                                if above_case.non_isothermal_model:
                                    amalgamated.X[i][j][k].VALUE.value = [above_case.X[i][j][k][0]]
                                    amalgamated.Y[i][j][k].VALUE.value = [above_case.Y[i][j][k][0]]
                                    amalgamated.T_h_out_x[i][j][k].VALUE.value = [above_case.T_h_out_x[i][j][k][0]]
                                    amalgamated.T_c_out_y[i][j][k].VALUE.value = [above_case.T_c_out_y[i][j][k][0]]
                            
                    for i in range(self.I):
                        for k in range(above_case.K):
                            if above_case.z_i_active[i] > 0: # stream active above pinch
                                amalgamated.T_h[i][k].VALUE.value = [above_case.T_h[i][k][0]]
                            else: # stream terminates below pinch so stage temp is still inlet temp
                                amalgamated.T_h[i][k].VALUE.value = [amalgamated.T_h_in[i]]

                    for j in range(self.J):
                        for k in range(above_case.K):
                            if above_case.z_j_active[j] > 0: # stream active above pinch
                                amalgamated.T_c[j][k].VALUE.value = [above_case.T_c[j][k][0]]
                            else: # stream starts below pinch so stage temp is still outlet temp
                                amalgamated.T_c[j][k].VALUE.value = [amalgamated.T_c_out[j]]

                    for j in range(self.J):
                        amalgamated.Q_h[j].VALUE.value  =  [above_case.Q_h[j][0]]
                        amalgamated.z_hu[j].VALUE.value  =  [above_case.z_hu[j][0]]
                    
                    if below_case.CU_target == 0: # set cold utility to 0 for threshold
                        for i in range(self.I):
                            amalgamated.Q_c[i].VALUE.value  =  [0]
                            amalgamated.z_cu[i].VALUE.value  =  [0] 
                            amalgamated.minimisation_goal = 'hot utility' 
                
                # Amalgamate below pinch (RHS)    
                if below_case.CU_target > 0 and below_case.mSuccess == 1:
                    amalgamated.mSuccess = below_case.mSuccess 
                    amalgamated.TAC = below_case.TAC
                    amalgamated.solve_time = below_case.solve_time
                    
                    
                    if above_case.HU_target == 0: # CU threshold problem so entire soln exists below pinch (RHS), need to reset S & K so it starts from beginning
                        above_case.S = 0
                        above_case.K = 0
                        
                    for i in range(self.I):
                        for j in range(self.J):
                            for k in range(above_case.S, amalgamated.S): # shift amalagamted list by above cases stage count, don't include 0th position i.e pinch temp since this is set by the above pinch amalgamation
                                amalgamated.z[i][j][k].VALUE.value = [below_case.z[i][j][k - above_case.S][0]]
                                amalgamated.Q_r[i][j][k].VALUE.value = [below_case.Q_r[i][j][k - above_case.S][0]]
                                amalgamated.theta_1[i][j][k].VALUE.value = [below_case.theta_1[i][j][k - above_case.S][0]]
                                amalgamated.theta_2[i][j][k].VALUE.value = [below_case.theta_2[i][j][k - above_case.S][0]]
                                if below_case.non_isothermal_model:
                                    amalgamated.X[i][j][k].VALUE.value = [below_case.X[i][j][k - above_case.S][0]]
                                    amalgamated.Y[j][i][k].VALUE.value = [below_case.Y[j][i][k - above_case.S][0]]
                                    amalgamated.T_h_out_x[i][j][k].VALUE.value = [below_case.T_h_out_x[i][j][k - above_case.S][0]]
                                    amalgamated.T_c_out_y[j][i][k].VALUE.value = [below_case.T_c_out_y[j][i][k - above_case.S][0]]
                                
                    for i in range(self.I):
                        for k in range(above_case.K, amalgamated.K):
                            if below_case.z_i_active[i] > 0: # stream active below pinch
                                amalgamated.T_h[i][k].VALUE.value = [below_case.T_h[i][k- above_case.K + 1][0]] if above_case.HU_target > 0 else [round(below_case.T_h[i][k][0],5)] # copy entire list over since no above pinch
                            else: # stream starts above pinch so stage temp is still outlet temp
                                amalgamated.T_h[i][k].VALUE.value = [amalgamated.T_h_out[i]]

                    for j in range(self.J):
                        for k in range(above_case.K, amalgamated.K):
                            if below_case.z_j_active[j] > 0: # stream active below pinch
                                amalgamated.T_c[j][k].VALUE.value = [below_case.T_c[j][k - above_case.K + 1][0]] if above_case.HU_target > 0 else  [round(below_case.T_c[j][k][0],5)] # copy entire list over since no above pinch
                            else: # stream starts above pinch so stage temp is still inlet temp
                                amalgamated.T_c[j][k].VALUE.value = [amalgamated.T_c_in[j]]

                    for i in range(self.I):
                        amalgamated.Q_c[i].VALUE.value  =  [round(below_case.Q_c[i][0], 5)]
                        amalgamated.z_cu[i].VALUE.value  =  [below_case.z_cu[i][0]]
                    
                    if above_case.HU_target == 0: # set hot utility to 0 for threshold
                        for j in range(self.J):
                            amalgamated.Q_h[j].VALUE.value  =  [0]
                            amalgamated.z_hu[j].VALUE.value  =  [0]
                            amalgamated.minimisation_goal = 'cold utility'
                            
                if above_case.HU_target > 0 and below_case.CU_target > 0 and above_case.mSuccess == 1 and below_case.mSuccess == 1:
                    amalgamated.mSuccess = 1 
                    amalgamated.TAC = below_case.TAC + above_case.TAC
                    amalgamated.solve_time = above_case.solve_time + below_case.solve_time 
                    amalgamated.S = above_case.S + below_case.S 
                
                amalgamated.K = amalgamated.S + 1    
                amalgamated.z_allowed = [[[1 if amalgamated.Q_r[i][j][k][0] > self.tol else 0 for k in range(amalgamated.S)] for j in range(amalgamated.J)] for i in range(amalgamated.I)]
                
        except ValueError as e:
                    print(f"An error occurred: {e}")    
        
        return amalgamated    

    def calculate_pinch(self):
        '''
        Calculates pinch temperature

        Uses an adaptation of python openpinch to perform the PTA
        '''     
        # Set streams
        self.process = Process(name='process', zone_num=1)
        self.set_streams(self.hot_names, self.T_h_in_OG, self.T_h_out_OG, self.T_h_cont, self.htc_h, self.f_h)
        self.set_streams(self.cold_names, self.T_c_in_OG, self.T_c_out_OG, self.T_c_cont, self.htc_c, self.f_c)

        # Calculate pinch
        self.process.Target_Process()
        self.HU_target = self.process.hot_utility_target
        self.CU_target = self.process.cold_utility_target
        # Set the pinch temperature (note this is shifted temperature!!)
        if self.HU_target == 0: # hot threshold
            self.T_pinch = self.process.cold_pinch + 273.15
        elif self.CU_target == 0:
            self.T_pinch = self.process.hot_pinch + 273.15
        else:
            self.T_pinch = self.process.hot_pinch + 273.15
            
    def set_streams(self, names, Tsupply, Ttarget, dt_cont, htc_s, mCP):
        '''Assign stream data to stream object
        '''     
        # Hot streams
        for y in range(len(names)):
          
            # Create and initialise stream from row of data at SD[i]
            Stream_j = Stream(name=names[y])
            Stream_j.set_t_supply(t_supply=Tsupply[y] - 273.15)
            Stream_j.set_t_target(t_target=Ttarget[y] - 273.15)
            Stream_j.set_heat_flow(abs(Ttarget[y] - Tsupply[y]) * mCP[y])
            Stream_j.set_dt_cont(dt_cont=dt_cont[y])
            Stream_j.set_htc(htc=htc_s[y])

            if Tsupply[y] > Ttarget[y]:
                # This is a hot stream that needs to be cooled down
                Stream_j.set_t_min(Stream_j.t_target)
                Stream_j.set_t_max(Stream_j.t_supply)
                Stream_j.set_t_min_star(Stream_j.t_min - Stream_j.dt_cont)
                Stream_j.set_t_max_star(Stream_j.t_max - Stream_j.dt_cont)
            else:
                Stream_j.set_t_min(Stream_j.t_supply)
                Stream_j.set_t_max(Stream_j.t_target)
                Stream_j.set_t_min_star(Stream_j.t_min + Stream_j.dt_cont)
                Stream_j.set_t_max_star(Stream_j.t_max + Stream_j.dt_cont)

            Stream_j.set_CP(Stream_j.heat_flow /  (Stream_j.t_max - Stream_j.t_min))
            Stream_j.set_RCP_prod(Stream_j.CP / Stream_j.htc)

            if Tsupply[y] > Ttarget[y]:
                self.process.add_hot_stream(Stream_j)
            else:
                self.process.add_cold_stream(Stream_j)                

    def verify(self) -> tuple[bool, list[str]]:
        return solution_verification.verify_solution(self)
