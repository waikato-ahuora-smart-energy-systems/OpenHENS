__author__ = ''

class Stream:
    """Represents a process stream.
    flow_supply: The endpoint of this stream
    flow_target: The startpoint of this stream
    process: The process this stream is a part of
    """
    def __init__(self, name=''):
        self.name = name
        self.flow_supply = None
        self.flow_target = None
        self.process = None
        self.t_supply = None
        self.t_target = None
        self.heat_flow = None
        self.dt_cont = None
        self.htc = None
        self.t_min = None
        self.t_max = None
        self.t_min_star = None
        self.t_max_star = None
        self.CP = None
        self.RCP_prod = None

    def set_name(self, name):
        self.name = name

    def set_flow_supply(self, flow_supply):
        self.flow_supply = flow_supply

    def set_flow_target(self, flow_target):
        self.flow_target = flow_target

    def set_process(self, process):
        self.process = process

    def set_t_supply(self, t_supply):
        self.t_supply = t_supply

    def set_t_target(self, t_target):
        self.t_target = t_target

    def set_heat_flow(self, heat_flow):
        self.heat_flow = heat_flow

    def set_dt_cont(self, dt_cont):
        self.dt_cont = dt_cont

    def set_htc(self, htc):
        self.htc = htc

    def set_t_min(self, t_min):
        self.t_min = t_min

    def set_t_max(self, t_max):
        self.t_max = t_max

    def set_t_min_star(self, t_min_star):
        self.t_min_star = t_min_star

    def set_t_max_star(self, t_max_star):
        self.t_max_star = t_max_star

    def set_CP(self, CP):
        self.CP = CP

    def set_RCP_prod(self, RCP_prod):
        self.RCP_prod = RCP_prod

    def to_string(self):
        print('Stream:\n  name: ', self.name, '\n  flow_supply: ', self.flow_supply, '\n  flow_target:', self.flow_target, '\n  process:', self.process, \
            '\n  t_supply: ', self.t_supply, '\n  t_target: ', self.t_target, '\n  heat_flow: ', self.heat_flow, '\n  dt_cont: ', self.dt_cont, \
                '\n  htc: ', self.htc, '\n  t_min: ', self.t_min, '\n  t_max: ', self.t_max, '\n  t_min_star: ', self.t_min_star, \
                    '\n  t_max_star: ', self.t_max_star, '\n  CP: ', self.CP, '\n  RCP_prod: ', self.RCP_prod, '\n}')