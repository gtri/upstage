# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

from upstage_des.geography import Spherical


def test_distance(atl: tuple[float, float], nas: tuple[float, float]) -> None:
    dist = Spherical.distance(atl, nas)
    assert dist == pytest.approx(186.94317974521996)


def test_bearing(atl: tuple[float, float], nas: tuple[float, float]) -> None:
    bearing = Spherical.bearing(atl, nas)
    assert bearing == pytest.approx(321.5766379719283)


def test_linspace(atl: tuple[float, float], nas: tuple[float, float]) -> None:
    latlons = Spherical.geo_linspace(atl, nas, 10)
    assert len(latlons) == 11
    lats, lons = zip(*latlons)
    assert pytest.approx(lats[0]) == atl[0]
    assert pytest.approx(lats[-1]) == nas[0]
    assert pytest.approx(lons[0]) == atl[1]
    assert pytest.approx(lons[-1]) == nas[1]


def test_geo_circle(atl: tuple[float, float]) -> None:
    latlons = Spherical.geo_circle(atl, radius=100, num_points=20)
    for lat, lon in latlons:
        d = Spherical.distance(atl, (lat, lon))
        assert d == pytest.approx(100)


def test_point_along(atl: tuple[float, float], nas: tuple[float, float]) -> None:
    pt = Spherical.point_along(atl, nas, 0.0)
    assert pt[0] == atl[0]
    assert pt[1] == atl[1]


def test_bearing_dist_from_point(atl: tuple[float, float], nas: tuple[float, float]) -> None:
    bearing = Spherical.bearing(atl, nas)
    dist = Spherical.distance(atl, nas)
    pt = Spherical.point_from_bearing_dist(atl, bearing, dist, "nmi")
    new_dist = Spherical.distance(pt, nas, "nmi")
    assert new_dist <= 1e-4


def test_cross_track(
    nyc: tuple[float, float], lax: tuple[float, float], atl: tuple[float, float]
) -> None:
    res = Spherical.cross_track_point(nyc, lax, atl)
    dist = Spherical.cross_track_distance(nyc, lax, atl)
    dist2 = Spherical.distance(res, atl)
    assert pytest.approx(dist) == dist2
