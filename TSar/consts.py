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

from enum import IntEnum, IntFlag
from typing import Optional, Any
from functools import wraps, cached_property
import struct

from generics import *

#US7844054B2
class COPY_PERMISSION(IntEnum):
    COPY_FREE = 0b00
    NO_MORE_COPY = 0b01
    COPY_ONCE = 0b10
    COPY_PROHIBITED = 0b11

class SCRAMBLING_CONTROL(IntEnum):
    NOT_SCRAMBLED = 0b00
    USER_DEFINED = 0b01
    USER_DEFINED_A = 0b10
    USER_DEFINED_B = 0b11

class AdaptationFieldControl(IntFlag):
    PAYLOAD = 0b01
    ADAPTATION = 0b10

class PTS_DTS_flags(IntFlag):
    DTS = 0b01
    PTS = 0b10

def __patch_enums():
    _ptsdts_new = PTS_DTS_flags.__new__
    def _new_ptsdts_flag(cls, value: int) -> PTS_DTS_flags:
        assert value & 0b11 != 0b01, "Illegal PTS_DTS_Flag"
        return _ptsdts_new(cls, value)
    PTS_DTS_flags.__new__ = _new_ptsdts_flag

    _afc_new = AdaptationFieldControl.__new__
    def _new_afc(cls, value: int) -> AdaptationFieldControl:
        assert value > 0, "Illegal adaptation_field_control"
        return _afc_new(cls, value)
    AdaptationFieldControl.__new__ = _new_afc
__patch_enums()

####
