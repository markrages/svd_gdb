#!/usr/bin/python3

from . import base
from .. import svd_gdb

import struct

class NRF5xPin(base.Pin):
    def __init__(self, parent, pinnumber):
        if pinnumber > 31:
            port = 1
            self.port = parent.P1
        else:
            port = 0
            self.port = parent.P0
        self.pinnumber = pinnumber
        self.pin = pinnumber & 31 # pin within port
        self.pinmask = 1<<self.pin
        self.parent = parent

        self.name = "P%d_%02d"%(port, self.pin)

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

    @property
    def v(self):
        if self.pinnumber in self.parent._analog_pin_map:
            return self.parent._read_adc(self.pinnumber)
        else:
            return NotImplemented

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

    _analog_pin_map = {None:None,
                       2:0,
                       3:1,
                       4:2,
                       5:3,
                       28:4,
                       29:5,
                       30:6,
                       31:7}

    def _read_adc(self, pin):
        return self._read_saadc_se(pin)

    def _read_saadc_se(self, pin=None, setup=True):
        """pin is the P0.xx number, not the ain number.
        scribbles over start of RAM.

        returns reading in V, floating-point
        """

        ain = self._analog_pin_map[pin]

        RESULT_ADDRESS = 0x20000000
        if setup:
            self.SAADC.RESOLUTION = 2 # 12 bits
            self.SAADC.OVERSAMPLE = 0 # disabled
            self.SAADC.ENABLE = 1

            self.SAADC.CH[0].CONFIG = 0x00020000 # 10us, single-ended, no resistor, internal ref
            self.SAADC.CH[0].PSELN = 0 # not connected
            if ain is None:
                self.SAADC.CH[0].PSELP = 9
            else:
                self.SAADC.CH[0].PSELP = ain + 1

            self._gdb.write32(RESULT_ADDRESS, 0)
            self.SAADC.RESULT.PTR = RESULT_ADDRESS
            self.SAADC.RESULT.MAXCNT = 1
            self.SAADC.EVENTS_CALIBRATEDONE = 0
            self.SAADC.TASKS_CALIBRATEOFFSET = 1

            while not self.SAADC.EVENTS_CALIBRATEDONE:
                pass

        self.SAADC.EVENTS_END = 0
        self.SAADC.TASKS_START = 1
        self.SAADC.TASKS_SAMPLE = 1
        while not self.SAADC.EVENTS_END:
            pass

        value, = struct.unpack('<h', self._gdb.read_mem(RESULT_ADDRESS, 2))
        ref = 0.6
        gain = 1/6
        res = 1<<12

        return value * ref / (gain * res)

class NRF51822(NRF51):
    pass
    
class NRF52840(NRF52):
    svd_name = 'nrf52840.svd'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_pins(32 + 16)

class NRF52832(NRF52): pass

class NRF52833(NRF52):
    svd_name = 'nrf52833.svd'

class NRF52820(NRF52):

    svd_name = 'nrf52820.svd'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_pins(32)

    _analog_pin_map = {None:None,
                       2:0,
                       3:1,
                       4:2,
                       5:3}

    def _read_adc(self, pin):
        "Reads volts in 0..2.4 V"
        counts = self._read_comp_se(pin, ref=2)
        return (counts + 0.5) * 2.4 / 64

    def _read_comp_se(self, pin=7, ref=0):
        """Uses the comparator and reference divider as a 6-bit SAR ADC.

        In the block diagram in
        https://en.wikipedia.org/wiki/Successive-approximation_ADC,
        the "DAC" and "Comparator" blocks are supplied by hardware,
        and this function supplies the "SAR" block.

        pin 7 is VDDH/5
        ref = 0 for 1.2v, 1 for 1.8, 2 for 2.4

        """

        c = self.COMP

        # start init

        c.REFSEL = ref

        c.MODE.MAIN = 0
        c.MODE.SP = 1 # 1=normal, 2=fast
        c.HYST = 0

        c.SHORTS = 0
        c.INTEN = 0
        c.PSEL = pin

        c.ENABLE = 2

        # end of init

        bit = 32
        c.TH = 0
        while bit:

            #c.TASKS_STOP = 1
            last_th = int(c.TH)

            mask = 0x101 * bit
            c.TH = last_th | mask

            #c.EVENTS_READY = 0
            #c.TASKS_START = 1
            #while c.EVENTS_READY == 0:
            #    pass
            c.TASKS_SAMPLE = 1

            if not c.RESULT:
                c.TH = last_th

            bit >>= 1

        return c.TH & 63


if __name__=="__main__":
    pass
