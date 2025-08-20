__author__ = 'Alex Geary'

import copy
from .zone import Zone
from .refFloat import RefFloat
# from heatExchangerEq import HX_NTU
# import parameters as params
from .publicOperations import *
from . import publicOperations as publicOps
# from turbineFunctions import Target_Power_Above_Pinch
# from xSteamTables import Tsat_p

class Process(Zone):
    """Represents a process that manipulates multiple streams through various unit operations and utilities.
    local_utilities: Utilities that are utilised only by this process
    hot_central_utilities: defset of IndustrialSite.central_utilities with type: 'Hot'
    cold_central_utilities: defset of IndustrialSite.central_utilities with type: 'Cold'
    streams: List of streams that are run through this process
    processes: List of processes within this process
    """
    def __init__(self, name='', zone_num=None):
        super().__init__(name)
        self.area = 0.0
        self.capital_cost = 0.0
        self.cold_central_utilities = []
        self.cold_pinch = 0
        self.ETE = 0
        self.exergy_des_min = 0
        self.exergy_req_min = 0
        self.exergy_sinks = 0
        self.exergy_sources = 0
        self.hot_pinch = 0
        self.cold_streams = []
        self.cold_utility_target = 0.0
        self.degree_of_int = None
        self.heat_rec_target = 0.0
        self.hot_central_utilities = []
        self.hot_streams = []
        self.hot_utility_target = 0.0
        self.local_utilities = []
        self.num_units = 0
        self.processes = []
        self.results = {}
        self.total_cost = 0.0
        self.utility_cost = 0
        self.w_eff_target = 0
        self.w_target = 0
        self.zone_num = zone_num

    """'-------------------------------------------------------------------------------------------------------------------------------------------------
    Attribute setters and adders.
    """
    def set_area(self, area):
        self.area = area

    def set_capital_cost(self, capital_cost):
        self.capital_cost = capital_cost

    def set_cold_pinch(self, cold_pinch):
        self.cold_pinch = cold_pinch

    def set_cold_streams(self, streams):
        self.cold_streams = streams

    def set_cold_utility_target(self, cold_utility_target):
        self.cold_utility_target = cold_utility_target

    def set_degree_of_int(self, degree_of_int):
        self.degree_of_int = degree_of_int

    def set_ETE(self, ete):
        self.ETE = ete

    def set_exergy_des_min(self, exergy_des_min):
        self.exergy_des_min = exergy_des_min

    def set_exergy_sinks(self, sink):
        self.exergy_sinks = sink

    def set_exergy_sources(self, source):
        self.exergy_sources = source

    def set_exergy_req_min(self, exergy_req_min):
        self.exergy_req_min = exergy_req_min

    def set_heat_rec_limit(self, heat_rec_limit):
        self.heat_rec_limit = heat_rec_limit

    def set_heat_rec_target(self, heat_rec_target):
        self.heat_rec_target = heat_rec_target

    def set_hot_streams(self, streams):
        self.hot_streams = streams

    def set_hot_pinch(self, hot_pinch):
        self.hot_pinch = hot_pinch

    def set_hot_utility_target(self, hot_utility_target):
        self.hot_utility_target = hot_utility_target

    def set_name(self, name):
        super().set_name(name)

    def set_num_units(self, num_units):
        self.num_units = num_units

    def set_retrofit_target(self, retrofit_target):
        self.retrofit_target = retrofit_target

    def set_total_cost(self, total_cost):
        self.total_cost = total_cost

    def set_utility_cost(self, utility_cost):
        self.utility_cost = utility_cost

    def set_w_eff_target(self, w_eff_target):
        self.w_eff_target = w_eff_target

    def set_w_target(self, w_target):
        self.w_target = w_target

    def set_zone_num(self, num):
        self.zone_num = num

    def add_cold_central_utility(self, util):
        self.cold_central_utilities.append(util)

    def add_cold_stream(self, stream):
        self.cold_streams.append(stream)

    def add_hot_central_utility(self, util):
        self.hot_central_utilities.append(util)

    def add_hot_stream(self, stream):
        self.hot_streams.append(stream)

    def add_local_utility(self, util):
        self.local_utilities.append(util)

    def add_process(self, process):
        self.processes.append(process)

    def add_result(self, name, result):
        self.results[name] = result

    def add_unit_op(self, unit_op):
        super().add_unit_op(unit_op)


    """'-------------------------------------------------------------------------------------------------------------------------------------------------
    Functions for processing pinch.
    """
    def Target_Process(self, TIT_analysis=False):
        """Main function that calls deffunctions to calculate all process-level Pinch
        Targets and prepare data for Total Site.
        """
        # Extract temperature intervals
        PT_star, PT = self.Extract_Temperature_Interval()

        # Calculate the shifted and unshifted composite curves.
        self.PT_Algorithm(PT_star, PT)

        # print_2D_array(PT_star, 'pyarray2.txt')
        # Calculate GCC without pockets
        GCC_NP = self.Calc_GCC_NP(PT_star)

        # Calculate extreme GCC, assuming vertical heat transfer in the heat recovery region
        GCC_Ex = self.Calc_GCC_Extreme(PT_star) if params.SETTINGSFORM_ENERGY_RETROFIT_BUTTON else None

        GCC_Mod = GCC_NP

        # Target multiple utility use
        GCC_Act = self.Calc_GCC_Act(GCC_Mod, GCC_Ex)
        GHLP_P = self.Calc_GHLP(GCC_Act, 1)

        self.set_hot_pinch(GHLP_P[0][self.Find_PinchRow(GHLP_P, 1, 'Hot')])
        self.set_cold_pinch(GHLP_P[0][self.Find_PinchRow(GHLP_P, 1, 'Cold')])
        
        self.Target_Utility(GHLP_P, 0, 1, 'Hot')
        self.Target_Utility(GHLP_P, 0, 2, 'Cold')

        GCC_Ut = self.Calc_GCC_Ut(PT, False)
        GCC_Ut_star = self.Calc_GCC_Ut(PT_star, True)

        for Utility_k in self.hot_central_utilities:
            self.utility_cost += (Utility_k.heat_flow / 1000 * Utility_k.price)
        
        for Utility_k in self.cold_central_utilities:
            self.utility_cost += (Utility_k.heat_flow / 1000 * Utility_k.price)

        # Determine Balanced CC for real and shifted temperature scales
        BCC = None
        BCC_star = None
        if params.SETTINGSFORM_EXERGY_BUTTON or params.SETTINGSFORM_AREA_BUTTON or params.GRAPH_OPTIONSFORM_BCC_CHECKBOX:
            BCC = self.Calc_BCC(PT, GCC_Ut, True)
            BCC_star = self.Calc_BCC(PT_star, GCC_Ut_star, False)

        # Target exergy supply, rejection, and destruction
        GCC_X = self.Target_Exergy(PT, BCC, GCC_Act) if params.SETTINGSFORM_EXERGY_BUTTON else None

        self.add_result('PT', PT)
        self.add_result('PT_star', PT_star)
        self.add_result('GCC_Act', GCC_Act)
        self.add_result('GCC_NP', GCC_NP)
        self.add_result('GCC_Ut', GCC_Ut)
        self.add_result('GCC_Ut_star', GCC_Ut_star)

        GCC_AI = None
        if params.DEFAULTFORM_AHT_BUTTON_SELECTED:
            self.add_result('GCC_AI', GCC_AI)

        if params.SETTINGSFORM_EXERGY_BUTTON or params.SETTINGSFORM_AREA_BUTTON or params.GRAPH_OPTIONSFORM_BCC_CHECKBOX:
            self.add_result('BCC', BCC)
            self.add_result('BCC_star', BCC_star)

        if params.SETTINGSFORM_EXERGY_BUTTON:
            self.add_result('GCC_X', GCC_X)

        if params.SETTINGSFORM_ENERGY_RETROFIT_BUTTON:
            self.add_result('GCC_Ex', GCC_Ex)

        # Target heat transfer area and number of exchanger units based on Balanced CC
        if params.SETTINGSFORM_AREA_BUTTON:
            self.set_area(self.Target_Area(BCC))
            self.set_num_units(self.MinNumberHX(PT_star, BCC_star))

        # Target co-generation of heat and power
        if params.SETTINGSFORM_TURBINE_WORK_BUTTON:
            Target_Power_Above_Pinch(self)

        # Save data for TS profiles based on HT direction
        if params.SETTINGSFORM_TS_BUTTON_SELECTED and self.name != TIT_NAME \
                and self.hot_utility_target + self.cold_utility_target > ZERO:
            if publicOps.total_site.TSP_data == None:
                publicOps.total_site.set_TSP_data([[], [], [], []])
                publicOps.total_site.set_TSU_star_data(copy.deepcopy(publicOps.total_site.TSP_data))
                publicOps.total_site.set_TSU_data(copy.deepcopy(publicOps.total_site.TSP_data))

            publicOps.total_site.set_TSP_data(self.Store_TSP_data(publicOps.total_site.TSP_data, GCC_Act, True))      # TS data based on doubled shifted temperatures, i.e. utility scale T
            publicOps.total_site.set_TSU_star_data(self.Store_TSP_data(publicOps.total_site.TSU_star_data, GCC_Ut_star))   # TS data based on shifted temperatures
            publicOps.total_site.set_TSU_data(self.Store_TSP_data(publicOps.total_site.TSU_data, GCC_Ut))             # TS data based on real temperatures

    def Find_PinchRow(self, inputArray, Col_h=10, U_Type='Hot'):
        """Returns the row of the selected Pinch Temperature.
        """
        row_i = None
        if U_Type == 'Hot':
            for i in range(len(inputArray[0])):
                if inputArray[Col_h][i] < ZERO:
                    row_i = i
                    break
            if i == 0:
                for i in range(i + 1, len(inputArray[0])):
                    if inputArray[Col_h][i] > ZERO:
                        row_i = i - 1
                        break
                else:
                    row_i = len(inputArray[0]) - 1

        if U_Type == 'Cold':
            for i in range(len(inputArray[0]) - 1, -1, -1):
                if inputArray[Col_h][i] < ZERO:
                    row_i = i
                    break
            if i == len(inputArray[0]) - 1:
                for i in range(i - 1, -1, -1):
                    if inputArray[Col_h][i] > ZERO:
                        row_i = i + 1
                        break
                else:
                    row_i = 0

        return row_i

    def Target_Utility(self, Input_GCC, Col_T=0, Col_h=1, Utility_Type='Both', Real_T=False):
        """Targets multiple utility use considering a fixed target temperature.
        """
        hot_utilities = self.hot_central_utilities
        cold_utilities = self.cold_central_utilities
        Num_HU = len(hot_utilities)
        Num_CU = len(cold_utilities)

        Hot_Pinch_row = self.Find_PinchRow(Input_GCC, Col_h, 'Hot')
        #self.set_hot_pinch(Input_GCC[0][self.Find_PinchRow(Input_GCC, Col_h, 'Hot')])
        if (Utility_Type == 'Hot' or Utility_Type == 'Both') and self.hot_utility_target > ZERO:
            H0 = RefFloat(Input_GCC[Col_h][Hot_Pinch_row])
            T0 = RefFloat(Input_GCC[Col_T][Hot_Pinch_row])
            j = RefFloat(Hot_Pinch_row)
            for k in range(Num_HU - 1, -1, -1):
                Utility_k = hot_utilities[k]
                if self.hot_utility_target - H0.value < ZERO:
                    break
                T_shift = 0 if Real_T else Utility_k.dt_cont
                TT_star = Utility_k.t_target - T_shift
                if TT_star + ZERO >= T0.value:
                    # Hot utility required above the pinch
                    self.Calc_UtilityDuty(Utility_k, Input_GCC, j, T0, H0, 0, T_shift, TT_star, Col_T, Col_h, 'Hot')
        
        Cold_Pinch_row = self.Find_PinchRow(Input_GCC, Col_h, 'Cold')
        #self.set_cold_pinch(Input_GCC[0][self.Find_PinchRow(Input_GCC, Col_h, 'Cold')])
        if (Utility_Type == 'Cold' or Utility_Type == 'Both') and self.cold_utility_target > ZERO:
            H0 = RefFloat(Input_GCC[Col_h][Cold_Pinch_row])
            T0 = RefFloat(Input_GCC[Col_T][Cold_Pinch_row])
            j = RefFloat(Cold_Pinch_row)
            for k in range(0, Num_CU):
                Utility_k = cold_utilities[k]
                if self.cold_utility_target - H0.value < ZERO:
                    break
                T_shift = 0 if Real_T else Utility_k.dt_cont
                TT_star = Utility_k.t_target + T_shift
                if T0.value + ZERO >= TT_star:
                    # Cold utility required below the pinch
                    self.Calc_UtilityDuty(Utility_k, Input_GCC, j, T0, H0, len(Input_GCC[0]), T_shift, TT_star, Col_T, Col_h, 'Cold')
    def Calc_UtilityDuty(self, Utility_k, Input_GCC, j, T0, H0, j_limit, T_shift, TT_star, Col_T, Col_h, Utility_Type):
        """Performs multi-level utility targeting for either hot or cold.
        """
        unit_sign = 1 if Utility_Type == 'Cold' else -1

        TS_star = Utility_k.t_supply + T_shift * unit_sign
        dh = self.Max_Ut_Duty(Input_GCC, TS_star, TT_star, Col_T, Col_h, min(int(j.value), j_limit), max(int(j.value), j_limit), Utility_Type, H0.value)
        
        if dh > ZERO:
            Utility_k.set_heat_flow(dh)
            print_line(Utility_k.heat_flow, 'pyarray2.txt')
            Utility_k.set_ut_cost(dh / 1000 * Utility_k.price)
            Utility_k.set_CP(dh / abs(TT_star - TS_star))
        else:
            Utility_k.set_heat_flow(0)

            Utility_k.set_ut_cost(0)
            Utility_k.set_CP(0)
        H0.set_value(H0.value + dh)

        if unit_sign == -1:
            while j.value >= j_limit - unit_sign:
                if (H0.value - Input_GCC[Col_h][j.value]) < ZERO:
                    break
                j.set_value(j.value - 1)
        else:
            while j.value <= j_limit - unit_sign:
                if (H0.value - Input_GCC[Col_h][j.value]) < ZERO:
                    break
                j.set_value(j.value + 1)

        T0.set_value(Input_GCC[Col_T][j.value])
    #     if abs(H0.value - Input_GCC[Col_h][j]) < ZERO:
    #        for j in range(j, j_limit - unit_sign, unit_sign):
    #            if abs(Input_GCC[Col_h][j] - H0.value) > ZERO:
    #                break
    #        T0.set_value(Input_GCC[Col_T][j])
    #     else:
    #         print('T interval missing... check Calc_UtilityDuty def.', vbCritical, 'Error')
    #         End
    #         T0.set_value(Inter_Val(H0.value, Input_GCC[Col_h][j], Input_GCC[Col_h][j] - unit_sign), Input_GCC[Col_T][j], Input_GCC[Col_T][j] - unit_sign)))

        if (j.value * unit_sign) > (j_limit * unit_sign): # TODO: This is going to multiply by 0 when j_limit is 0
            j.set_value(j_limit)

    def Max_Ut_Duty(self, InputGCC, TS_star, TT_star, Col_T, Col_h, i_upper, i_lower, Utility_Type='Cold', H0=None):
        """Returns the "maximum" utility duty for a given utility quality and GCC.
        """
        CP_max = 10000000000.0
        if H0 == None:
            H0 = min(InputGCC[Col_h][i_upper], InputGCC[Col_h][i_lower])
        if Utility_Type == 'Hot':
            for j in range(i_lower, i_upper, -1):
                dh = InputGCC[Col_h][j] - H0
                if dh > ZERO:
                    dt = min(InputGCC[Col_T][j] - TT_star, abs(TT_star - TS_star)) if abs(TT_star - InputGCC[Col_T][j]) > ZERO else -1
                    if dh / dt < CP_max and dt > ZERO:
                        CP_max = dh / dt
                    if abs(TS_star - InputGCC[Col_T][j]) < ZERO:
                        break
            if j < i_upper:
                j += 1
        else:
            for j in range(i_upper, i_lower):
                dh = InputGCC[Col_h][j] - H0
                if dh > 0:
                    dt = min(TT_star - InputGCC[Col_T][j], abs(TT_star - TS_star)) if abs(TT_star - InputGCC[Col_T][j]) > ZERO else -1
                    if dh / dt < CP_max and dt > ZERO:
                        CP_max = dh / dt
                    if abs(TS_star - InputGCC[Col_T][j]) < ZERO:
                        break
            if j > i_lower:
                j -= 1

        dh = min(CP_max * abs(TT_star - TS_star), InputGCC[Col_h][j] - H0)
        return dh

    def Target_Exergy(self, PT, BCC, GCC_Act):
        """Determine Exergy Transfer Effectiveness including process and utility streams.
        """
        # Exergy Transfer Effectiveness proposed by Marmolejo-Correa, D., Gundersen, T., 2012. 
        # A comparison of exergy efficiency definitions with focus on low temperature processes. 
        # Energy 44, 477–489. https://doi.org/10.1016/j.energy.2012.06.001
        x_source, x_sink, n_ETE = self.Calc_Total_Exergy(BCC)
        self.set_exergy_sources(x_source)
        self.set_exergy_sinks(x_sink)
        self.set_ETE(n_ETE)

        GCC_X = self.Calc_ExGCC(GCC_Act)
        x_source, x_sink, n_ETE = self.Calc_Total_Exergy(PT, Col_T=0, Col_HCC=4, Col_CCC=7)
        
        self.set_exergy_req_min(GCC_X[1][1])
        self.set_exergy_des_min(GCC_X[1][-1])

        return GCC_X

    def PT_Algorithm(self, PT_star, PT):
        """Applies the Problem Table Algorithm to each process.
        """
        CP_sum = [0] * 3
        R_ave = [0] * 3

        # Insert Null in the first row of the interval cascades
        for i in range(1, 10):
            if i != 4 and i != 7:
                PT_star[i][0] = None
                PT[i][0] = None

        # Initialise min H values
        min_H_star = 0
        min_H = 0

        # Problem Table algorithm applied to shifted temperature data set
        for i in range(1, len(PT_star[0])):
            # dT (shifted)
            PT_star[1][i] = PT_star[0][i - 1] - PT_star[0][i]
            self.Sum_CP(PT_star[0][i - 1], PT_star[0][i], CP_sum, R_ave, True)
            # Hot shifted composite curve
            PT_star[2][i] = CP_sum[1]
            PT_star[3][i] = R_ave[1]
            PT_star[4][i] = PT_star[1][i] * PT_star[2][i] + PT_star[4][i - 1]
            # Cold shifted composite curve
            PT_star[5][i] = CP_sum[2]
            PT_star[6][i] = R_ave[2]
            PT_star[7][i] = PT_star[1][i] * PT_star[5][i] + PT_star[7][i - 1]
            # Cascade / Grand shifted composite curve
            PT_star[8][i] = PT_star[2][i] - PT_star[5][i]
            PT_star[9][i] = PT_star[1][i] * PT_star[2][i] - PT_star[1][i] * PT_star[5][i]
            PT_star[10][i] = PT_star[9][i] + PT_star[10][i - 1]
            # Find minimum H for GCC
            if PT_star[10][i] < min_H_star:
                min_H_star = PT_star[10][i]

        # Problem Table algorithm applied to real temperature data set
        for i in range(1, len(PT[0])):
            # dT
            PT[1][i] = PT[0][i - 1] - PT[0][i]
            self.Sum_CP(PT[0][i - 1], PT[0][i], CP_sum, R_ave, False)
            # Hot  composite curve
            PT[2][i] = CP_sum[1]
            PT[3][i] = R_ave[1]
            PT[4][i] = PT[1][i] * PT[2][i] + PT[4][i - 1]
            # Cold  composite curve
            PT[5][i] = CP_sum[2]
            PT[6][i] = R_ave[2]
            PT[7][i] = PT[1][i] * PT[5][i] + PT[7][i - 1]
            # Cascade / Grand  composite curve
            PT[8][i] = PT[2][i] - PT[5][i]
            PT[9][i] = PT[1][i] * PT[2][i] - PT[1][i] * PT[5][i]
            PT[10][i] = PT[9][i] + PT[10][i - 1]
            # Find minimum H for GCC
            if PT[10][i] < min_H:
                min_H = PT[10][i]

        # Determine the end H values of the CCs
        hot_max = PT_star[4][-1]
        cold_min = PT_star[10][-1] - min_H_star
        cold_max = PT_star[7][-1] + cold_min

        # Transform the shifted temperature CCs and GCC
        for j in range(len(PT_star[0])):
            PT_star[4][j] = hot_max - PT_star[4][j]
            PT_star[7][j] = cold_max - PT_star[7][j]
            PT_star[10][j] = PT_star[10][j] - min_H_star
            
            if abs(PT_star[4][j]) < ZERO:
                PT_star[4][j] = 0
            if abs(PT_star[7][j]) < ZERO:
                PT_star[7][j] = 0
            if abs(PT_star[10][j]) < ZERO:
                PT_star[10][j] = 0

        # Transform the real temperature CCs and GCC
        for j in range(len(PT[0])):
            PT[4][j] = hot_max - PT[4][j]
            PT[7][j] = cold_max - PT[7][j]
            PT[10][j] = PT[10][j] - min_H_star
            
            if abs(PT[4][j]) < ZERO:
                PT[4][j] = 0
            if abs(PT[7][j]) < ZERO:
                PT[7][j] = 0
            if abs(PT[10][j]) < ZERO:
                PT[10][j] = 0

        # Record the process level targets
        self.set_heat_rec_target(PT_star[4][0] - PT_star[10][-1])
        self.set_hot_utility_target(PT_star[10][0])
        self.set_cold_utility_target(PT_star[10][-1])
        self.set_heat_rec_limit(PT[4][0] - PT[10][-1])
        if self.heat_rec_limit > 0:
            self.set_degree_of_int(self.heat_rec_target / self.heat_rec_limit)
        else:
            self.set_degree_of_int(1)
        
        # Shift the thermodynamic GCC out to the targeted utility levels
        for elem in PT[10]:
            elem += (self.heat_rec_limit - self.heat_rec_target)

    def Calc_GHLP(self, GCC, Col_dH):
        """Determines the gross heating or cooling profile of a system from the GCC.
        """
        i_max = len(GCC[0])
        GHLP_P = [[ None for j in range(i_max) ] for i in range(3)]
        GHLP_P[0][0] = GCC[0][0]
        GHLP_P[1][0] = 0 # Cold stream profile requiring hot utility
        GHLP_P[2][0] = 0 # Hot stream profile requiring cold utility

        for i in range(1, i_max):
            GHLP_P[0][i] = GCC[0][i]
            dh = GCC[Col_dH][i - 1] - GCC[Col_dH][i]
            if dh >= 0:
                GHLP_P[1][i] = GHLP_P[1][i - 1] - dh
                GHLP_P[2][i] = GHLP_P[2][i - 1]
            else:
                GHLP_P[1][i] = GHLP_P[1][i - 1]
                GHLP_P[2][i] = GHLP_P[2][i - 1] - dh

        HUt_max = -GHLP_P[1][i_max - 1]
        for i in range(i_max):
            GHLP_P[1][i] = GHLP_P[1][i] + HUt_max
        
        return GHLP_P

    def Store_TSP_data(self, TSP_data, GCC, Second_Shift=False):
        """Saves the process stream segment data for Total Site analysis.
        """
        k = 0
        UtShift = ''
        Utility_k = None

        if Second_Shift:
            # Find the first utility with demand
            UtShift = 'H'
            for k in range(len(self.hot_central_utilities)):
                if self.hot_central_utilities[k].heat_flow > ZERO:
                    Utility_k = self.hot_central_utilities[k]
                    break
            else:
                UtShift = 'C'
                for k in range(len(self.cold_central_utilities)):
                    if self.cold_central_utilities[k].heat_flow > ZERO:
                        Utility_k = self.cold_central_utilities[k]
                        break
                else:
                    print('Individual utilities have no demand, yet utility targets are above zero. See def Store_TSP_data.')

        j = len(TSP_data[0])
        for i in range(len(TSP_data)):
            TSP_data[i] += [0 for k in range(len(GCC[0]))]

        for i in range(len(GCC[0]) - 1):
            dh = GCC[1][i] - GCC[1][i + 1]
            dt = GCC[0][i] - GCC[0][i + 1]
            if abs(dh) > ZERO and dt > ZERO:
                if dh > ZERO:
                    TSP_data[2][j] = 0
                    TSP_data[3][j] = dh / dt
                elif dh < -ZERO:
                    TSP_data[2][j] = -dh / dt
                    TSP_data[3][j] = 0
                else:
                    TSP_data[2][j] = 0
                    TSP_data[3][j] = 0

                TSP_data[0][j] = min(GCC[0][i], GCC[0][i + 1])
                TSP_data[1][j] = max(GCC[0][i], GCC[0][i + 1])

                if Second_Shift:
                    if GCC[1][i] > GCC[1][i + 1]:
                        TSP_data[0][j] = TSP_data[0][j] + Utility_k.dt_cont
                        TSP_data[1][j] = TSP_data[1][j] + Utility_k.dt_cont
                    else:
                        TSP_data[0][j] = TSP_data[0][j] - Utility_k.dt_cont
                        TSP_data[1][j] = TSP_data[1][j] - Utility_k.dt_cont
                    U_duty = -abs(dh)
                    if U_duty < ZERO:
                        br = False
                        if UtShift == 'H':
                            UtShift = 'H'
                            for k in range(k, len(self.hot_central_utilities)):
                                if self.hot_central_utilities[k].heat_flow > ZERO:
                                    Utility_k = self.hot_central_utilities[k]
                                    br = True
                                    break
                            else:
                                k = 1
                                UtShift = 'C'
                        if br == False:
                            if UtShift == 'C':
                                for k in range(k, len(self.cold_central_utilities)):
                                    if self.cold_central_utilities[k].heat_flow > ZERO:
                                        Utility_k = self.cold_central_utilities[k]
                                        break
                j += 1

        TSP_data = TSP_data[:4]
        if j > 0:
            for i in range(len(TSP_data)):
                TSP_data[i] = TSP_data[i][:j]
        return TSP_data

    def Store_TSU_Data(self, TSU_data, GCC, shift=False):
        if shift:
            # Find the first utility with demand
            UtShift = 'H'
            for k in range(len(self.hot_central_utilities)):
                if self.hot_central_utilities[k].heat_flow > ZERO:
                    Utility_k = self.hot_central_utilities[k]
                    break
            else:
                UtShift = 'C'
                for k in range(len(self.cold_central_utilities)):
                    if self.cold_central_utilities[k].heat_flow > ZERO:
                        Utility_k = self.cold_central_utilities[k]
                        break
                else:
                    print('Individual utilities have no demand, yet utility targets are above zero. See def Store_TSU_Data.')
        
        j = len(TSU_data[0])
        TSU_data = TSU_data[:4]
        for i in range(len(TSU_data)):
            TSU_data[i] = TSU_data[i][:j + len(GCC[0])]
        
        for i in range(len(GCC[0]) - 1):
            dh = GCC[1][i] - GCC[1][i + 1]
            dt = GCC[0][i] - GCC[0][i + 1]
            if abs(dh) > ZERO and dt > ZERO:
                j += 1
                TSU_data[0][j] = min(GCC[0][i], GCC[0][i + 1])
                TSU_data[1][j] = max(GCC[0][i], GCC[0][i + 1])
                
                if shift:
                    if GCC[1][i] > GCC[1][i + 1]:
                        TSU_data[0][j] = TSU_data[0][j] + Utility_k.dt_cont
                        TSU_data[1][j] = TSU_data[1][j] + Utility_k.dt_cont
                    else:
                        TSU_data[0][j] = TSU_data[0][j] - Utility_k.dt_cont
                        TSU_data[1][j] = TSU_data[1][j] - Utility_k.dt_cont
                    U_duty = U_duty - abs(dh)
                    if U_duty < ZERO:
                        br = False
                        if UtShift == 'H':
                            UtShift = 'H'
                            for k in range(k, len(self.hot_central_utilities)):
                                if self.hot_central_utilities[k].heat_flow > ZERO:
                                    Utility_k = self.hot_central_utilities[k]
                                    br = True
                                    break
                            else:
                                k = 1
                                UtShift = 'C'
                        if br == False:
                            if UtShift == 'C':
                                for k in range(k, len(self.cold_central_utilities)):
                                    if self.cold_central_utilities[k].heat_flow > ZERO:
                                        Utility_k = self.cold_central_utilities[k]
                                        break
                if dh > ZERO:
                    TSU_data[2][j] = 0
                    TSU_data[3][j] = dh / dt
                elif dh < -ZERO:
                    TSU_data[2][j] = -dh / dt
                    TSU_data[3][j] = 0
                else:
                    TSU_data[2][j] = 0
                    TSU_data[3][j] = 0

        TSU_data = TSU_data[:4]
        for i in range(len(TSU_data)):
            TSU_data[i] = TSU_data[i][:j]
        return TSU_data

    def Target_Area(self, BCC):
        """Estimates a heat transfer area target for a zone based on counter-current heat transfer.
        """
        Area = 0

        # Calculates the area table
        H_val = [0 for i in range(len(BCC[0]) * 2)]

        ColT = 0
        ColRH = 1
        ColHCC = 2
        ColRC = 3
        ColCCC = 4

        # Check the BCC is balanced, if not stop the calculation and return an error
        if abs(BCC[ColHCC][0] - BCC[ColCCC][0]) > ZERO:
            print('Balanced Composite Curves are imbalanced...')

        # Collate all H intervals
        for i in range(1, len(BCC[0])):
            H_val[i * 2 - 2] = BCC[ColHCC][i - 1]
            H_val[i * 2 - 1] = BCC[ColCCC][i - 1]

        H_val = OrganiseArray(H_val, 0)

        CalcTable = [ [None for j in range(len(H_val) - 1)] for i in range(10)]

        for i in range(len(H_val) - 1):
            CalcTable[0][i] = H_val[i]
            CalcTable[1][i] = H_val[i + 1]

        r_h = 0
        r_c = 0
        for i in range(len(CalcTable[0])):
            while (CalcTable[0][i] - BCC[ColHCC][r_h + 1]) <= ZERO and r_h + 2 <= len(BCC[0]):
                r_h += 1
            while (CalcTable[0][i] - BCC[ColCCC][r_c + 1]) <= ZERO and r_c + 2 <= len(BCC[0]):
                r_c += 1

            if (CalcTable[0][i] - BCC[ColHCC][r_h + 1] <= ZERO or CalcTable[0][i] - BCC[ColCCC][r_c + 1] <= ZERO) \
                    and (r_h + 1 == len(BCC[0]) or r_c + 1 == len(BCC[0])):
                break

            T_h1 = Inter_Val(CalcTable[0][i], BCC[ColHCC][r_h], BCC[ColHCC][r_h + 1], BCC[ColT][r_h], BCC[ColT][r_h + 1])
            T_h2 = Inter_Val(CalcTable[1][i], BCC[ColHCC][r_h], BCC[ColHCC][r_h + 1], BCC[ColT][r_h], BCC[ColT][r_h + 1])
            T_c1 = Inter_Val(CalcTable[0][i], BCC[ColCCC][r_c], BCC[ColCCC][r_c + 1], BCC[ColT][r_c], BCC[ColT][r_c + 1])
            T_c2 = Inter_Val(CalcTable[1][i], BCC[ColCCC][r_c], BCC[ColCCC][r_c + 1], BCC[ColT][r_c], BCC[ColT][r_c + 1])

            dh = CalcTable[0][i] - CalcTable[1][i]

            T_LMTD = Find_LMTD(T_h1, T_h2, T_c1, T_c2)
            CalcTable[2][i] = T_LMTD

            CP_hot = dh / (T_h1 - T_h2)
            CP_cold = dh / (T_c1 - T_c2)

            CP_min = min(CP_hot, CP_cold)
            CP_max = max(CP_hot, CP_cold)
            eff = dh / (CP_min * (T_h1 - T_c2))
            CP_star = CP_min / CP_max

            Arrangement = None
            if params.HXFORM_CF_SELECTED:
                Arrangement = CF
            elif params.HXFORM_PF_SELECTED:
                Arrangement = PF
            else:
                Arrangement = ShellTube

            Ntu = HX_NTU(Arrangement, eff, CP_star)

            # Heat transfer resistance and coefficient
            R_hot = BCC[ColRH][r_h + 1]
            R_cold = BCC[ColRC][r_c + 1]
            U_o = 1 / (R_hot + R_cold)

            CalcTable[3][i] = Ntu * CP_min / U_o
            CalcTable[4][i] = dh / (U_o * T_LMTD)

            Area = Area + CalcTable[3][i]

        return Area

    def MinNumberHX(self, PT_star, BCC_star):
        """Estimates the minimum number of heat exchanger units for a given Pinch problem.
        """
        Num_HX = 0
        i = 0
        while i < len(PT_star[0]) - 1:
            if abs(BCC_star[4][i + 1] - BCC_star[2][i + 1]) > ZERO:
                break
            i += 1

        i_1 = i
        i = i + 1
        while i < len(PT_star[0]):
            i_0 = i_1

            if abs(BCC_star[4][i] - BCC_star[2][i]) < ZERO or i == len(PT_star[0]) - 1:
                i_1 = i
                T_high = PT_star[0][i_0]
                T_low = PT_star[0][i_1]

                for Stream_j in self.hot_streams:
                    T_max = Stream_j.t_max_star
                    T_min = Stream_j.t_min_star
                    if (T_max > T_low + ZERO and T_max <= T_high + ZERO) or (T_min >= T_low - ZERO \
                            and T_min < T_high - ZERO) or (T_min < T_low - ZERO and T_max > T_high + ZERO):
                        Num_HX += 1

                for Stream_j in self.cold_streams:
                    T_max = Stream_j.t_max_star
                    T_min = Stream_j.t_min_star
                    if (T_max > T_low + ZERO and T_max <= T_high + ZERO) or (T_min >= T_low - ZERO \
                            and T_min < T_high - ZERO) or (T_min < T_low - ZERO and T_max > T_high + ZERO):
                        Num_HX += 1

                for Utility_k in self.hot_central_utilities:
                    T_max = Utility_k.t_max_star
                    T_min = Utility_k.t_min_star
                    if (T_max > T_low + ZERO and T_max <= T_high + ZERO) or (T_min >= T_low - ZERO and T_min < T_high - ZERO):
                        Num_HX += 1

                for Utility_k in self.cold_central_utilities:
                    T_max = Utility_k.t_max_star
                    T_min = Utility_k.t_min_star
                    if (T_max > T_low + ZERO and T_max <= T_high + ZERO) or (T_min >= T_low - ZERO and T_min < T_high - ZERO):
                        Num_HX += 1

                Num_HX -= 1

                j = i_1
                while j < len(PT_star[0]) - 1:
                    if abs(BCC_star[4][j + 1] - BCC_star[2][j + 1]) > ZERO:
                        break
                    j += 1

                i = j
                i_1 = j

            i += 1

        return Num_HX

    def Calc_BCC(self, PT, GCC_Ut, HTR_calc=False):
        """Creates the balanced CC using both process and utility streams.
        """
        Tot_rows = len(PT[0])

        BCC = [ [ 0 for j in range(Tot_rows) ] for i in range(5)]
        HLP_HU = [ [ 0 for j in range(Tot_rows) ] for i in range(3)]
        HLP_CU = copy.deepcopy(HLP_HU)

        for i in range(Tot_rows):
            BCC[0][i] = PT[0][i]
            HLP_HU[0][i] = PT[0][i]
            HLP_CU[0][i] = PT[0][i]

            if i >= 1:
                dh = GCC_Ut[1][i - 1] - GCC_Ut[1][i] if i <= len(GCC_Ut[0]) else 0
                HLP_HU[1][i] = HLP_HU[1][i - 1]
                HLP_CU[1][i] = HLP_CU[1][i - 1]

                if HTR_calc:
                    HLP_HU[2][i] = 0
                    HLP_CU[2][i] = 0

                if dh > ZERO: # hot utility
                    HLP_HU[1][i] = HLP_HU[1][i - 1] - dh
                    if HTR_calc:
                        HLP_HU[2][i] = GCC_Ut[2][i]
                if dh < -ZERO: # cold utility
                    HLP_CU[1][i] = HLP_CU[1][i - 1] + dh
                    if HTR_calc:
                        HLP_CU[2][i] = GCC_Ut[2][i]
            else:
                HLP_HU[1][i] = 0
                HLP_CU[1][i] = 0

        for i in range(Tot_rows):
            HLP_HU[1][i] = HLP_HU[1][i] - HLP_HU[1][-1] # -1 is last element
            HLP_CU[1][i] = HLP_CU[1][i] - HLP_CU[1][-1]

            BCC[2][i] = PT[4][i] + HLP_HU[1][i]
            BCC[4][i] = PT[7][i] + HLP_CU[1][i] - PT[7][Tot_rows - 1]

            if HTR_calc and i >= 1:
                dH_tot = abs(BCC[2][i - 1] - BCC[2][i])
                if dH_tot > 0:
                    beta = abs(PT[4][i - 1] - PT[4][i]) / dH_tot
                    BCC[1][i] = PT[3][i] * beta + HLP_HU[2][i] * (1 - beta)
                else:
                    BCC[1][i] = 0

                dH_tot = (abs(BCC[4][i - 1] - BCC[4][i]) + abs(HLP_CU[2][i - 1] - HLP_CU[2][i]))
                if dH_tot > 0:
                    beta = abs(PT[7][i - 1] - PT[7][i]) / dH_tot
                    BCC[3][i] = PT[6][i] * beta + HLP_CU[2][i] * (1 - beta)
                else:
                    BCC[3][i] = 0

            if BCC[2][i] < ZERO:
                BCC[2][i] = 0
            if BCC[4][i] < ZERO:
                BCC[4][i] = 0

        return BCC

    def Extract_Temperature_Interval(self):
        PT_star = [[] for i in range(11)]
        PT = copy.deepcopy(PT_star)

        hot_utilities = self.hot_central_utilities
        cold_utilities = self.cold_central_utilities

        for Stream_j in self.hot_streams:
            PT_star[0].append(Stream_j.t_min_star)
            PT[0].append(Stream_j.t_min)
            PT_star[0].append(Stream_j.t_max_star)
            PT[0].append(Stream_j.t_max)
        
        for Stream_j in self.cold_streams:
            PT_star[0].append(Stream_j.t_min_star)
            PT[0].append(Stream_j.t_min)
            PT_star[0].append(Stream_j.t_max_star)
            PT[0].append(Stream_j.t_max)

        for Utility_k in hot_utilities:
            PT_star[0].append(Utility_k.t_min_star)
            PT[0].append(Utility_k.t_min)
            PT_star[0].append(Utility_k.t_max_star)
            PT[0].append(Utility_k.t_max)

        for Utility_k in cold_utilities:
            PT_star[0].append(Utility_k.t_min_star)
            PT[0].append(Utility_k.t_min)
            PT_star[0].append(Utility_k.t_max_star)
            PT[0].append(Utility_k.t_max)

        if params.SETTINGSFORM_TURBINE_WORK_BUTTON:
            PT_star[0].append(params.TURBINEFORM_T_TURBINE_BOX)
            PT[0].append(params.TURBINEFORM_T_TURBINE_BOX)
            PT_star[0].append(Tsat_p(params.TURBINEFORM_P_TURBINE_BOX))
            PT[0].append(Tsat_p(params.TURBINEFORM_P_TURBINE_BOX))

        PT_star[0].append(params.DEFAULTFORM_TEMP_REF)
        PT[0].append(params.DEFAULTFORM_TEMP_REF)

        for i in range(1, len(PT_star)):
            PT_star[i] = [0 for j in range(len(PT_star[0]))]
            PT[i] = [0 for j in range(len(PT[0]))]

        PT_star = OrganiseArray(PT_star)
        PT = OrganiseArray(PT)

        return PT_star, PT

    def Calc_GCC_Extreme(self, PT_star):
        """Returns the extreme GCC.
        """
        GCC_Ex = [ copy.deepcopy(PT_star[0]) ] # Initialise GCC_Ex with first element

        HU_target = PT_star[10][0]
        CU_target = PT_star[10][-1]
        HR_target = PT_star[7][0] - CU_target - HU_target

        GCC_Ex.append([None for i in range(len(GCC_Ex[0]))])

        i = 0
        while i < len(PT_star[0]):
            GCC_Ex[1][i] = PT_star[7][i] - (HR_target + CU_target)
            if abs(GCC_Ex[1][i]) <= ZERO:
                break
            i += 1

        if i < len(PT_star[0]):
            GCC_Ex[1][i] = 0
        i_0 = i
        
        i = len(PT_star[0]) - 1
        while i >= 0:
            GCC_Ex[1][i] = CU_target - PT_star[4][i]
            if abs(GCC_Ex[1][i]) <= ZERO:
                break
            i -= 1

        if i >= 0:
            GCC_Ex[1][i] = 0
        i_1 = i
        
        for i in range(i_0, i_1):
            GCC_Ex[1][i] = 0

        return GCC_Ex

    def Calc_ExGCC(self, GCC_Act):
        """Transposes a normal GCC (T-h) into a exergy GCC (Tx-X).
        """
        GCC_X = copy.deepcopy(GCC_Act)
        Min_X = 0
        AbovePT = True
        GCC_X[0][0] = Calc_ExergeticT(GCC_Act[0][0] + params.DEFAULT_DTCONT / 2)
        GCC_X[1][0] = 0
        i_upper = len(GCC_X[0]) + 1
        
        # Transpose to exergetic temperature and exergy flow
        i = 1
        gcc_act_i = 1
        while i <= i_upper:
            if AbovePT:
                GCC_X[0][i] = Calc_ExergeticT(GCC_Act[0][gcc_act_i] + params.DEFAULT_DTCONT / 2)
                GCC_X[1][i] = (GCC_Act[1][gcc_act_i - 1] - GCC_Act[1][gcc_act_i]) / (GCC_Act[0][gcc_act_i - 1] - GCC_Act[0][gcc_act_i])
                GCC_X[1][i] = GCC_X[1][i - 1] - GCC_X[1][i] * (GCC_X[0][i - 1] - GCC_X[0][i])
                if GCC_Act[1][gcc_act_i] < ZERO:
                    Min_X = GCC_X[1][i]
                    for row in GCC_X:
                        row += [0, 0]
                    i += 2
                    gcc_act_i += 1
                    GCC_X[0][i] = Calc_ExergeticT(GCC_Act[0][gcc_act_i - 1] - params.DEFAULT_DTCONT / 2)
                    GCC_X[1][i] = GCC_X[1][i - 1]
                    AbovePT = False
            else:
                GCC_X[0][i] = Calc_ExergeticT(GCC_Act[0][gcc_act_i - 1] - params.DEFAULT_DTCONT / 2)
                GCC_X[1][i] = (GCC_Act[1][gcc_act_i - 2] - GCC_Act[1][gcc_act_i - 1]) / (GCC_Act[0][gcc_act_i - 2] - GCC_Act[0][gcc_act_i - 1])
                GCC_X[1][i] = GCC_X[1][i - 1] - GCC_X[1][i] * (GCC_X[0][i - 1] - GCC_X[0][i])
            i += 1
            gcc_act_i += 1

        # Shift Exergy GCC appropriately
        for i in range(1, len(GCC_X[0])):
            GCC_X[1][i] = GCC_X[1][i] + abs(Min_X)
            if abs(GCC_X[1][i]) < ZERO:
                GCC_X[1][i] = 0

        return GCC_X

    def Calc_GCC_PT(self, PT):
        """Writes a simplified array for the conventional process GCC.
        """
        GCC_PT = [ [None for j in range(len(PT[0]))] for i in range(2)]
        for i in range(len(PT[0])):
            GCC_PT[0][i] = PT[0][i]
            GCC_PT[1][i] = PT[10][i]
        return GCC_PT

    def Calc_GCC_Act(self, GCC_Mod, GCC_Ex):
        """Returns the GCC without pockets that corresponds to require utility use
        based on a selected direction of heat transfer.
        """
        if params.SETTINGSFORM_ENERGY_RETROFIT_BUTTON and params.RETROFITFORM_VHT_OPTION:
            # Define intended heat transfer direction.
            return copy.deepcopy(GCC_Ex)
        else:
            return copy.deepcopy(GCC_Mod)

    def Calc_GCC_AI(self, PT, GCC_NP):
        """Returns a simplified array for the assisted integration GCC.
        """
        GCC_AI = [ [ None for j in range(len(PT[0]))] for i in range(2)]
        for i in range(len(PT[0])):
            GCC_AI[0][i] = PT[0][i]
            GCC_AI[1][i] = PT[10][i] - GCC_NP[1][i]
        return GCC_AI

    def Calc_GCC_Ut(self, T_Values, shifted=True):
        """Returns the GCC profile for utility use of a process.
        """
        Phi = 1 if shifted else 0 # Turns temperature shift on (1) or off (0)
        
        Tot_rows = len(T_Values[0])
        GCC_Ut = [[ None for j in range(Tot_rows) ] for i in range(3)]
        CP_Ut = 0
        R_ave = 0
        
        for i in range(Tot_rows):
            GCC_Ut[0][i] = T_Values[0][i]
        
        GCC_Ut[1][0] = self.hot_utility_target
        for i in range(1, Tot_rows):
            for Utility_k in self.hot_central_utilities:
                if abs(GCC_Ut[0][i - 1] - (Utility_k.t_supply - Utility_k.dt_cont * Phi)) < ZERO:
                    CP_Ut += Utility_k.CP
                    R_ave += Utility_k.CP / Utility_k.htc
                if abs(GCC_Ut[0][i - 1] - (Utility_k.t_target - Utility_k.dt_cont * Phi)) < ZERO:
                    CP_Ut -= Utility_k.CP
                    R_ave -= Utility_k.CP / Utility_k.htc

            for Utility_k in self.cold_central_utilities:
                if abs(GCC_Ut[0][i - 1] - (Utility_k.t_supply + Utility_k.dt_cont * Phi)) < ZERO:
                    CP_Ut += Utility_k.CP
                    R_ave += Utility_k.CP / Utility_k.htc
                if abs(GCC_Ut[0][i - 1] - (Utility_k.t_target + Utility_k.dt_cont * Phi)) < ZERO:
                    CP_Ut -= Utility_k.CP
                    R_ave -= Utility_k.CP / Utility_k.htc

            dt = GCC_Ut[0][i - 1] - GCC_Ut[0][i]
            GCC_Ut[1][i] = GCC_Ut[1][i - 1] - CP_Ut * dt
            if abs(GCC_Ut[1][i]) < ZERO:
                GCC_Ut[1][i] = 0
            GCC_Ut[2][i] = R_ave / CP_Ut if abs(CP_Ut) > 0 else 0
        
        return GCC_Ut

    def Calc_GCC_NP(self, PT_star):
        # Extract GCC from PT
        GCC_NP = [
            [x for x in PT_star[0]],
            [x for x in PT_star[10]]
        ]

        # Locate hot pinch
        Hot_Pinch = self.Find_PinchRow(PT_star, 10, 'Hot')

        # Remove pocket segments above the Pinch
        if GCC_NP[1][0] > ZERO:
            i = 0
            while i < Hot_Pinch:
                if GCC_NP[1][i] < GCC_NP[1][i + 1] - ZERO:
                    H0 = GCC_NP[1][i]
                    i_upper = i
                    i += 1
                    while H0 < GCC_NP[1][i] + ZERO:
                        i += 1
                    i -= 1
                    
                    # Add an intermediate temperature, if needed
                    if GCC_NP[1][i] - H0 > ZERO:
                        i += 1
                        i_0 = i
                        T0 = Inter_Val(H0, PT_star[10][i], PT_star[10][i - 1], PT_star[0][i], PT_star[0][i - 1])
                        Add_PT_Tint(PT_star, T0, i_0)
                        Add_GCC_T_int(GCC_NP, T0, i_0)
                        Hot_Pinch += 1

                    # Remove pocket
                    i_lower = i
                    if i > i_upper:
                        for j in range(i_upper + 1, i_lower):
                            GCC_NP[1][j] = GCC_NP[1][i_upper]
                i += 1
        
        # Locate cold pinch
        Cold_Pinch = self.Find_PinchRow(PT_star, 10, 'Cold')

        # Remove pocket segments below the Pinch
        if GCC_NP[1][-1] > ZERO:
            i = len(GCC_NP[0]) - 1
            while i > Cold_Pinch:
                if GCC_NP[1][i] < GCC_NP[1][i - 1] - ZERO:
                    H0 = GCC_NP[1][i]
                    i_lower = i
                    i -= 1
                    while H0 < GCC_NP[1][i] + ZERO:
                        i -= 1
                    i += 1

                    # Add an intermediate temperature, if needed
                    if GCC_NP[1][i] - H0 > ZERO:
                        i_0 = i
                        T0 = Inter_Val(H0, PT_star[10][i], PT_star[10][i - 1], PT_star[0][i], PT_star[0][i - 1])
                        Add_PT_Tint(PT_star, T0, i_0)
                        Add_GCC_T_int(GCC_NP, T0, i_0)
                        i_lower += 1
                    
                    # Remove pocket
                    i_upper = i
                    if i < i_lower:
                        for j in range(i_upper + 1, i_lower):
                            GCC_NP[1][j] = GCC_NP[1][i_lower]
                i -= 1
        
        # Remove any possible pocket segments between the pinches
        if Hot_Pinch + 1 < Cold_Pinch:
            i_upper = Hot_Pinch
            i_lower = Cold_Pinch

            # Remove pocket
            for j in range(i_upper + 1, i_lower):
                GCC_NP[1][j] = 0

        return GCC_NP

    def Calc_Total_Exergy(self, CC, x_source=0, x_sink=0, n_ETE=0, Col_T=0, Col_HCC=2, Col_CCC=4):
        """Determines the source and sink exergy of a balanced CC.
        """
        for i in range(1, len(CC[0])):
            T_ex1 = Calc_ExergeticT(CC[Col_T][i - 1])
            T_ex2 = Calc_ExergeticT(CC[Col_T][i])
            CP_hot = (CC[Col_HCC][i - 1] - CC[Col_HCC][i]) / (CC[Col_T][i - 1] - CC[Col_T][i])
            CP_cold = (CC[Col_CCC][i - 1] - CC[Col_CCC][i]) / (CC[Col_T][i - 1] - CC[Col_T][i])
            
            if T_ex1 > 0:
                x_source = x_source + CP_hot * T_ex1
                x_sink = x_sink + CP_cold * T_ex1
            else:
                x_source = x_source + CP_cold * T_ex1
                x_sink = x_sink + CP_hot * T_ex1
            
            if T_ex2 > 0:
                x_source = x_source - CP_hot * T_ex2
                x_sink = x_sink - CP_cold * T_ex2
            else:
                x_source = x_source - CP_cold * T_ex2
                x_sink = x_sink - CP_hot * T_ex2

        n_ETE = x_sink / x_source if x_source > ZERO else 0

        return x_source, x_sink, n_ETE

    def Sum_CP(self, T_0, T_1, CP_sum, R_ave, shifted):
        """Sums the CP values between two temperatures.
        """
        CP_sum[1] = 0
        CP_sum[2] = 0
        R_ave[1] = 0
        R_ave[2] = 0
        
        if shifted:
            for Stream_j in self.hot_streams:
                if Stream_j.t_max_star > T_1 + ZERO and Stream_j.t_min_star < T_0 - ZERO:
                    CP_sum[1] = CP_sum[1] + Stream_j.CP
                    R_ave[1] = R_ave[1] + Stream_j.RCP_prod
            for Stream_j in self.cold_streams:
                if Stream_j.t_max_star > T_1 + ZERO and Stream_j.t_min_star < T_0 - ZERO:
                    CP_sum[2] = CP_sum[2] + Stream_j.CP
                    R_ave[2] = R_ave[2] + Stream_j.RCP_prod
        else:
            for Stream_j in self.hot_streams:
                if Stream_j.t_max > T_1 + ZERO and Stream_j.t_min < T_0 - ZERO:
                    CP_sum[1] = CP_sum[1] + Stream_j.CP
                    R_ave[1] = R_ave[1] + Stream_j.RCP_prod
            
            for Stream_j in self.cold_streams:
                if Stream_j.t_max > T_1 + ZERO and Stream_j.t_min < T_0 - ZERO:
                    CP_sum[2] = CP_sum[2] + Stream_j.CP
                    R_ave[2] = R_ave[2] + Stream_j.RCP_prod
        
        R_ave[1] = R_ave[1] / CP_sum[1] if CP_sum[1] > 0 else 0
        R_ave[2] = R_ave[2] / CP_sum[2] if CP_sum[2] > 0 else 0

    def Target_AssistedHT(self, PT_star, GCC_NP, GCC_AI, GHLP_CU, GHLP_HU):
        """This function is not working...
        """
        dH_HU = 0
        dH_CU = 0
        i = 0
        AbovePinch = True
        while i < len(GCC_AI[0]):
            # Characterise one pocket on shifted T scale
            for i in range(i, len(GCC_AI[0]) - 1):
                if abs(GCC_NP[2][i] - GCC_NP[2][i + 1]) > ZERO * 10:
                    if GCC_NP[2][i] > GCC_NP[2][i + 1]:
                        dH_HU += GCC_NP[2][i] - GCC_NP[2][i + 1]
                    else:
                        dH_CU += GCC_NP[2][i + 1] - GCC_NP[2][i]
                if GCC_NP[2][i] < ZERO:
                    AbovePinch = False
                if GCC_AI[2][i + 1] > ZERO:
                    break

            if i == len(GCC_AI[0]):
                break # Exit while loop
            i_upper = i
            
            dH_max = 0
            for i in range(i + 1, len(GCC_AI[0])):
                if GCC_AI[2][i] > dH_max:
                    dH_max = GCC_AI[2][i]
                if GCC_AI[2][i] < ZERO:
                    break

            i_lower = i
            # Find location where utility profiles cross, which represents maximum assisted heat transfer
            if AbovePinch:
                br = False
                for k in range(len(GHLP_CU[0])):
                    HU_temp = -dH_HU - GHLP_HU[2][k] if (-dH_HU - GHLP_HU[2][k]) > ZERO else 0
                    CU_temp = GHLP_CU[2][k] - dH_CU if (GHLP_CU[2][k] - dH_CU) > ZERO else 0
                    if (CU_temp - HU_temp) > -ZERO and CU_temp > ZERO and HU_temp > ZERO:
                        br = True
                        break
                else: # Break from loop did not happen
                    DH_0 = HU_temp
                    for k in range(len(GHLP_CU[0])):
                        HU_temp = -dH_HU - GHLP_HU[2][k] if (-dH_HU - GHLP_HU[2][k]) > ZERO else 0
                        CU_temp = GHLP_CU[2][k] - dH_CU if (GHLP_CU[2][k] - dH_CU) > ZERO else 0
                        if (HU_temp - CU_temp) > -ZERO and CU_temp > ZERO and HU_temp > ZERO:
                            break
                    k -= 1
                    dH_cut = (GHLP_CU[2][k] - dH_CU) - DH_0
                if br:
                    k -= 1
                    if k == len(GHLP_CU[0]):
                        i = i_lower
                        continue
                    DH_0 = (-dH_HU - GHLP_HU[2][k])
                    for k in range(len(GHLP_CU[0])):
                        HU_temp = -dH_HU - GHLP_HU[2][k] if (-dH_HU - GHLP_HU[2][k]) > ZERO else 0
                        CU_temp = GHLP_CU[2][k] - dH_CU if (GHLP_CU[2][k] - dH_CU) > ZERO else 0
                        if (HU_temp - CU_temp) > -ZERO and CU_temp > ZERO and HU_temp > ZERO:
                            break
                    k -= 1
                    dH_cut = (GHLP_CU[2][k] - dH_CU) - DH_0                
            else:
                for k in range(len(GHLP_CU[0])):
                    HU_temp = -dH_HU - GHLP_HU[2][k] if (-dH_HU - GHLP_HU[2][k]) > ZERO else 0
                    CU_temp = GHLP_CU[2][k] - dH_CU if (GHLP_CU[2][k] - dH_CU) > ZERO else 0
                    if (CU_temp - HU_temp) > -ZERO and CU_temp > ZERO and HU_temp > ZERO:
                        break
                k -= 1
                if k == len(GHLP_CU[0]):
                    i = i_lower
                    continue
                DH_0 = (-dH_HU - GHLP_HU[2][k])
                for k in range(len(GHLP_CU[0])):
                    HU_temp = -dH_HU - GHLP_HU[2][k] if (-dH_HU - GHLP_HU[2][k]) > ZERO else 0
                    CU_temp = GHLP_CU[2][k] - dH_CU if (GHLP_CU[2][k] - dH_CU) > ZERO else 0
                    if (HU_temp - CU_temp) > -ZERO and CU_temp > ZERO and HU_temp > ZERO:
                        break
                k -= 1
                dH_cut = (GHLP_CU[2][k] - dH_CU) - DH_0

            if dH_cut < ZERO:
                i = i_lower
                continue
            i = i_upper
            while True:
                if (GCC_AI[2][i] + ZERO < dH_cut and GCC_AI[2][i + 1] > dH_cut + ZERO) \
                        or (GCC_AI[2][i] > dH_cut + ZERO and GCC_AI[2][i + 1] + ZERO < dH_cut):
                    i_0 = i + 1
                    T0 = Inter_Val(dH_cut, GCC_AI[2][i], GCC_AI[2][i + 1], GCC_AI[1][i], GCC_AI[1][i + 1])
                    Add_PT_Tint(PT_star, T0, i_0)
                    Add_GCC_T_int(GCC_NP, T0, i_0)
                    Add_GCC_T_int(GCC_AI, T0, i_0)
                    if GCC_AI[2][i] > dH_cut + ZERO:
                        GCC_AI[2][i] = dH_cut
                    i += 1
                    i_lower += 1
                if GCC_AI[2][i] > dH_cut + ZERO:
                    GCC_AI[2][i] = dH_cut
                i += 1
                if i >= i_lower:
                    break
            i = i_lower

    def to_string(self):
        print('Process:\n  name: ', self.name, '\n  local_utilities: ', self.local_utilities, \
            '\n  hot_central_utilities: ', self.hot_central_utilities, '\n  cold_central_utilities: ', self.cold_central_utilities, \
            '\n  processes: ', self.processes, '\n  zone_num: ', self.zone_num, '\n  heat_rec_target: ', self.heat_rec_target, \
            '\n  hot_streams: ', self.hot_streams, '\n  hot_utility_target: ', self.hot_utility_target, \
            '\n  cold_utility_target: ', self.cold_utility_target, '\n  heat_rec_limit: ', self.heat_rec_limit, \
            '\n  degree_of_int: ', self.degree_of_int, '\n  cold_streams: ', self.cold_streams, \
            '\n  unit_ops: ', self.unit_ops, '\n}')