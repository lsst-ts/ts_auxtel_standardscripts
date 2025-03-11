# This file is part of ts_auxtel_standardscripts
#
# Developed for the LSST Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import logging
import random
import unittest
from unittest.mock import AsyncMock

from lsst.ts import standardscripts
from lsst.ts.auxtel.standardscripts import DisableATAOSCorrections
from lsst.ts.observatory.control.auxtel.atcs import ATCS, ATCSUsages

random.seed(47)  # for set_random_lsst_dds_partition_prefix

logging.basicConfig()


class TestDisableATAOSCorrections(
    standardscripts.BaseScriptTestCase, unittest.IsolatedAsyncioTestCase
):

    async def basic_make_script(self, index):
        self.script = DisableATAOSCorrections(index=index)
        self.script.atcs = ATCS(
            domain=self.script.domain, intended_usage=ATCSUsages.DryTest
        )
        self.script.atcs.assert_all_enabled = AsyncMock()
        self.script.atcs.disable_ataos_corrections = AsyncMock()
        return (self.script,)

    async def test_configure_ignore(self):
        async with self.make_script():
            # Test ignore feature.
            await self.configure_script(ignore=["atmcs", "atpneumatics"])

            assert not self.script.atcs.check.atmcs
            assert not self.script.atcs.check.atpneumatics

    async def test_configure_ignore_not_atcs_component(self):
        async with self.make_script():
            # Test the ignore feature with one non-ATCS component.
            components = ["not_atcs_comp", "atmcs"]
            await self.configure_script(ignore=components)

            assert not hasattr(self.script.atcs.check, "not_atcs_comp")
            assert self.script.atcs.check.atmcs is False

    async def test_configure_ignore_fail(self):
        # Test the ignore_fail configuration.
        async with self.make_script():
            # Test default value for ignore_fail
            await self.configure_script()
            assert self.script.ignore_fail
            # Test configuring ingore_fail value
            config_values = [True, False]
            for test_value in config_values:
                await self.configure_script(ignore_fail=test_value)
                assert self.script.ignore_fail == test_value

    async def test_run(self):
        async with self.make_script():
            await self.configure_script()

            await self.run_script()
            self.script.atcs.assert_all_enabled.assert_awaited()
            self.script.atcs.disable_ataos_corrections.assert_awaited()


if __name__ == "__main__":
    unittest.main()
