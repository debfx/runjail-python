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

import os
import subprocess
import sys
import unittest

class RunjailTest(unittest.TestCase):
    def test_ro_read(self):
        self.assertEqual(self.run_helper(["--ro=tests/data/ro"], "ro_read"), "ROTESTDATA")

    def test_ro_write(self):
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.run_helper(["--ro=tests/data/ro"], "ro_write")
        self.assertEqual(cm.exception.returncode, 3)

    def test_rw_write(self):
        self.run_helper(["--rw=tests/data/rw"], "rw_write")
        with open("tests/data/rw/write_test") as f:
            data = f.read().strip("\r\n\t ")
        self.assertEqual(data, "RWTESTDATA")

    def test_hide_read(self):
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.run_helper(["--hide=tests/data/hide"], "hide_read")
        self.assertEqual(cm.exception.returncode, 3)

    def test_hide_write(self):
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.run_helper(["--hide=tests/data/hide"], "hide_write")
        self.assertEqual(cm.exception.returncode, 3)

    def test_empty_read(self):
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.run_helper(["--empty=tests/data/empty"], "empty_read")
        self.assertEqual(cm.exception.returncode, 3)

    def test_empty_write(self):
        self.run_helper(["--empty=tests/data/empty"], "empty_write")

    def test_emptyro_read(self):
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.run_helper(["--empty-ro=tests/data/emptyro"], "emptyro_read")
        self.assertEqual(cm.exception.returncode, 3)

    def test_emptyro_write(self):
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.run_helper(["--empty-ro=tests/data/emptyro"], "emptyro_write")
        self.assertEqual(cm.exception.returncode, 3)

    @classmethod
    def tearDownClass(cls):
        RunjailTest.try_remove("tests/data/rw/write_test")

    @classmethod
    def try_remove(cls, path):
        if os.path.exists(path):
            os.remove(path)

    def run_helper(self, args, cmd):
        result = subprocess.check_output(["./runjail.py"] + args + ["--ro=tests", "--cwd=tests", "--", "./helper.py", cmd],
                                         universal_newlines=True)
        return result.strip("\r\n\t ")

if __name__ == '__main__':
    os.chdir(os.path.dirname(sys.argv[0]))

    unittest.main()

# kate: space-indent on; indent-width 4;
