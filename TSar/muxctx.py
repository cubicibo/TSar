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
from typing import Optional, ContextManager, Generator
from contextlib import nullcontext
from dataclasses import dataclass
import struct

from consts import AdaptationFieldControl
from streams import TransportStream, TSPacket
from pespacket import PESPacket

@dataclass
class PacketAttribute:
    tp_count: int
    pck_size: int
    pts: int
    dts: Optional[int] = None
    
    @classmethod
    def from_pa(cls, bstr: bytes) -> 'PacketAttribute':
        assert bstr[0] == 80 and len(bstr) >= 15
        tp_cnt, pck_size = struct.unpack(">HI", bstr[1:7])
        dts, pts = cls._decode_timestamps(bstr[6:15])
        return cls(tp_cnt, pck_size >> 8, pts, dts)
        
    @staticmethod
    def _decode_timestamps(tc_string) -> tuple[int, int]:
        dts = (struct.unpack(">I", tc_string[:4])[0]) << 1
        dts += (tc_string[4] >> 7)

        # PTS has 39 bits, whom 6 are unused, so we assume 33 bits.
        pts = (tc_string[4] & 0x7F) << 32
        pts += struct.unpack(">I", tc_string[5:])[0]
        return dts, (pts >> 6)
####

#%%
class PAF:
    def __init__(self, fp: Path) -> None:
        self._fp = Path(fp)
        assert self._fp.exists()
        self._pid = None
    
    @property
    def pid(self) -> int:
        return self._pid
    
    def gen_packet_attribute(self) -> Generator[PacketAttribute, None, None]:
        """
        Yields packet attributes from the PA collection in the file.
        """
        with open(self._fp, 'rb') as f:
            buffer = f.read(0x7FFF)
            
            self._pid, header = __class__._read_header(buffer)
            assert 0 < self._pid < 0x1FFF, "Bad file header."
            buffer = buffer[2+1+len(header):]
            
            while buffer:
                yield PacketAttribute.from_pa(buffer[:15])
                buffer = buffer[15:]
                if len(buffer) < 15:
                    buffer += f.read(0x7FFF)
                    assert len(buffer) >= 15 or len(buffer) == 0
        ####
    
    @staticmethod
    def _read_header(buffer: bytes) -> tuple[int, bytes]:
        assert len(buffer) > 2 and len(buffer) > buffer[2]
        pid = struct.unpack(">H", buffer[:2])[0]
        header = buffer[3:3+buffer[2]]
        return pid, header
        
        
    def __iter__(self):
        self._gp = self.gen_packets()
        return self

    def __next__(self):
        return next(self._gp)
####

#%%%
class Demux:
    def __init__(self, ts: TransportStream, excluded_pids: Optional[list[int]] = None) -> None:
        self.ts = ts
        self.excluded_pids = excluded_pids

    def index_streams(self, folder, pbar: ContextManager = nullcontext()) -> None:
        pafg = PAFGenerator(folder)

        # PMT, SIT, PMP, PCR, null packet
        excluded_pids = [0x0000, 0x001F, 0x0100, 0x1001, 0x1FFF]
        if self.excluded_pids:
            excluded_pids += self.excluded_pids
        pck_buffer = dict()
        
        if getattr(pbar, 'update', None) is None:
            pbar.update = lambda *args, **kwargs: None
        with pbar:
            for tp in self.ts:
                if tp.PID in excluded_pids:
                    continue
                assert tp.adaptation_field_control & AdaptationFieldControl.PAYLOAD
                pesp, cnt = __class__._proc_transport_packet(tp, pck_buffer)
    
                if cnt > 0:
                    pafg.add_packet(tp.PID, pesp, cnt)
                pbar.update()
        for pid, lpck in pck_buffer.items():
            pesp = PESPacket(b''.join(map(lambda pib: pib.payload, lpck)))
            pafg.add_packet(pid, pesp, len(lpck))
    ####

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
####

#%%
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
                f.write(sequence + b'\x00')

        self.append_index_file(pid, packet, cnt)

    def append_index_file(self, pid: int, packet: PESPacket, cnt: int) -> None:
        assert packet.pts is not None
        
        if packet.dts is None:
            dts = packet.pts
        else:
            dts = packet.dts
        temporal = __class__.encode_pts_dts(packet.pts, dts)
        assert any(temporal), "Zero PTS and DTS is illegal."

        with open(self._folder.joinpath(f"{pid:04X}" + '.paf'), 'ab') as f:
            spatial = struct.pack(">H", cnt) + struct.pack(">I", len(packet))[1:]
            f.write((b'P' + spatial + temporal))

    @staticmethod
    def encode_pts_dts(pts: int, dts: int) -> bytes:
        payload = bytearray(b'\x00'*9)
        # encode DTS MSBs.LSB
        payload[:4] = struct.pack(">I", (dts >> 1) & ((1 << 32) - 1))

        # encode PTS as 40 bits, easier than the misaligned 33 bits.
        payload[4:9] = struct.pack(">Q", (pts << 6) & ((1 << 39) - 1))[3:]
        payload[4] |= ((dts & 0x1) << 7)
        return payload
####

#%%
# class Mux:
#     def __init__(self, index_folder: Path, input_ts: Path) -> None:
#         self._index_fp = Path(index_folder)
#         assert self._if.exists()
        
#         self._input_ts = Path(input_ts)
#         assert self._input_ts.exists()
