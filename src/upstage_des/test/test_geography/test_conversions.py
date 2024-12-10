# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

from upstage_des.geography import conversions, spherical, wgs84
from upstage_des.geography.conversions import BaseConversions

SC = conversions.SphericalConversions
WSGC = conversions.WGS84Conversions
SC2 = spherical.Spherical
WSGC2 = wgs84.WGS84


@pytest.mark.parametrize("use", [SC, SC2, WSGC, WSGC2])
def test_conversions(use: BaseConversions, random_lla: list[tuple[float, float, float]]) -> None:
    # Do a back and forth test of random Lat Lon Alt
    ecef = use.lla2ecef(random_lla)
    lla_from_ecef = use.ecef2lla(ecef)
    for a, b in zip(lla_from_ecef, random_lla):
        assert pytest.approx(a) == b
