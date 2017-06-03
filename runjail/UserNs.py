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

import os
import sys

from runjail.Libc import Libc

class UserNs:
    def __init__(self):
        self._libc = Libc()
        # remember origina uid, changes when transitioning to new user ns
        self._uid = os.getuid()

    def create(self):
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

    def run(self, command, cwd=os.getcwd()):
        # move cwd to new mounts
        try:
            os.chdir(cwd)
        except FileNotFoundError:
            print("The current working directory '{}' doesn't exist in the new namespace.\nResetting to '/'.".format(cwd), file=sys.stderr)
            os.chdir("/")

        # drops all capabilities (if uid != 0)
        os.execvp(command[0], command)

    def mount_private_propagation(self, mountpoint):
        self._libc.mount("none", mountpoint, None, Libc.MS_REC | Libc.MS_PRIVATE)

    def mount_proc(self):
        self._libc.mount("proc", "/proc", "proc", Libc.MS_NOSUID | Libc.MS_NODEV | Libc.MS_NOEXEC)

    def remount_ro(self, path, existing_flags):
        self._libc.mount(path, path, None, existing_flags | Libc.MS_REC | Libc.MS_BIND | Libc.MS_REMOUNT | Libc.MS_RDONLY)

    def mount_inaccessible(self, path):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC, "mode=000")
        self.remount_ro(path, existing_flags=0)

    def mount_bind(self, source, target):
        self._libc.mount(source, target, None, Libc.MS_REC | Libc.MS_BIND)

    def mount_tmpfs(self, path, mode):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC | Libc.MS_NOSUID | Libc.MS_NOATIME, "mode=" + mode)

    def umount(self, path, flags=0):
        self._libc.umount2(path, flags)

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
