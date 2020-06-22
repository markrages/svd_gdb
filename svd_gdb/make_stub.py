#!/usr/bin/env python3

"""Uses gcc to compile "stub" sections as used in gdb_py.Gdb.run_stub().

Prerequisites:

 - working arm-none-eabi-gcc (and objcopy) on the PATH

Writing functions:

 - To keep from reinventing an operating system, each stub is one
   function (and any functions it calls).

 - The function must be named 'function'

 - The function can take up to four 32-bit arguments.  For more
   advanced usage, put some data in RAM somewhere and pass its
   address.  This also gets data out of the function.

 - Nothing special is done with the return value in run_stub().  The
   desperate can manually decode it, looking at registers and stack
   according to the ABI. Or extend run_stub().  Or just declare void
   and pass a pointer to put the result somewhere.

 - Python's struct and array classes are useful for encoding or
   decoding inputs and outputs. ctypes looks like it would work, but
   it is set up for the processor and ABI that Python was compiled
   for.

nRF5x notes:

 - To be portable, do not explicitly include nrf5x.h or
   nrf5x_bitfields.h.  The stub generator will do this for you.

"""

import tempfile,shutil
import subprocess

CC = "arm-none-eabi-gcc"

try:
    subprocess.check_output([CC,"--version"])
except subprocess.CalledProcessError:
    raise Exception("The program '%s' is not installed." % CC)

class MakeStub():
    def __init__(self, device_svd,
                 function_addr=0x20000000, heap_addr=0x20002000):
        self.include_path=[]
        self.cflags=['-Os',
                     '--std=gnu99',
                     '-mthumb',
                     '-mabi=aapcs',
                     '-nostdlib',
                     '-Wl,-Ttext,0x%x'%function_addr,
                     '-Wl,-Tdata,0x%x'%(heap_addr-0x400),
        ]
        self.defines=[]
        self.includes=[]
        self.sources=[]

        cpu = device_svd._cpu
        if cpu: # Not all SVD contain this information
            self.cflags.append({'CM0':'-mcpu=cortex-m0',
                                'CM3':'-mcpu=cortex-m3',
                                'CM4':'-mcpu=cortex-m4'}[cpu._name])

        self.function_addr = function_addr
        self.heap_addr = heap_addr

    def __call__(self,
                 c_code,
                 extra_include_path=None,
                 extra_includes=None,
                 extra_defines=None,
                 extra_cflags=None,
                 extra_sources=None):

        if 1:
            tmpdir = tempfile.mkdtemp(prefix='svd_gdb_')
        else:
            tmpdir = "/tmp/current"

        extra_include_path = extra_include_path or []
        extra_includes = extra_includes or []
        extra_defines = extra_defines or []
        extra_cflags = extra_cflags or []
        extra_sources = extra_sources or []

        print("""
.global _start
.extern function

_start:
    bl function
    bkpt
""", file=open(tmpdir+'/call.S','w'))

        c_code = '\n'.join(['#include '+i for i in self.includes + extra_includes] + [c_code])

        print(c_code, file=open(tmpdir+'/function.c','w'))

        cc_args = ([CC] +
                   self.cflags + extra_cflags +
                   ['-D%s'%d for d in self.defines+extra_defines] +
                   ['-I%s'%i for i in self.include_path+extra_include_path] +
                   ['-g3'] +
                   ['-o',tmpdir+'/a.out'] +
                   [tmpdir+'/call.S'] +
                   [tmpdir+'/function.c'] +
                   self.sources + extra_sources)
        try:
            subprocess.check_output(cc_args)
        except subprocess.CalledProcessError:
            print("Command was:",' '.join(cc_args))
            raise

        oc_args = (['arm-none-eabi-objcopy'] +
                   ['-O','binary'] +
                   [tmpdir+'/a.out'] +
                   [tmpdir+'/stub.bin'])
        subprocess.check_output(oc_args)
        stub = open(tmpdir+'/stub.bin','rb').read()

        # If error, we leak a directory.  On purpose, for debugging
        shutil.rmtree(tmpdir)
        return stub

def example_nRF_stub(d, *args, **kwargs):
    """Example stub function.

    For editing, you want an editor that understands Python and C at
    the same time.

    Emacs has indirect buffers built in. (C-x 4 c) See also
    https://emacswiki.org/emacs/MultipleModes .  For other editors,
    you're on your own.

    This example assumes an nRF51 attached with LED on pin 12.

    This example is an example of using Python as a preprocessor,
    although it would probably be clearer to pass led_pin as an
    argument or #define.

    """
    if not 'led_pin' in kwargs:
        kwargs['led_pin']=12

    return d.make_stub(
        """
#include "nrf_gpio.h"
#include "nrf_delay.h"

void function(uint32_t r0) {

  int i;
  nrf_gpio_cfg_output(%(led_pin)d);
  for (i=0; i<r0; i++) {
    nrf_gpio_pin_toggle(%(led_pin)d);
    nrf_delay_ms(50);
  }
}
    """%kwargs,
        extra_include_path=[d.sdk+'/components/libraries/delay'],)
#extra_sources=[sdk+'/components/drivers_nrf/delay/nrf_delay.c'])

def example_bp_stub(d, *args, **kwargs):
    """Example stub function for Bluepill board.

    The only IO we have on this board is an LED on GPIOC.13, which
    turns on for output low.

    """

    return d.make_stub(
        """
#include <stdint.h>

static void delay(uint32_t ct) {
    int i;
    for (i=0; i<ct; i++) asm("nop");
}

#define LED_PORT GPIOC
#define LED_PIN (13)

void function(uint32_t r0) {

  int i;
  LED_PORT->CRH |= 0x1 << ((LED_PIN*4) %% 32);

  for (i=0; i<r0; i++) {
    LED_PORT->ODR ^= (1<<13);
    delay(30000);
  }
}
    """%kwargs)

def nrf51_example():
    from svd_gdb.drivers import nrf5x
    d = nrf5x.NRF51()

    stub = example_nRF_stub(d, led_pin=12)
    print(stub)
    d._parent.run_stub_timeout(30, stub, 0x20000000, 200)

def stm32_bp_example():
    from svd_gdb.drivers import stm32
    d = stm32.STM32F103()

    stub = example_bp_stub(d, led_pin=12)
    print(stub)
    d._parent.run_stub_timeout(30, stub, 0x20000000, 10)


if __name__=="__main__":
    stm32_bp_example()
