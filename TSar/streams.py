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

from abc import abstractproperty
from typing import Generator, Type, Optional, Callable
from pathlib import Path

from tspacket import TSPacket, M2TSPacket
from pespacket import PESPacket

#%%
class AbstractTransportStream:
    def __init__(self, fpath: Path) -> None:
        self._fp = Path(fpath)

    @abstractproperty
    def packet_class(self) -> Type[TSPacket]:
        raise NotImplementedError

    def gen_packets(self) -> Generator[TSPacket, None, None]:
        file_hdl = open(self._fp, 'rb')
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

####

class ArbitraryTransportStream(AbstractTransportStream):
    def __init__(self, fpath: Path) -> None:
        super().__init__(fpath)
        self._pck_cls = None

        try:    pck_overhead = self.identify()
        except: ...
        else:
            if pck_overhead == 4:
                self._pck_cls = M2TSPacket
            elif pck_overhead == 0:
                self._pck_cls = TSPacket

    def set_packet_class(self, pck_class: Type[TSPacket]) -> None:
        assert pck_class.size >= 188
        self._pck_cls = pck_class

    @property
    def packet_class(self) -> Type[TSPacket]:
        return self._pck_cls

    def gen_packets(self) -> Generator[TSPacket, None, None]:
        assert self._pck_cls is not None
        yield from super().gen_packets()

    def identify(self) -> tuple[Type[TSPacket], int]:
        assert self._fp.exists()
        with open(self._fp, 'rb') as f:
            buffer = f.read(16384)
        pck_overhead = buffer.find(b'G')
        assert pck_overhead >= 0, "Cannot find any sync byte in first kilobytes!"

        trials = 0
        while (trials := trials + 1) < 5:
            size_pck = 188 + pck_overhead
            cnt = hit = 0
            while (cnt := cnt + 1) < 4:
                hit += ord(b'G') == buffer[pck_overhead + cnt*size_pck]
            #aligned on sync bytes?
            if hit == cnt - 1:
                break
            else:
                pck_overhead = 1 + pck_overhead + buffer[pck_overhead+1:].find(b'G')
        assert trials < 5
        return pck_overhead

class TransportStream(AbstractTransportStream):
    @property
    def packet_class(self) -> Type[TSPacket]:
        return TSPacket
    ####
####

class M2TransportStream(AbstractTransportStream):
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
