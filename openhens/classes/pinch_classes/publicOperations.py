__author__ = ''

import random, math
import numpy as np
from . import parameters as params

total_site = None

# General constants/limits
MAX_ROWS = 10000
MAX_STREAMS = 500
MAX_UTILITIES = 40
MAX_ZONES = 200
MAX_PT_COL = 2000

# Names
TLI_NAME = 'Thermodynamic Limit'
TIT_NAME = 'Total Integrated Target'
TZT_NAME = 'Total Process Target'
CTS_NAME = 'Conventional Total Site Target'
UTS_NAME = 'Unified Total Site Target'
RET_NAME = 'Process Retrofit Target'

CD_SHEET = 'Derivatives'

# Summary data columns
ROW_S_0 = 5

# Stream data (array) columns
COL_SD_zone = 0
COL_SD_steam = 1
COL_SD_Tmin = 2
COL_SD_Tmax = 3
COL_SD_Tmin_star = 4
COL_SD_Tmax_star = 5
COL_SD_CP_hot = 6
COL_SD_CP_cold = 7
COL_SD_r_CP_hot = 8
COL_SD_r_CP_cold = 9

# Utility data (array) columns
COL_U_name = 0
COL_U_type = 1
COL_U_Ts = 2
COL_U_Tt = 3
COL_U_dTcont = 4
COL_U_cost = 5
COL_U_h = 6
COL_U_CP1 = 7
COL_U_Q = 8
COL_U_UC = 9

# Problem table columns
ROW_1 = 6
COL_PT_ST = 1
COL_PT_SCC = 1

COL_PT_RT = 18
COL_PT_CC = 18

COL_PT_MGCC = 13
COL_PT_ExGCC = 14
COL_PT_ActGCC = 15
COL_PT_UtGCC = 16
COL_PT_BCC = 30
COL_PT_XGCC = 35

COL_PT_TSP = 38
COL_PT_TSUP0 = 50
COL_PT_TSUP1 = 62
COL_PT_TIUP0 = 74
COL_PT_TIUP1 = 86

COL_PT_AdvT = 98

# Reference states
C_to_K = 273.15 # degrees
ZERO = 0.00001
T_CRIT = 373.9 # C
P_CRIT = 220.6 # bar

# Heat exchanger types
CF = 'Counter Flow'
PF = 'Parallel Flow'
CrFUU = 'Crossflow - Both Unmixed'
CrFMM = 'Crossflow - Both Mixed'
CrFMUmax = 'Crossflow - Cmax Unmixed'
CrFMUmin = 'Crossflow - Cmin Unmixed'
ShellTube = '1-n Shell and Tube'
CondEvap = 'Condensing or Evaporating'

PRINT_SUMMARY = True

# From HENART file in vba
COUNTER_MAX = 100000

"""Functions -----------------------------------------------------------------------------------------------------------------------
"""
def Annual_Factor(i, n):
    """Calculate annualisation factor.
    """
    return i * (1 + i) ** (n) / ((1 + i) ** (n) - 1)

def Calc_ExergeticT(T_C, T_ref=None, Units='C'):
    """Calculate exergetic temperatures.
    """
    # Marmolejo-Correa, D., Gundersen, T., 2013. New Graphical Representation of Exergy Applied to Low Temperature Process Design. 
    # Industrial & Engineering Chemistry Research 52, 7145–7156. https://doi.org/10.1021/ie302541e
    T_amb = params.DEFAULTFORM_TEMP_REF + C_to_K if T_ref == None else T_ref + C_to_K
    T_K = T_C + C_to_K if Units == 'C' else 0
    return T_amb * (T_K / T_amb - 1 - math.log(T_K / T_amb))

def Add_GCC_T_int(InputGCC, T0, i_0):
    """Adds a temperature interval to a GCC.
    """
    for row in InputGCC:
        row.append(None)

    for i in range(len(InputGCC[0]) - 1, i_0, -1):
        InputGCC[0][i] = InputGCC[0][i - 1]
        InputGCC[1][i] = InputGCC[1][i - 1]
    i = i_0
    InputGCC[0][i] = T0
    InputGCC[1][i] = Inter_Val(T0, InputGCC[0][i - 1], InputGCC[0][i + 1], InputGCC[1][i - 1], InputGCC[1][i + 1])

