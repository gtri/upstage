# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from typing import Any

import pytest

from upstage_des.api import (
    Actor,
    CartesianLocationChangingState,
    EnvironmentContext,
    GeodeticLocationChangingState,
    InterruptStates,
    LinearChangingState,
    State,
    Task,
    Wait,
    add_stage_variable,
)
from upstage_des.data_types import CartesianLocation, GeodeticLocation
from upstage_des.geography import Spherical
from upstage_des.type_help import TASK_GEN


class Mover(Actor):
    location = CartesianLocationChangingState(recording=True)
    speed = State[float](recording=True)
    fuel = LinearChangingState(recording=True)
    fuel_burn = State[float](recording=True)

    def get_distance(self, waypoints: list[CartesianLocation]) -> float:
        d = waypoints[0] - self.location
        for i in range(1, len(waypoints)):
            d += waypoints[i] - waypoints[i - 1]
        return d


class MoverGeo(Actor):
    location = GeodeticLocationChangingState(recording=True)
    speed = State[float](recording=True)
    fuel = LinearChangingState(recording=True)
    fuel_burn = State[float](recording=True)

    def get_distance(self, waypoints: list[GeodeticLocation]) -> float:
        d = waypoints[0] - self.location
        for i in range(1, len(waypoints)):
            d += waypoints[i] - waypoints[i - 1]
        return d


class MoveTask(Task):
    def task(self, *, actor: Mover | MoverGeo) -> TASK_GEN:
        destinations = list(self.get_actor_knowledge(actor, "destinations"))
        actor.activate_state(
            state="location",
            task=self,
            speed=actor.speed,
            waypoints=destinations,
        )
        actor.activate_state(
            state="fuel",
            task=self,
            rate=actor.fuel_burn,
        )
        dist = actor.get_distance(destinations)
        time = dist / actor.speed
        yield Wait(time)
        actor.deactivate_all_states(task=self)

    def on_interrupt(self, *, actor: Mover | MoverGeo, cause: Any) -> InterruptStates:
        if cause == "restart":
            rem_wypts = actor.get_remaining_waypoints(
                location_state="location",
            )
            self.set_actor_knowledge(
                actor,
                "destinations",
                rem_wypts,
                overwrite=True,
            )
            actor.speed /= 2
            return self.INTERRUPT.RESTART
        else:
            return self.INTERRUPT.END


WAYPOINTS = [
    (3, 4),
    (6, 0),
]

ATLANTA = [33.7490, -84.3880, 1050]
DENVER = [39.7392, -104.9903, 30_000]
SAN_FRAN = [37.7749, -122.4194, 0]

WAYPOINTS_GEO = [
    DENVER,
    SAN_FRAN,
]


def test_regular_run() -> None:
    with EnvironmentContext() as env:
        add_stage_variable("distance_units", "nmi")
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("stage_model", Spherical)

        mover = Mover(
            name="example",
            location=CartesianLocation(0, 0),
            speed=10,
            fuel=500,
            fuel_burn=10,
        )
        waypoints = [CartesianLocation(*x) for x in WAYPOINTS]
        mover.set_knowledge("destinations", waypoints)
        task = MoveTask()
        task.run(actor=mover)
        env.run()
        assert env.now == 1
        d = mover.location - waypoints[-1]
        assert pytest.approx(d) == 0


def test_first_interrupt() -> None:
    with EnvironmentContext() as env:
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("distance_units", "nmi")
        add_stage_variable("stage_model", Spherical)

        mover = Mover(
            name="example",
            location=CartesianLocation(0, 0),
            speed=10,
            fuel=500,
            fuel_burn=10,
        )
        waypoints = [CartesianLocation(*x) for x in WAYPOINTS]
        mover.set_knowledge("destinations", waypoints)
        task = MoveTask()
        proc = task.run(actor=mover)
        env.run(until=0.25)
        proc.interrupt(cause="restart")
        env.run()
        assert env.now == (2 - 0.25)
        d = mover.location - waypoints[-1]
        assert pytest.approx(d) == 0


def test_second_interrupt() -> None:
    with EnvironmentContext() as env:
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("distance_units", "nmi")
        add_stage_variable("stage_model", Spherical)

        mover = Mover(
            name="example",
            location=CartesianLocation(0, 0),
            speed=10,
            fuel=500,
            fuel_burn=10,
        )
        waypoints = [CartesianLocation(*x) for x in WAYPOINTS]
        mover.set_knowledge("destinations", waypoints)
        task = MoveTask()
        proc = task.run(actor=mover)
        env.run(until=0.75)
        proc.interrupt(cause="restart")
        env.run()
        assert env.now == (2 - 0.75)
        d = mover.location - waypoints[-1]
        assert pytest.approx(d) == 0


def test_regular_run_geo() -> None:
    with EnvironmentContext() as env:
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("distance_units", "nmi")
        add_stage_variable("stage_model", Spherical)

        mover = MoverGeo(
            name="example",
            location=GeodeticLocation(*SAN_FRAN),
            speed=10,
            fuel=500000,
            fuel_burn=10,
        )
        waypoints = [GeodeticLocation(*x) for x in WAYPOINTS_GEO]
        mover.set_knowledge("destinations", waypoints)
        task = MoveTask()
        task.run(actor=mover)
        env.run()
        assert env.now == 164.81767330428073
        d = mover.location - waypoints[-1]
        assert pytest.approx(d) == 0


def test_first_interrupt_geo() -> None:
    with EnvironmentContext() as env:
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("distance_units", "nmi")
        add_stage_variable("stage_model", Spherical)

        mover = MoverGeo(
            name="example",
            location=GeodeticLocation(*SAN_FRAN),
            speed=10,
            fuel=500000,
            fuel_burn=10,
        )
        waypoints = [GeodeticLocation(*x) for x in WAYPOINTS_GEO]
        mover.set_knowledge("destinations", waypoints)
        task = MoveTask()
        proc = task.run(actor=mover)
        env.run(until=40)
        proc.interrupt(cause="restart")
        env.run()
        assert pytest.approx(env.now) == (164.81767330428073 * 2 - 40)
        d = mover.location - waypoints[-1]
        assert pytest.approx(d) == 0


def test_second_interrupt_geo() -> None:
    with EnvironmentContext() as env:
        add_stage_variable("altitude_units", "ft")
        add_stage_variable("distance_units", "nmi")
        add_stage_variable("stage_model", Spherical)

        mover = MoverGeo(
            name="example",
            location=GeodeticLocation(*SAN_FRAN),
            speed=10,
            fuel=500000,
            fuel_burn=10,
        )
        waypoints = [GeodeticLocation(*x) for x in WAYPOINTS_GEO]
        mover.set_knowledge("destinations", waypoints)
        task = MoveTask()
        proc = task.run(actor=mover)
        env.run(until=130)
        proc.interrupt(cause="restart")
        env.run()
        assert pytest.approx(env.now) == (130 + 69.635346608)
        d = mover.location - waypoints[-1]
        assert pytest.approx(d) == 0
