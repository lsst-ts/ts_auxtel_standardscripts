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

import unittest

import pytest
from lsst.ts import salobj
from lsst.ts.auxtel.standardscripts.calibrations import RunCalibrationSequence
from lsst.ts.observatory.control.auxtel.atcalsys import ATCalsys, ATCalsysUsages
from lsst.ts.observatory.control.auxtel.latiss import LATISS, LATISSUsages
from lsst.ts.standardscripts import BaseScriptTestCase


class TestRunCalibrationSequence(BaseScriptTestCase, unittest.IsolatedAsyncioTestCase):

    async def basic_make_script(self, index):

        self.script = RunCalibrationSequence(index=index)

        self.script.latiss = LATISS(
            domain=self.script.domain,
            log=self.script.log,
            intended_usage=LATISSUsages.DryTest,
        )
        self.script.atcalsys = ATCalsys(
            domain=self.script.domain,
            log=self.script.log,
            intended_usage=ATCalsysUsages.DryTest,
        )

        return (self.script,)

    async def test_config(self):
        async with self.make_script():
            await self.configure_script(sequence_name="at_whitelight_r")
            assert self.script.sequence_name == "at_whitelight_r"

    async def test_config_fail_if_empty(self):
        async with self.make_script():
            with pytest.raises(salobj.ExpectedError):
                await self.configure_script()

    async def test_exposure_log_error_tracking(self):
        async with self.make_script():
            # Configure the script
            await self.configure_script(sequence_name="at_whitelight_r")

            error_atcalsys = ATCalsys(
                domain=self.script.domain,
                log=self.script.log,
                intended_usage=ATCalsysUsages.DryTest,
            )

            error_atcalsys.prepare_for_flat = unittest.mock.AsyncMock()

            async def mock_run_sequence(*args, **kwargs):
                await error_atcalsys.exposure_log.add_entry(
                    "exposure_1",
                    {
                        "wavelength": 650.0,
                        "status": "success",
                        "electrometer_status": "success",
                        "fiber_spectrum_status": "success",
                    },
                )
                await error_atcalsys.exposure_log.add_entry(
                    "exposure_2",
                    {
                        "wavelength": 660.0,
                        "status": "failed",
                        "error_message": "Failed to take exposure",
                        "electrometer_status": "timeout",
                        "electrometer_error_message": "AckTimeoutError: Command timed out",
                    },
                )

                return {
                    "sequence_name": "at_whitelight_r",
                    "steps": [
                        {"wavelength": 650.0, "latiss_exposure_info": {"exp1": {}}},
                        {"wavelength": 660.0, "latiss_exposure_info": {}},
                    ],
                }

            error_atcalsys.run_calibration_sequence = mock_run_sequence

            self.script.atcalsys = error_atcalsys

            self.script.publish_sequence_summary = unittest.mock.AsyncMock()

            await self.script.run_block()

            assert "exposure_log" in self.script.sequence_summary
            assert len(self.script.sequence_summary["exposure_log"]) == 2

            success_entry = next(
                entry
                for entry in self.script.sequence_summary["exposure_log"]
                if entry["exposure_id"] == "exposure_1"
            )
            assert success_entry["status"] == "success"

            error_entry = next(
                entry
                for entry in self.script.sequence_summary["exposure_log"]
                if entry["exposure_id"] == "exposure_2"
            )
            assert error_entry["status"] == "failed"
            assert "error_message" in error_entry
            assert error_entry["electrometer_status"] == "timeout"
            assert "AckTimeoutError" in error_entry["electrometer_error_message"]
