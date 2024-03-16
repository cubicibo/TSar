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

from typing import Optional, Any, Callable
from functools import wraps

from consts import *

STREAM_IDS_NO_PES_PACKET_HEADER = [0xBC, 0xBE, 0xBF, 0xF0, 0xF1, 0xF2, 0xF8, 0xFF]

def zero_if_empty(f):
    @wraps(f)
    def _impl(self) -> int:
        return f(self) if len(self.data) > 0 else 0
    return _impl

def none_if_empty(f):
    @wraps(f)
    def _impl(self) -> Optional[Any]:
        return f(self) if len(self.data) > 0 else None
    return _impl

def standard_stream(f):
    @wraps(f)
    def _impl(self) -> Optional[Any]:
        if self.stream_id not in STREAM_IDS_NO_PES_PACKET_HEADER:
            return f(self)
        return None
    return _impl

def standard_stream_offset(f):
    @wraps(f)
    def _impl(self) -> Optional[Any]:
        if self.stream_id not in STREAM_IDS_NO_PES_PACKET_HEADER:
            return f(self)
        return 0
    return _impl

def optional_property(f):
    return property(none_if_empty(f))

def standard_stream_property(f):
    return property(standard_stream(f))
####

def exist_if(flag: property, _filter: Callable[[Any], bool] = lambda flg: flg):
    def decorator(f):
        @wraps(f)
        def wrapper(self, *args, **kwargs):
            return f(self, *args, **kwargs) if _filter(flag.__get__(self, self.__class__)) else None
        return wrapper
    return decorator

# https://stackoverflow.com/a/7864317
class classproperty(property):
    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()
    def __set__(self, cls, value):
        return classmethod(self.fset).__set__(None, value)()

class OptionalBlock:
    __slots__ = 'data'
    def __init__(self, data: bytes) -> None:
        self.data = data
        if len(self.data):
            self.data = self.data[:self.size()]

    def __len__(self):
        return self.size()

    def size(self) -> int:
        raise NotImplementedError

####
