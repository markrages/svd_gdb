#!/usr/bin/python3

from . import base
from .. import svd_gdb

class STM32F1Pin(base.Pin):
    def __init__(self, parent, port, pinnumber):
        self.parent = parent
        self.port = port
        self.pinnumber = pinnumber
        self.pin = pinnumber
        self.pinmask = 1<<self.pin

        self.name = "P%s_%d"%(port._name[-1:], self.pin)

    def c_macro(self, prefix):
        return """
#define %(prefix)sCNFMODE(val) \\
\t%(port)s->%(CR)s = ((%(port)s->%(CR)s & ~(0xf << (4u * (7 & %(pin)d)))) | \\
\t          ((val) << (4u * (7 & %(pin)d))))

#define %(prefix)sOUTHIGH do { \\
\t%(port)s->BSRR = (1u<<%(pin)du); \\
\t%(prefix)sCNFMODE(1); \\
} while (0)

#define %(prefix)sOUTLOW do { \\
\t%(port)s->BSRR = (0x10000u<<%(pin)du); \\
\t%(prefix)sCNFMODE(1); \\
} while (0)

#define %(prefix)sINPULLUP ( \\
\t%(prefix)sCNFMODE(8), \\
\t%(port)s->BSRR = (1u<<%(pin)du), \\
\t(!!(%(port)s->IDR & (1u<<%(pin)du))))

#define %(prefix)sIN ( \\
\t%(port)s->BSRR = (1u<<%(pin)du), \\
\t%(prefix)sCNFMODE(3), \\
\t(!!(%(port)s->IDR & (1u<<%(pin)du))))
        """%{'prefix':prefix,
             'CR':['CRL','CRH'][self.pin >= 8],
             'pin':self.pin,
             'port':self.port._name.split('.')[-1]}

    @property
    def i(self):
        "Reads digital input latch, in [0, 1]"
        self._setin()
        return int(bool(self.port.IDR & self.pinmask))

    @property
    def o(self):
        "Reads digital output latch, in [0, 1]"
        return int(bool(self.port.ODR & self.pinmask))

    def _setoutl(self, level):
        if (level):
            self.port.BSRR = self.pinmask
        else:
            self.port.BSRR = self.pinmask << 16

    @o.setter
    def o(self, val):
        "Sets digital output latch to val"
        #self.port.DIRSET = self.pinmask
        self._setoutl(val)
        self._setout()

    @property
    def pull(self):
        "Returns selected pullup, in [None, 'h', 'l']"
        if self._cnfmode != 0b1000:
            return None
        return 'lh'[self.o]

    def _setin(self):
        cnfmode = self._cnfmode
        cnfmode &= ~0b11
        self._cnfmode = cnfmode

    def _setout(self):
        "Sets to 10 MHz push-pull"
        self._cnfmode = 0b0001

    @property
    def _cnfmode(self):
        "Return CNF+MODE bits. 0..15"
        if self.pinnumber > 8:
            cr = self.port.CRH
        else:
            cr = self.port.CRL

        return 15 & (cr >> 4 * (7 & self.pinnumber))

    @_cnfmode.setter
    def _cnfmode(self, new_cnfmode):
        cr = self._cnfmode

        cr &= ~(0b1111 << 4 * (7 & self.pinnumber))
        cr |= (new_cnfmode << 4 * (7 & self.pinnumber))

        if self.pinnumber > 8:
            self.port.CRH = cr
        else:
            self.port.CRL = cr

    @pull.setter
    def pull(self, v):
        "Sets selected pullup, in [None, 'h', 'l']"
        cnfmode,out = {None:(0b1001,0),
                       'l':(0b1000,0),
                       'h':(0b1000,1)}[v]
        # for input, MODE0 = 00
        # for pull-up input, set CNF1, clear CNF0
        # ODR sets pull dirction
        self._cnfmode = cnfmode
        if cnfmode:
            self._setoutl(out)

def STM32F3Pin(parent, port, pinnumber):
    pinname = 'P%s%d'%(port._name[-1:], pinnumber)

    analog_map = {'PC0':6,
                  'PC1':7,
                  'PC2':8,
                  'PC3':9,
                  'PA0':1,
                  'PA1':2,
                  'PA2':3,
                  'PA3':4,
                  'PA4':5,
                  'PA6':10,
                  'PA7':15,
                  'PB0':11,
                  'PB1':12,
                  'PB11':14,
                  'PB13':13}
    if pinname in analog_map:
        return STM32F3AnalogPin(parent, port, pinnumber, analog_map[pinname])
    else:
        return STM32F3DigitalPin(parent, port, pinnumber)

