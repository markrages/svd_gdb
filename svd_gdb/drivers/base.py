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

class SPI_bitbang:
    """Bitbanged SPI master using GPIO pins.

    Pins must support .o (output setter) and .i (input getter).
    """

    def __init__(self, sck, mosi, miso, csn=None, cpol=0, cpha=0):
        self.sck = sck
        self.mosi = mosi
        self.miso = miso
        self.csn = csn
        self.cpol = cpol
        self.cpha = cpha

        self.sck.o = cpol
        if csn is not None:
            csn.o = 1

    def _xc_byte(self, byte):
        outb = 0
        active = self.cpol ^ 1

        for bit in range(7, -1, -1):
            if self.cpha == 0:
                if self.mosi is not None:
                    self.mosi.o = 1 if (byte & (1 << bit)) else 0
                self.sck.o = active
                outb <<= 1
                if self.miso is not None and self.miso.i:
                    outb |= 1
                self.sck.o = self.cpol
            else:
                self.sck.o = active
                if self.mosi is not None:
                    self.mosi.o = 1 if (byte & (1 << bit)) else 0
                self.sck.o = self.cpol
                outb <<= 1
                if self.miso is not None and self.miso.i:
                    outb |= 1

        return outb

    def xfer(self, tx_data, rx_len=None, timeout=1):
        """SPI transaction. Returns received bytes."""
        if rx_len is None:
            rx_len = len(tx_data)

        if self.csn is not None:
            self.csn.o = 0

        result = []
        for i in range(max(len(tx_data), rx_len)):
            byte = tx_data[i] if i < len(tx_data) else 0
            result.append(self._xc_byte(byte))

        self.sck.o = self.cpol

        if self.csn is not None:
            self.csn.o = 1

        return bytes(result[:rx_len])


from .. import svd_gdb

class Device(svd_gdb.Device):
    def read_mem(self, addr, size):
        return self._gdb.read_mem(addr, size)

    def spi(self, sck, mosi, miso, csn=None, cpol=0, cpha=0):
        """Return a bitbanged SPI instance for the given pins."""
        return SPI_bitbang(sck, mosi, miso, csn, cpol, cpha)

class Accel():
    name = "unknown accelerometer"

    def read(self):
        """Returns ((x, y, z) in g, temperature in C)."""
        raise Exception('subclass me')

from svd_gdb.github_dl import cached

def cmsis_svd_file(vendor, filename):
    return cached.fetch("/".join(['data',vendor,filename]))
