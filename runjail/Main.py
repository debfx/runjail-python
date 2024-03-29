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
import os
import sys

from runjail.Runjail import Options, Runjail


def error(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def get_defaults(runjail):
    defaults = { "ro": [],
                 "rw": ["/dev/null", "/dev/zero", "/dev/full", "/dev/random", "/dev/urandom", "/dev/tty", "/dev/pts", "/dev/ptmx"],
                 "hide": [],
                 "empty": ["/tmp", "/var/tmp", "/dev/shm", runjail.get_user_runtime_dir(), runjail.get_home_dir()],
                 "emptyro": ["/home", "/dev", "/run"],
                 "symlink": {} }

    for name in os.listdir("/"):
        path = "/" + name

        # ideally we'd mount a new sysfs but the kernel only allows this if we are admin of the network namespace

        if name in ("bin", "boot", "etc", "sbin", "selinux", "sys", "usr", "var", "mnt") or name.startswith("lib"):
            if os.path.islink(path):
                defaults["symlink"][path] = os.readlink(path)
            else:
                defaults["ro"].append(path)

    hide_if_exists = [ "/sys/fs/fuse" ]

    defaults["hide"].extend([path for path in hide_if_exists if os.path.exists(path)])

    return defaults


def main():
    runjail = Runjail()

    parser = argparse.ArgumentParser()
    parser.add_argument("--ro", action="append", default=[],
                        help="Mount file/directory from parent namespace read-only.")
    parser.add_argument("--rw", action="append", default=[],
                        help="Mount file/directory from parent namespace read-write.")
    parser.add_argument("--hide", action="append", default=[],
                        help="Make file/directory inaccessible.")
    parser.add_argument("--empty", action="append", default=[],
                        help="Mount tmpfs on the specified path.")
    parser.add_argument("--empty-ro", action="append", default=[], dest="emptyro",
                        help="Mount tmpfs on the specified path.")
    parser.add_argument("--cwd", default=os.getcwd(),
                        help="Set the current working directory.")
    parser.add_argument("--nonet", action="store_true",
                        help="Disable network access.")
    parser.add_argument("command", nargs="*", default=[runjail.get_user_shell()])
    args = parser.parse_args()

    defaults = get_defaults(runjail)

    user_mounts = { "ro": args.ro,
                    "rw": args.rw,
                    "hide": args.hide,
                    "empty": args.empty,
                    "emptyro": args.emptyro }
    user_mounts_all = []

    for category in ("ro", "rw", "hide", "empty", "emptyro"):
        user_mounts[category] = [Runjail.preprocess_path(mount) for mount in user_mounts[category]]
        # remove duplicates
        user_mounts[category] = list(set(user_mounts[category]))
        user_mounts_all.extend(user_mounts[category])

    for mount in user_mounts_all:
        if not os.path.exists(mount):
            error("Mountpoint \"{}\" doesn't exist.".format(mount))

    user_mounts_set = set()
    for mount in user_mounts_all:
        if mount.startswith("/runjail"):
            error("Mountpoint /runjail* is reserved for internal usage.")

        if mount in user_mounts_set:
            error("\"{}\" specified multiple times.".format(mount))
        user_mounts_set.add(mount)

        # user arguments override defaults
        for category in ("ro", "rw", "hide", "empty", "emptyro"):
            try:
                defaults[category].remove(mount)
            except ValueError:
                # is not in list, ignore
                pass

    for mount in user_mounts["ro"] + user_mounts["rw"] + user_mounts["empty"] + user_mounts["emptyro"]:
        for hide_mount in user_mounts["hide"] + defaults["hide"]:
            if mount.startswith(hide_mount + "/"):
                error("Can't mount \"{}\" since it's beneath hidden mountpoint \"{}\".".format(mount, hide_mount))

    options = Options(ro=defaults["ro"] + user_mounts["ro"],
                      rw=defaults["rw"] + user_mounts["rw"],
                      hide=defaults["hide"] + user_mounts["hide"],
                      empty=defaults["empty"] + user_mounts["empty"],
                      emptyro=defaults["emptyro"] + user_mounts["emptyro"],
                      symlink=defaults["symlink"],
                      cwd=args.cwd,
                      nonet=args.nonet)

    runjail.run(options, args.command)
