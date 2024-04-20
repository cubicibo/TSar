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

from typing import Optional, Type
from generics import *
from consts import *

class PESPacket:
    __slots__ = 'data'
    def __init__(self, data: bytes) -> None:
        assert len(data) >= 6
        self.data = data
        assert self.packet_start_code_prefix == 0x000001
        #Video streams do not have to report a valid pes_packet_length
        if self.stream_id & 0xF0 != 0xE0:
            assert len(self.data) >= self.size()
            self.data = self.data[:self.size()]

    def __len__(self) -> int:
        return len(self.data)

    def size(self) -> int:
        if self.stream_id & 0xF0 != 0xE0:
            return self.pes_packet_length + 6
        return len(self.data)

    @property
    def packet_start_code_prefix(self) -> int:
        return (self.data[0] << 16) + (self.data[1] << 8) + self.data[2]

    @property
    def stream_id(self) -> int:
        return self.data[3]

    @property
    def pes_packet_length(self) -> int:
        return (self.data[4] << 8) + self.data[5]

    @standard_stream_property
    def pes_scrambling_control(self) -> int:
        assert (self.data[6] >> 6) == 0b10
        return (self.data[6] >> 4) & 0b11

    @standard_stream_property
    def pes_priority(self) -> bool:
        return (self.data[6] & 0x08) > 0

    @standard_stream_property
    def data_alignment_indicator(self) -> bool:
        return (self.data[6] & 0x04) > 0

    @standard_stream_property
    def copyright(self) -> bool:
        return (self.data[6] & 0x02) > 0

    @standard_stream_property
    def original_or_copy(self) -> bool:
        return (self.data[6] & 0x01) > 0

    @standard_stream_property
    def pts_dts_flags(self) -> int:
        return PTS_DTS_flags((self.data[7] >> 6) & 0b11)

    @standard_stream_property
    def escr_flag(self) -> bool:
        return (self.data[7] & 0x20) > 0

    @standard_stream_property
    def es_rate_flag(self) -> bool:
        return (self.data[7] & 0x10) > 0

    @standard_stream_property
    def dsm_trick_mode_flag(self) -> bool:
        return (self.data[7] & 0x08) > 0

    @standard_stream_property
    def additional_copy_info_flag(self) -> bool:
        return (self.data[7] & 0x04) > 0

    @standard_stream_property
    def pes_crc_flag(self) -> bool:
        return (self.data[7] & 0x02) > 0

    @standard_stream_property
    def pes_extension_flag(self) -> bool:
        return (self.data[7] & 0x01) > 0

    @standard_stream_property
    def pes_header_data_length(self) -> int:
        return self.data[8]

    @staticmethod
    def _parse_xts(data: bytes) -> int:
        xts = (data[0] & 0x0E) << 30
        xts |= (data[1] & 0xFF) << 22
        xts |= (data[2] & 0xFE) << 14
        xts |= (data[3] & 0xFF) << 7
        return xts | ((data[4] & 0xFE) >> 1)

    @standard_stream_property
    @exist_if(pts_dts_flags, lambda pdf: PTS_DTS_flags.PTS in pdf)
    def pts(self) -> int:
        assert PTS_DTS_flags.PTS & (self.data[9] >> 4)
        return __class__._parse_xts(self.data[9:14])

    @standard_stream_property
    @exist_if(pts_dts_flags, lambda pdf: PTS_DTS_flags.DTS in pdf)
    def dts(self) -> int:
        assert PTS_DTS_flags.PTS & (self.data[9] >> 4) > 0
        return __class__._parse_xts(self.data[14:19])

    @standard_stream_offset
    def _pts_dts_offset(self) -> int:
        return sum([5 for flag in PTS_DTS_flags if flag in self.pts_dts_flags])

    @standard_stream_offset
    def _escr_offset(self) -> int:
        return 6*self.escr_flag + self._pts_dts_offset()

    @standard_stream_offset
    def _es_rate_offset(self) -> int:
        return 3*self.escr_flag + self._escr_offset()

    @standard_stream_offset
    def _dsm_trick_mode_offset(self) -> int:
        return 1*self.dsm_trick_mode_flag + self._es_rate_offset()

    @standard_stream_offset
    def _additional_copy_info_offset(self) -> int:
        return 1*self.additional_copy_info_flag + self._dsm_trick_mode_offset()

    @standard_stream_offset
    def _previous_pes_packet_crc_offset(self) -> int:
        return 2*self.pes_crc_flag + self._additional_copy_info_offset()

    @standard_stream_offset
    def _pes_extension_offset(self) -> int:
        pes_ext = self.pes_extension
        return (0 if pes_ext is None else len(pes_ext)) + self._previous_pes_packet_crc_offset()

    @standard_stream_property
    @exist_if(escr_flag)
    def escr(self) -> int:
        raise NotImplementedError

    @standard_stream_property
    @exist_if(es_rate_flag)
    def es_rate(self) -> int:
        raise NotImplementedError

    @standard_stream_property
    @exist_if(additional_copy_info_flag)
    def additional_copy_info(self) -> int:
        raise NotImplementedError

    @standard_stream_property
    @exist_if(pes_crc_flag)
    def previous_pes_packet_crc(self) -> int:
        raise NotImplementedError

    @standard_stream_property
    @exist_if(pes_extension_flag)
    def pes_extension(self) -> int:
        offset = self._previous_pes_packet_crc_offset()
        length = 1
        length += 16 * bool(self.data[9+offset] & 0x80)
        if self.data[9+offset] & 0x40:
            length += self.data[9+offset+length] + 1
        length += 2 * bool(self.data[9+offset] & 0x20)
        length += 2 * bool(self.data[9+offset] & 0x10)
        if self.data[9+offset] & 0x01:
            assert self.data[9+offset+length] & 0x80
            length += 0x7F & self.data[9+offset+length]
        return self.data[9+offset:9+offset+length]

    @standard_stream_property
    def stuffing(self) -> bytes:
        start_idx = 9 + self._pes_extension_offset()
        stop_idx = 9 + self.pes_header_data_length
        assert stop_idx - start_idx >= 0
        assert all(map(lambda x: x == 0xFF, self.data[start_idx:stop_idx]))
        return self.data[start_idx:stop_idx]

    @property
    def packet_data(self) -> bytes:
        offs = 6
        if self.pes_scrambling_control is not None: #Standard stream
            offs += 3 + self._pes_extension_offset() + len(self.stuffing)
        return self.data[offs:]

    @property
    @exist_if(stream_id, lambda sid: sid == 0xBE)
    def padding(self) -> bytes:
        padding = self.data[6:6+self.pes_packet_length]
        assert len(padding) == len(self.pes_packet_length)
        assert all(map(lambda x: x==0xFF, padding))
        return padding
####
