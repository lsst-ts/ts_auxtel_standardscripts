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

import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from lsst.ts import standardscripts, utils
from lsst.ts.auxtel.standardscripts.prepare_for import PrepareForVent
from lsst.ts.auxtel.standardscripts.prepare_for.vent import (
    FAN_TARGET_FREQUENCY,
    VENT_GATE_INDEX,
    WIND_AVERAGE_WINDOW,
    WIND_SPEED_THRESHOLD,
)
from lsst.ts.observatory.control.mock import ATCSMock


class TestPrepareForOnSky(
    standardscripts.BaseScriptTestCase, unittest.IsolatedAsyncioTestCase
):
    async def basic_make_script(self, index):
        self.script = PrepareForVent(index=index, remotes=False)
        self.atcs_mock = ATCSMock()

        return (self.script, self.atcs_mock)

    async def test_config(self):
        async with self.make_script():
            config = dict()
            await self.configure_script(**config)
            assert self.script.config.end_at_sun_elevation == 0

            config = dict(end_at_sun_elevation=10.0)
            await self.configure_script(**config)
            assert (
                self.script.config.end_at_sun_elevation
                == config["end_at_sun_elevation"]
            )

    async def test_assert_vent_feasibility(self):
        expected_feasibility = [
            False,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            False,
            False,
        ]
        sun_azel_sample = [
            (116.51, 0.59),
            (107.35, 16.61),
            (99.06, 33.42),
            (90.18, 50.61),
            (76.71, 67.76),
            (24.81, 82.10),
            (292.31, 73.68),
            (273.66, 56.82),
            (263.92, 39.58),
            (255.63, 22.60),
            (245.19, 3.38),
            (243.40, 0.55),
        ]

        async with self.make_script():
            for feasibility, sun_azel in zip(expected_feasibility, sun_azel_sample):
                with self.subTest(feasibility=feasibility, sun_azel=sun_azel):
                    if feasibility:
                        self.script.assert_vent_feasibility(*sun_azel)
                    else:
                        with self.assertRaisesRegex(
                            RuntimeError, "Vent constraints not met."
                        ):
                            self.script.assert_vent_feasibility(*sun_azel)

    async def test_estimate_duration(self):
        async with self.make_script():
            duration = self.script.estimate_duration()
            assert duration > 0

    @patch.multiple(
        PrepareForVent,
        get_sun_azel=Mock(
            side_effect=[
                (255.63, 22.60),
                (245.19, 3.38),
                (243.40, -0.55),
            ]
        ),
        prepare_for_vent=AsyncMock(),
        reposition_telescope_and_dome=AsyncMock(),
    )
    async def test_run(self):
        async with self.make_script():
            await self.configure_script()
            self.script.track_sun_sleep_time = 0.5
            await self.run_script()

            self.script.get_sun_azel.assert_called()
            self.script.prepare_for_vent.assert_awaited()
            self.script.reposition_telescope_and_dome.assert_awaited()

    def _inject_wind_samples(self, speeds):
        """Populate _wind_history with recent samples at the given speeds."""
        now = utils.current_tai()
        for i, speed in enumerate(speeds):
            self.script._wind_history.append((speed, now - len(speeds) + i))

    def _mock_atbuilding(self):
        """Replace ATBuilding high-level methods with AsyncMocks."""
        self.script.atbuilding.open_vent_gates = AsyncMock()
        self.script.atbuilding.close_vent_gates = AsyncMock()
        self.script.atbuilding.start_extraction_fan = AsyncMock()
        self.script.atbuilding.stop_extraction_fan = AsyncMock()

    async def test_average_wind_speed_no_data(self):
        """Returns nan when no wind samples have been collected."""
        async with self.make_script():
            assert self.script._average_wind_speed() is None

    async def test_average_wind_speed_single_sample(self):
        """Returns the sample value when only one sample is present."""
        async with self.make_script():
            self._inject_wind_samples([7.0])
            assert self.script._average_wind_speed() == 7.0

    async def test_average_wind_speed_multiple_samples(self):
        """Returns the mean of all samples in the window."""
        async with self.make_script():
            self._inject_wind_samples([4.0, 6.0, 8.0])
            assert self.script._average_wind_speed() == 6.0

    async def test_air_flow_callback_appends_sample(self):
        """Each callback invocation appends a new (speed, timestamp) entry."""
        async with self.make_script():
            now = utils.current_tai()
            sample = types.SimpleNamespace(speed=5.5, private_sndStamp=now)
            await self.script._air_flow_callback(sample)

            assert len(self.script._wind_history) == 1
            assert self.script._wind_history[0] == (5.5, now)

    async def test_air_flow_callback_prunes_stale_samples(self):
        """Samples older than WIND_AVERAGE_WINDOW are pruned on callback."""
        async with self.make_script():
            now = utils.current_tai()
            stale_stamp = now - WIND_AVERAGE_WINDOW - 10
            self.script._wind_history.append((3.0, stale_stamp))

            fresh = types.SimpleNamespace(speed=8.0, private_sndStamp=now)
            await self.script._air_flow_callback(fresh)

            assert len(self.script._wind_history) == 1
            assert self.script._wind_history[0][0] == 8.0

    async def test_open_vent_and_fan_skips_when_no_wind_data(self):
        """Gate and fan are not activated when no ESS wind data available."""
        async with self.make_script():
            self._mock_atbuilding()
            await self.script._open_vent_and_fan()

            self.script.atbuilding.open_vent_gates.assert_not_called()
            self.script.atbuilding.start_extraction_fan.assert_not_called()
            assert not self.script._vent_gate_opened
            assert not self.script._fan_started

    async def test_open_vent_and_fan_skips_when_wind_at_threshold(self):
        """Gate and fan are not activated when wind equals the threshold."""
        async with self.make_script():
            self._mock_atbuilding()
            self._inject_wind_samples([WIND_SPEED_THRESHOLD])
            await self.script._open_vent_and_fan()

            self.script.atbuilding.open_vent_gates.assert_not_called()
            assert not self.script._vent_gate_opened

    async def test_open_vent_and_fan_skips_when_wind_above_threshold(self):
        """Gate and fan are not activated when wind exceeds the threshold."""
        async with self.make_script():
            self._mock_atbuilding()
            self._inject_wind_samples([WIND_SPEED_THRESHOLD + 1.0])
            await self.script._open_vent_and_fan()

            self.script.atbuilding.open_vent_gates.assert_not_called()
            assert not self.script._vent_gate_opened

    async def test_open_vent_and_fan_activates_when_wind_below_threshold(self):
        """Gate 3 opens, fan starts at FAN_TARGET_FREQUENCY when wind low."""
        async with self.make_script():
            self._mock_atbuilding()
            self._inject_wind_samples([WIND_SPEED_THRESHOLD - 1.0])
            await self.script._open_vent_and_fan()

            self.script.atbuilding.open_vent_gates.assert_awaited_once_with(
                [VENT_GATE_INDEX]
            )
            self.script.atbuilding.start_extraction_fan.assert_awaited_once_with(
                FAN_TARGET_FREQUENCY
            )
            assert self.script._vent_gate_opened
            assert self.script._fan_started

    async def test_close_vent_and_fan_noop_when_nothing_opened(self):
        """No commands are issued when the gate and fan were never opened."""
        async with self.make_script():
            self._mock_atbuilding()
            await self.script._close_vent_and_fan()

            self.script.atbuilding.stop_extraction_fan.assert_not_called()
            self.script.atbuilding.close_vent_gates.assert_not_called()

    async def test_close_vent_and_fan_stops_fan_and_closes_gate(self):
        """Fan is set to 0 Hz and gate is closed when both were opened."""
        async with self.make_script():
            self._mock_atbuilding()
            self.script._fan_started = True
            self.script._vent_gate_opened = True

            await self.script._close_vent_and_fan()

            self.script.atbuilding.stop_extraction_fan.assert_awaited_once()
            self.script.atbuilding.close_vent_gates.assert_awaited_once_with(
                [VENT_GATE_INDEX]
            )
            assert not self.script._fan_started
            assert not self.script._vent_gate_opened

    async def test_close_vent_and_fan_is_idempotent(self):
        """A second call to _close_vent_and_fan is a no-op after the first."""
        async with self.make_script():
            self._mock_atbuilding()
            self.script._fan_started = True
            self.script._vent_gate_opened = True

            await self.script._close_vent_and_fan()
            self.script.atbuilding.stop_extraction_fan.reset_mock()
            self.script.atbuilding.close_vent_gates.reset_mock()

            await self.script._close_vent_and_fan()

            self.script.atbuilding.stop_extraction_fan.assert_not_called()
            self.script.atbuilding.close_vent_gates.assert_not_called()

    async def test_wind_exceedance_closes_gate_and_fan(self):
        """When wind exceeds threshold mid-run, gate and fan are closed."""
        async with self.make_script():
            self._mock_atbuilding()
            self.script._fan_started = True
            self.script._vent_gate_opened = True
            self._inject_wind_samples([WIND_SPEED_THRESHOLD + 2.0])

            avg_wind = self.script._average_wind_speed()
            if (
                not self.script._vent_closed_due_to_wind
                and avg_wind is not None
                and avg_wind >= WIND_SPEED_THRESHOLD
            ):
                await self.script._close_vent_and_fan()
                self.script._vent_closed_due_to_wind = True

            self.script.atbuilding.stop_extraction_fan.assert_awaited_once()
            self.script.atbuilding.close_vent_gates.assert_awaited_once_with(
                [VENT_GATE_INDEX]
            )
            assert self.script._vent_closed_due_to_wind

    async def test_wind_exceedance_does_not_close_twice(self):
        """Once _vent_closed_due_to_wind is set, exceedances are ignored."""
        async with self.make_script():
            self._mock_atbuilding()
            self.script._vent_closed_due_to_wind = True
            self._inject_wind_samples([WIND_SPEED_THRESHOLD + 5.0])

            avg_wind = self.script._average_wind_speed()
            if (
                not self.script._vent_closed_due_to_wind
                and avg_wind is not None
                and avg_wind >= WIND_SPEED_THRESHOLD
            ):
                await self.script._close_vent_and_fan()

            self.script.atbuilding.stop_extraction_fan.assert_not_called()
            self.script.atbuilding.close_vent_gates.assert_not_called()

    @patch.multiple(
        PrepareForVent,
        get_sun_azel=Mock(
            side_effect=[
                (255.63, 22.60),
                (245.19, 3.38),
                (243.40, -0.55),
            ]
        ),
        prepare_for_vent=AsyncMock(),
        reposition_telescope_and_dome=AsyncMock(),
        _open_vent_and_fan=AsyncMock(),
        _close_vent_and_fan=AsyncMock(),
    )
    async def test_run_with_wind_logic(self):
        """run calls _open_vent_and_fan after prepare and _close_vent_and_fan
        on exit."""
        async with self.make_script():
            await self.configure_script()
            self.script.track_sun_sleep_time = 0.5
            await self.run_script()

            self.script._open_vent_and_fan.assert_awaited_once()
            self.script._close_vent_and_fan.assert_awaited()


if __name__ == "__main__":
    unittest.main()
