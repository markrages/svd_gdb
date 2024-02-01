#!/usr/bin/python3

import xml.etree.ElementTree as ET
import textwrap

def int0(s):
    s = s.lower()
    if s.startswith('0x'):
        return int(s,16)
    else:
        return int(s)

def bool0(s):
    s = s.lower().strip()
    return s in ['1','true']

from .mutable_number import MutableInteger
class Int32(int):
    def __str__(self):
        return "0x%08x"%self

    def __repr__(self):
        return "0x%08x"%self

class IntX(int):
    def __new__(cls, width, *args, **kwargs):
        if 'extra' in kwargs:
            extra = kwargs['extra']
            del kwargs['extra']
        else:
            extra = None
        obj = int.__new__(cls, *args, **kwargs)
        obj._width = width
        obj._extra = extra
        return obj

    def __str__(self):
        w = 1+(self._width-1)//4
        return "0x%%0%dx"%w%self

    def __repr__(self):
        ret = str(self)
        if self._extra:
            ret += ' '+self._extra
        return ret

class EnumeratedValue():
    def __init__(self, value, name, description):
        "value is a string type, decoded into value and mask according to enumeratedValue rules"
        if type(value)==str:
            value = value.lower()
            binvalue = None
            if value.startswith('0b'):
                binvalue = value[2:]
            elif value.startswith('#'):
                binvalue = value[1:]

            if binvalue is None:
                self._values = set((int0(value),))
            else:
                def both(x):
                    ret = []
                    for y in x:
                        if not 'x' in y:
                            ret.append(y)
                        else:
                            ret += both([y.replace('x','0',1)])
                            ret += both([y.replace('x','1',1)])
                    return ret
                self._values = set(int(x,2) for x in both([binvalue]))
        else:
            self._values = set(value)

        self._name = name
        self._description = description

    def __eq__(self, other):
        return other in self._values
    def __int__(self):
        return self._values[0]

class SvdObj():
    _strfields = (('_name','name'),
                  ('_description','description'))
    _intfields = ()

    def __init__(self, svd, parent):
        self._svd = svd
        self._parent = parent
        self._gdb = parent._gdb

        for attname, fieldname in self._strfields:
            x = svd.find(fieldname)
            if x is not None:
                x = x.text
                if x is not None: # Yep, Element.text returns None for zero-length string.
                    x = x.strip()
                    x = ' '.join(x.split()) # Remove weird whitespace
            setattr(self, attname, x)

        for attname, fieldname in self._intfields:
            x = svd.find(fieldname)
            if x is not None:
                x = int0(x.text)
            setattr(self, attname, x)

    def __repr__(self):
        return repr(self._parent)+'.'+self._name

class CPU(SvdObj):
    def __init__(self, svd, parent):
        self._svd = svd
        self._name = svd.find('name').text.strip()
    def __repr__(self):
        return self._name

class ElementGroup(tuple):
    """ Read-only list of registers, but you can assign values
    to individual registers. """

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            indexes = range(*key.indices(len(self)))

            if len(indexes) != len(value):
                raise ValueError()

            for i,v in zip(indexes, value):
                self[i] = v

        else:
            while key < 0:
                key += len(self)
            self[key]._set(value)

    def __getitem__(self, key):
        ret = super().__getitem__(key)

        if isinstance(key, slice):
            return self.__class__(ret)
        else:
            return ret

    def __repr__(self):
        return repr(list(self))

    @property
    def _child_regs(self):
        ret = []
        for s in self:
            ret.extend(s._child_regs)

        return ret

