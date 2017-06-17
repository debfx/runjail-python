# Copyright (C) 2017 Felix Geyer <debfx@fobos.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 or (at your option)
# version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import ctypes
import ctypes.util


class Pcap:
    def __init__(self):
        self._libcap = ctypes.CDLL(ctypes.util.find_library("cap"))
        self._libcap.cap_init.argtypes = []
        self._libcap.cap_init.restype = ctypes.c_void_p
        self._libcap.cap_clear.argtypes = [ctypes.c_void_p]
        self._libcap.cap_clear.restype = ctypes.c_int
        self._libcap.cap_set_proc.argtypes = [ctypes.c_void_p]
        self._libcap.cap_set_proc.restype = ctypes.c_int
        self._libcap.cap_free.argtypes = [ctypes.c_void_p]
        self._libcap.cap_free.restype = ctypes.c_int

        self._cap_p = self._libcap.cap_init()

    def __del__(self):
        self._libcap.cap_free(self._cap_p)

    def clear(self):
        self._libcap.cap_clear(self._cap_p)

    def set_proc(self):
        self._libcap.cap_set_proc(self._cap_p)
