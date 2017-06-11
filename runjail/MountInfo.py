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
import re

from runjail.Libc import Libc

_MountInfoEntry = collections.namedtuple("MountInfoEntry",
                                         ["mount_id", "parent_id", "major_minor", "root",
                                          "mount_point", "mount_options", "optional_fields",
                                          "fs_type", "mount_source", "super_options"])


class MountInfoEntry(_MountInfoEntry):
    OPTION_FLAG_MAP = { "ro":          Libc.MS_RDONLY,
                        "noexec":      Libc.MS_NOEXEC,
                        "nosuid":      Libc.MS_NOSUID,
                        "nodev":       Libc.MS_NODEV,
                        "sync":        Libc.MS_SYNCHRONOUS,
                        "dirsync":     Libc.MS_DIRSYNC,
                        "silent":      Libc.MS_SILENT,
                        "mand":        Libc.MS_MANDLOCK,
                        "noatime":     Libc.MS_NOATIME,
                        "iversion":    Libc.MS_I_VERSION,
                        "nodiratime":  Libc.MS_NODIRATIME,
                        "relatime":    Libc.MS_RELATIME,
                        "strictatime": Libc.MS_STRICTATIME,
                        "lazytime":    Libc.MS_LAZYTIME }

    def __init__(self, *args):
        _MountInfoEntry.__init__(self, args)

    def get_mount_flags(self):
        flags = 0

        for option in self.mount_options.split(","):
            try:
                flags |= MountInfoEntry.OPTION_FLAG_MAP[option]
            except KeyError:
                # ignore unknown options
                pass

        return flags


class MountInfo:
    def __init__(self):
        self._mounts = []
        self._mountpoints = {}

        with open("/proc/self/mountinfo") as f:
            for line in f:
                fields = line.rstrip("\n").split(" ")
                fields = [MountInfo._unescape_field(field) for field in fields]
                index_dash = -1
                # field 6 until separator field ("-") are optional fields
                for i in range(6, len(fields)):
                    if fields[i] == "-":
                        index_dash = i
                if index_dash == -1:
                    raise RuntimeError("Missing optional fields separator.")
                entry = MountInfoEntry._make(fields[:6] + [fields[6:index_dash]] + fields[index_dash + 1:])
                self._mounts.append(entry)
                self._mountpoints[entry.mount_point] = entry

    def get_list(self):
        return self._mounts

    def get_mountpoint(self, path):
        return self._mountpoints[path]

    def has_mountpoint(self, path):
        return path in self._mountpoints

    @staticmethod
    def _octal_to_char(match):
        return chr(int(match.group(1), 8))

    @staticmethod
    def _unescape_field(field):
        return re.sub(r"\\(\d{1,3})", MountInfo._octal_to_char, field)
