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

   For alternative approaches to production testing, see Appendix A.

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

This script uses gdb.py from the Black Magic Probe project, and
extends it with register definitions from the
`SVD <http://www.keil.com/pack/doc/CMSIS/SVD/html/>`_ ("system view
description") file provided by the microcontroller's vendor.

It is no accident that the SVD file happens to contain exactly the
correct information to make an ergonomic Python interface to the
microcontroller functionality.  This is what SVD was invented to do.

This package uses the `cmsis_svd
<https://github.com/posborne/cmsis-svd>`_ Python package to provide a
collection of SVD files.  But it uses its own parser.

Appendix A. Alternative approaches to production board testing
--------------------------------------------------------------


  1. Full electrical test of every node

     An ICT (In-circuit test) machine and a custom bed-of-nails
     fixture can test connectivity of every node to verify that the
     circuit is assembled correctly. For full testing, this requires
     (almost) every node of the circuit to be brought out to a
     probe-accessible test point.

     This is a comprehensive test.  It is good for high-volume
     production, but the relatively-high NRE (non-recurring expense),
     including PCB redesign, makes it an expensive choice for short
     and medium production runs.

     I have also run into trouble with ICT's simpleminded
     understanding of normal circuit operation. I had a section of the
     circuit that was powered down most of the time for battery-life
     reasons, and the ICT could not test that section of the circuit.

     If you like to see Gaussian statistics computed for a digital
     output's bi-modal voltage, then you will enjoy ICT.

  2. Boundary scan

     If you have full JTAG capability, you could test for connectivity
     by clocking patterns into the "boundary scan" shift register,
     which toggles outputs and reads inputs to verify that the chips
     were soldered together correctly.

     But processors below a certain size tend to use SWD which doesn't
     support boundary scan.

  3. Debug protocol in firmware

     A common pattern for test development is to bake some kind of
     debugging protocol into the firmware of the device under
     development.  Often this takes the form of an ASCII serial
     interactive shell, were commands can be entered to exercise the
     hardware and exchange data.

     There are reasons to avoid this approach however.

     1. The protocol must be designed and debugged, at some cost of
        time and attention.

     2. The testing is tightly coupled to the firmware and is less
        cohesive.  Making an unforeseen change to the testing scheme
        will usually require releasing new firmware as well as
        updating the test scripts, and the two must be kept
        synchronized to have a legible system.

     3. Because of the friction of #2, not every test that might be
	    useful will be run.

     4. Because of #2, development of testing scripts is blocked on
        development of firmware.

     5. An additional connection to the target is required, beyond the
        SWD connection already required for firmware loading.

     6. Code space is occupied by routines that are only used during
        production.  I have seen microcontroller programs where half
        the flash space is occupied by implementations of ``printf()``,
        ``strtok()``, and the like.  Not only does this reduce space for
        useful code, it prevents use of smaller and cheaper
        processors.

	 .. note:: When your embedded flash image contains ANSI color escape codes, the firmware may not be optimized for code size.

     7. The debug shell and debug modes are aberrant modes, states
        where the firmware is not executing its intended function.
        For reliability and security, we should remove such states
        from shipping firmware as much as possible.

  4. No connectivity testing, just overall functional testing

	 One approach to testing is just to test the overall operation of
	 the device, instead of the connectivity of the circuit inside
	 it. You might consider this if the device is very simple and
	 well-specified, without any error conditions or unusual operating
	 conditions. But if you must test for those, the test time will
	 stretch towards infinity.

     In software engineering, there has been plenty written about
     unit testing vs integration testing.  Some of those arguments may
     be useful for production testing.  But most of them only pertain
     to design verification testing.
