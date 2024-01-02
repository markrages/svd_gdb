#!/usr/bin/python3

class Pin():
    "ABC for microprocessor pins"

    @property
    def v(self):
        "Return voltage (for ADC-capable pins). Floating-point."
        return NotImplemented

    @property
    def i(self):
        "Reads digital input, in [0, 1]"
        return NotImplemented

    @property
    def o(self):
        "Reads digital output latch, in [0, 1]"
        return NotImplemented

    @o.setter
    def o(self, val):
        "Sets digital output latch to val"
        raise Exception(NotImplemented)

    @property
    def pull(self):
        "Returns selected pullup, in [None, 'h', 'l']"
        return NotImplemented

    @pull.setter
    def pull(self, updown):
        "Sets pullup/down, one of [None, 'h', 'l'].  Sets to input"
        raise Exception(NotImplemented)

    @property
    def hiz(self):
        """For digital pin, uses pullups to guess if it's connected to a
        high-impedance"""
        d = []
        psave = self.pull
        self.pull = 'h'; d.append(self.i)
        self.pull = 'l'; d.append(self.i)
        self.pull = psave
        return d == [1, 0]

class Accel():
    name = "unknwon accelerometer"

    def read(self):
        """ Returns scaled acceleration, raw temperature """
        raise Exception('subclass me')

from svd_gdb.github_dl import cached

def cmsis_svd_file(vendor, filename):
    return cached.fetch("/".join(['data',vendor,filename]))
