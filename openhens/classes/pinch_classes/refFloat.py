__author__ = 'Alex Geary'

"""Class used to create floats that can be passed by reference.
"""

class RefFloat:
    def __init__(self, value):
        self.value = value

    def set_value(self, value):
        self.value = value