def Add_PT_Tint(PT, New_T, i):
    """Adds a temperature interval to a PT.
    """
    for row in PT:
        row.append(None)

    for j in range(11):
        for k in range(len(PT[0]) - 1, i, -1):
            PT[j][k] = PT[j][k - 1]
        PT[j][i] = ''

    PT[0][i] = New_T
    PT[1][i] = PT[0][i - 1] - PT[0][i]
    PT[1][i + 1] = PT[0][i] - PT[0][i + 1]
    
    PT[2][i] = PT[2][i + 1]
    PT[3][i] = PT[3][i + 1]
    PT[4][i] = Inter_Val(PT[0][i], PT[0][i + 1], PT[0][i - 1], PT[4][i + 1], PT[4][i - 1])
    
    PT[5][i] = PT[5][i + 1]
    PT[6][i] = PT[6][i + 1]
    PT[7][i] = Inter_Val(PT[0][i], PT[0][i + 1], PT[0][i - 1], PT[7][i + 1], PT[7][i - 1])
    
    PT[8][i] = PT[2][i] - PT[5][i]
    PT[9][i] = PT[1][i] * PT[8][i]
    PT[9][i + 1] = PT[1][i + 1] * PT[8][i + 1]
    PT[10][i] = Inter_Val(PT[0][i], PT[0][i + 1], PT[0][i - 1], PT[10][i + 1], PT[10][i - 1])

def Add_PT_ConstH(CC_PT, Col_T, Col_HCC, Col_CCC, DFP=False):
    # TODO: Test this function is correct
    """Adds a temperature interval to the PT based on a constant h values.
    """
    # HCC to CCC projection of constant H
    k = 0
    for i in range(1, len(CC_PT[0]) - 1):
        if CC_PT[Col_HCC][i] > CC_PT[Col_HCC][i + 1] + ZERO:
            break
    
    while i < len(CC_PT[0]) and k < 2:
        h_0 = CC_PT[Col_HCC][i]
        for j in range(len(CC_PT[0]) - 1, 0, -1):
            if abs(h_0 - CC_PT[Col_CCC][j]) < ZERO:
                k += 1
                break
            if h_0 < CC_PT[Col_CCC][j - 1] - ZERO and h_0 > CC_PT[Col_CCC][j] + ZERO:
                j_0 = j
                T_C = Inter_Val(h_0, CC_PT[Col_CCC][j], CC_PT[Col_CCC][j - 1], CC_PT[Col_T][j], CC_PT[Col_T][j - 1])
                Add_PT_Tint(CC_PT, T_C, j_0)
                k += 1
                break
        i = j

    # CCC to HCC projection of constant H
    k = 0
    for i in range(len(CC_PT[0]) - 1, 0, -1):
        if CC_PT[Col_CCC][i - 1] > CC_PT[Col_CCC][i] + ZERO:
            break

    while i > 1 and k < 2:
        h_0 = CC_PT(Col_CCC, i)
        for j in range(1, len(CC_PT[0]) - 1):
            if abs(CC_PT(Col_HCC, j) - h_0) < ZERO:
                k += 1
                break
            if h_0 < CC_PT[Col_HCC][j] - ZERO and h_0 > CC_PT[Col_HCC][j + 1] + ZERO:
                j_0 = j + 1
                T_C = Inter_Val(h_0, CC_PT[Col_HCC][j], CC_PT[Col_HCC][j + 1], CC_PT[Col_T][j], CC_PT[Col_T][j + 1])
                Add_PT_Tint(CC_PT, T_C, j_0)
                k += 1
                break
        i = j

def Calc_CapitalCost(HEN_area, n):
    """Returns a capital cost estimate for a heat exchanger (or HEN).
    """
    a = params.COSTING_OPTIONSFORM_FC
    b = params.COSTING_OPTIONSFORM_VC
    c = params.COSTING_OPTIONSFORM_EXP
    i = params.COSTING_OPTIONSFORM_DISCOUNT_RATE
    years = params.COSTING_OPTIONSFORM_SERV_LIFE
    if n > 0:
        capital = n * (a + b * (HEN_area / n) ** c)
        factor = i * (1 + i) ** years / ((1 + i) ** years - 1)
        return capital * factor
    else:
        return -1

