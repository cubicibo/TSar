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

import re
import numpy as np

from typing import Generator, Type, Optional, Callable
from pathlib import Path

from tspacket import TSPacket, M2TSPacket
from pespacket import PESPacket

#%%
class ArbitraryPacket:
    def __init__(self, header: int, footer: int) -> None:
        self.header = header
        self.footer = footer
    @property
    def size(self) -> int:
        return 188 + self.header + self.footer
    def identify(self) -> [int, int]:
        return self.header, self.footer
    @property
    def packet_class(self) -> Type[TSPacket]:
        return lambda b: TSPacket(b[self.header:self.header+188])

class ArbitraryTransportStream:
    def __init__(self, fpath: Path) -> None:
        self._fp = Path(fpath)
        self._fs_offset = 0
        self._pck_cls = None

        try:
            header, footer = self.identify()
        except:
            header = footer = None
        else:
            if header == 4 and 0 == footer:
                self.set_packet_class(M2TSPacket)
            elif header == 0 == footer:
                self.set_packet_class(TSPacket)
            else:
                self.set_packet_class(ArbitraryPacket(header, footer))

    def gen_packets(self) -> Generator[TSPacket, None, None]:
        file_hdl = open(self._fp, 'rb')
        file_hdl.seek(self._fs_offset)

        buffer = bytearray(file_hdl.read(0xFFFF))
        size_pck = self.packet_class.size
        while buffer:
            assert len(buffer) >= size_pck
            yield self.packet_class(buffer[:size_pck])
            buffer = buffer[size_pck:]
            if len(buffer) < size_pck:
                new_data = file_hdl.read(0xFFFF)
                if len(new_data) == 0:
                    break
                buffer += new_data
        assert len(buffer) == 0
        file_hdl.close()
        return

    def _file_writer_packets(self, packets: list[TSPacket], mode: str) -> None:
        assert mode in ['ab', 'wb']
        with open(self._fp, mode) as f:
            #Do not use b''.join, as that would duplicate the file in memory.
            for packet in packets:
                f.write(bytes(packet))

    def append_packet(self, packet: TSPacket) -> None:
        self._file_writer_packets([packet], 'ab')

    def append_packets(self, packets: list[TSPacket]) -> None:
        self._file_writer_packets(packets, 'ab')

    def write_packet(self, packet: TSPacket) -> None:
        self._file_writer_packets([packet], 'wb')

    def write_packets(self, packets: list[TSPacket]) -> None:
        self._file_writer_packets(packets, 'wb')

    def __iter__(self):
        self._gp = self.gen_packets()
        return self

    def __next__(self):
        return next(self._gp)

    def set_packet_class(self, pck_class: Type[TSPacket]) -> None:
        assert pck_class.size >= 188
        self._pck_cls = pck_class

    @property
    def packet_class(self) -> Type[TSPacket]:
        return self._pck_cls

    def identify(self) -> int:
        assert self._fp.exists()
        with open(self._fp, 'rb') as f:
            buffer = f.read(16384)

        possible_syncs = [m.start() for m in re.finditer(b'G', buffer)]
        assert len(possible_syncs), "no sync"
        syncs = np.asarray(possible_syncs)
        pck_size = int(np.median(np.abs(np.diff(syncs[:, None] - syncs))))

        footer = header = 0
        match pck_size:
            case 192:
                header = 4
            case 204:
                footer = 16

        syncs = set(possible_syncs)
        max_sync = possible_syncs[-1]//pck_size
        sync = next(filter(lambda s: syncs.issuperset(range(s, max_sync, pck_size)), possible_syncs))

        assert (file_offset := sync - header) >= 0
        self._fs_offset = file_offset
        return header, footer

    @property
    def path(self) -> Path:
        return Path(self._fp)

class TransportStream(ArbitraryTransportStream):
    def identify(self) -> int:
        ts_type = super().identify()
        if ts_type == (0, 0):
            return (0, 0)
        raise TypeError(f"TS packet properties mismatch: (header, footer)={ts_type}.")

    @property
    def packet_class(self) -> Type[TSPacket]:
        return TSPacket
    ####
####

class M2TransportStream(ArbitraryTransportStream):
    def identify(self) -> int:
        ts_type = super().identify()
        if (4, 0) == ts_type:
            return ts_type
        raise TypeError(f"TS packet properties mismatch: (header, footer)={ts_type}.")
    @property
    def packet_class(self) -> Type[M2TSPacket]:
        return M2TSPacket

    def gen_headerless_packet(self) -> Generator[TSPacket, None, None]:
        yield from map(lambda pck: TSPacket(pck.data), self.gen_packets())
    ####
####

#%%
#proto implementation, this should probably send the packet to individual TBs
class PIDFilter:
    def __init__(self, filter: Optional[Callable[[int], bool]] = None) -> None:
        assert filter is None or callable(filter)
        self._filter = (lambda x: True) if filter is None else filter
        assert isinstance(self._filter(0), (int, bool))

    def filter(self, packet: TSPacket) -> TSPacket:
        if self._filter(packet.PID):
            return packet

class Packetizer:
    def __init__(self, max_size: int = 32 << 10) -> None:
        self._max_size = max_size
        assert self._max_size > 0
        self._buffer = bytearray()

    def packetize(self) -> Generator[Optional[PESPacket], None, None]:
        tp = yield
        while tp is not None:
            pes_pck = None
            if tp.payload_unit_start_indicator:
                pes_pck = PESPacket(bytes(self._buffer))
                self._buffer.clear()
            self._buffer += tp.payload
            assert len(self._buffer) < self._max_size
            tp = yield pes_pck
        ####
        if len(self._buffer) > 0:
            try:
                yield PESPacket(self._buffer)
            except:
                ...
        return
    ####