class Field(SvdObj, MutableInteger):
    def __init__(self, svd, parent):
        super().__init__(svd, parent)

        self._bit_offset = 0
        self._bit_width = 32

        b1 = svd.find('bitOffset')
        b2 = svd.find('lsb')
        b3 = svd.find('bitRange')
        if b1 is not None:
            self._bit_offset = int0(b1.text)
            self._bit_width = int0(svd.find('bitWidth').text)
        elif b2 is not None:
            self._bit_offset = int0(b2.text)
            self._bit_width = 1 + int0(svd.find('msb').text) - self._bit_offset
        elif b3 is not None:
            'A string in the format: "[<msb>:<lsb>]"'
            s = b3.text.strip()
            assert s[0]=='['
            assert s[-1]==']'
            msb,lsb = s[1:-1].split(':')
            self._bit_offset = int0(lsb)
            self._bit_width = 1 + int0(msb) - self._bit_offset
        else:
            assert False
        assert self._bit_width >= 1

        self._enum = []
        ev = svd.find('enumeratedValues')
        if ev is not None:
            default_value = None
            for val in ev.findall('enumeratedValue'):
                name = val.find('name').text.strip()
                d = val.find('description')
                if d is not None:
                    d = d.text
                    if d is not None:
                        d = d.strip()
                description = d

                value = val.find('value')
                if value is None:
                    isd = val.find('isDefault')
                    if isd is not None and bool0(isd.text):
                        default_value = (name, description)
                else:
                    value = value.text.strip()
                    self._enum.append(EnumeratedValue(value,name,description))
            if default_value:
                all_values = list(range(1<<self._bit_width))
                for v in all_values:
                    if v in self._enum:
                        all_values.remove(v)
                self._enum.append(EnumeratedValue(all_values,name,description))

    def _set(self, value):
        if self._bit_width==1:
            if value & 1:
                self._parent._set_bit(self._bit_offset)
            else:
                self._parent._clear_bit(self._bit_offset)
        elif self._bit_width==32:
            self._parent_set(value)
        else:
            mask = ((1 << self._bit_width)-1) << self._bit_offset
            x = self._parent._get()
            x &= ~mask
            x |= value << self._bit_offset
            self._parent._set(x)

    def _get(self):
        if self._bit_width==1:
            ret = self._parent._is_bit_set(self._bit_offset)
        elif self._bit_width==32:
            ret = self._parent._get()
        else:
            mask = ((1 << self._bit_width)-1)
            x = self._parent._get()
            x >>= self._bit_offset
            ret = x & mask

        try:
            i = self._enum.index(ret)
        except ValueError:
            return IntX(self._bit_width, ret)

        extra = "(%s)"%self._enum[i]._name
        return IntX(self._bit_width, ret, extra=extra)

    @property
    def _n(self):
        return self._get()

    @_n.setter
    def _n(self, v):
        return self._set(v)

    def __repr__(self):
        return self._parent._repr_no_get()+'.'+self._name+' = '+repr(self._get())

class FieldHaver():
    def __setattr__(self, attname, value):
        if hasattr(self, '_freezeattr'): # avoid recursion
            if attname != '_freezeattr':
                if attname == '_n':
                    self._set(value)
                else:
                    self._fieldmap[attname]._set(value)
        else:
            super().__setattr__(attname, value)

class Register(SvdObj, FieldHaver, MutableInteger):
    _intfields = (('_address_offset','addressOffset'),)

    def __init__(self, svd, parent):
        super().__init__(svd, parent)

        self._fields = []
        self._fieldmap = {}
        fsvd = svd.find('fields')

        if fsvd is not None:
            for f in fsvd.findall('field'):
                # Deal with derived fields when we actually find an
                # SVD with derived field.

                xx = f.attrib.get('derivedFrom',None)
                assert xx is None
                for ff in make_field(f, self):
                    self._fields.append(ff)
                    setattr(self, ff._name, ff)
                    self._fieldmap[ff._name] = ff

    @property
    def _address(self):
        return Int32(self._address_offset + self._parent._address)

    def _get(self):
        return Int32(self._gdb.read32(self._address))

    def _set(self, value):
        return self._gdb.write32(self._address, int(value))

    def _set_bit(self, bit):
        return self._gdb.set_bit(self._address, bit)

    def _clear_bit(self, bit):
        return self._gdb.clear_bit(self._address, bit)

    def _is_bit_set(self, bit):
        return self._gdb.is_bit_set(self._address, bit)

    def _repr_no_get(self):
        return super().__repr__()

    def __repr__(self):
        return self._repr_no_get()+' = '+repr(self._get())

    @property
    def _n(self):
        return self._get()

    @property
    def _child_regs(self):
        return [self]

    def _dump_repr(self):
        pad = ' '*12
        ret = pad+self._repr_no_get()+'\n'
        if self._description:
            for descline in textwrap.wrap(self._description.strip(),60):
                ret += pad+'| '+descline+'\n'
        v = self._get()
        vs = ''.join('   '+x for x in "%08x"%v)
        ret += "%s: 0x%s\n"%(self._address, vs)
        fs = self._fields[:]
        fs.sort(key=lambda x:x._bit_offset)
        fmaplines = []
        binary = format(v, '032b')
        fmaplines.append(binary)
        if fs:
            underlines = [' ']*len(binary)
            for f in fs:
                underlines[32-f._bit_offset-f._bit_width:32-f._bit_offset] = (
                    ['^'] * f._bit_width)
            fmaplines.append(''.join(underlines))

            for f_ind in range(len(fs)):
                f0 = fs[f_ind]
                frem = fs[f_ind+1:]

                nextline = [' ']*len(binary)
                nextline[32-f0._bit_offset-1:] = ['+']+(['-']*f0._bit_offset)
                for f in frem:
                    nextline[32-f._bit_offset-1] = '|'
                desc = f0._description or ''
                tmp = '%s = %r'%(f0._name,f0._get())
                fmaplines.append('%s %14s | %s'%(''.join(nextline),tmp,desc))
        fmaplines[0] = '0b'+fmaplines[0]
        fmaplines[1:] = ['  '+f for f in fmaplines[1:]]

        for fmapline in fmaplines:
            ret += pad+fmapline+'\n'

        ret += '\n'
        return ret

    def _dump(self):
        print(self._dump_repr())

