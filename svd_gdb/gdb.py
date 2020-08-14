#!/usr/bin/env python
#
# gdb.py: Python module for low level GDB protocol implementation
# Copyright (C) 2009  Black Sphere Technologies
# Written by Gareth McMullin <gareth@blacksphere.co.nz>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


# Used to parse XML memory map from target
from xml.dom.minidom import parseString
import struct,array
import time

def hexify(s):
    """Convert a bytes object into hex bytes representation"""
    return s.hex().encode()

def unhexify(s):
    """Convert a hex-encoded bytes into bytes object"""
    return bytes.fromhex(s.decode())

class GetPacketTimeoutException(Exception):
    pass

class InvalidStubResponseException(Exception):
    pass

class FakeSocket():
    """Emulate socket functions send and recv on a file object"""
    def __init__(self, file):
        self.file = file
        self.sendall = self.send

    def send(self, data):
        self.file.write(data)

    def gettimeout(self):
        return self.file.timeout

    def settimeout(self, seconds):
        self.file.timeout = seconds

    def recv(self, bufsize):
        return self.file.read(bufsize)

    def flushInput(self):
        #print("hanging out",)
        extra = self.file.read(self.file.inWaiting())
        #print(extra)

class FlashMemory(object):
    def __init__(self, flash_ranges):
        self.flash_ranges = flash_ranges

    class Segment:
        def __init__(self, offset, length, blocksize):
            self.offset = offset
            self.length = length
            self.blocksize = blocksize
            self.blocks = list(None for i in range(length // blocksize))

        def prog(self, offset, data):
            assert type(data)==bytes

            assert ((offset >= self.offset) and
                (offset + len(data) <= self.offset + self.length))

            while data:
                index = (offset - self.offset) // self.blocksize
                bloffset = (offset - self.offset) % self.blocksize
                bldata = data[:self.blocksize-bloffset]
                data = data[len(bldata):]; offset += len(bldata)
                if self.blocks[index] is None: # Initialize a clear block
                    self.blocks[index] = bytes(0xff for i in range(self.blocksize))
                self.blocks[index] = (self.blocks[index][:bloffset] + bldata +
                        self.blocks[index][bloffset+len(bldata):])

    def flash_probe(self):
        self.mem = []
        for offset, length, blocksize in self.flash_ranges:
            mem = FlashMemory.Segment(offset, length, blocksize)
            self.mem.append(mem)

        return self.mem

    def flash_prepare_hex(self, hexfile):
        lowest_addr = 0xffffffff
        highest_addr = 0

        f = open(hexfile)
        addrhi = 0
        addr16 = 0
        for line in f:
            if line[0] != ':': raise Exception("Error in hex file")
            reclen = int(line[1:3], 16)
            addrlo = int(line[3:7], 16)
            rectype = int(line[7:9], 16);
            if sum(unhexify(line[1:11+reclen*2])) & 0xff != 0:
                raise Exception("Checksum error in hex file")
            if rectype == 0: # Data record
                addr = (addrhi << 16) + (addr16 << 4) + addrlo
                data = unhexify(line[9:9+reclen*2])
                if addr < lowest_addr: lowest_addr = addr
                if addr+len(data) > highest_addr: highest_addr = addr+len(data)
                self.flash_write_prepare(addr, data)
                pass
            elif rectype == 4: # High address record
                addrhi = int(line[9:13], 16)
                pass
            elif rectype == 2: # Extend address record
                addr16 = int(line[9:13], 16)
                pass
            elif rectype == 5: # Entry record
                pass
            elif rectype == 1: # End of file record
                break
            elif rectype == 3: # Start segment address...
                break
            else:
                raise Exception("Invalid record in hex file")

        return lowest_addr, highest_addr

    def flash_write_prepare(self, address, data):
        for m in self.mem:
            if (address >= m.offset) and (address + len(data) <= m.offset + m.length):
                 m.prog(address, data)

    @property
    def ihex(self):
        """Returns the same data in a intelhex-derived object.

        Documentation at http://pythonhosted.org/IntelHex/

        It would be nice to unify the code, but until then this
        function provides some glue."""

        import intelhex
        ret = intelhex.IntelHex()

        for segment in self.mem:
            data = []
            for num,block in enumerate(segment.blocks):
                if block:
                    for i,c in enumerate(block):
                        address = (segment.offset +
                                   num * segment.blocksize +
                                   i)
                        ret[address] = c
        return ret

class Target(FlashMemory):
    def __init__(self, sock):
        if "send" in dir(sock):
            self.sock = sock

            # Debugging involves back-and-forth with lots of tiny packets
            # Nagle's algorithm makes debug 10x slower
            import socket
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        else:
            self.sock = FakeSocket(sock)

        self.PacketSize=0x100 # default
        self.sock.send(b'+')
        self.sock.flushInput()
        self.get_supported()

    def getpacket(self, timeout=3, skipdollar=False):
        """Return the first correctly received packet from GDB target"""

        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(timeout)
        try:
            return self.getpacket_(timeout, skipdollar)
        finally:
            self.sock.settimeout(old_timeout)

    def getpacket_(self, timeout, skipdollar):
        t0 = time.time()
        while True:
            while True and not skipdollar:
                c = self.sock.recv(1)
                if c == b'$':
                    break
                if time.time() - t0 >  timeout:
                    raise GetPacketTimeoutException()

            csum = 0
            packet = [] # list-of-small-int

            while True:
                c, = self.sock.recv(1)
                if c == ord('#'): break

                if c == ord('$'):
                    packet = []
                    csum = 0
                    continue

                if c == ord('}'):
                    c, = self.sock.recv(1)
                    csum += c + ord('}')
                    packet.append(c ^ 0x20)
                    continue

                packet.append(c)
                csum += c

            if (csum & 0xFF) == int(self.sock.recv(2),16):
                break

            self.sock.send(b'-')

        self.sock.send(b'+')
        return bytes(packet)

    def _singlepacket(self, packet):
        out = []

        for c in packet:
            if (c in b'$#}'):
                out.append(ord('}'))
                out.append(c ^ 0x20)
            else:
                out.append(c)

        csum = sum(out)
        outb = b'$'+bytes(out)+b'#%02X' % (csum & 0xff)

        self.sock.send(outb),outb

    def putpacket(self, packet):
        """Send packet to GDB target and wait for acknowledge
        packet is bytes or string"""

        if type(packet) == str:
            packet = packet.encode()

        while True:
            self._singlepacket(packet)

            c = self.sock.recv(1)
            if c == b'+':
                break
            if c == b'$':
                print("Skipped packet-instead-of-ack")
                pack=self.getpacket(skipdollar=True)
                print(pack)
                raise Exception

    def get_supported(self):
        self.putpacket(b"qSupported")
        supported = self.getpacket()
        self.supported_features=set()
        self.unsupported_features=set()

        for feature in supported.split(b";"):
            if feature.endswith(b'+'):
                self.supported_features.add(feature)
            elif feature.endswith(b'-'):
                self.unsupported_features.add(feature)
            elif b'=' in feature:
                key,val = feature.split(b'=',1)
                setattr(self,key.decode(),int(val,16))

    def monitor(self, cmd):
        """Send gdb "monitor" command to target"""
        if type(cmd) == str:
            cmd = cmd.encode()

        ret = []
        self.putpacket(b"qRcmd," + hexify(cmd))

        while True:
            s = self.getpacket()

            if s == b'': return None
            if s == b'OK': return ret
            if s.startswith(b'O'):
                ret.append(unhexify(s[1:]))
            else:
                raise InvalidStubResponseException('Invalid GDB stub response %r'%s)

    def monitor_s(self, cmd):
        "like monitor() but returns string"
        return ''.join(l.decode() for l in self.monitor(cmd))

    @property
    def target_name(self):
        connected = [name for i, name, connected
                     in self.targets()
                     if connected]
        if len(connected)==0:
            return None
        elif len(connected)==1:
            return connected[0]
        else:
            raise Exception('more than one target connected')

    def targets(self):
        "Returns list of target id, name, connected"
        ret = []
        import re
        target_re = re.compile(b'([0-9]+)(.*)')
        for line in self.monitor('targets'):
            l = line.strip()
            m = target_re.match(l)
            if m:
                index,name = m.groups()
                index = int(index)
                name = name.strip()
                if name.startswith(b'*'):
                    connected = True
                    name = name[1:]
                else:
                    connected = False

                name = name.strip().decode()
                yield (index, name, connected)


    def attach(self, pid):
        """Attach to target process (gdb "attach" command)"""
        self.putpacket(b"vAttach;%08X" % pid)
        reply = self.getpacket()
        if (reply == b'') or (reply[:1] == b'E'):
            raise Exception('Failed to attach to remote pid %d' % pid)
        self.last_stub = None

    def detach(self):
        """Detach from target process (gdb "detach" command)"""
        self.putpacket(b"D")
        if self.getpacket() != b'OK':
            raise Exception("Failed to detach from remote process")

    def reset(self):
        """Reset the target system"""
        self.putpacket(b"r")

    def read_mem(self, addr, length):
        """Read length bytes from target at address addr"""
        addr = int(addr)
        length = int(length)
        ret = b''
        while length:
            # print "Read"
            packlen = min(length,self.PacketSize//2)
            self.putpacket(b"m%08X,%08X" % (addr, packlen))
            reply = self.getpacket()
            if (reply == b'') or (reply[:1] == b'E'):
                raise Exception('Error reading memory at 0x%08X' % addr)
            try:
                data = unhexify(reply)
            except Exception:
                raise Exception('Invalid response to memory read packet: %r' % reply)
            ret += data
            length -= packlen
            addr += packlen

        return ret

    def write_mem(self, addr, data):
        """Write data to target at address addr"""
        data = bytes(data)

        while data:
            d = data[:self.PacketSize-44]
            data = data[len(d):]
            #print("Writing %d bytes at 0x%X" % (len(d), addr))
            pack = b"X%08X,%08X:%s" % (addr, len(d), d)
            self.putpacket(pack)

            response = self.getpacket()
            if response != b'OK':
                raise Exception('%s Error writing to memory at 0x%08X' % (response, addr))
            addr += len(d)

    def write32(self, address, value):
        """Convenience function.
        uint32_t little-endian values are everywhere.
        """
        assert address & 3 == 0
        #print("write %08x to %08x"%(value, address))
        self.write_mem(address, struct.pack('<I',value))

    def read32(self, address):
        assert address & 3 == 0
        value, = struct.unpack('<I',self.read_mem(address, 4))
        #print("read %08x from %08x"%(value, address))
        return value

    def read_regs(self):
        """Read target core registers"""
        self.putpacket(b"g")
        reply = self.getpacket()
        if (reply == b'') or (reply[:1] == b'E'):
            raise Exception('Error reading memory at 0x%08X' % addr)
        try:
            data = unhexify(reply)
        except Exception:
            raise Exception('Invalid response to memory read packet: %r' % reply)
        ret = array.array('I',data)
        return ret

    def write_regs(self, *regs):
        """Write target core registers"""
        data = struct.pack("=%dL" % len(regs), *regs)
        self.putpacket(b"G" + hexify(data))
        if self.getpacket() != b'OK':
            raise Exception('Error writing to target core registers')

    def memmap_read(self):
        """Read the XML memory map from target"""
        offset = 0
        ret = b''
        while True:
            self.putpacket(b"qXfer:memory-map:read::%08X,%08X" % (offset, 512))
            reply = self.getpacket()
            if (reply[0] in b'ml'):
                offset += len(reply) - 1
                ret += reply[1:]
            else:
                raise Exception('Invalid GDB stub response %r'%reply)

            if reply[:1] == b'l': return ret

    def resume(self):
        """Resume target execution"""
        self.putpacket(b"c")
        #self.last_stub = None

    def interrupt(self):
        """Interrupt target execution"""
        self.sock.send(b"\x03")
        self.last_stub = None
        self.await_stop_response('SIGINT')

    def run_stub_timeout(self, timeout, stub, address, *args):
        """Execute a binary stub at address, passing args in core registers."""
        #self.reset() # Ensure processor is in sane state
        #time.sleep(0.1)

        def pr():
            regnames = "r0 r1 r2 r3 r4 r5 r6 r7 r8 r9 r10 r11 r12 sp lr pc xpsr fpscr msp psp special".split()
            print('\n'.join("%s = 0x%x"%(a,b) for a,b in zip(regnames,self.read_regs())))

        if not stub==self.last_stub:
            self.write_mem(address, stub)
            self.last_stub = stub

            # disable interrupts by writing ICE:
            self.write_mem(0xE000E180, b'\xff'*4*8)
            self.write_mem(0xE000E280, b'\xff'*4*8)

        stack_pointer = self.ram[0][0] + self.ram[0][1] # end of ram

        regs = list(self.read_regs())
        regs[:len(args)] = args
        old_pc = regs[15]
        regs[15] = address # pc
        regs[17] = stack_pointer # msp, sets sp
        regs[18] = regs[17] # psp, just in case
        self.write_regs(*regs)
        regs = list(self.read_regs())
        assert regs[15] == address
        self.resume()
        self.await_stop_response('SIGTRAP', timeout=timeout)

    def await_stop_response(self, await_signame, timeout=5):
        reply = None
        while not reply:
            reply = self.getpacket(timeout=timeout)

        reply_signame = {b'T02':'SIGINT',
                         b'T05':'SIGTRAP',
                         b'T0B':'SIGSEGV',
                         b'T1D':'SIGLOST'}.get(reply,repr(reply))

        if not reply_signame == await_signame:
            message = "Invalid stop response: %r" % reply
            message += ' (%s)'%reply_signame
            raise Exception(message)

    def run_stub(self, stub, address, *args):
        return self.run_stub_timeout(3, stub, address, *args)

    def flash_erase(self, startaddr, length):
        #print "Erasing flash at 0x%X" % startaddr
        self.putpacket(b"vFlashErase:%08X,%08X" %
                       (startaddr, length))
        if self.getpacket() != b'OK':
            raise Exception("Failed to erase flash")

    def commit(self, mem, progress_cb=None, erase=True):
        """Commits the blocks of memory to flash.

        Returns a tuple of (address, length, crc32), which could be
        used for verification.
        """

        totalblocks = 0
        for b in mem.blocks:
            if b is not None: totalblocks += 1

        combined = b''
        for i in range(len(mem.blocks)):
            data = mem.blocks[i]
            if data is None:
                data = b''
            # pad
            data += b'\xff' * (mem.blocksize - len(data))
            combined += data

        ret = (mem.offset, len(combined), binascii.crc32(combined))

        block = 0
        for i in range(len(mem.blocks)):
            data = mem.blocks[i]
            addr = mem.offset + mem.blocksize * i
            if data is None: continue

            block += 1
            if isinstance(progress_cb, collections.Callable):
                progress_cb(block*100//totalblocks)

            # Erase the block
            if erase:
                self.flash_erase(mem.offset + mem.blocksize*i, mem.blocksize)

            while data:
                d = data[:self.PacketSize-44]
                data = data[len(d):]
                #print "Writing %d bytes at 0x%X" % (len(d), addr)
                self.putpacket(b"vFlashWrite:%08X:%s" % (addr, d))
                addr += len(d)
                if self.getpacket() != b'OK':
                    raise Exception("Failed to write flash")

            self.putpacket(b"vFlashDone")
            if self.getpacket() != b'OK':
                raise Exception("Failed to commit")

        mem.blocks = list(None for i in range(mem.length // mem.blocksize))
        return ret

    def flash_probe(self):
        self.mem = []
        self.ram = []
        xmldom = parseString(self.memmap_read())

        for memrange in xmldom.getElementsByTagName("memory"):
            mem_type = memrange.getAttribute("type")
            if mem_type == "flash":
                offset = eval(memrange.getAttribute("start"))
                length = eval(memrange.getAttribute("length"))
                for property in memrange.getElementsByTagName("property"):
                    if property.getAttribute("name") == "blocksize":
                        blocksize = eval(property.firstChild.data)
                        break
                mem = FlashMemory.Segment(offset, length, blocksize)
                self.mem.append(mem)
            elif mem_type == "ram":
                offset = eval(memrange.getAttribute("start"))
                length = eval(memrange.getAttribute("length"))
                self.ram.append((offset, length))

            else:
                print("Unknown mem_type",mem_type)

        xmldom.unlink()

        return self.mem

    def flash_commit(self, progress_cb=None, erase=True):
        ret = []
        for m in self.mem:
            ret.append(self.commit(m, progress_cb, erase))
            print()
        return ret

    def flash_write_hex(self, hexfile, progress_cb=None, erase=False):
        self.flash_probe()
        self.flash_prepare_hex(self, hexfile)
        try:
            self.flash_commit(progress_cb, erase)
        except:
            print("Flash write failed! Is device protected?\n")
            raise
