import pickle


def open_pickle(load_path, name):
    # Load solution from pickle 
    i=1
    pickle_list = []
    while True:
        file_to_open = load_path / f'{i} {name}.pkl'
        try:
            with open(file_to_open, 'rb') as file:
                P_i = pickle.load(file)
                pickle_list.append(P_i)
        except FileNotFoundError:
            break
        i +=1
    return pickle_list
    