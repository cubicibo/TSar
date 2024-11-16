#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copyright (C) 2024 cibo
This file is part of TSar <https://github.com/cubicibo/TSar>.

TSar is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

TSar is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with TSar.  If not, see <http://www.gnu.org/licenses/>.
"""

import struct

from generics import *
from consts import AdaptationFieldControl

class ProgramClockReference(OptionalBlock):
    def size(self) -> int:
        return 6

    @property
    def base(self) -> int:
        return struct.unpack(">I", self.data[:4])[0] << 1 | (self.data[4] >> 7)

    @property
    def extension(self) -> int:
        return ((self.data[4] & 0x01) << 8) | self.data[5]

    def to_pcr(self) -> int:
        return self.extension + (self.base * 300)

    @classmethod
    def from_stc(cls, stc: int) -> 'ProgramClockReference':
        base = (stc/300) & ((1 << 33) - 1)
        extension = stc % 300
        ba = bytearray(b'\x00'*6)
        ba[:5] = struct.pack(">Q", base << 7)[3:]
        ba[5] = extension & 0xFF
        ba[4] |= (ba >> 8) & 0x01
        return ba

class TransportPrivateData(OptionalBlock):
    def size(self) -> int:
        return self.length + 1

    @property
    def length(self) -> int:
        return self.data[0]

    @property
    def payload(self) -> bytes:
        return self.data[1:self.length]

class AdaptationFieldExtension(OptionalBlock):
    def size(self) -> int:
        return self.data[0] + 1

#%%
class AdaptationField(OptionalBlock):
    def size(self) -> int:
        return self.length + 1

    @property
    def length(self) -> int:
        return self.data[0]

    @property
    def PCR_flag(self) -> bool:
        return (self.data[1] & 0x10) > 0

    @property
    def OPCR_flag(self) -> bool:
        return (self.data[1] & 0x08) > 0

    @property
    def splicing_point_flag(self) -> bool:
        return (self.data[1] & 0x04) > 0

    @property
    def transport_private_data_flag(self) -> bool:
        return (self.data[1] & 0x02) > 0

    @property
    def adaptation_field_extension_flag(self) -> bool:
        return (self.data[1] & 0x01) > 0

    def _offset_pcr(self) -> int:
        return 2

    def _offset_opcr(self) -> int:
        return 6*self.PCR_flag + self._offset_pcr()

    def _offset_splice_countdown(self) -> int:
        return 6*self.OPCR_flag + self._offset_opcr()

    def _offset_tprivdat(self) -> int:
        return 1*self.splicing_point_flag + self._offset_splice_countdown()

    @property
    @exist_if(PCR_flag)
    def program_clock_reference(self) -> ProgramClockReference:
        return ProgramClockReference(self.data[self._offset_pcr():])

    @property
    @exist_if(OPCR_flag)
    def original_program_clock_reference(self) -> ProgramClockReference:
        return ProgramClockReference(self.data[self._offset_opcr():])

    @property
    @exist_if(splicing_point_flag)
    def splice_countdown(self) -> int:
        return self.data[self._offset_splice_countdown()]

    @property
    @exist_if(transport_private_data_flag)
    def transport_private_data(self) -> TransportPrivateData:
        return TransportPrivateData(self.data[self._offset_tprivdat():])

    def _offset_afe(self) -> int:
        return self._offset_tprivdat() + (len(self.transport_private_data) if self.transport_private_data_flag else 0)

    @property
    @exist_if(adaptation_field_extension_flag)
    def adaptation_field_extension(self) -> AdaptationFieldExtension:
        return AdaptationFieldExtension(self.data[self._offset_afe():])

    def _offset_stuffing(self) -> int:
        return self._offset_afe() + (len(self.adaptation_field_extension) if self.adaptation_field_extension_flag else 0)

    @property
    def stuffing(self) -> bytes:
        off_stuff = self._offset_stuffing()
        len_stuff = self.length - off_stuff
        assert len_stuff >= 0
        assert not any(filter(lambda x: x != 0xFF, self.data[off_stuff:off_stuff+len_stuff]))
        return self.data[off_stuff:off_stuff+len_stuff]
####

#%%
class TSPacket:
    __slots__ = ("data")
    @classproperty
    def size(cls) -> int:
        return 188

    @classproperty
    def header_len(cls) -> int:
        return 0

    def __init__(self, data: bytes) -> None:
        assert len(data) >= __class__.size
        self.data = data[:__class__.size]
        assert self.sync_byte == ord(b'G')

    def __bytes__(self) -> bytes:
        return bytes(self.data)

    def __str__(self) -> str:
        return f"{self.PID:04X} {self.continuity_counter:1X}: PUSI={self.payload_unit_start_indicator:1} AFC={self.adaptation_field_control:1}"

    def __len__(self) -> int:
        return self.size

    def __getitem__(self, n: [int | slice]) -> int:
        return self.data[n]

    @property
    def sync_byte(self) -> int:
        return self.data[0]

    @property
    def transport_error_indicator(self) -> bool:
        return (self.data[1] & 0x80) > 0

    @property
    def payload_unit_start_indicator(self) -> bool:
        return (self.data[1] & 0x40) > 0

    @property
    def transport_priority(self) -> bool:
        return (self.data[1] & 0x20) > 0

    @property
    def PID(self) -> int:
        return ((self.data[1] & 0x1F) << 8) | self.data[2]

    @property
    def transport_scrambling_control(self) -> int:
        return self.data[3] >> 6

    @property
    def adaptation_field_control(self) -> int:
        return AdaptationFieldControl((self.data[3] >> 4) & 0b11)

    @property
    def continuity_counter(self) -> int:
        return self.data[3] & 0xF

    @property
    @exist_if(adaptation_field_control, lambda afc: AdaptationFieldControl.ADAPTATION in afc)
    def adaptation_field(self) -> AdaptationField:
        return AdaptationField(self.data[4:])

    @property
    @exist_if(adaptation_field_control, lambda afc: AdaptationFieldControl.PAYLOAD in afc)
    def payload(self) -> bytes:
        offset = 0 if self.adaptation_field is None else self.adaptation_field.size()
        return self.data[4 + offset:]
####

#%%
class M2TSPacket(TSPacket):
    __slots__ = ('tp_extra_header')

    @classproperty
    def size(cls) -> int:
        return 192

    @classproperty
    def header_len(cls) -> int:
        return 4

    def __init__(self, data: bytes):
        assert len(data) >= __class__.size
        super().__init__(data[4:__class__.size])
        self.tp_extra_header = data[:4]

    def to_tspacket(self) -> TSPacket:
        return TSPacket(self.data)

    def __bytes__(self) -> bytes:
        return bytes(self.tp_extra_header + self.data)

    @property
    def arrival_time_stamp(self) -> int:
        atc = self.tp_extra_header[0] & 0x3F
        for k in range(1, 4):
            atc = (atc << 8) + self.tp_extra_header[k]
        return atc

    @arrival_time_stamp.setter
    def arrival_time_stamp(self, atc: int) -> None:
        self.tp_extra_header[0] = (self.tp_extra_header[0] & 0xC0) | ((atc >> 24) & 0x3F)

        for k in range(1, 4):
            self.tp_extra_header[k] = (atc >> (24 - k*8)) & 0xFF

    @property
    def copy_permission_indicator(self) -> int:
        return self.tp_extra_header[0] >> 6

    @copy_permission_indicator.setter
    def copy_permission_indicator(self, cpi: int) -> None:
        self.tp_extra_header[0] = (self.tp_extra_header[0] & 0x3F) | ((cpi & 0b11) << 6)
####

#%%
# class ArbitraryPacket(TSPacket):
#     __slots__ = ('header', 'tail')
#     @property
#     def size(cls):
#         return self._size

#     @size.setter
#     def size(self, size: int) -> None:
#         self._size = size

#     @property
#     def header_len(self):
#         return self._header_len

#     @header_len.setter
#     def header_len(self, header_len: int) -> None:
#         self._header_len = header_len

#     def __call__(self, *args, **kwargs) -> ''

#     def __init__(self, data: bytes):
#         assert len(data) >= __class__.size
#         super().__init__(data[__class__.header_len:super().size+__class__.header_len])
#         self.header = data[:__class__.header_len]
#         self.tail = data[super().size+__class__.header_len:__class__.size]
