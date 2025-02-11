# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from dataclasses import FrozenInstanceError
from math import radians, sqrt

import pytest

import upstage_des.api as UP
from upstage_des.geography import Spherical, get_intersection_locations

STAGE_SETUP = dict(
    altitude_units="ft",
    distance_units="nmi",
    intersection_model=get_intersection_locations,
    stage_model=Spherical,
)


def test_basics() -> None:
    with UP.EnvironmentContext():
        with pytest.raises(NotImplementedError):
            l1 = UP.Location()
            l1 - 3


def test_hashable() -> None:
    with UP.EnvironmentContext():
        p1 = [10, 10]
        point_1 = UP.CartesianLocation(*p1)
        key = point_1._key()
        assert key == (10, 10, 0.0, False)
        # assert getattr(point_1, "__hash__") is not None
        _ = {point_1: 1.0}


def test_cartesian() -> None:
    with UP.EnvironmentContext():
        for k, v in STAGE_SETUP.items():
            UP.add_stage_variable(k, v)

        p1 = [10.0, 10.0]
        p2 = [1.0, 2.0, 3.0]
        origin = UP.CartesianLocation(0, 0)
        point_1 = UP.CartesianLocation(*p1)
        point_2 = UP.CartesianLocation(*p2)

        assert origin - point_1 == sqrt(200)
        assert origin - point_1 == point_1 - origin

        assert point_1 - point_2 > 0
        for index, value in enumerate(p2):
            assert point_2[index] == value

        assert "10" in point_1.__repr__()

        with pytest.raises(ValueError):
            point_2[3] is None

        with pytest.raises(ValueError):
            point_1 - 10

        with pytest.raises(ValueError):
            point_2 == 10

        point_3 = UP.CartesianLocation(*p2, use_altitude_units=True)

        assert point_3 != point_2

        point_2a = UP.CartesianLocation(1, 2, 3.000000001)
        assert point_2 == point_2a, f"Nearly equal points are still {point_2 - point_2a} too far"


def test_geodetic() -> None:
    with UP.EnvironmentContext():
        for k, v in STAGE_SETUP.items():
            UP.add_stage_variable(k, v)

        lat, lon, alt = 33, -86, 1000
        loc_up = UP.GeodeticLocation(lat, lon, alt)

        with pytest.raises(FrozenInstanceError):
            loc_up.alt = 5_000

        loc_up_rad = loc_up.to_radians()
        assert loc_up_rad.lat == radians(loc_up.lat)
        assert loc_up_rad.lon == radians(loc_up.lon)
        assert loc_up_rad.alt == loc_up.alt

        loc_up_rad_1 = UP.GeodeticLocation(
            lat=radians(loc_up.lat),
            lon=radians(loc_up.lon),
            in_radians=True,
        )
        assert loc_up_rad_1.lat == loc_up_rad.lat
        assert loc_up_rad_1.lon == loc_up_rad.lon

        assert loc_up_rad == loc_up_rad.to_radians()
        assert loc_up == loc_up.to_degrees()

        assert loc_up_rad == loc_up
        assert loc_up == loc_up_rad

        assert loc_up_rad - UP.GeodeticLocation(10, 10) > 0
        assert UP.GeodeticLocation(10, 10) - loc_up_rad > 0


def test_data_objects() -> None:
    cart1 = UP.CartesianLocationData(1.0, 2.1, 3.2)
    cart2 = UP.CartesianLocationData(1.0, 2.1, 3.2)
    assert cart1 == cart2

    with pytest.raises(ValueError):
        cart1 == (1.0, 2.1, 3.2)

    geo1 = UP.GeodeticLocationData(13.0, 12.1, 11.2)
    geo2 = UP.GeodeticLocationData(13.0, 12.1, 11.2)
    assert geo1 == geo2

    geo3 = UP.GeodeticLocationData(radians(13.0), radians(12.1), 11.2, in_radians=True)
    assert geo1 == geo3
    assert geo3 == geo1

    with pytest.raises(ValueError):
        geo1 == (13.0, 12.1, 11.2)

    with UP.EnvironmentContext():
        for k, v in STAGE_SETUP.items():
            UP.add_stage_variable(k, v)

        loc1 = geo1.make_location()
        assert isinstance(loc1, UP.GeodeticLocation)

        loc3 = geo3.make_location()

        assert loc1 - loc3 == 0.0
        assert loc1 == loc3

        loc1 = cart1.make_location()
        loc2 = cart2.make_location()
        assert loc1 == loc2