class STM32F3DigitalPin(base.Pin):
    def __init__(self, parent, port, pinnumber):
        self.parent = parent
        self.port = port
        self.pinnumber = pinnumber
        self.pin = pinnumber
        self.pinmask = 1<<self.pin

        self.name = "P%s_%d"%(port._name[-1:], self.pin)

    @property
    def i(self):
        "Reads digital input latch, in [0, 1]"
        self._setin()
        return int(bool(self.port.IDR & self.pinmask))

    @property
    def o(self):
        "Reads digital output latch, in [0, 1]"
        return int(bool(self.port.ODR & self.pinmask))

    def _setoutl(self, level):
        if (level):
            self.port.BSRR = self.pinmask
        else:
            self.port.BSRR = self.pinmask << 16

    @o.setter
    def o(self, val):
        "Sets digital output latch to val"
        #self.port.DIRSET = self.pinmask
        self._setoutl(val)
        self._setout()

    def _set_moder(self, new_mode):
        moder = self.port.MODER
        moder &= ~(0b11 << (2*self.pinnumber))
        moder |= new_mode << (2*self.pinnumber)
        self.port.MODER=moder

    def _setin(self):
        self._set_moder(0)

    def _setout(self):
        self._set_moder(1)

    @property
    def pull(self):
        "Returns selected pullup, in [None, 'h', 'l']"
        pupdr = 3 & self.port.PUPDR >> (2*self.pinnumber)
        return {0b00:None,
                0b01:'h',
                0b10:'l',
                0b11:NotImplemented}[pupdr]

    @pull.setter
    def pull(self, v):
        "Sets selected pullup, in [None, 'h', 'l']"
        pupdr = {None:0b00,
                 'h':0b01,
                 'l':0b10}[v]

        reg = self.port.PUPDR & ~(3 << (2*self.pinnumber))
        reg |= pupdr << (2*self.pinnumber)
        self.port.PUPDR = reg

class STM32F3AnalogPin(STM32F3DigitalPin):
    def __init__(self, parent, port, pinnumber, analog_ch):
        super().__init__(parent,port,pinnumber)
        self.analog_ch = analog_ch

    @property
    def v(self):
        return 3.3*self.rawadc/4096

    @property
    def rawadc(self):
        self.parent._init_adc()
        adc = self.parent.ADC
        self._set_moder(3)

        adc.SQR1 = self.analog_ch << adc.SQR1.SQ1._bit_offset
        adc.CR.ADSTART = 1
        # USB delay is enough
        return adc.DR

class STM32F(svd_gdb.Device):
    sdk = "/opt/cubeMX/Drivers"
    mfgr_name = 'STMicro'
    svd_name = ''

    def __init__(self, target=None):
        svd_filename = base.cmsis_svd_file(self.mfgr_name, self.svd_name)
        #svd_filename = self.svd_name
        gdb_int = svd_gdb.GdbInterface(target)
        super().__init__(svd_filename, gdb_int)
        self._gdb.make_stub.include_path.append(self.sdk+'/CMSIS/Include')

    def _ports_on(self, reg):
        # power up all the GPIOs by building a mask for RCC
        enbits = [b
                  for b in dir(reg)
                  if b.startswith('IOP') and b.endswith('EN')]
        mask = 0
        for bit in enbits:
            field = getattr(reg, bit)
            mask |= 1<<field._bit_offset

        reg |= mask

class STM32F1(STM32F):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert 'STM32F1' in self._gdb.target_name

        for gpio in (x for x in dir(self) if x.startswith('GPIO')):
            port = getattr(self, gpio)
            self._add_pins(port, 16)

        self._ports_on(self.RCC.APB2ENR)

        self._gdb.make_stub.include_path.append(self.sdk+'/CMSIS/Device/ST/STM32F1xx/Include')
        self._gdb.make_stub.cflags.append('-mcpu=cortex-m3')

    def _add_pins(self, port, pins=8):

        for pin_number in range(pins):
            pin = STM32F1Pin(self, port, pin_number)
            setattr(self, pin.name, pin)
            self._pins.append(pin)

class STM32F3(STM32F):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert 'STM32F3' in self._gdb.target_name

        for gpio in (x for x in dir(self) if x.startswith('GPIO')):
            port = getattr(self, gpio)
            self._add_pins(port, 16)

        self._ports_on(self.RCC.AHBENR)
        self._gdb.make_stub.cflags.append('-mcpu=cortex-m4')
        self._gdb.make_stub.include_path.append(self.sdk+'/CMSIS/Device/ST/STM32F3xx/Include')
        self._adc_initted = False

    def _add_pins(self, port, pins=8):

        for pin_number in range(pins):
            pin = STM32F3Pin(self, port, pin_number)
            setattr(self, pin.name, pin)
            self._pins.append(pin)

    def _init_adc(self):
        if not self._adc_initted:
            # Have to assume no adc is set up.
            self.RCC.AHBRSTR.ADC1RST = 1
            self.RCC.AHBRSTR.ADC1RST = 0
            self.RCC.CFGR2.ADC1PRES = 0
            self.RCC.AHBENR.ADC1EN = 1
            adc = self.ADC
            adc.CRR.CKMODE = 1 # async
            adc.CR = 0 # All off, regulator prep
            adc.CR.ADVREGEN = 1 # regulator on

            adc.CR.ADCALDIF = 0
            adc.CR.ADCAL = 1
            while (adc.CR.ADCAL):
                pass

            adc.CR.ADEN = 1
            adc.CFGR = 0
            adc.CFGR.OVRMOD = 1 # enable overrun
            adc.SMPR1 = 0
            adc.SMPR1.SMP1 = 5 # 61.5 ADC cycles
            adc.DIFSEL = 0
            self._adc_initted = True

class STM32F103(STM32F1):
    svd_name = 'STM32F103xx.svd'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gdb.make_stub.includes += ['"stm32f103xb.h"']
        assert 'STM32F1' in self._gdb.target_name

class STM32F301(STM32F3):
    svd_name = 'STM32F301.svd'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gdb.make_stub.includes += '"stm32f301x8.h"'
        assert 'STM32F3' in self._gdb.target_name

if __name__=="__main__":
    pass
