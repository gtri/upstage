# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test unit conversion."""

from itertools import combinations

import pytest

from upstage_des.units import _distance_to_m, _time_to_s, unit_convert, speed_convert


def test_convert_fail() -> None:
    with pytest.raises(ValueError):
        unit_convert(100, "parsec", "km")


def test_convert_reverse() -> None:
    for unit_grp in [_distance_to_m, _time_to_s]:
        for unit_1, unit_2 in combinations(unit_grp, 2):
            ans = unit_convert(1.0, unit_1, unit_2)
            reverse = unit_convert(ans, unit_2, unit_1)
            assert pytest.approx(reverse) == 1


def test_convert_sped() -> None:
    kps = speed_convert(60, "miles", "hour", "km", "second")
    assert kps == pytest.approx(0.0268224)
    kts = speed_convert(1, "meters", "second", "nmi", "hr")
    assert kts == pytest.approx(1.94384, rel=0.001)
