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

from setuptools import setup

setup(
    name="runjail",
    version="0.1",
    description="Run commands in a sandboxed environment on Linux",
    url="https://github.com/debfx/runjail",
    author="Felix Geyer",
    author_email="debfx@fobos.de",
    license="GPL-3",
    packages=["runjail"],
    entry_points={
        "console_scripts": [
            "runjail = runjail.Main:main",
        ],
    }
)
