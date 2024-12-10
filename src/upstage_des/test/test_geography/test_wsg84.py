# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

from upstage_des.geography import WGS84


def test_distance_and_bearing(atl: tuple[float, float], nas: tuple[float, float]) -> None:
    dist = WGS84.distance(atl, nas, "nmi")
    assert dist == pytest.approx(186.64143600171283)
    bearing = WGS84.bearing(atl, nas)
    assert bearing == pytest.approx(321.4499587022779)
    d2, b2 = WGS84.distance_and_bearing(atl, atl)
    assert pytest.approx(0) == d2


def test_linspace(atl: tuple[float, float], nas: tuple[float, float]) -> None:
    latlons = WGS84.geo_linspace(atl, nas, 10)
    assert len(latlons) == 11
    lats, lons = zip(*latlons)
    assert lats[0] == atl[0]
    assert lats[-1] == pytest.approx(nas[0])
    assert lons[0] == pytest.approx(atl[1])
    assert lons[-1] == pytest.approx(nas[1])


def test_geo_circle(atl: tuple[float, float]) -> None:
    latlons = WGS84.geo_circle(atl, radius=100, num_points=20)
    for lat, lon in latlons:
        d = WGS84.distance(atl, (lat, lon))
        assert d == pytest.approx(100, rel=0.001)


def test_bearing_dist_from_point(atl: tuple[float, float], nas: tuple[float, float]) -> None:
    dist, bearing = WGS84.distance_and_bearing(atl, nas, units="km")
    pt = WGS84.point_from_bearing_dist(atl, bearing, dist, distance_units="km")
    new_dist = WGS84.distance(pt, nas, units="km")
    assert 0 == pytest.approx(new_dist, abs=0.01)


def test_addtional_2() -> None:
    point_1 = (50 + 3 / 60 + 58.76 / 3600, -(5 + 42 / 60 + 53.10 / 3600))
    point_2 = (58 + 38 / 60 + 38.48 / 3600, -(3 + 4 / 60 + 12.34 / 3600))
    dist, bearing = WGS84.distance_and_bearing(point_1, point_2, units="km")
    assert dist == pytest.approx(969.954114)
    actual_bearing = 9 + 8 / 60 + 30.70 / 3600
    assert bearing == pytest.approx(actual_bearing)


def test_addtional_3() -> None:
    point_1 = (-(37 + 57 / 60 + 3.72030 / 3600), 144 + 25 / 60 + 29.52440 / 3600)
    point_2 = (-(37 + 39 / 60 + 10.15610 / 3600), 143 + 55 / 60 + 35.38390 / 3600)
    dist, bearing = WGS84.distance_and_bearing(point_1, point_2, units="km")
    assert dist == pytest.approx(54.972271)
    actual_bearing = 306 + 52 / 60 + 5.37 / 3600
    assert bearing == pytest.approx(actual_bearing)