class RegHaver():
    def __setattr__(self, attname, value):
        if hasattr(self, '_freezeattr'): # avoid recursion
            self._registermap[attname]._set(value)
        else:
            super().__setattr__(attname, value)

def regs_and_clusters(self, svd):

    self._registers = getattr(self, '_registers', [])
    self._registermap = getattr(self, '_registermap', {})
    self._clusters = getattr(self, '_clusters', [])

    if svd is None:
        return

    for r in svd.findall('register'):
        for rr in make_register(r, self):
            self._registers.append(rr)
            self._registermap[rr._name] = rr
            setattr(self, rr._name, rr)
            rr._freezeattr = True

    for c in svd.findall('cluster'):
        for cc in make_cluster(c, self):
            self._clusters.append(cc)
            setattr(self, cc._name, cc)
            cc._freezeattr = True

class Cluster(SvdObj, RegHaver):
    _intfields = (('_address_offset','addressOffset'),)

    def __init__(self, svd, parent):
        super().__init__(svd, parent)

        regs_and_clusters(self, svd)

    def __repr__(self):
        return repr(self._parent)+'.'+self._name

    @property
    def _address(self):
        return Int32(self._address_offset + self._parent._address)

    @property
    def _child_regs(self):
        ret = []
        for c in self._registers+self._clusters:
            ret.extend(c._child_regs)

        return ret

def fixup_eg_name(n):
    "asdf[%s] -> asdf, False otherwise"
    if n.endswith('[%s]'):
        return n[:-4]
    else:
        return False

def make_cls_or_array(svd, parent, cls):
    """If there is no dim, just create a new object and return it.
    If there is a plain dim like NAME[%s] then we need to return array-like.
    If there is a dimIndex defined, then we need to return a list.

    For convenience, we will *always* return a list, and the caller
    won't need special-case code to apply it.

    """

    dim = svd.find('dim')
    if dim is None:
        return [cls(svd, parent)]
    else:
        dim = int0(dim.text)
        dimIncrement = int0(svd.find('dimIncrement').text)

        di = svd.find('dimIndex')
        if di is not None:
            t = di.text.strip()
            if "," in t:
                dimIndex = t.split(',')
            elif "-" in t:
                first,last = t.split("-")
                dimIndex = [str(x) for x in range(int(first),1+int(last))]
        else:
            dimIndex = [str(x) for x in range(dim)]

        assert len(dimIndex) == dim

        objs = []
        for r in range(dim):
            obj = cls(svd, parent)
            if cls==Field:
                obj._bit_offset += r*dimIncrement
            else:
                obj._address_offset += r*dimIncrement
            obj._name %= dimIndex[r]
            obj._freezeattr = True
            objs.append(obj)

        trimmed_name = fixup_eg_name(svd.find('name').text)
        if trimmed_name:
            eg = ElementGroup(objs)
            eg._name = trimmed_name
            return [eg]
        else:
            return objs

def make_field(svd, parent):
    return make_cls_or_array(svd, parent, Field)

def make_cluster(svd, parent):
    return make_cls_or_array(svd, parent, Cluster)

def make_register(svd, parent):
    return make_cls_or_array(svd, parent, Register)

