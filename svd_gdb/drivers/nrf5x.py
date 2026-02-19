#!/usr/bin/python3

from . import base
from .. import svd_gdb

import struct

class NRF5xPin(base.Pin):
    def __init__(self, parent, pinnumber, ports):
        port = pinnumber // 32
        self.port = ports[port]

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

class NRF5x(base.Device):
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

    def _add_pins(self, pins=32, ports=[]):
        for pin_number in range(pins):
            pin = NRF5xPin(self, pin_number, ports)
            setattr(self, pin.name, pin)
            self._pins.append(pin)

    @property
    def vdd(self):
        return self._read_adc(None)

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
        self._add_pins(32, [self.P0])

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

        self._add_pins(32, [self.P0])

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
        self._add_pins(32 + 16, [self.P0, self.P1])

class NRF52832(NRF52): pass

class NRF52833(NRF52):
    svd_name = 'nrf52833.svd'

class NRF52820(NRF52):

    svd_name = 'nrf52820.svd'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_pins(32, [self.P0])

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

import re
import time

class SPI_nRF_SPIM:
    """SPI master interface using an nRF SPIM peripheral."""

    CHUNK_SIZE = 4096

    SCRATCH_ADDR = 0x20000000

    CORE_CLOCK = 128_000_000

    def __init__(self, gdb, spim, sck, mosi, miso, csn=None,
                 clock_frequency=None, cpol=0, cpha=0):
        self._gdb = gdb
        self.spim = spim
        self.csn = csn

        spim.ENABLE = 0
        spim.PSEL.SCK = sck.pinnumber
        spim.PSEL.MOSI = mosi.pinnumber
        spim.PSEL.MISO = miso.pinnumber

        if clock_frequency is not None:
            spim.PRESCALER = self.CORE_CLOCK // clock_frequency

        spim.CONFIG = (cpha << 1) | (cpol << 2)

        hw_limit = (1 << spim.DMA.TX.MAXCNT.MAXCNT._bit_width) - 1
        self.CHUNK_SIZE = min(self.CHUNK_SIZE, hw_limit)

        if csn is not None:
            csn.o = 1

    def _xfer_chunk(self, tx_data, rx_len, timeout):
        if tx_data:
            self._gdb.write_mem(self.SCRATCH_ADDR, tx_data)

        self.spim.DMA.TX.PTR = self.SCRATCH_ADDR
        self.spim.DMA.TX.MAXCNT = len(tx_data)
        self.spim.DMA.RX.PTR = self.SCRATCH_ADDR
        self.spim.DMA.RX.MAXCNT = rx_len

        self.spim.ENABLE = 7
        self.spim.EVENTS_END = 0
        self.spim.TASKS_START = 1

        t0 = time.time()
        while not self.spim.EVENTS_END:
            if time.time() > t0 + timeout:
                self.spim.TASKS_STOP = 1
                raise TimeoutError("SPI transaction timed out")

        self.spim.ENABLE = 0
        return self._gdb.read_mem(self.SCRATCH_ADDR, rx_len)

    def xfer(self, tx_data, rx_len=None, timeout=1):
        """SPI transaction. Returns received bytes. Scribbles on start of RAM."""
        if rx_len is None:
            rx_len = len(tx_data)

        if self.csn is not None:
            self.csn.o = 0

        total = max(len(tx_data), rx_len)
        result = b''
        offset = 0
        while offset < total:
            chunk = min(self.CHUNK_SIZE, total - offset)
            tx_chunk = tx_data[offset:offset + chunk]
            rx_chunk = min(chunk, max(0, rx_len - offset))
            result += self._xfer_chunk(tx_chunk, rx_chunk, timeout)
            offset += chunk

        if self.csn is not None:
            self.csn.o = 1

        return result


class NRF54(NRF5x):
    svd_name = 'nrf54l15_application.svd'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert 'nRF54' in self._gdb.target_name

        ns_re = re.compile('GLOBAL_(.*)_NS')
        s_re = re.compile('GLOBAL_(.*)_S')

        # First collect all insecure peripherals
        for att in dir(self):
            m = ns_re.match(att)
            if m:
                setattr(self, m.group(1), getattr(self, att))

        # Override the insecure with secure addresses
        for att in dir(self):
            m = s_re.match(att)
            if m:
                setattr(self, m.group(1), getattr(self, att))

        self._gdb.make_stub.include_path = [
            self.sdk+'/modules/nrfx/templates/nrf54/'
        ] + self._gdb.make_stub.include_path

        self._gdb.make_stub.includes += ['<nrf54.h>', '<nrf54_bitfields.h>']
        self._gdb.make_stub.defines += ['NRF54']

        self._add_pins(32+32+32, [self.P0,
                                  self.P1,
                                  self.P2])

    # AIN pin mapping for nRF54L15 (QFN48)
    # All AIN pins are on Port 1
    _analog_pin_map = {None: None,  # VDD
                       36: 0,   # P1.04 -> AIN0
                       37: 1,   # P1.05 -> AIN1
                       38: 2,   # P1.06 -> AIN2
                       39: 3,   # P1.07 -> AIN3
                       43: 4,   # P1.11 -> AIN4
                       44: 5,   # P1.12 -> AIN5
                       45: 6,   # P1.13 -> AIN6
                       46: 7}   # P1.14 -> AIN7

    def _read_adc(self, pin):
        return self._read_saadc_se(pin)

    def _read_saadc_se(self, pin=None, setup=True):
        """pin is the Px.yy number (e.g. 36 for P1.04), not the AIN number.
        scribbles over start of RAM.

        returns reading in V, floating-point
        """

        RESULT_ADDRESS = 0x20000000
        if setup:
            self.SAADC.RESOLUTION = 2 # 12 bits
            self.SAADC.OVERSAMPLE = 0 # disabled
            self.SAADC.ENABLE = 1

            # GAIN=2/8(7), REFSEL=0(internal 0.9V), MODE=0(SE),
            # TACQ=79 -> (79+1)*125ns = 10us
            self.SAADC.CH[0].CONFIG = (79 << 16) | (7 << 8)
            self.SAADC.CH[0].PSELN = 0 # not connected
            if pin is None:
                # VDD: CONNECT=Internal(2), INTERNAL=Vdd(2)
                self.SAADC.CH[0].PSELP = (2 << 30) | (2 << 12)
            else:
                port = pin // 32
                p = pin & 31
                # CONNECT=AnalogInput(1), PORT, PIN
                self.SAADC.CH[0].PSELP = (1 << 30) | (port << 8) | p

            self._gdb.write32(RESULT_ADDRESS, 0)
            self.SAADC.RESULT.PTR = RESULT_ADDRESS
            self.SAADC.RESULT.MAXCNT = 2 # bytes (1 sample = 2 bytes)
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
        ref = 0.9
        gain = 2/8
        res = 1<<12

        return value * ref / (gain * res)

    def spi(self, spim, sck, mosi, miso, csn=None,
            clock_frequency=None, cpol=0, cpha=0):
        """Return an SPI instance for the given SPIM peripheral and pins."""
        return SPI_nRF_SPIM(self._gdb, spim, sck, mosi, miso, csn,
                            clock_frequency, cpol, cpha)


if __name__=="__main__":
    pass
