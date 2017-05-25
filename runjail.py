#!/usr/bin/python3

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
import errno
import os
import sys

class Libc:
    CLONE_NEWIPC =  0x08000000
    CLONE_NEWNS =   0x00020000
    CLONE_NEWPID =  0x20000000
    CLONE_NEWUSER = 0x10000000
    CLONE_NEWUTS =  0x04000000

    MS_NOATIME =    0x00400
    MS_BIND =       0x01000
    MS_NODEV =      0x00004
    MS_NOEXEC =     0x00008
    MS_NOSUID =     0x00002
    MS_PRIVATE =    0x40000
    MS_RDONLY =     0x00001
    MS_REC =        0x04000
    MS_REMOUNT =    0x00020

    def __init__(self):
        self._lib = ctypes.CDLL("libc.so.6", use_errno=True)

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

    def mount(self, source, target, fstype, mountflags = 0, data = None):
        result = self._lib.mount(self._to_c_string(source),
                                 self._to_c_string(target),
                                 self._to_c_string(fstype),
                                 mountflags,
                                 self._to_c_string(data))

        if result != 0:
            raise self._errno_exception()


class Runjail:
    def __init__(self, directory):
        self._libc = Libc()
        self._uid = os.getuid()
        self._dir = os.path.realpath(directory)

    def jail(self):
        if not os.path.isdir(self._dir):
            raise RuntimeError("Dir '{}' doesn't exist".format(path))

        self._libc.unshare(Libc.CLONE_NEWUSER | Libc.CLONE_NEWNS | Libc.CLONE_NEWPID | Libc.CLONE_NEWIPC)

        # fork is necessary in order to remount proc in the new PID namespace
        pid = os.fork()
        if pid != 0:
            # parent process:
            # wait for child and exit with its exit code
            _, status = os.waitpid(pid, 0)
            sys.exit(os.WEXITSTATUS(status))

        self.setup_user_mapping()

        self.mount_private_propagation("/")

        self.mount_tmpfs_ro("/run")
        os.makedirs("/run/runjail{}".format(self._dir), 0o700)
        self.mount_bind(self._dir, "/run/runjail{}".format(self._dir))

        self.mount_proc()

        self.mount_inaccessible("/root")

        self.mount_tmp("/tmp")
        self.mount_tmp("/var/tmp")

        os.makedirs("/run/user/{}".format(self._uid), 0o700)
        self.mount_tmpfs_rw("/run/user/{}".format(self._uid))

        self.mount_tmpfs_ro("/home")

        os.makedirs(self._dir, 0o700)
        self.mount_bind("/run/runjail{}".format(self._dir), self._dir)

        self.mount_inaccessible("/run/runjail")

    def run(self, command):
        # move cwd to new mounts
        os.chdir(self._dir)

        # drops all capabilities (if uid != 0)
        os.execvp(command[0], command)

    def mount_private_propagation(self, mountpoint):
        self._libc.mount("none", mountpoint, None, Libc.MS_REC | Libc.MS_PRIVATE)

    def mount_proc(self):
        self._libc.mount("proc", "/proc", "proc", Libc.MS_NOSUID | Libc.MS_NODEV | Libc.MS_NOEXEC)

    def mount_ro(self, path):
        self.mount_bind(path, path)
        self._libc.mount(path, path, None, Libc.MS_REC | Libc.MS_BIND | Libc.MS_REMOUNT | Libc.MS_RDONLY)

    def mount_inaccessible(self, path):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC, "mode=000")

    def mount_bind(self, source, target, readonly=False):
        self._libc.mount(source, target, None, Libc.MS_REC | Libc.MS_BIND)
        if readonly:
            # Linux doesn't support read-only bind mounts in a single mount() call
            self._libc.mount(source, target, None, Libc.MS_REC | Libc.MS_BIND | Libc.MS_REMOUNT | Libc.MS_RDONLY)

    def mount_tmpfs_ro(self, path):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC | Libc.MS_NOSUID | Libc.MS_NOATIME, "mode=550")

    def mount_tmpfs_rw(self, path):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC | Libc.MS_NOSUID | Libc.MS_NOATIME, "mode=750")

    def mount_tmp(self, path):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC | Libc.MS_NOSUID | Libc.MS_NOATIME, "mode=1777")

    def setup_user_mapping(self):
        """Map the uid/gid in the parent namespace to the same inside the new namespace."""

        with open("/proc/self/uid_map", "w") as f:
            f.write("{} {} 1\n".format(self._uid, self._uid))

        # set setgroups to "deny" so we are allowed to write to gid_map
        try:
            with open("/proc/self/setgroups", "w") as f:
                f.write("deny")
        except FileNotFoundError:
            # pre 3.19 kernels don't have this restriction, ignore
            pass

        with open("/proc/self/gid_map", "w") as f:
            f.write("{} {} 1\n".format(self._uid, self._uid))


def main():
    args = sys.argv[1:]
    if not args:
        args = [ "bash" ]

    runjail = Runjail(os.getcwd())
    runjail.jail()
    runjail.run(args)


if __name__ == "__main__":
    main()

# kate: space-indent on; indent-width 4;
