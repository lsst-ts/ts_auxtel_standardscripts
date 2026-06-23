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

__all__ = ["PrepareForVent"]

import asyncio
import collections
import dataclasses

import yaml
from astroplan import Observer
from lsst.ts import salobj, utils
from lsst.ts.observatory.control.auxtel.atbuilding import ATBuilding, ATBuildingUsages
from lsst.ts.observatory.control.auxtel.atcs import ATCS, ATCSUsages
from lsst.ts.xml.enums.ATBuilding import VentGateState

# ESS SAL index for the outdoor weather station at the AuxTel site.
ESS_INDEX = 301

# Index of the vent gate to open when wind conditions allow.
VENT_GATE_INDEX = 2

# Wind speed threshold (m/s) below which the vent gate and fan are activated.
WIND_SPEED_THRESHOLD = 10.0

# Rolling window (s) over which to average wind speed.
WIND_AVERAGE_WINDOW = 600.0

# Extraction fan drive frequency (Hz) to use when venting.
FAN_TARGET_FREQUENCY = 20


@dataclasses.dataclass
class VentConstraints:
    sun_elevation_max = 90.0
    sun_elevation_min = 5.0

    def __repr__(self) -> str:
        return (
            "VentConstraints:: \n\n"
            f"Sun elevation between {self.sun_elevation_max} and {self.sun_elevation_min} degrees.\n"
        )