def OrganiseArray(inputArray, num_dim=2, reverse=True):
    """Organises a list of temperatures that form the intervals for a PT.
    """
    if num_dim == 2:
        inputArray[0] = list(filter((None).__ne__, inputArray[0]))
        QuickSort_2D(inputArray)
        RemoveDuplicates_2D(inputArray)
        if reverse:
            ReverseArray_2D(inputArray)
    else:
        inputArray = list(filter((None).__ne__, inputArray))
        QuickSort_1D(inputArray)
        inputArray = RemoveDuplicates_1D(inputArray)
        if reverse:
            ReverseArray_1D(inputArray)

    return inputArray


def ReverseArray_1D(inputArray):
    inputArray.reverse()

def ReverseArray_2D(inputArray):
    for row in inputArray:
        row.reverse()

def RemoveDuplicates_1D(inputArray, text_compare=False):
    """Returns a 1D array after removing duplicates.
    """
    j = 0
    if text_compare:
        for i in range(1, len(inputArray)):
            if inputArray[j] != inputArray[i]:
                j += 1
                inputArray[j] = inputArray[i]
    else:
        for i in range(1, len(inputArray)):
            if abs(inputArray[j] - inputArray[i]) > ZERO:
                j += 1
                inputArray[j] = inputArray[i]
    return inputArray[:j + 1]

def RemoveDuplicates_2D(inputArray):
    """Returns a 2D array after removing adjacent duplicates from col = 1 only.
    Moves all values beyond a duplicate closer to start of array then cuts off end of array.
    All other rows are sliced to match the size of the 1st row.
    """
    initial_length = len(inputArray[0])
    
    res = []
    [res.append(x) for x in inputArray[0] if x not in res]
    inputArray[0] = res

    amount_removed = initial_length - len(inputArray[0])
    if amount_removed > 0:
        for i in range(1, len(inputArray)):
            inputArray[i] = inputArray[i][:-amount_removed]

def QuickSort_1D(pvarArray, plngLeft=0, plngRight=0):
    """Returns a sorted list for 1D -- MedianThreeQuickSort1.
    """
    # Omit plngLeft & plngRight; they are used internally during recursion
    if plngRight == 0:
        plngLeft = 0 # LBound(pvarArray)
        plngRight = len(pvarArray) - 1

    lngFirst = plngLeft
    lngLast = plngRight
    lngIndex = plngRight - plngLeft + 1
    a = int(lngIndex * random.random()) + plngLeft
    b = int(lngIndex * random.random()) + plngLeft
    c = int(lngIndex * random.random()) + plngLeft
    if pvarArray[a] <= pvarArray[b] and pvarArray[b] <= pvarArray[c]:
        lngIndex = b
    else:
        if pvarArray[b] <= pvarArray[a] and pvarArray[a] <= pvarArray[c]:
            lngIndex = a
        else:
            lngIndex = c
    varMid = pvarArray[lngIndex]
    while True:
        while pvarArray[lngFirst] < varMid and lngFirst < plngRight:
            lngFirst += 1
        while varMid < pvarArray[lngLast] and lngLast > plngLeft:
            lngLast -= 1
        if lngFirst <= lngLast:
            varSwap = pvarArray[lngFirst]
            pvarArray[lngFirst] = pvarArray[lngLast]
            pvarArray[lngLast] = varSwap
            lngFirst += 1
            lngLast -= 1
        if lngFirst > lngLast:
            break
    if lngLast - plngLeft < plngRight - lngFirst:
        if plngLeft < lngLast:
            QuickSort_1D(pvarArray, plngLeft, lngLast)
        if lngFirst < plngRight:
            QuickSort_1D(pvarArray, lngFirst, plngRight)
    else:
        if lngFirst < plngRight:
            QuickSort_1D(pvarArray, lngFirst, plngRight)
        if plngLeft < lngLast:
            QuickSort_1D(pvarArray, plngLeft, lngLast)

