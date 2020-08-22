# This file is part of ts_standardscripts
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

import logging
import random
import unittest
import asynctest

from lsst.ts import salobj
from lsst.ts import standardscripts
from lsst.ts.standardscripts.auxtel import EnableATTCS
from lsst.ts.observatory.control.mock import ATCSMock

random.seed(47)  # for set_random_lsst_dds_domain

logging.basicConfig()


class TestEnableATTCS(standardscripts.BaseScriptTestCase, asynctest.TestCase):
    async def basic_make_script(self, index):
        self.script = EnableATTCS(index=index)
        self.atcs_mock = ATCSMock()

        return (self.script, self.atcs_mock)

    async def test_run(self):
        async with self.make_script():
            await self.configure_script()

            await self.run_script()

            for comp in self.script.group.components:
                with self.subTest(f"{comp} summary state", comp=comp):
                    self.assertEqual(
                        getattr(
                            self.atcs_mock.controllers, comp
                        ).evt_summaryState.data.summaryState,
                        salobj.State.ENABLED,
                    )

    async def test_components(self):
        async with self.make_script():
            for component in self.script.group.components:
                with self.subTest(f"Check {component}", comp=component):
                    if getattr(self.script.group.check, component):
                        self.assertIn(component, self.script.components())

    async def test_executable(self):
        scripts_dir = standardscripts.get_scripts_dir()
        script_path = scripts_dir / "auxtel" / "enable_atcs.py"
        await self.check_executable(script_path)


if __name__ == "__main__":
    unittest.main()