class PrepareForVent(salobj.BaseScript):
    """Run prepare for vent on ATCS.

    Optionally opens ATBuilding vent gate 3 and starts the extraction fan at
    20% of the maximum drive frequency when the 10-minute average wind speed
    reported by ESS 301 is below 10 m/s.  The fan and gate are closed/stopped
    at the end of the script or on early termination.

    Parameters
    ----------
    index : `int`
        Index of Script SAL component.
    """

    def __init__(self, index, remotes=True):
        super().__init__(index=index, descr="Prepare for vent.")

        self.track_sun_sleep_time = 60.0

        self.vent_constraints = VentConstraints()

        self.atcs = ATCS(
            domain=self.domain,
            log=self.log,
            intended_usage=None if remotes else ATCSUsages.DryTest,
        )

        self.atbuilding = ATBuilding(
            domain=self.domain,
            log=self.log,
            intended_usage=None if remotes else ATBuildingUsages.DryTest,
        )

        self.ess_remote = (
            salobj.Remote(
                domain=self.domain,
                name="ESS",
                index=ESS_INDEX,
                include=["airFlow"],
            )
            if remotes
            else None
        )

        # Rolling wind-speed history: deque of (speed_m_s, tai_timestamp).
        self._wind_history: collections.deque = collections.deque()

        # Track whether we opened the gate/fan so cleanup knows what to undo.
        self._vent_gate_opened = False
        self._fan_started = False
        # Set to True when wind forces the gate/fan closed mid-run so we don't
        # attempt to re-open them.
        self._vent_closed_due_to_wind = False

    @classmethod
    def get_schema(cls):
        schema_yaml = """
            $schema: http://json-schema.org/draft-07/schema#
            $id: https://github.com/lsst-ts/ts_standardscripts/auxtel/prepare_for/vent.yaml
            title: PrepareForVent v1
            description: Configuration for Prepare for vent.
            type: object
            properties:
                end_at_sun_elevation:
                    description: >-
                        Stop venting when sun reaches this altitude.
                    type: number
                    default: 0.0
                skip_vent_gates:
                    description: >-
                        If true, skip all vent gate and extraction fan
                        operations.
                    type: boolean
                    default: false
            additionalProperties: false
        """
        return yaml.safe_load(schema_yaml)

    async def configure(self, config):
        self.config = config

        if self.ess_remote is not None:
            self.ess_remote.tel_airFlow.callback = self._air_flow_callback

    def set_metadata(self, metadata):
        metadata.duration = self.estimate_duration()

    async def run(self):
        sun_az, sun_el = self.get_sun_azel()

        self.assert_vent_feasibility(sun_az, sun_el)

        await self.checkpoint("Preparing...")

        await self.prepare_for_vent()

        if self.config.skip_vent_gates:
            self.log.info(
                "skip_vent_gates=True; skipping vent gate and extraction fan."
            )
        else:
            await self._open_vent_and_fan()

        self.log.info(f"Venting until sun reaches {self.config.end_at_sun_elevation}.")

        try:
            while sun_el > self.config.end_at_sun_elevation:
                avg_wind = self._average_wind_speed()
                wind_str = (
                    f"avg wind {avg_wind:.2f} m/s"
                    if avg_wind is not None
                    else "avg wind unavailable"
                )

                await self.checkpoint(
                    f"Sun @ {sun_el:.2f} deg [limit={self.config.end_at_sun_elevation}], "
                    f"{wind_str} [limit={WIND_SPEED_THRESHOLD} m/s]."
                )

                if (
                    not self._vent_closed_due_to_wind
                    and avg_wind is not None
                    and avg_wind >= WIND_SPEED_THRESHOLD
                ):
                    self.log.warning(
                        f"Average wind speed {avg_wind:.2f} m/s exceeded threshold "
                        f"{WIND_SPEED_THRESHOLD} m/s. Closing vent gate and fan."
                    )
                    await self._close_vent_and_fan()
                    self._vent_closed_due_to_wind = True

                self.log.debug(f"Waiting {self.track_sun_sleep_time}...")
                await asyncio.sleep(self.track_sun_sleep_time)

                (
                    tel_vent_azimuth,
                    dome_vent_azimuth,
                ) = self.atcs.get_telescope_and_dome_vent_azimuth()

                self.log.debug(
                    f"Repositioning the telescope and dome: {tel_vent_azimuth=}, {dome_vent_azimuth}."
                )

                await self.reposition_telescope_and_dome(
                    tel_vent_azimuth, dome_vent_azimuth
                )
                _, sun_el = self.get_sun_azel()
        finally:
            await self._close_vent_and_fan()

    async def reposition_telescope_and_dome(self, tel_vent_azimuth, dome_vent_azimuth):
        try:
            await self.atcs.point_azel(
                target_name="Vent Position",
                az=tel_vent_azimuth,
                el=self.atcs.tel_vent_el,
                rot_tel=self.atcs.tel_park_rot,
                wait_dome=False,
            )
            await self.atcs.stop_tracking()

            await self.atcs.slew_dome_to(dome_vent_azimuth)
        except Exception:
            self.log.exception(
                "Error repositioning the telescope and/or done. Continuing..."
            )

    async def prepare_for_vent(self):
        await self.atcs.prepare_for_vent(partially_open_dome=True)

    def get_sun_azel(self):
        """Get sun azel from ATCS.

        Returns
        -------
        `tuple`[`float`, `float`]
            Current azimuth and elevation of the sun.
        """
        return self.atcs.get_sun_azel()

    def assert_vent_feasibility(self, sun_az, sun_el):
        """Check that it is ok to vent, raise an exception if not.

        Parameters
        ----------
        sun_az : `float`
            Sun azimuth in degrees.
        sun_el : `float`
            Sun elevation, in degrees.

        Raises
        ------
        RuntimeError
            If not in the vent band.
        """
        if (
            sun_el > self.vent_constraints.sun_elevation_max
            or sun_el < self.vent_constraints.sun_elevation_min
        ):
            raise RuntimeError(
                f"Vent constraints not met. Sun currently @ {sun_az=:.2f},{sun_el=:.2f}. "
                f"Constraints are {self.vent_constraints!r}."
            )

    async def cleanup(self) -> None:
        """Close the vent gate and stop the fan if stopped early."""
        await self._close_vent_and_fan()

    async def _air_flow_callback(self, air_flow: salobj.BaseMsgType) -> None:
        """Append an ESS airFlow sample to the rolling wind-speed history."""
        now = air_flow.private_sndStamp
        self._wind_history.append((air_flow.speed, now))

        # Prune samples older than the averaging window.
        cutoff = now - WIND_AVERAGE_WINDOW
        while self._wind_history and self._wind_history[0][1] < cutoff:
            self._wind_history.popleft()

    def _average_wind_speed(self) -> float | None:
        """Return the average wind speed (m/s) over the rolling window.

        Returns `None` if no samples have been collected.
        """
        if not self._wind_history:
            return None
        speeds = [s for s, _ in self._wind_history]
        return sum(speeds) / len(speeds)

    async def _open_vent_and_fan(self) -> None:
        """Open vent gate 3 and start the extraction fan if wind allows.

        If the average wind speed is unavailable (no ESS data) the operation
        is skipped with a warning.
        """
        avg_wind = self._average_wind_speed()

        if avg_wind is None:
            self.log.warning(
                "No wind speed data available from ESS %d. "
                "Skipping vent gate and extraction fan activation.",
                ESS_INDEX,
            )
            return

        self.log.info(
            f"Average wind speed over last {WIND_AVERAGE_WINDOW:.0f} s: "
            f"{avg_wind:.2f} m/s (threshold {WIND_SPEED_THRESHOLD} m/s)."
        )

        if avg_wind >= WIND_SPEED_THRESHOLD:
            self.log.info(
                "Wind speed at or above threshold. "
                "Vent gate 3 and extraction fan will not be activated."
            )
            return

        self.log.info(
            f"Opening vent gate {VENT_GATE_INDEX} and starting extraction fan "
            f"at {FAN_TARGET_FREQUENCY} Hz."
        )

        await self.atbuilding.open_vent_gates(
            [VENT_GATE_INDEX],
            expected_state=VentGateState.PARTIALLY_OPEN,
        )

        self._vent_gate_opened = True

        await self.atbuilding.start_extraction_fan(FAN_TARGET_FREQUENCY)
        self._fan_started = True

    async def _close_vent_and_fan(self) -> None:
        """Stop the extraction fan and close vent gate 3 if opened."""
        if self._fan_started:
            self.log.info("Stopping extraction fan.")
            try:
                await self.atbuilding.stop_extraction_fan()
            except Exception:
                self.log.exception("Error stopping extraction fan.")
            finally:
                self._fan_started = False

        if self._vent_gate_opened:
            self.log.info(f"Closing vent gate {VENT_GATE_INDEX}.")
            try:
                await self.atbuilding.close_vent_gates([VENT_GATE_INDEX])
            except Exception:
                self.log.exception(f"Error closing vent gate {VENT_GATE_INDEX}.")
            finally:
                self._vent_gate_opened = False

    def estimate_duration(self):
        """Estimate the script duration.

        Returns
        -------
        `float`
            Estimated duration (in seconds).
        """

        observer = Observer(
            location=self.atcs.location, name="Rubin", timezone="Chile/Continental"
        )

        time_sunset = observer.sun_set_time(
            utils.astropy_time_from_tai_unix(utils.current_tai()), which="next"
        )

        return time_sunset.unix_tai - utils.current_tai()