def QuickSort_2D(pvarArray, Index1=0, plngLeft=0, plngRight=0):
    """Returns a sorted list for 2D --- MedianThreeQuickSort1.
    The order of the 1st row determines the order of the remaining rows.
    """
    # Alternative that may work! Need to check for all cases of input data
    # for row in pvarArray:
    #     row.sort()

    #Omit plngLeft & plngRight; they are used internally during recursion
    if plngRight == 0:
        plngLeft = 0
        plngRight = len(pvarArray[0]) - 1

    lngFirst = plngLeft
    lngLast = plngRight
    lngIndex = plngRight - plngLeft + 1
    a = int(lngIndex * random.random()) + plngLeft
    b = int(lngIndex * random.random()) + plngLeft
    c = int(lngIndex * random.random()) + plngLeft

    if pvarArray[Index1][a] <= pvarArray[Index1][b] and pvarArray[Index1][b] <= pvarArray[Index1][c]:
        lngIndex = b
    else:
        if pvarArray[Index1][b] <= pvarArray[Index1][a] and pvarArray[Index1][a] <= pvarArray[Index1][c]:
            lngIndex = a
        else:
            lngIndex = c

    varMid = pvarArray[Index1][lngIndex]
    while 1:
        while pvarArray[Index1][lngFirst] < varMid and lngFirst < plngRight:
            lngFirst = lngFirst + 1
        while varMid < pvarArray[Index1][lngLast] and lngLast > plngLeft:
            lngLast = lngLast - 1

        if lngFirst <= lngLast:
            for i in range(len(pvarArray)):
                varSwap = pvarArray[i][lngFirst]
                pvarArray[i][lngFirst] = pvarArray[i][lngLast]
                pvarArray[i][lngLast] = varSwap
            lngFirst = lngFirst + 1
            lngLast = lngLast - 1
        if lngFirst > lngLast:
            break

    if ( lngLast - plngLeft )  <  ( plngRight - lngFirst ) :
        if plngLeft < lngLast:
            QuickSort_2D(pvarArray, Index1, plngLeft, lngLast)
        if lngFirst < plngRight:
            QuickSort_2D(pvarArray, Index1, lngFirst, plngRight)
    else:
        if lngFirst < plngRight:
            QuickSort_2D(pvarArray, Index1, lngFirst, plngRight)
        if plngLeft < lngLast:
            QuickSort_2D(pvarArray, Index1, plngLeft, lngLast)

def Sum_Inbetweens_2D(inputArray, Col_minT, Col_maxT, Col_mcp, lower_T, upper_T):
    """Sums all values in a range that are inbetween two values.
    """
    total = 0
    for i in range(len(inputArray[0])):
        if upper_T - inputArray[Col_maxT][i] <= ZERO and inputArray[Col_maxT][i] > lower_T and inputArray[Col_minT][i] - lower_T <= ZERO:
            total += inputArray[Col_mcp][i]
    return total

def Find_LMTD(T_h1, T_h2, T_c1, T_c2):
    """Returns the log mean temperature difference.
    """
    dT_1 = T_h1 - T_c1
    dT_2 = T_h2 - T_c2
    if dT_1 == dT_2 or dT_2 <= 0 or dT_1 <= 0:
        return (abs(dT_1) + abs(dT_2)) / 2
    else:
        return (dT_1 - dT_2) / math.log(dT_1 / dT_2)

def Inter_Val(x, X1, X2, Y1, Y2):
    """Returns linear interpolation.
    """
    if X1 != X2:
        m = (Y1 - Y2) / (X1 - X2)
        c = Y1 - m * X1
        return m * x + c
    else:
        return 0

