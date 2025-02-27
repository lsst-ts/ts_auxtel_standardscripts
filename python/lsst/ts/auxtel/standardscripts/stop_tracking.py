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

__all__ = ["StopTracking"]

from lsst.ts.observatory.control.auxtel.atcs import ATCS, ATCSUsages
from lsst.ts.standardscripts.base_stop_tracking import BaseStopTracking


class StopTracking(BaseStopTracking):
    """Stop telescope and dome tracking.

    Parameters
    ----------
    index : `int`
        Index of Script SAL component.
    """

    def __init__(self, index):
        super().__init__(index=index, descr="ATCS stop tracking.")

        self._atcs = ATCS(self.domain, intended_usage=ATCSUsages.Slew, log=self.log)

    @property
    def tcs(self):
        return self._atcs
