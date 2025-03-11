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

__all__ = ["OfflineATCS"]

from lsst.ts.observatory.control.auxtel.atcs import ATCS, ATCSUsages
from lsst.ts.standardscripts.offline_group import OfflineGroup


class OfflineATCS(OfflineGroup):
    """Put ATCS components in offline.

    Parameters
    ----------
    index : `int`
        Index of Script SAL component.

    Notes
    -----
    **Checkpoints**

    None

    """

    def __init__(self, index):
        super().__init__(index=index, descr="Put all ATCS components in offline state.")

        self._atcs = ATCS(
            self.domain, intended_usage=ATCSUsages.StateTransition, log=self.log
        )

    @property
    def group(self):
        return self._atcs

    @staticmethod
    def components():
        """Return list of components name as appeared in
        `self.group.components`.

        Returns
        -------
        components : `list` of `str`.

        """
        return {
            "atmcs",
            "atptg",
            "ataos",
            "atpneumatics",
            "athexapod",
            "atdome",
            "atdometrajectory",
        }
