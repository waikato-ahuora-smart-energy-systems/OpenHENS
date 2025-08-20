__author__ = ''

import sys, copy
from classes import Process, Utility, Stream
from . import parameters as params
from .publicOperations import *
from .vbaFunctions import *

#######################################################################################################
# Main Functions
#######################################################################################################

def Prepare_Data(total_site, wb, Stream_Data_Extract=True, Utility_Data_Extract=True, \
    Targets_Initialisation=True, test_SD_Extraction=False, test_UD_Extraction=False):
    """Calls the private routines that extract data from the sheets for the analysis."""
    if Stream_Data_Extract:
        Extract_SD(total_site, wb)
    if Utility_Data_Extract:
        Extract_UD(total_site, wb)
    # if Targets_Initialisation:
    #     InitialiseTargets(total_site)

def InitialiseTargets(total_site):
    i = 7 + len(total_site.central_utilities)
    if params.SETTINGSFORM_TURBINE_WORK_BUTTON:
        i += 2
    if params.SETTINGSFORM_EXERGY_BUTTON:
        i += 6
    if params.SETTINGSFORM_AREA_BUTTON:
        i += 4
    
    processes = total_site.get_processes_without_sites()

    j = len(processes) + 5
    Targets = [ [ 0 for x in range(j)] for y in range(i)]
    total_site.set_TSP_data([ [0] for x in range(i)])
    total_site.set_TSU_star_data([ [0] for x in range(4)])
    total_site.set_TSU_data([ [0] for x in range(4)])
    total_site.add_result('Targets', Targets)
    total_site.add_result('TSP data', total_site.TSP_data)
    total_site.add_result('TSU star data', total_site.TSU_star_data)
    total_site.add_result('TSU data', total_site.TSU_data)

def Extract_SD(total_site, wb):
    """Extracts all the stream data.
    """
    unit = None
    # Default dt_cont (minimum temperature shift that is needed for each stream to make in order to make both their temperatures the same at the pinch point)
    dt_cont = params.DEFAULT_DTCONT / 2
    HTC = params.DEFAULT_HTC

    # Grab stream data from sheet
    SD_Sheet = wb.sheets['Stream Data']
    SD = SD_Sheet.range('A1').current_region.offset(2, 0).value
    SD = SD[:-2] # Slice off last two elements

    # Fill missing (None) values
    for i in range(len(SD)):
        if SD[i][2] == None or SD[i][3] == None or SD[i][4] == None:
            print('Stream data input incomplete...')
            sys.exit(0)
        if SD[i][5] == None or params.DEFAULTFORM_OVERRIDEDT_BUTTON_SELECTED:
            SD[i][5] = dt_cont
        if SD[i][6] == None or SD[i][6] <= 0:
            SD[i][6] = HTC
        SD[i][7] = 0
        SD[i][8] = 0
        SD[i][9] = 0

    # Sort rows by col A
    SD.sort(key=lambda row: row[0])

    # Check the multiplication factor on the stream data input sheet
    select_variable_0 = SD_Sheet.cells(2, 5).value
    if select_variable_0 == 'W':
        unit = 1 / 1000
    elif select_variable_0 == 'kW':
        unit = 1
    elif select_variable_0 == 'MW':
        unit = 1000
    elif select_variable_0 == 'GW':
        unit = 1000 * 1000

    # Copy across the stream data
    AllHotStream_Set = []
    AllColdStream_Set = []

    # Create and initialise 1st process to be added to total_site.processes collection
    process = Process(name=SD[0][0], zone_num=1)

    for i in range(len(SD)):
        if process.name != SD[i][0]:
            total_site.add_process(process)
            process = Process(name=SD[i][0], zone_num=len(total_site.processes) + 1)

        # Create and initialise stream from row of data at SD[i]
        Stream_j = Stream(CutName(SD[i][1]))
        Stream_j.set_t_supply(SD[i][2])
        Stream_j.set_t_target(SD[i][3])
        Stream_j.set_heat_flow(SD[i][4])
        Stream_j.set_dt_cont(SD[i][5])
        Stream_j.set_htc(SD[i][6])

        if SD[i][2] > SD[i][3]:
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

        Stream_j.set_CP(Stream_j.heat_flow /  (Stream_j.t_max - Stream_j.t_min) * unit)
        Stream_j.set_RCP_prod(Stream_j.CP / Stream_j.htc * unit)

        if SD[i][2] > SD[i][3]:
            process.add_hot_stream(Stream_j)
            AllHotStream_Set.append(Stream_j)
        else:
            process.add_cold_stream(Stream_j)
            AllColdStream_Set.append(Stream_j)

    # Add the stream sets to the process and add this final process to the totalsite
    total_site.add_process(process)

    # (Total Integrated Target) is Totally Integrated Site button
    if params.SETTINGSFORM_TIT_BUTTON_SELECTED:
        TIT_Site = Process(name=TIT_NAME)
        TIT_Site.set_hot_streams(AllHotStream_Set)
        TIT_Site.set_cold_streams(AllColdStream_Set)
        total_site.add_process(TIT_Site)

    if params.SETTINGSFORM_TS_BUTTON_SELECTED:
        UTS_Site = Process(name=UTS_NAME) # (Unified Total Site Target)
        total_site.add_process(UTS_Site)

        CTS_Site = Process(name=CTS_NAME) # (Conventional Total Site Target)
        total_site.add_process(CTS_Site)

    TZT_Site = Process(name=TZT_NAME) # (Total Zonal/Process Target)
    TZT_Site.set_hot_streams(AllHotStream_Set)
    TZT_Site.set_cold_streams(AllColdStream_Set)
    total_site.add_process(TZT_Site)

