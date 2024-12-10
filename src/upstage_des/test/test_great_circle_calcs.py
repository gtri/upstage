# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from math import degrees, pi, radians

import pytest

import upstage_des.api as UP
from upstage_des.motion.great_circle_calcs import (
    get_course_rad,
    get_dist_rad,
    get_great_circle_points,
    get_pos_from_points_and_distance,
)


def test_distance() -> None:
    """Test great circle distance calc."""
    with UP.EnvironmentContext():
        p1 = UP.GeodeticLocation(0, 180, 0).to_radians()
        p2 = UP.GeodeticLocation(1, 180, 0).to_radians()
        assert pytest.approx(get_dist_rad(p1, p2)) == pi / 180

        p3 = UP.GeodeticLocation(0, 180, 0).to_radians()
        p4 = UP.GeodeticLocation(0, 181, 0).to_radians()
        assert pytest.approx(get_dist_rad(p3, p4)) == pi / 180


def test_course() -> None:
    """Test great circle course calc."""
    with UP.EnvironmentContext():
        p1 = UP.GeodeticLocation(0, 180, 0).to_radians()
        p2 = UP.GeodeticLocation(1, 180, 0).to_radians()
        assert pytest.approx(get_course_rad(p1, p2)) == 2 * pi

        p3 = UP.GeodeticLocation(0, 180, 0).to_radians()
        p4 = UP.GeodeticLocation(0, 181, 0).to_radians()
        assert pytest.approx(get_course_rad(p3, p4)) == 3 * pi / 2.0


def test_position_from_point_distance() -> None:
    """Test position from point and distance calc."""
    with UP.EnvironmentContext():
        p1 = UP.GeodeticLocation(0, 180, 0).to_radians()
        p2 = UP.GeodeticLocation(1, 180, 0).to_radians()
        dist = 0.5 * (pi / 180)
        half_point = get_pos_from_points_and_distance(p1, p2, dist)
        assert pytest.approx(degrees(half_point[0])) == 0.5
        assert pytest.approx(degrees(half_point[1])) == -180


def test_great_circle_points() -> None:
    """Test calculation of points on creat circle path."""
    with UP.EnvironmentContext():
        p1 = UP.GeodeticLocation(0, 180, 0).to_radians()
        p2 = UP.GeodeticLocation(5, 180, 0).to_radians()
        p3 = UP.GeodeticLocation(3, 180, 0).to_radians()
        dist = pi / 180
        x = get_great_circle_points(p1, p2, p3, dist)
        assert x is not None
        points, distances = x
        assert len(points) == 2

        assert pytest.approx(points[0][0]) == radians(2)
        assert pytest.approx(points[0][1]) == radians(-180)
        assert pytest.approx(points[1][0]) == radians(4)
        assert pytest.approx(points[1][1]) == radians(-180)
        assert pytest.approx(distances[0]) == radians(2)
        assert pytest.approx(distances[1]) == radians(4)


def test_caching() -> None:
    with UP.EnvironmentContext():
        get_dist_rad.cache_clear()
        get_course_rad.cache_clear()
        get_pos_from_points_and_distance.cache_clear()
        get_great_circle_points.cache_clear()

        p1 = UP.GeodeticLocation(0, 180, 0).to_radians()
        p2 = UP.GeodeticLocation(1, 180, 0).to_radians()
        p3 = UP.GeodeticLocation(3, 180, 0).to_radians()
        dist = pi / 180

        get_dist_rad(p1, p2)
        get_dist_rad(p1, p2)
        cache_info = get_dist_rad.cache_info()
        assert cache_info.hits == 1
        assert cache_info.currsize == 1

        get_course_rad(p1, p2)
        get_course_rad(p1, p2)
        cache_info = get_course_rad.cache_info()
        assert cache_info.hits == 1
        assert cache_info.currsize == 1

        get_pos_from_points_and_distance(p1, p2, dist)
        get_pos_from_points_and_distance(p1, p2, dist)
        cache_info = get_pos_from_points_and_distance.cache_info()
        assert cache_info.hits == 1
        assert cache_info.currsize == 1

        get_great_circle_points(p1, p2, p3, dist)
        get_great_circle_points(p1, p2, p3, dist)
        cache_info = get_great_circle_points.cache_info()
        assert cache_info.hits == 1
        assert cache_info.currsize == 1