class Peripheral(RegHaver):
    def __init__(self, svd, parent):
        self._parent = parent
        self._gdb = parent._gdb
        self._update(svd)

    def _update(self, svd):
        self._svd = svd

        self._name = svd.findtext('name').strip()
        d = svd.find('description')
        if d is not None:
            self._description = d.text

        self._address = Int32(int0(svd.find('baseAddress').text))

        rsvd = svd.find('registers')

        regs_and_clusters(self, rsvd)

    def _copy(self):
        c = self.__class__(self._svd, self._parent)
        try:
            del c._freezeattr
        except AttributeError:
            pass
        assert c._registermap.keys() == self._registermap.keys()
        return c

    def __repr__(self):
        return repr(self._parent)+'.'+self._name

    @property
    def _child_regs(self):
        regs = []
        for c in self._registers + self._clusters:
            regs.extend(c._child_regs)

        regs.sort(key=lambda x:x._address)
        return regs

    def _dump(self, file=None):
        """ Pretty-printed look at all the registers in a peripheral """

        dump = '\n'.join([r._dump_repr() for r in self._child_regs])
        if file:
            file.write(dump)
        else:
            import pydoc
            pydoc.getpager()(dump)

class DebugInterface():
    """ Functions to interface from the device description to the gdb proxy object.
    Dummy object, subclass for more interesting object """
    verbose=False

    def setup_make_stub(self, svd_device):
        pass

    def read32(self, address):
        if self.verbose:
            print("Read from",repr(address))
        return Int32(0)

    def write32(self, address, val):
        if self.verbose:
            print("Write",val,"to",repr(address))
        pass

    def _set_bit_rmw(self, address, bit):
        x = self.read32(address)
        x |= (1<<bit)
        self.write32(address, x)

    def _clear_bit_rmw(self, address, bit):
        x = self.read32(address)
        x &= ~(1<<bit)
        self.write32(address, x)

    def set_bit(self, address, bit):
        return self._set_bit_rmw(address, bit)

    def clear_bit(self, address, bit):
        return self._clear_bit_rmw(address, bit)

    def is_bit_set(self, address, bit):
        return bool(self.read32(address) & (1<<bit))

    @property
    def target_name(self):
        return self.gdb.target_name

from . import gdb

def get_first_swd():
    import serial

    s=serial.Serial('/dev/ttyBmpGdb',timeout=0.3)
    target = gdb.Target(s)

    target.monitor('swd')
    target.attach(1)
    return target


class GdbInterface(DebugInterface):
    def __init__(self, gdb_):
        if gdb_ is None:
            gdb_ = get_first_swd()

        self.gdb = gdb_

    def setup_make_stub(self, svd_device):
        from . import make_stub
        self.make_stub = make_stub.MakeStub(svd_device)

    def read32(self, address):
        val = self.gdb.read32(address)
        if self.verbose:
            print("Read from",repr(address),"= %08x"%val)
        return val

    def read_mem(self, address, length):
        if self.verbose:
            print("Reading",length,"bytes from",repr(address))
        return self.gdb.read_mem(address, length)

    def write32(self, address, val):
        if self.verbose:
            print("Write %08x"%val,"to",repr(address))
        return self.gdb.write32(address, val)

    def write_mem(self, addr, data):
        if self.verbose:
            print("Writing",len(data),"bytes at",repr(address))
        return self.gdb_write(address, data)

    @property
    def target_name(self):
        return self.gdb.target_name

class Device():
    def __init__(self, xmlfilename, gdb=None):
        if gdb is None:
            gdb = DebugInterface()

        self._gdb = gdb

        # print(xmlfilename.split('/')[-1])
        tree = ET.parse(xmlfilename)
        root = tree.getroot()

        self._name = root.find('name').text.strip()

        c = root.find('cpu')
        if c is not None:
            self._cpu = CPU(root.find('cpu'), self)
        else:
            self._cpu = None

        svd = root.find('peripherals')

        self._peripherals = []
        for psvd in svd.findall('peripheral'):
            df = psvd.attrib.get('derivedFrom',None)
            if df:
                p = getattr(self, df)._copy()
                p._update(psvd)
            else:
                p = Peripheral(psvd, self)
            p._freezeattr = True
            setattr(self, p._name, p)
            self._peripherals.append(p)

        self._r=root
        self._gdb.setup_make_stub(self)

        self._pins = []

    def __repr__(self):
        return self._name

#d = Device('nrf52.svd')

if __name__=="__main__":
    import sys
    for arg in sys.argv[1:]:
        d = Device(arg)

        try:
            print(repr(d.TIM1)+'.OR at', d.TIM1.OR._address)
        except AttributeError:
            pass

        #del d
