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

import argparse
import collections
import ctypes
import enum
import errno
import os
import pwd
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

    def umount(self, target):
        result = self._lib.umount(self._to_c_string(target))

        if result != 0:
            raise self._errno_exception()


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

    def remount_ro(self, path):
        self._libc.mount(path, path, None, Libc.MS_REC | Libc.MS_BIND | Libc.MS_REMOUNT | Libc.MS_RDONLY)

    def mount_inaccessible(self, path):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC, "mode=000")

    def mount_bind(self, source, target, readonly=False):
        self._libc.mount(source, target, None, Libc.MS_REC | Libc.MS_BIND)
        if readonly:
            # Linux doesn't support read-only bind mounts in a single mount() call
            self._libc.mount(source, target, None, Libc.MS_REC | Libc.MS_BIND | Libc.MS_REMOUNT | Libc.MS_RDONLY)

    def mount_tmpfs(self, path, mode):
        self._libc.mount("tmpfs", path, "tmpfs", Libc.MS_REC | Libc.MS_NOSUID | Libc.MS_NOATIME, "mode=" + mode)

    def umount(self, path):
        self._libc.umount(path)

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


Options = collections.namedtuple("Options", ["ro", "rw", "hide", "empty", "emptyro", "cwd"])

class MountType(enum.Enum):
    RO = 1
    RW = 2
    HIDE = 3
    EMPTY = 4
    EMPTYRO = 5

Mount = collections.namedtuple("Mount", ["path", "type"])


class Runjail:
    TMP_MOUNT_BASE = "/run/runjail"

    def __init__(self):
        self._userns = UserNs()
        self._uid = os.getuid()
        self._pwd = pwd.getpwuid(self._uid)
        self._bind_mapping = {}
        self._bind_mapping_counter = 0

    def prepare_bind_mount(self, path):
        tmp_path = "{}/{}".format(self.TMP_MOUNT_BASE, self._bind_mapping_counter)
        self._bind_mapping[path] = tmp_path
        self._bind_mapping_counter += 1

        os.makedirs(tmp_path, 0o700)
        self._userns.mount_bind(path, tmp_path)

    def bind_mount(self, path, readonly):
        tmp_path = self._bind_mapping[path]
        os.makedirs(path, 0o700, exist_ok=True)
        self._userns.mount_bind(tmp_path, path, readonly)
        self._userns.umount(tmp_path)

    def rmdirs(self, path):
        for root, dirs, files in os.walk(path, topdown=False):
            for name in dirs:
                os.rmdir(os.path.join(root, name))

    def preprocess_path(self, path):
        return os.path.realpath(os.path.expanduser(path))

    def get_home_dir(self):
        try:
            return os.environ["HOME"]
        except KeyError:
            return self._pwd.pw_dir

    def get_user_shell(self):
        return self._pwd.pw_shell

    def get_user_id(self):
        return self._uid

    def run(self, options, command):
        mounts = []

        for path in options.ro:
            mounts.append(Mount(self.preprocess_path(path), MountType.RO))

        for path in options.rw:
            mounts.append(Mount(self.preprocess_path(path), MountType.RW))

        for path in options.hide:
            mounts.append(Mount(self.preprocess_path(path), MountType.HIDE))

        for path in options.empty:
            mounts.append(Mount(self.preprocess_path(path), MountType.EMPTY))

        for path in options.emptyro:
            mounts.append(Mount(self.preprocess_path(path), MountType.EMPTYRO))

        # make sure we handle parent paths before sub paths
        mounts.sort(key=lambda mount: mount.path)

        cwd = self.preprocess_path(options.cwd)

        self._userns.create()

        # hard-coded as we need /run/runjail for temporary bind mounts
        self._userns.mount_tmpfs("/run", "550")

        for mount in mounts:
            if mount.type is MountType.RO or mount.type is MountType.RW:
                self.prepare_bind_mount(mount.path)

        self._userns.mount_proc()

        for mount in mounts:
            if mount.type in (MountType.RO, MountType.RW):
                os.makedirs(mount.path, 0o700, exist_ok=True)
                # MountType.RO is remounted read-only later
                self.bind_mount(mount.path, readonly=False)
            elif mount.type is MountType.HIDE:
                self._userns.mount_inaccessible(mount.path)
            elif mount.type is MountType.EMPTY:
                os.makedirs(mount.path, 0o700, exist_ok=True)
                self._userns.mount_tmpfs(mount.path, "750")
            elif mount.type is MountType.EMPTYRO:
                os.makedirs(mount.path, 0o700, exist_ok=True)
                self._userns.mount_tmpfs(mount.path, "550")

        # we don't need to touch those anymore, so mount them actually read-only
        for mount in mounts:
            if mount.type in (MountType.RO, MountType.EMPTYRO):
                self._userns.remount_ro(mount.path)

        self.rmdirs(self.TMP_MOUNT_BASE)
        self._userns.remount_ro("/run")

        self._userns.run(command, cwd)


def main():
    runjail = Runjail()

    parser = argparse.ArgumentParser()
    parser.add_argument("--ro", action="append", default=[], help="Mount file/directory from parent namespace read-only.")
    parser.add_argument("--rw", action="append", default=[], help="Mount file/directory from parent namespace read-write.")
    parser.add_argument("--hide", action="append", default=[], help="Make file/directory inaccessible.")
    parser.add_argument("--empty", action="append", default=[], help="Mount tmpfs on the specified path.")
    parser.add_argument("--empty-ro", action="append", default=[], dest="emptyro", help="Mount tmpfs on the specified path.")
    parser.add_argument("--cwd", default=os.getcwd(), help="Set the current working directory.")
    parser.add_argument("command", nargs="*", default=[runjail.get_user_shell()])
    args = parser.parse_args()

    options = Options(ro=["/usr"] + args.ro,
                      rw=args.rw,
                      hide=["/root"] + args.hide,
                      empty=["/tmp", "/var/tmp", "/run/" + str(runjail.get_user_id()), runjail.get_home_dir()] + args.empty,
                      emptyro=["/home"] + args.emptyro,
                      cwd=args.cwd)

    runjail.run(options, args.command)


if __name__ == "__main__":
    main()

# kate: space-indent on; indent-width 4;
