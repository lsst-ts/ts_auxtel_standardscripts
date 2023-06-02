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
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import types
import unittest

from lsst.ts import salobj
from lsst.ts.idl.enums.MTM1M3 import BumpTest, DetailedState

from lsst.ts.standardscripts import get_scripts_dir
from lsst.ts.standardscripts import BaseScriptTestCase
from lsst.ts.standardscripts.maintel.m1m3 import CheckActuators


class TestCheckActuators(BaseScriptTestCase, unittest.IsolatedAsyncioTestCase):
    async def basic_make_script(self, index):
        self.script = CheckActuators(index=index, add_remotes=False)
        self.script.mtcs.run_m1m3_actuator_bump_test = unittest.mock.AsyncMock(
            side_effect=self.mock_test_bump
        )
        self.script.mtcs.stop_m1m3_bump_test = unittest.mock.AsyncMock()
        self.script.mtcs.enter_m1m3_engineering_mode = unittest.mock.AsyncMock()
        self.script.mtcs.exit_m1m3_engineering_mode = unittest.mock.AsyncMock()
        self.script.mtcs.assert_liveliness = unittest.mock.AsyncMock()
        self.script.mtcs.assert_all_enabled = unittest.mock.AsyncMock()
        self.script.mtcs.assert_m1m3_detailed_state = unittest.mock.AsyncMock()

        self.script.mtcs.get_m1m3_bump_test_status = unittest.mock.AsyncMock(
            side_effect=self.mock_get_m1m3_bump_test_status
        )

        self.script.mtcs.rem.mtm1m3 = unittest.mock.AsyncMock()
        self.script.mtcs.rem.mtm1m3.configure_mock(
            **{
                "evt_detailedState.aget": self.get_m1m3_detailed_state,
            }
        )

        self.bump_test_status = types.SimpleNamespace(
            testState=[BumpTest.NOTTESTED] * len(self.script.m1m3_actuator_ids)
        )

        return (self.script,)

    async def get_m1m3_detailed_state(self, *args, **kwags):
        return types.SimpleNamespace(detailedState=DetailedState.PARKED)

    # Side effects
    async def mock_test_bump(self, actuator_id, primary, secondary):
        await asyncio.sleep(0.5)
        actuator_index = self.script.mtcs.get_m1m3_actuator_index(actuator_id)
        self.bump_test_status.testState[actuator_index] = BumpTest.PASSED

    # Create a side effect function for mock_bump_test_status method from mcts
    # object. This function will be called when mock_bump_test_status method is
    # called
    async def mock_get_m1m3_bump_test_status(self, actuator_id):
        self.m1m3_bump_test_status = BumpTest.PASSED, BumpTest.PASSED
        return self.m1m3_bump_test_status

    async def test_configure_all(self):
        """Testing a valid configuration: all actuators"""

        # Configure with "all" actuators
        async with self.make_script():
            actuators = "all"

            await self.configure_script(actuators=actuators)

            assert self.script.actuators_to_test == self.script.m1m3_actuator_ids

    async def test_configure_valid_ids(self):
        """Testing a valid configuation: valid actuators ids"""

        # Try configure with a list of valid actuators ids
        async with self.make_script():
            actuators = [101, 210, 301, 410]

            await self.configure_script(
                actuators=actuators,
            )

            assert self.script.actuators_to_test == actuators

    async def test_configure_bad(self):
        """Testing an invalid configuration: bad actuators ids"""

        async with self.make_script():
            # Invalid actuators: 501 and 505
            actuators = [501, 505]

            # If actuators_bad_ids is not empty, it should raise a ValueError
            actuators_bad_ids = [
                actuator
                for actuator in actuators
                if actuator not in self.script.m1m3_actuator_ids
            ]
            if actuators_bad_ids:
                with self.assertRaises(salobj.ExpectedError):
                    await self.configure_script(
                        actuators=actuators_bad_ids,
                    )

    async def test_run(self):
        # Run the script
        async with self.make_script():
            actuators = "all"
            await self.configure_script(actuators=actuators)

            # Run the script
            await self.run_script()

            # Assert all passed on mocked bump test. Had to get indexes.
            actuators_to_test_index = [
                self.script.mtcs.get_m1m3_actuator_index(actuator_id)
                for actuator_id in self.script.actuators_to_test
            ]

            assert all(
                [
                    self.bump_test_status.testState[actuator_index] == BumpTest.PASSED
                    for actuator_index in actuators_to_test_index
                ]
            )
            # Expected awaint for assert_all_enabled method
            expected_awaits = len(self.script.actuators_to_test) + 1

            # Assert we await once for all mock methods defined above
            self.script.mtcs.enter_m1m3_engineering_mode.assert_awaited_once()
            self.script.mtcs.exit_m1m3_engineering_mode.assert_awaited_once()
            self.script.mtcs.assert_liveliness.assert_awaited_once()
            self.script.mtcs.assert_m1m3_detailed_state.assert_awaited_once()
            assert self.script.mtcs.assert_all_enabled.await_count == expected_awaits

            expected_calls = [
                unittest.mock.call(
                    actuator_id=actuator_id,
                    primary=True,
                    secondary=self.script.has_secondary_actuator(actuator_id),
                )
                for actuator_id in self.script.m1m3_actuator_ids
            ]

            self.script.mtcs.run_m1m3_actuator_bump_test.assert_has_calls(
                expected_calls
            )

    async def test_executable(self):
        scripts_dir = get_scripts_dir()
        script_path = scripts_dir / "maintel" / "m1m3" / "check_actuators.py"
        await self.check_executable(script_path)


if __name__ == "__main__":
    unittest.main()
