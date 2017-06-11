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

import collections
import enum
import os
import pwd
import re
import tempfile

from runjail.Libc import Libc
from runjail.MountInfo import MountInfo
from runjail.UserNs import UserNs

Options = collections.namedtuple("Options", ["ro", "rw", "hide", "empty", "emptyro", "cwd", "nonet"])


class MountType(enum.Enum):
    RO = 1
    RW = 2
    HIDE = 3
    EMPTY = 4
    EMPTYRO = 5


Mount = collections.namedtuple("Mount", ["path", "type"])


class Runjail:
    def __init__(self):
        self._uid = os.getuid()
        self._pwd = pwd.getpwuid(self._uid)
        self._bind_mapping = {}
        self._bind_mapping_counter = 0
        self._mount_base = tempfile.mkdtemp(prefix="runjail")
        self._mount_hide_base = self._mount_base + "/runjail-hide"
        self._mount_hide_dir = self._mount_hide_base + "/dir"
        self._mount_hide_file = self._mount_hide_base + "/file"
        self._userns = UserNs(self._mount_base)

    def create_file(self, path, mode):
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT, mode))

    def init_hide_mounts(self):
        os.mkdir(self._mount_hide_base, 0o500)
        os.mkdir(self._mount_hide_dir, 0o000)
        self.create_file(self._mount_hide_file, 0o000)

    def bind_mount(self, path, read_only):
        abs_target_path = self._mount_base + path

        if os.path.isdir(path):
            os.makedirs(abs_target_path, 0o700, exist_ok=True)
        else:
            os.makedirs(self._mount_base + os.path.dirname(path), 0o700, exist_ok=True)
            if not os.path.exists(abs_target_path):
                self.create_file(abs_target_path, 0o600)

        if not read_only:
            self._userns.mount_bind(path, abs_target_path)
        else:
            mount_info_before = MountInfo()
            self._userns.mount_bind(path, abs_target_path)
            mount_info_after = MountInfo()

            # remount submounts read-only
            for mount in mount_info_after.get_list():
                if not mount_info_before.has_mountpoint(mount.mount_point):
                    self._userns.remount_ro(mount.mount_point,
                                            mount_info_after.get_mountpoint(mount.mount_point).get_mount_flags())

    @staticmethod
    def preprocess_path(path):
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

    def get_user_runtime_dir(self):
        return "/run/" + str(self.get_user_id())

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

        self._userns.create(new_net=options.nonet)
        self._userns.mount_tmpfs(self._mount_base, "550")

        os.mkdir(self._mount_base + "/proc", 0o550)
        self._userns.mount_proc(self._mount_base + "/proc")

        self.init_hide_mounts()

        for mount in mounts:
            abs_mount_path = self._mount_base + mount.path

            if mount.type is MountType.RO:
                self.bind_mount(mount.path, read_only=True)
            elif mount.type is MountType.RW:
                self.bind_mount(mount.path, read_only=False)
            elif mount.type is MountType.HIDE:
                if os.path.isdir(abs_mount_path):
                    os.makedirs(abs_mount_path, 0o700, exist_ok=True)
                    self._userns.mount_bind(self._mount_hide_dir, abs_mount_path)
                    self._userns.remount_ro(abs_mount_path, 0)
                else:
                    if not os.path.exists(abs_mount_path):
                        self.create_file(abs_mount_path, 0o000)
                    self._userns.mount_bind(self._mount_hide_file, abs_mount_path)
                    self._userns.remount_ro(abs_mount_path, 0)
            elif mount.type is MountType.EMPTY:
                os.makedirs(abs_mount_path, 0o700, exist_ok=True)
                self._userns.mount_tmpfs(abs_mount_path, "750")
            elif mount.type is MountType.EMPTYRO:
                os.makedirs(abs_mount_path, 0o700, exist_ok=True)
                # is later remounted read-only
                self._userns.mount_tmpfs(abs_mount_path, "550")

        mount_info = MountInfo()

        for mount in mounts:
            mount_path = self._mount_base + mount.path

            if mount.type is MountType.EMPTYRO:
                self._userns.remount_ro(mount_path,
                                        mount_info.get_mountpoint(mount_path).get_mount_flags())

        self._userns.remount_ro(self._mount_base, mount_info.get_mountpoint(self._mount_base).get_mount_flags())

        self._userns.set_no_new_privs()
        self._userns.run(command, cwd)
