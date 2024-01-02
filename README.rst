*******
svd_gdb
*******

Talk to microcontrollers through a debug probe.

Example 1
=========

We have an nRF51822 on a Black Magic Probe.  Let's see its unique
device ID::

 >>> from svd_gdb.drivers.nrf5x import NRF51
 >>> d = NRF51()
 >>> d.FICR.DEVICEID
 [nrf51.FICR.DEVICEID[0] = 0xb5b527cd, nrf51.FICR.DEVICEID[1] = 0x15896259]

The nRF51 has a random number generator.  Let's collect some random
numbers with it::

 >>> d.RNG.TASKS_START=1
 >>> bytes(d.RNG.VALUE for _ in range(15))
 b'\xa8qS\x0e\x86\xacw\xfb\x7fP\xb2\x02a9X'

Let's see why the last reset happened::

  >>> d.POWER.RESETREAS._dump()
              nrf51.POWER.RESETREAS
              | Reset reason.
  0x40000400: 0x   0   0   0   0   0   0   0   4
              0b00000000000000000000000000000100
                             ^^^            ^^^^
                             |||            |||+ RESETPIN = 0x0 (NotDetected) | Reset from pin-reset detected.
                             |||            ||+- DOG = 0x0 (NotDetected) | Reset from watchdog detected.
                             |||            |+-- SREQ = 0x1 (Detected) | Reset from AIRCR.SYSRESETREQ detected.
                             |||            +--- LOCKUP = 0x0 (NotDetected) | Reset from CPU lock-up detected.
                             ||+---------------- OFF = 0x0 (NotDetected) | Reset from wake-up from OFF mode detected by the use of DETECT signal from GPIO.
                             |+----------------- LPCOMP = 0x0 (NotDetected) | Reset from wake-up from OFF mode detected by the use of ANADETECT signal from LPCOMP.
                             +------------------ DIF = 0x0 (NotDetected) | Reset from wake-up from OFF mode detected by entering into debug interface mode.

Example 2
=========

We have a Bluepill board on the probe.  A Bluepill has an STM32F103 processor, with an LED on pin C13. Let's toggle it on::

 >>> from svd_gdb.drivers.stm32 import STM32F103
 >>> d = STM32F103()
 >>> d.PC_13.o ^= 1

Let's see if pin C12 is floating::

 >>> d.PC_12.hiz
 False

It is not.  Is it pulled high or low?
::

 >>> d.PC_12.i
 0

That means it is pulled low.
 
Rationale
=========

What is a Python library like this useful for?

 - Production test scripting.

   In a production test of a microcontroller system, you are already
   connected to a debugger, to program the application code.

   Using this library, in addition to programming code, you can do
   basic tests on connectivity.  If your script can measure supply
   current, you can verify that LEDs are installed correctly.  You can
   take readings from sensors on the board under test, and store
   calibration parameters.

   For comparison to alternative approaches to production testing, see
   `Appendix A <other_approaches.rst>`_.

 - Development

   For a typically poorly-specified sensor like a commercial
   accelerometer, there is a fair amount of trying-and-tuning
   different register settings to find an optimal configuration. Using
   this library (perhaps with a wireless debugger), the settings can
   be determined in the actual circuit, before writing any firmware
   code.

   The same is even true for microcontroller peripherals -- sometimes
   it is easier to prototype their operation in a scripting
   environment.

   I have used the library to prototype LED blinking behavior in
   actual hardware, for the approval of product management.  We
   iterated through a handful of different blinking patterns in a few
   minutes, much faster than an approach that involves compilation
   cycles, or an approach that requires designing and implementing a
   "blink specification protocol" to control firmware at run time.

Implementation
==============

This script uses ``gdb.py`` from the Black Magic Probe project, and
extends it with register definitions from the
`SVD <http://www.keil.com/pack/doc/CMSIS/SVD/html/>`_ ("system view
description") file provided by the microcontroller's vendor.

It is no accident that the SVD file happens to contain exactly the
correct information to make an ergonomic Python interface to the
microcontroller functionality.  This kind of thing is what SVD was
invented to do.

This package gets the SVD files on demand from the `cmsis-svd <https://github.com/cmsis-svd/cmsis-svd-data>`_ project.  But it uses its own parser.
 
Other projects
==============

To use SVD files for more convenient debugging within the gdb's shell, see 
https://github.com/bnahill/PyCortexMDebug
