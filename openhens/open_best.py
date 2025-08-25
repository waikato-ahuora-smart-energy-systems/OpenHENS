'''
__author__ = 'Keegan Hall and Tim Walmsley'
__credits__ = ['tbc']

Open n-best pkl files from results folder for viewing
'''

import pickle
import matplotlib.pyplot as plt
from pathlib import Path
import sys

# Add OpenHENS project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from openhens.classes import Grid_Diagram

parent_folder = Path(__file__).parent.parent # location of folder that contans the entire package
 
# Open best soln
n_index = 1 # n best soln to return
problem_name = 'Nine-stream-Linnhoff-and-Ahmad-1999-1'
file_to_open = parent_folder / 'examples' / 'results'  / problem_name / '{} best.pkl'.format(n_index)  
best = pickle.load(open(file_to_open,'rb'))
print('{} best from file'.format(n_index), best.name, best.case.TAC)
best.case.verify()

if best.parent.framework == 'ESM': # best soln is ESM
    PDM = best.parent.parent  
    TDM = best.parent  
    PDM_grid = Grid_Diagram(network=PDM.case, non_iso=False, draw_stages=False, comparison_network=best.case) 
    TDM_grid = Grid_Diagram(network=TDM.case, non_iso=False, draw_stages=False, comparison_network=best.case)
elif best.parent.framework == 'TDM':# best soln is TDM (very unlikely)
    PDM = best.parent
else: # best soln is PDM (shouldnt occur)
    pass
 

best_grid = Grid_Diagram(network=best.case, non_iso=True, draw_stages=False, comparison_network=None)  
plt.title(f"{n_index} Best Solution", y=0.95)
best.case.output_to_cmd_line()
plt.show()



