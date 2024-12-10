# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from itertools import combinations

import pytest

from upstage_des.units.convert import CONVERSIONS, unit_convert


def test_convert_fail() -> None:
    with pytest.raises(ValueError):
        unit_convert(100, "parsec", "km")


def test_convert() -> None:
    result = unit_convert(100, "km", "mi")
    assert result == 0.62137119223 * 100

    result = unit_convert(3600, "s", "hr")
    assert result == 1.0

    result = unit_convert(10, "min", "s")
    assert result == 10.0 * 60.0


def test_convert_reverse() -> None:
    for unit_1, unit_2 in combinations(CONVERSIONS, 2):
        if unit_2 in CONVERSIONS[unit_1]:
            ans = unit_convert(1.0, unit_1, unit_2)
            reverse = unit_convert(ans, unit_2, unit_1)
            assert pytest.approx(reverse) == 1
