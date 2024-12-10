# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

from upstage_des.geography import WGS84, Spherical, get_intersection_locations
from upstage_des.motion.cartesian_model import ray_intersection

from .conftest import POS


@pytest.mark.parametrize("earth", [WGS84, Spherical])
def test_intersections(
    intersect_positions: tuple[tuple[POS, POS, POS], float, str, list[str]],
    earth: WGS84 | Spherical,
) -> None:
    pos, sensor_range, range_units, answer = intersect_positions
    start_lla, finish_lla, sensor_lla = pos
    sensor_loc = (sensor_lla[0], sensor_lla[1])
    intersects = get_intersection_locations(
        start_lla,
        finish_lla,
        sensor_lla,
        sensor_range,
        range_units,
        earth,
        dist_between=9260,
        subdivide_levels=[20, 20],
    )
    # without visibility, the intersections should be very close to the right
    # range, unless they are inside the range due to START_IN
    for i, an in zip(intersects, answer):
        assert i.kind == an
        loc = (i.begin[0], i.begin[1])
        dist = earth.distance(loc, sensor_loc, range_units)
        if an in ["EXIT", "ENTER"]:
            assert sensor_range == pytest.approx(dist, rel=0.001)
        else:
            assert dist < sensor_range


@pytest.mark.parametrize("earth", [WGS84, Spherical])
def test_short_intersections(
    earth: WGS84 | Spherical, short_intersections: tuple[tuple[POS, POS, POS], float, str]
) -> None:
    pos, sensor_range, range_units = short_intersections
    start_lla, finish_lla, sensor_lla = pos
    _ = get_intersection_locations(
        start_lla,
        finish_lla,
        sensor_lla,
        sensor_range,
        range_units,
        earth,
        dist_between=9260,
        subdivide_levels=[20, 20],
    )


def test_ray_trace() -> None:
    input_1 = ((0, 2), (0, 1.8), (0, 0), (1, 1))
    input_2 = ((0, 2), (1, 2), (0, 0), (1, 1))
    input_3 = ((0, 2, 0), (0, 1.8, 0), (0, 0, 0), (1, 1, 1))
    input_4 = ((0, 2, 0), (1, 2, 0), (0, 0, 0), (1, 1, 1))

    points1, _ = ray_intersection(*input_1, 1.0)
    for x, y in points1:
        assert pytest.approx(0) == x
        assert pytest.approx(1) == abs(y)

    points2, _ = ray_intersection(*input_2, 1.0)
    assert not points2

    points3, _ = ray_intersection(*input_3, 1.0)
    for x, y, z in points3:
        assert pytest.approx(0) == x
        assert pytest.approx(1) == abs(y)

    points4, _ = ray_intersection(*input_4, 1.0)
    assert not points4
