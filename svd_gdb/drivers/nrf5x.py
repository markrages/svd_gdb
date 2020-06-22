#!/usr/bin/python3

from . import base
from .. import svd_gdb

class NRF5xPin(base.Pin):
    def __init__(self, parent, pinnumber):
        if pinnumber > 31:
            port = 1
            self.port = parent.P1
        else:
            port = 0
            self.port = parent.P0
        self.pinnummber = pinnumber
        self.pin = pinnumber & 31 # pin within port
        self.pinmask = 1<<self.pin

        self.name = "P%d_%d"%(port, self.pin)

    @property
    def i(self):
        "Reads digital input latch, in [0, 1]"
        self.port.DIRCLR = self.pinmask
        self.port.PIN_CNF[self.pin].INPUT = 0 # Not default!
        return int(bool(self.port.IN & self.pinmask))

    @property
    def o(self):
        "Reads digital output latch, in [0, 1]"
        return int(bool(self.port.OUT & self.pinmask))

    @o.setter
    def o(self, val):
        "Sets digital output latch to val"
        self.port.DIRSET = self.pinmask
        if (val):
            self.port.OUTSET = self.pinmask
        else:
            self.port.OUTCLR = self.pinmask

    @property
    def pull(self):
        "Returns selected pullup, in [None, 'h', 'l']"
        return [None, 'l', NotImplemented, 'h'][self.port.PIN_CNF[self.pin].PULL]

    @pull.setter
    def pull(self, v):
        "Sets selected pullup, in [None, 'h', 'l']"
        self.port.PIN_CNF[self.pin].PULL = {None: 0,
                                            'l': 1,
                                            'h': 3}[v]

    def __repr__(self):
        return self.name

class NRF5x(svd_gdb.Device):
    sdk = "/opt/nRF5_SDK_15.3.0/"
    mfgr_name = 'Nordic'
    svd_name = '' # override me

    def __init__(self, target=None):
        svd_filename = base.cmsis_svd_file(self.mfgr_name, self.svd_name)
        gdb_int = svd_gdb.GdbInterface(target)
        super().__init__(svd_filename, gdb_int)

        self._gdb.make_stub.include_path += [
            self.sdk+'/CMSIS/Include',
            self.sdk+'/modules/nrfx/mdk/',
            self.sdk+'/modules/nrfx/hal/',
            self.sdk+'/modules/nrfx/',
            self.sdk+'/integration/nrfx/',
            self.sdk+'/components/libraries/util/',
            self.sdk+'/components/drivers_nrf/nrf_soc_nosd/',
            self.sdk+'/components/toolchain/',
            self.sdk+'/components/toolchain/gcc',
            self.sdk+'/components/toolchain/cmsis/include'
        ]

    def _add_pins(self, pins=32):

        for pin_number in range(pins):
            pin = NRF5xPin(self, pin_number)
            setattr(self, pin.name, pin)
            self._pins.append(pin)

class NRF51(NRF5x):
    svd_name = 'nrf51.svd'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert 'nRF51' in self._gdb.target_name

        self._gdb.make_stub.include_path = [
            self.sdk+'/modules/nrfx/templates/nRF51/'
        ] + self._gdb.make_stub.include_path

        self._gdb.make_stub.includes += ['<nrf51.h>', '<nrf51_bitfields.h>']
        self._gdb.make_stub.defines += ['NRF51']

        self.P0 = self.GPIO # compatibility name
        self._add_pins(32)

class NRF52(NRF5x):
    svd_name = 'nrf52.svd'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert 'nRF52' in self._gdb.target_name

        self._gdb.make_stub.include_path = [
            self.sdk+'/modules/nrfx/templates/nrf52/'
        ] + self._gdb.make_stub.include_path

        self._gdb.make_stub.includes += ['<nrf52.h>', '<nrf52_bitfields.h>']
        self._gdb.make_stub.defines += ['NRF52']

        self._add_pins(32)

if __name__=="__main__":
    pass
