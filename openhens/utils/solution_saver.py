import pickle


def save_pickle(save_path, soln_list, name):
    # Save solution to pickle
    i=1 # start ranking as 1=best 2=next best
    for P_i in soln_list: # iterate across each best soln
        file_to_save = save_path / f'{i} {name}.pkl'
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