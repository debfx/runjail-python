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

import sys

def helper_ro_read():
    print(open("data/ro/rofile").read())

def helper_ro_write():
    open("data/ro/write_test", "w")

def main():
    cmd = sys.argv[1]

    if cmd == "ro_read":
        helper_ro_read()
    elif cmd == "ro_write":
        helper_ro_write()
    else:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

# kate: space-indent on; indent-width 4;
