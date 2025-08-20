__author__ = ''

from abc import ABC, abstractmethod

class Zone(ABC):
    """Abstract class represents a process/utility that contains multiple unit operations.
    unit_ops: List of unit operations that are used within this zone
    """
    @abstractmethod
    def __init__(self, name):
        self.name = name
        self.unit_ops = []

    @abstractmethod
    def set_name(self, name):
        self.name = name

    @abstractmethod
    def add_unit_op(self, unit_op):
        self.unit_ops.append(unit_op)