def Extract_UD(total_site, wb):
    """Extracts all the utility data.
    """
    U_0 = 0
    U_cost = 0.0

    # Grab utility data from sheet
    UD_Sheet = wb.sheets['Utility Data']
    UD = UD_Sheet.range('A1').current_region.offset(2, 0).value
    UD = UD[:-2] # Slice off last two elements

    # Set default dTcont_0 and h from input boxes
    dTcont_0 = params.DEFAULT_DTCONT / 2
    HTC = params.DEFAULT_HTC
    dt = 0.01
    if params.COSTING_OPTIONSFORM_ANNUAL_OP_TIME == '' or params.COSTING_OPTIONSFORM_ANNUAL_OP_TIME == 0:
        params.COSTING_OPTIONSFORM_ANNUAL_OP_TIME = 8500
    Price = params.DEFAULTFORM_UTILITY_PRICE * params.COSTING_OPTIONSFORM_ANNUAL_OP_TIME

    # Find highest TT of a cold stream and lowest TT of a hot stream
    HU_T_min = -10000
    CU_T_max = 10000

    processes = total_site.get_processes_without_sites()

    for process_i in processes:
        for Stream_j in process_i.hot_streams:
            if CU_T_max > Stream_j.t_min_star:
                CU_T_max = Stream_j.t_min_star
        for Stream_j in process_i.cold_streams:
            if HU_T_min < Stream_j.t_max_star:
                HU_T_min = Stream_j.t_max_star

    # Fill in any missing data
    AddDefaultHU = True
    AddDefaultCU = True

    if len(UD) > 0:
        for i in range(len(UD)):
            if UD[i][COL_U_type] == 'Hot':
                # There doesn't appear to be a 9th column on the sheet??
                UD[i][COL_U_Q] = 1
            elif UD[i][COL_U_type] == 'Cold':
                UD[i][COL_U_Q] = 3
            else:
                UD[i][COL_U_type] = 'Both'
                UD[i][COL_U_Q] = 2

            if UD[i][COL_U_Tt] == None:
                UD[i][COL_U_Tt] = UD[i][COL_U_Ts] - dt
            if UD[i][COL_U_dTcont] == None or UD[i][COL_U_dTcont] < 0 or params.DEFAULTFORM_OVERRIDEDT_BUTTON_SELECTED:
                UD[i][COL_U_dTcont] = dTcont_0
            if UD[i][COL_U_cost] == None:
                UD[i][COL_U_cost] = Price
            if UD[i][COL_U_h] == None or UD[i][COL_U_h] <= 0:
                UD[i][COL_U_h] = HTC
            if UD[i][COL_U_Q] <= 2 and min(UD[i][COL_U_Ts], UD[i][COL_U_Tt]) - UD[i][COL_U_dTcont] >= HU_T_min:
                AddDefaultHU = False
            if UD[i][COL_U_Q] >= 2 and max(UD[i][COL_U_Ts], UD[i][COL_U_Tt]) - UD[i][COL_U_dTcont] <= CU_T_max:
                AddDefaultCU = False

    # Add default hot and cold utilities if user wants to
    if AddDefaultHU:
        UD.append([
            'Default HU',
            'Hot',
             HU_T_min + dTcont_0 * 2,
             (HU_T_min + dTcont_0 * 2) - dt,
             dTcont_0,
             Price,
             HTC,
             False,
             1,
             None
        ])
    if AddDefaultCU:
        UD.append([
            'Default CU',
            'Cold',
            CU_T_max - dTcont_0 * 2,
            (CU_T_max - dTcont_0 * 2) + dt,
            dTcont_0,
            Price,
            HTC,
            False,
            3,
            None
        ])

    HotUtility = Utility()
    ColdUtility = Utility()

    # Grab hot utility levels
    T_max = 100000
    U = 0
    for i in range(len(UD)):
        # Find the next hot utility in ascending supply temperature order
        U_0 = U
        for j in range(len(UD)):
            if ( UD[j][COL_U_type] == 'Hot' or UD[j][COL_U_type] == 'Both' ) and UD[j][COL_U_Ts] < T_max \
                    and ( UD[U][COL_U_Ts] <= UD[j][COL_U_Ts] or UD[U][COL_U_type] == '' or UD[U][COL_U_type] == 'Cold' ):
                U = j
        if U == U_0 and HotUtility.name != '':
            break
        T_max = UD[U][COL_U_Ts]
        if UD[U][COL_U_type] == 'Hot':
            UD[U][COL_U_type] = ''
        else:
            UD[U][COL_U_type] = 'Cold'
        HotUtility.set_name(CutName(UD[U][COL_U_name]))
        HotUtility.set_type('Hot')
        HotUtility.set_t_supply(max(UD[U][COL_U_Ts], UD[U][COL_U_Tt]))
        HotUtility.set_t_target(min(UD[U][COL_U_Ts], UD[U][COL_U_Tt]))
        HotUtility.set_dt_cont(UD[U][COL_U_dTcont])
        HotUtility.set_t_min(HotUtility.t_target)
        HotUtility.set_t_max(HotUtility.t_supply)
        HotUtility.set_t_min_star(HotUtility.t_min - HotUtility.dt_cont)
        HotUtility.set_t_max_star(HotUtility.t_max - HotUtility.dt_cont)

        # Write the correct utility price for the hot utility
        if is_numeric(str(UD[U][COL_U_cost])):
            HotUtility.set_price(UD[U][COL_U_cost])
        else:
            U_cost = UD[U][COL_U_cost]
            for j in range(len(U_cost)):
                if Mid(U_cost, j, 1) == ';' or Mid(U_cost, j, 1) == ',' or Mid(U_cost, j, 1) == ':':
                    break
            HotUtility.price = Left(U_cost, j - 1)
        HotUtility.set_htc(UD[U][COL_U_h])
        total_site.add_central_utility(HotUtility)
        HotUtility = copy.deepcopy(HotUtility)

    T_max = 100000
    U = 0
    for i in range(len(UD)):
        # Find the next cold utility in ascending supply temperature order
        U_0 = U
        for j in range(len(UD)):
            if ( UD[j][COL_U_type] == 'Cold' ) and UD[j][COL_U_Ts] < T_max \
                    and ( UD[U][COL_U_Ts] <= UD[j][COL_U_Ts] or UD[U][COL_U_type] == '' ):
                U = j
        if U == U_0 and ColdUtility.name != '':
            break
        T_max = UD[U][COL_U_Ts]
        UD[U][COL_U_type] = ''

        # Record the next cold utility
        ColdUtility.name = CutName(UD[U][COL_U_name])
        ColdUtility.set_type('Cold')
        ColdUtility.set_t_supply(min(UD[U][COL_U_Ts], UD[U][COL_U_Tt]))
        ColdUtility.set_t_target(max(UD[U][COL_U_Ts], UD[U][COL_U_Tt]))
        ColdUtility.set_dt_cont(UD[U][COL_U_dTcont])
        ColdUtility.set_t_min(ColdUtility.t_supply)
        ColdUtility.set_t_max(ColdUtility.t_target)
        ColdUtility.set_t_min_star(ColdUtility.t_min + ColdUtility.dt_cont)
        ColdUtility.set_t_max_star(ColdUtility.t_max + ColdUtility.dt_cont)

        # Write the correct utility price for the cold utility
        if is_numeric(str(UD[U][COL_U_cost])):
            ColdUtility.set_price(UD[U][COL_U_cost])
        else:
            U_cost = UD[U][COL_U_cost]
            for j in range(len(U_cost)):
                if Mid(U_cost, j, 1) == ';' or Mid(U_cost, j, 1) == ',' or Mid(U_cost, j, 1) == ':':
                    break
            ColdUtility.set_price(Right(U_cost, len(U_cost) - j))
        ColdUtility.set_htc(UD[U][COL_U_h])
        total_site.add_central_utility(ColdUtility)
        ColdUtility = copy.deepcopy(ColdUtility)

    # Record the utility data for each process and site level analyses
    CopyUtilitySets(total_site)

    #Ensures the inlet pressure to the turbine is below the critical pressure
    if params.SETTINGSFORM_TURBINE_WORK_BUTTON == True and params.TURBINEFORM_P_TURBINE_BOX > 220:
        params.TURBINEFORM_P_TURBINE_BOX = 200

#######################################################################################################
# Testing
#######################################################################################################

def test_Extract_SD(total_site):
    i = 0
    for p in total_site.processes:
        i += 1
        p.to_string()

def test_Extract_UD(total_site):
    total_site.to_string()
    i = 0
    for p in total_site.processes:
        i += 1
        p.to_string()

#######################################################################################################
# Helper Functions
#######################################################################################################

def CutName(inputStr):
    pos = InStr(0, inputStr, '(')
    if pos > 0:
        inputStr = CutName(Left(inputStr, pos - 1))
    pos = InStr(0, inputStr, '[')
    if pos > 0:
        inputStr = CutName(Left(inputStr, pos - 1))
    if Left(inputStr, 1) == ' ':
        inputStr = CutName(Right(inputStr, len(inputStr) - 1))
    if Right(inputStr, 1) == ' ':
        inputStr = CutName(Left(inputStr, len(inputStr) - 1))
    return inputStr

def CopyUtilitySets(site):
    for util in site.central_utilities:
        for process in site.processes:
            if util.type == 'Hot':
                process.add_hot_central_utility(copy.deepcopy(util))
            elif util.type == 'Cold':
                process.add_cold_central_utility(copy.deepcopy(util))