def Extract_Zone_Names(Stream_Data, Zone_Names):
    """Returns the names of all the zones.
    """
    Zone_Names = Zone_Names[:1000]
    j = 0
    Zone_Names[j] = TIT_NAME if params.SETTINGSFORM_TIT_BUTTON_SELECTED else Stream_Data[COL_SD_zone][j]
    for i in range(len(Stream_Data[0])):
        if Zone_Names[j] != Stream_Data[COL_SD_zone][i]:
            j += 1
            Zone_Names[j] = Stream_Data[COL_SD_zone][i]
    Zone_Names = Zone_Names[:j]
    if j == 1 and params.SETTINGSFORM_TIT_BUTTON_SELECTED:
        Zone_Names[0] = Zone_Names[1]
        Zone_Names = Zone_Names[0]
        params.SETTINGSFORM_TS_BUTTON_SELECTED = False
    return Zone_Names

def Interpolate(x, x0, y0):
    """Interpolate based on two ranges.
    """
    # Check that rows are same size'
    if (x0.cells.count != y0.cells.count):
        print('X and Y vector to interpolate command has to be same size!')
    
    n = x0.cells.count
    
    # 'Check that x0 are increasing'
    for i in range(0, n - 1):
        j = x0(i).Value
        k = x0(i + 1).Value
        if j > k:
            print('X vector to interpolate command has to be increasing!')
            return
    
    # 'Check if x<x0(1)'
    if x < x0(1).Value:
        k = (y0(2).Value - y0(1).Value) / (x0(2).Value - x0(1).Value)
        return y0(1).Value + (x - x0(1).Value) * k
    # 'Check if X0>x0(END)'
    elif x > x0(n).Value:
        k = (y0(n).Value - y0(n - 1).Value) / (x0(n).Value - x0(n - 1).Value)
        return y0(n).Value + (x - x0(n).Value) * k
    else:
        # 'Loop through values and find where the value are'
        for i in range(n):
            if x <= x0(i).Value:
                if (x0(i).Value - x0(i - 1).Value) != 0:
                    k = (y0(i).Value - y0(i - 1).Value) / (x0(i).Value - x0(i - 1).Value)
                    return y0(i).Value + (x - x0(i).Value) * k
                else:
                    return y0(i).Value + x0(i).Value
                break

def Transpose_Array(array, Trans, col_start, col_end, row_start, row_end):
    array = array[col_start:col_end]
    for row in array:
        row = row[row_start:row_end]
    transposed_array = np.array(array).T.tolist()
    return transposed_array

def is_numeric(string):
    try:
        float(string)
        return True
    except ValueError:
        return False

def center_window(window, window_width, window_height):
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    x = int((screen_width / 2) - (window_width / 2))
    y = int((screen_height / 2) - (window_height / 2))

    window.geometry("{}x{}+{}+{}".format(window_width, window_height, x, y))

def print_line(line, filename):
    f = open(filename, 'a')
    if line == 'None':
        f.write('None')
    else:
        if type(line) is float:
            line = round(line, 5)
            if line == int(line):
                line = int(line)
        f.write(str(line))
    f.write('\n')
    f.close()

def print_1D_array(output_array, filename):
    f = open(filename, 'a')

    for i in range(len(output_array)):
        val = output_array[i]
        if val == None:
            f.write('None')
        else:
            if type(val) is float:
                val = round(val, 5)
                if val == int(val):
                    val = int(val)
            f.write(str(val))
        if i < len(output_array) - 1:
            f.write(';')
    f.write('\n')
    f.close()

def print_2D_array(output_array, filename):
    f = open(filename, 'a')

    for i in range(len(output_array)):
        for j in range(len(output_array[0])):
            val = output_array[i][j]
            if val == None:
                f.write('None')
            else:
                if type(val) is float:
                    val = round(val, 5)
                    if val == int(val):
                        val = int(val)
                f.write(str(val))
            if j < len(output_array[0]) - 1:
                f.write(';')
        f.write('\n')
    f.close()

def print_3D_array(output_array, filename):
    f = open(filename, 'a')

    for i in range(len(output_array)):
        for j in range(len(output_array[0])):
            for k in range(len(output_array[0][0])):
                val = output_array[i][j][k]
                if val == None:
                    f.write('None')
                else:
                    if type(val) is float:
                        val = round(val, 5)
                        if val == int(val):
                            val = int(val)
                    f.write(str(val))
                if k < len(output_array[0][0]) - 1:
                    f.write(';')
            f.write('\n')
    f.close()
