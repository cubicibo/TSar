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

from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from consts import AdaptationFieldControl
from streams import TransportStream, TSPacket
from pespacket import PESPacket

class Demux:
    def __init__(self, ts: TransportStream, excluded_pids: Optional[list[int]] = None) -> None:
        self.ts = ts
        self.excluded_pids = excluded_pids

    def index_streams(self, folder) -> None:
        pafg = PAFGenerator(folder)

        # PMT, SIT, PMP, PCR, null packet
        excluded_pids = [0x0000, 0x001F, 0x0100, 0x1001, 0x1FFF]
        if self.excluded_pids:
            excluded_pids += self.excluded_pids
        pck_buffer = dict()
        for tp in self.ts:
            if tp.PID in excluded_pids:
                continue
            assert tp.adaptation_field_control & AdaptationFieldControl.PAYLOAD
            pesp, cnt = __class__._proc_transport_packet(tp, pck_buffer)

            if cnt > 0:
                pafg.add_packet(tp.PID, pesp, cnt)
        
        for pid, lpck in pck_buffer.items():
            pesp = PESPacket(b''.join(map(lambda pib: pib.payload, lpck)))
            pafg.add_packet(pid, pesp, len(lpck))

    @staticmethod
    def _proc_transport_packet(tp: TSPacket, buffer: dict[int, list[TSPacket]]) -> Optional[tuple[PESPacket, int]]:
        ret = None, 0
        if tp.payload_unit_start_indicator and len(buffer.get(tp.PID, [])) > 0:
            tp_grp = buffer.pop(tp.PID)
            pesp = PESPacket(b''.join(map(lambda pib: pib.payload, tp_grp)))
            ret = (pesp, len(tp_grp))
        if buffer.get(tp.PID, None) is None:
            buffer[tp.PID] = []
        buffer[tp.PID].append(tp)
        return ret

# @dataclass
# class PIDDemuxCtx:
#     continuity_counter: int
#     last_tsp: bytes = b'\x00'*9

class PAFGenerator:
    #Packet Attributes File Generator
    def __init__(self, folder: [Path | str]) -> None:
        self._folder = Path(folder)
        assert self._folder.exists()
        self._pids = set()

    def add_packet(self, pid: int, packet: PESPacket, cnt: int) -> None:
        assert 0 <= pid <= 0x1FFF

        if pid not in self._pids:
            sequence = bytes([pid >> 8, pid & 0xFF])
            self._pids.add(pid)
            with open(self._folder.joinpath(f"{pid:04X}" + '.paf'), 'wb') as f:
                f.write(sequence)

        self.append_index_file(pid, packet, cnt)

    def append_index_file(self, pid: int, packet: PESPacket, cnt: int) -> None:
        assert packet.pts is not None
        
        if packet.dts is None:
            dts = packet.pts
        else:
            dts = packet.dts
        tsp = __class__.encode_pts_dts(packet.pts, dts)
        assert any(tsp)

        with open(self._folder.joinpath(f"{pid:04X}" + '.paf'), 'ab') as f:
            f.write((b'P' + tsp) * cnt)

    @staticmethod
    def encode_pts_dts(pts: int, dts: int) -> bytes:
        payload = bytearray(b'\x00'*9)
        # encode DTS MSBs.LSB
        payload[:4] = pack(">I", (dts >> 1) & ((1 << 32) - 1))

        # encode PTS as 40 bits, easier than the misaligned 33 bits.
        payload[4:9] = pack(">Q", (pts << 6) & ((1 << 39) - 1))[3:]
        payload[4] |= ((dts & 0x1) << 7)
        return payload