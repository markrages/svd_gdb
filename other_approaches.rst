Appendix A. Alternative approaches to production board testing
--------------------------------------------------------------


1. Full electrical test of every node

   An ICT (In-circuit test) machine and a custom bed-of-nails fixture
   can test connectivity of every node to verify that the circuit is
   assembled correctly. For full testing, this requires (almost) every
   node of the circuit to be brought out to a probe-accessible test
   point.

   This is a comprehensive test.  It is good for high-volume
   production, but the relatively-high NRE (non-recurring expense),
   including PCB redesign, makes it an expensive choice for short and
   medium production runs.

   I have also run into trouble with ICT's simpleminded understanding
   of normal circuit operation. I had a section of the circuit that
   was powered down most of the time for battery-life reasons, and the
   ICT could not test that section of the circuit.

   If you like to see Gaussian statistics computed for a digital
   output's bi-modal voltage, then you will enjoy ICT.

2. Boundary scan

   If you have full JTAG capability, you could test for connectivity
   by clocking patterns into the "boundary scan" shift register, which
   toggles outputs and reads inputs to verify that the chips were
   soldered together correctly.

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
      will usually require releasing new firmware as well as updating
      the test scripts, and the two must be kept synchronized to have
      a legible system.
   
   3. Because of the friction of #2, not every test that might be
	  useful will be run.
   
   4. Because of #2, development of testing scripts is blocked on
      development of firmware.
   
   5. An additional connection to the target is required, beyond the
      SWD connection already required for firmware loading.
   
   6. Code space is occupied by routines that are only used during
      production.  I have seen microcontroller programs where half the
      flash space is occupied by implementations of ``printf()``,
      ``strtok()``, and the like.  Not only does this reduce space for
      useful code, it prevents use of smaller and cheaper processors.
   
	 .. note:: When your embedded flash image contains ANSI color escape codes, the firmware may not be optimized for code size.
   
   7. The debug shell and debug modes are aberrant modes, states where
      the firmware is not executing its intended function.  For
      reliability and security, we should remove such states from
      shipping firmware as much as possible.

4. No connectivity testing, just overall functional testing

   One approach to testing is just to test the overall operation of
   the device, instead of the connectivity of the circuit inside
   it. You might consider this if the device is very simple and
   well-specified, without any error conditions or unusual operating
   conditions. But if you must test for those, the test time will
   stretch towards infinity.

   In software engineering, there has been plenty written about unit
   testing vs integration testing.  Some of those arguments may be
   useful for production testing.  But most of them only pertain to
   design verification testing.
