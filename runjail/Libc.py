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
import errno
import sys


class Libc:
    CLONE_NEWIPC =  0x08000000
    CLONE_NEWNET =  0x40000000
    CLONE_NEWNS =   0x00020000
    CLONE_NEWPID =  0x20000000
    CLONE_NEWUSER = 0x10000000
    CLONE_NEWUTS =  0x04000000

    MNT_DETACH =    0x2

    MS_RDONLY =      0x00000001
    MS_NOSUID =      0x00000002
    MS_NODEV =       0x00000004
    MS_NOEXEC =      0x00000008
    MS_SYNCHRONOUS = 0x00000010
    MS_REMOUNT =     0x00000020
    MS_MANDLOCK =    0x00000040
    MS_DIRSYNC =     0x00000080
    MS_NOATIME =     0x00000400
    MS_NODIRATIME =  0x00000800
    MS_BIND =        0x00001000
    MS_MOVE =        0x00002000
    MS_REC =         0x00004000
    MS_SILENT =      0x00008000
    MS_POSIXACL =    0x00010000
    MS_UNBINDABLE =  0x00020000
    MS_PRIVATE =     0x00040000
    MS_SLAVE =       0x00080000
    MS_SHARED =      0x00100000
    MS_RELATIME =    0x00200000
    MS_KERNMOUNT =   0x00400000
    MS_I_VERSION =   0x00800000
    MS_STRICTATIME = 0x01000000
    MS_LAZYTIME =    0x02000000
    MS_ACTIVE =      0x40000000
    MS_NOUSER =      0x80000000

    PR_SET_NO_NEW_PRIVS = 38

    def __init__(self):
        self._lib = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

    def _to_c_string(self, string):
        if string is None:
            return None
        else:
            return ctypes.create_string_buffer(string.encode(sys.getdefaultencoding()))

    def _errno_exception(self):
        return OSError(ctypes.get_errno(), errno.errorcode[ctypes.get_errno()])

    def unshare(self, flags):
        if self._lib.unshare(flags) != 0:
            raise self._errno_exception()

    def mount(self, source, target, fstype, mountflags=0, data=None):
        result = self._lib.mount(self._to_c_string(source),
                                 self._to_c_string(target),
                                 self._to_c_string(fstype),
                                 mountflags,
                                 self._to_c_string(data))

        if result != 0:
            raise self._errno_exception()

    def umount2(self, target, flags):
        result = self._lib.umount2(self._to_c_string(target), flags)

        if result != 0:
            raise self._errno_exception()

    def chroot(self, path):
        result = self._lib.chroot(self._to_c_string(path))

        if result != 0:
            raise self._errno_exception()

    def prctl(self, option, arg2, arg3, arg4, arg5):
        result = self._lib.prctl(option, arg2, arg3, arg4, arg5)

        if result == -1:
            raise self._errno_exception()
        else:
            return result
