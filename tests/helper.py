#!/usr/bin/env python3

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

import sys


def helper_ro_read():
    print(open("data/ro/rofile").read())


def helper_ro_write():
    open("data/ro/write_test", "w")


def helper_rw_write():
    open("data/rw/write_test", "w").write("RWTESTDATA")


def helper_hide_read():
    open("data/hide/emptyfile", "r")


def helper_hide_write():
    open("data/hide/write_test", "w")


def helper_empty_read():
    open("data/empty/emptyfile", "r")


def helper_empty_write():
    open("data/empty/write_test", "w")


def helper_emptyro_read():
    open("data/emptyro/emptyrofile", "r")


def helper_emptyro_write():
    open("data/emptyro/write_test", "w")


def main():
    cmd = sys.argv[1]

    try:
        if cmd == "ro_read":
            helper_ro_read()
        elif cmd == "ro_write":
            helper_ro_write()
        elif cmd == "rw_write":
            helper_rw_write()
        elif cmd == "hide_read":
            helper_hide_read()
        elif cmd == "hide_write":
            helper_hide_write()
        elif cmd == "empty_read":
            helper_empty_read()
        elif cmd == "empty_write":
            helper_empty_write()
        elif cmd == "emptyro_read":
            helper_emptyro_read()
        elif cmd == "emptyro_write":
            helper_emptyro_write()
        else:
            sys.exit(1)
    except (OSError, FileNotFoundError) as e:
        sys.exit(3)

    sys.exit(0)


if __name__ == "__main__":
    main()
