from openhens import OpenHENS
import logging
from openhens.classes import Grid_Diagram
import matplotlib
import matplotlib.pyplot as plt
from wakepy import keep
matplotlib.use('TkAgg') 

if __name__ == '__main__':
  
    problem_name = 'Four-stream-Yee-and-Grossmann-1990-1'
    options = { 'input_folder': f'examples/cases/{problem_name}.csv', # File path to the stream data CSV
                'output_folder': f'examples/results/{problem_name}', # File path to results folder where outputs will be saved
                'min_dT_list': [2, 4, 6, 8, 10, 12, 14, 16, 18, 20,], # List of Δ𝑇min values that define distinct PDM instances
                'min_dqda_list': [0.5, 0.9, 1.3, 1.7, 2.1, 2.4, 2.8, 3.2, 3.6, 4.0], # List of (𝑑𝑄𝑑𝐴)min values that define distinct TDM instances for each PDM
                'stage_selection': 'automated', # Selection of stages. 'automated' will automatically determine stages, manual overide [stages in above pinch PDM, stages in below pinch PDM]
                'tolerance': 1e-3, # Numerical convergence tolerance
                'max_parallel': 10, # Number of models to solve in parallel (should be ≤ CPU cores)
                'best_solns_to_save': 10, # Number of N-best ESM solutions to retain
                'log_level': logging.WARNING, # Logging level for controlling screen output
               } 
   
    with keep.running(): 
        model = OpenHENS(**options) 
        
        model.solve()
        
        # Display results
        model.display_run_metrics()
        model.display_best_from_run()
        model.display_n_best_from_file()  
    
    for soln in model._best_solns:
        soln.get_grid_diagram() 
        print(f"Case {soln.name} TAC: {soln.case.TAC} Time: {soln.case.solve_time:.2f} seconds")
        
    plt.show()
 