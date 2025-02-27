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

from lsst.ts import salobj, standardscripts
from lsst.ts.auxtel.standardscripts import StandbyLATISS
from lsst.ts.observatory.control.mock import LATISSMock

random.seed(47)  # for set_random_lsst_dds_partition_prefix

logging.basicConfig()


class TestStandbyLATISS(
    standardscripts.BaseScriptTestCase, unittest.IsolatedAsyncioTestCase
):
    async def basic_make_script(self, index):
        self.script = StandbyLATISS(index=index)
        self.latiss_mock = LATISSMock()

        return (self.script, self.latiss_mock)

    async def test_components(self):
        async with self.make_script():
            for component in self.script.group.components_attr:
                with self.subTest(f"Check {component}", component=component):
                    if getattr(self.script.group.check, component):
                        assert component in self.script.components()

    async def test_run(self):
        async with self.make_script():
            await self.configure_script()

            await self.run_script()

            for comp in self.latiss_mock.components:
                with self.subTest(f"{comp} summary state", comp=comp):
                    assert (
                        getattr(
                            self.latiss_mock.controllers, comp
                        ).evt_summaryState.data.summaryState
                        == salobj.State.STANDBY
                    )


if __name__ == "__main__":
    unittest.main()
