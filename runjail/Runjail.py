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
    TMP_MOUNT_BASE =      "/run/runjail"
    TMP_MOUNT_HIDE_BASE = "/run/runjail-hide"
    TMP_MOUNT_HIDE_DIR =  TMP_MOUNT_HIDE_BASE + "/dir"
    TMP_MOUNT_HIDE_FILE = TMP_MOUNT_HIDE_BASE + "/file"

    def __init__(self):
        self._userns = UserNs()
        self._uid = os.getuid()
        self._pwd = pwd.getpwuid(self._uid)
        self._bind_mapping = {}
        self._bind_mapping_counter = 0
        self._bind_submounts = {}

    def create_file(self, path, mode):
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT, mode))

    def init_bind_mounts(self):
        os.mkdir(self.TMP_MOUNT_BASE, 0o700)

        os.mkdir(self.TMP_MOUNT_HIDE_BASE, 0o500)
        os.mkdir(self.TMP_MOUNT_HIDE_DIR, 0o000)
        self.create_file(self.TMP_MOUNT_HIDE_FILE, 0o000)

    def prepare_bind_mount(self, path):
        tmp_path = "{}/{}".format(self.TMP_MOUNT_BASE, self._bind_mapping_counter)
        self._bind_mapping[path] = tmp_path
        self._bind_mapping_counter += 1

        if os.path.isdir(path):
            os.mkdir(tmp_path, 0o700)
        else:
            self.create_file(tmp_path, 0o600)
        self._userns.mount_bind(path, tmp_path)

    def populate_bind_submounts(self):
        for path in self._bind_mapping.values():
            self._bind_submounts[path] = []

        # Get a list of sub-mounts beneath the bind-mounted paths.
        # We need to keep track of those so we can remount them read-only later.
        for mount in MountInfo().get_list():
            match = re.search(r"^(" + re.escape(self.TMP_MOUNT_BASE) + r"/\d+)(/.+)$", mount.mount_point)
            if match:
                tmp_path = match.group(1)
                sub_mount = match.group(2)
                self._bind_submounts[tmp_path].append(sub_mount)

    def bind_mount(self, path):
        tmp_path = self._bind_mapping[path]
        if os.path.isdir(tmp_path):
            os.makedirs(path, 0o700, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(path), 0o700, exist_ok=True)
            if not os.path.exists(path):
                self.create_file(path, 0o600)

        self._userns.mount_bind(tmp_path, path)
        self._userns.umount(tmp_path, Libc.MNT_DETACH)

    def cleanup_bind_mounts(self):
        # Before we start deleting stuff, check that there is no mount left.
        # Needs to be a separate loop as the deleting happens bottom up.
        for root, dirs, files in os.walk(self.TMP_MOUNT_BASE):
            for name in files + dirs:
                path = os.path.join(root, name)
                if os.path.ismount(path):
                    raise RuntimeError(path + " is still mounted.")

        for root, dirs, files in os.walk(self.TMP_MOUNT_BASE, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))

            for name in dirs:
                os.rmdir(os.path.join(root, name))

        os.rmdir(self.TMP_MOUNT_BASE)

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

        # hard-coded as we need /run/runjail for temporary bind mounts
        self._userns.mount_tmpfs("/run", "550")
        self.init_bind_mounts()

        for mount in mounts:
            if mount.type is MountType.RO or mount.type is MountType.RW:
                self.prepare_bind_mount(mount.path)

        self._userns.mount_proc()
        self.populate_bind_submounts()

        for mount in mounts:
            if mount.type in (MountType.RO, MountType.RW):
                # MountType.RO is remounted read-only later
                self.bind_mount(mount.path)
            elif mount.type is MountType.HIDE:
                if os.path.isdir(mount.path):
                    self._userns.mount_bind(self.TMP_MOUNT_HIDE_DIR, mount.path)
                    self._userns.remount_ro(mount.path, 0)
                else:
                    self._userns.mount_bind(self.TMP_MOUNT_HIDE_FILE, mount.path)
                    self._userns.remount_ro(mount.path, 0)
            elif mount.type is MountType.EMPTY:
                os.makedirs(mount.path, 0o700, exist_ok=True)
                self._userns.mount_tmpfs(mount.path, "750")
            elif mount.type is MountType.EMPTYRO:
                os.makedirs(mount.path, 0o700, exist_ok=True)
                self._userns.mount_tmpfs(mount.path, "550")

        mount_info = MountInfo()

        # we don't need to touch those anymore, so mount them actually read-only
        for mount in mounts:
            if mount.type in (MountType.RO, MountType.EMPTYRO):
                remount_ro_paths = [mount.path]

                # remount sub-mounts read-only
                if mount.type == MountType.RO:
                    tmp_path = self._bind_mapping[mount.path]
                    for submount_path in self._bind_submounts[tmp_path]:
                        remount_ro_paths.append(mount.path + submount_path)

                for mount_path in remount_ro_paths:
                    self._userns.remount_ro(mount_path,
                                            mount_info.get_mountpoint(mount_path).get_mount_flags())

        self.cleanup_bind_mounts()
        self._userns.remount_ro("/run", mount_info.get_mountpoint("/run").get_mount_flags())
        # ideally we'd mount a new sysfs but the kernel only allows this if we are admin of the network namespace
        self._userns.remount_ro("/sys", mount_info.get_mountpoint("/sys").get_mount_flags())

        self._userns.set_no_new_privs()
        self._userns.run(command, cwd)
