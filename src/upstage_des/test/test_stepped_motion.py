# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from typing import Protocol

import pytest

import upstage_des.api as UP
from upstage_des.motion import SteppedMotionManager
from upstage_des.type_help import TASK_GEN
from upstage_des.utils import waypoint_time_and_dist


class LocatedActor(Protocol):
    location: UP.CartesianLocation


class StaticSensor(UP.Actor):
    radius = UP.State[float](valid_types=float, default=2.0)
    history = UP.State[list](default_factory=list)
    location = UP.State[UP.CartesianLocation](valid_types=(UP.CartesianLocation,))

    def entity_entered_range(self, detected: LocatedActor) -> None:
        dist = self.location - detected.location
        self.history.append((self.env.now, "saw", detected.location, dist))

    def entity_exited_range(self, detected: LocatedActor) -> None:
        dist = self.location - detected.location
        self.history.append((self.env.now, "lost", detected.location, dist))


class Mover(UP.Actor):
    location = UP.CartesianLocationChangingState()
    history = UP.State[list](default_factory=list, recording=False)
    radius = UP.State[float](default=2.0)
    visible = UP.DetectabilityState(default=True)
    speed = UP.State[float](default=1.0)

    def entity_entered_range(self, detected: LocatedActor) -> None:
        dist = self.location - detected.location
        self.history.append((self.env.now, "saw", detected, dist))

    def entity_exited_range(self, detected: LocatedActor) -> None:
        dist = self.location - detected.location
        self.history.append((self.env.now, "lost", detected, dist))


class DoMotion(UP.Task):
    waypoints: list[UP.CartesianLocation]

    # Hacking together, assuming start location is (2, 1, 0)
    def task(self, *, actor: Mover) -> TASK_GEN:
        waypoints = [x.copy() for x in self.waypoints]
        time, dist = waypoint_time_and_dist(actor.location, waypoints, actor.speed)
        actor.activate_state(
            state="location",
            task=self,
            speed=actor.speed,
            waypoints=waypoints,
        )
        yield UP.Wait(time)
        actor.deactivate_all_states(task=self)


class EndDetectable(UP.Task):
    time: float

    def task(self, *, actor: Mover) -> TASK_GEN:
        yield UP.Wait(self.time)
        actor.visible = False


class StartDetectable(UP.Task):
    time: float

    def task(self, *, actor: Mover) -> TASK_GEN:
        yield UP.Wait(self.time)
        actor.visible = True


def test_basic_functions() -> None:
    with UP.EnvironmentContext() as env:
        motion = SteppedMotionManager(0.01)
        UP.add_stage_variable("motion_manager", motion)

        sense = StaticSensor(
            name="Static",
            radius=1.7,
            location=UP.CartesianLocation(0, 0, 0),
        )
        move = Mover(
            name="A_Mover",
            location=UP.CartesianLocation(2, 1, 0),
        )

        motion.add_sensor(sense, "radius", "location")
        # This line is handled automatically now
        # motion.add_detectable(move, "location")

        waypoints = [
            UP.CartesianLocation(1, 1, 1),
            UP.CartesianLocation(0, 0, 2),
        ]

        move_task = DoMotion()
        move_task.waypoints = waypoints
        move_task.run(actor=move)
        motion.run()
        env.run()
        assert len(sense.history[0]) == 4, "Wrong intersection history"


def test_dual_sense() -> None:
    with UP.EnvironmentContext() as env:
        motion = SteppedMotionManager(0.01)
        UP.add_stage_variable("motion_manager", motion)

        move1 = Mover(
            name="A_Mover1",
            location=UP.CartesianLocation(-3, 0, 1),
            radius=2,
        )
        move2 = Mover(
            name="A_Mover2",
            location=UP.CartesianLocation(3, 0, 0.5),
            radius=1,
        )

        for obj in [move1, move2]:
            motion.add_sensor(obj, "radius", "location")
            motion.add_detectable(obj, "location")

        waypoints1 = [
            UP.CartesianLocation(3, 0, 0.5),
        ]
        waypoints2 = [
            UP.CartesianLocation(-3, 0, 1),
        ]

        move_task1 = DoMotion()
        move_task1.waypoints = waypoints1
        move_task1.run(actor=move1)

        move_task2 = DoMotion()
        move_task2.waypoints = waypoints2
        move_task2.run(actor=move2)

        motion.run()
        env.run()
        assert len(move1.history[0]) == 4, "Wrong intersection history"
        assert len(move2.history[0]) == 4, "Wrong intersection history"
        assert move1.history[0][2] is move2
        assert move1.history[1][2] is move2
        assert move2.history[0][2] is move1
        assert move2.history[1][2] is move1
        # different distances
        assert move1.history[0][3] != move2.history[0][3]
        # but correct distances - within a loose tolerance
        assert pytest.approx(move1.history[0][3], abs=0.1) == 2
        assert pytest.approx(move2.history[0][3], abs=0.1) == 1


def test_detectability_change() -> None:
    with UP.EnvironmentContext() as env:
        motion = SteppedMotionManager(0.01)
        UP.add_stage_variable("motion_manager", motion)

        move1 = Mover(
            name="A_Mover1",
            location=UP.CartesianLocation(-3, 0, 1),
            radius=2,
        )
        move2 = Mover(
            name="A_Mover2",
            location=UP.CartesianLocation(3, 0, 0.5),
            radius=1,
        )

        for obj in [move1, move2]:
            motion.add_sensor(obj, "radius", "location")
            motion.add_detectable(obj, "location")

        waypoints1 = [
            UP.CartesianLocation(3, 0, 0.5),
        ]
        waypoints2 = [
            UP.CartesianLocation(-3, 0, 1),
        ]

        move_task1 = DoMotion()
        move_task1.waypoints = waypoints1
        move_task1.run(actor=move1)

        move_task2 = DoMotion()
        move_task2.waypoints = waypoints2
        move_task2.run(actor=move2)

        task_end = EndDetectable()
        task_end.time = 2.9
        task_end.run(actor=move1)

        task_start = StartDetectable()
        task_start.time = 3.1
        task_start.run(actor=move1)

        motion.run()
        env.run()
        assert len(move1.history[0]) == 4, "Wrong intersection history"
        assert len(move2.history[0]) == 4, "Wrong intersection history"
        assert move1.history[0][2] is move2
        assert move1.history[1][2] is move2
        assert move2.history[0][2] is move1
        assert move2.history[1][2] is move1
        assert move2.history[1][0] == 2.9
        assert move2.history[2][0] == 3.1
        assert pytest.approx(move2.history[2][0], abs=0.01) == 3.1


if __name__ == "__main__":
    test_basic_functions()
