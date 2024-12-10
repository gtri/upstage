# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

from upstage_des.actor import Actor
from upstage_des.api import EnvironmentContext, SimulationError, add_stage_variable
from upstage_des.data_types import GeodeticLocation
from upstage_des.geography import Spherical
from upstage_des.states import GeodeticLocationChangingState

# example lat lon alts
ATLANTA = [33.7490, -84.3880, 1050]
DENVER = [39.7392, -104.9903, 30_000]
SAN_FRAN = [37.7749, -122.4194, 0]


def test_create_geodetic() -> None:
    with EnvironmentContext():
        atl = GeodeticLocation(
            *ATLANTA,
        )
        san_fran = GeodeticLocation(
            *SAN_FRAN,
        )

        atl[0] == ATLANTA[0]
        with pytest.raises(IndexError):
            san_fran[3]

        with pytest.raises(ValueError):
            atl - 1

        with pytest.raises(ValueError):
            atl == 1

        assert atl != san_fran
        assert atl == atl
        assert san_fran == san_fran.copy()


def test_subtraction_geodetic() -> None:
    with EnvironmentContext():
        add_stage_variable("stage_model", Spherical)
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("distance_units", "nmi")

        atl = GeodeticLocation(
            ATLANTA[0],
            ATLANTA[1],
            0.0,  # set feet to zero to test the distance against no altitude change
        )
        san_fran = GeodeticLocation(
            *SAN_FRAN,
        )
        dist = atl - san_fran
        assert abs(dist - 1857.8524277061492) <= 1e-6

        d = atl - atl.copy()
        assert d == 0

        atl = GeodeticLocation(*ATLANTA)
        den = GeodeticLocation(*DENVER)
        dist = atl.dist_with_altitude(den)
        assert abs(dist - 1052.67744200) <= 1e-6


def test_create_geodetic_changing() -> None:
    class StateTest(Actor):
        loc_state = GeodeticLocationChangingState(
            recording=True,
        )

    with EnvironmentContext():
        add_stage_variable("stage_model", Spherical)
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("distance_units", "nmi")

        tester = StateTest(
            name="Geodetic Loc",
            loc_state=GeodeticLocation(*ATLANTA),
        )
        assert tester.loc_state == GeodeticLocation(*ATLANTA)
        assert tester.loc_state != GeodeticLocation(*DENVER)


def test_active_geodetic_changing() -> None:
    class StateTest(Actor):
        loc_state = GeodeticLocationChangingState(
            recording=True,
        )

    with EnvironmentContext():
        add_stage_variable("stage_model", Spherical)
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("distance_units", "nmi")

        tester = StateTest(
            name="Geodetic Loc",
            loc_state=GeodeticLocation(*ATLANTA),
        )
        waypoints = [
            GeodeticLocation(*DENVER),
            GeodeticLocation(*SAN_FRAN),
        ]
        tester.activate_state(
            state="loc_state",
            task="dummy_task",  # type: ignore [arg-type]
            speed=1.0,
            waypoints=waypoints,
        )
        assert "loc_state" in tester._active_states
        assert tester._active_states["loc_state"] == tester.get_active_state_data("loc_state")

        # check the data created
        # ask for the state to update it
        tester.loc_state
        data = tester.get_active_state_data("loc_state")
        assert "path_data" in data
        assert len(data["path_data"]["times"]) == 2

        assert tester.loc_state == GeodeticLocation(*ATLANTA)
        tester.env.run(until=100)
        assert tester.loc_state != GeodeticLocation(*ATLANTA)
        assert tester.loc_state.alt > ATLANTA[2]

        # run time to reach Denver
        tester.env.run(until=1052.6666594454714)
        assert abs(tester.loc_state.lat - DENVER[0]) <= 1e-6
        assert abs(tester.loc_state.lon - DENVER[1]) <= 1e-6
        assert abs(tester.loc_state.alt - DENVER[2]) <= 1e-6

        # make sure it moves to the next waypoint
        tester.env.run(until=1200)
        tester.loc_state
        assert tester.loc_state.alt < DENVER[2]
        assert tester.loc_state.lon < DENVER[1]

        tester.env.run(until=1052.6666594454714 + 824.0883665214037)
        tester.loc_state
        assert abs(tester.loc_state.lat - SAN_FRAN[0]) <= 1e-6
        assert abs(tester.loc_state.lon - SAN_FRAN[1]) <= 1e-6
        assert abs(tester.loc_state.alt - SAN_FRAN[2]) <= 1e-6

        tester.env.run(until=tester.env.now + 10)
        with pytest.raises(SimulationError):
            tester.loc_state
