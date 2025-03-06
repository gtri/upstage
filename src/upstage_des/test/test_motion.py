# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from typing import Any, Generic, TypeVar, cast

import pytest
import simpy as SIM

import upstage_des.api as UP
from upstage_des.geography import Spherical, get_intersection_locations
from upstage_des.motion.cartesian_model import cartesian_linear_intersection as cli
from upstage_des.motion.geodetic_model import analytical_intersection as agi
from upstage_des.motion.geodetic_model import subdivide_intersection as gi
from upstage_des.type_help import TASK_GEN

LOC = TypeVar("LOC", bound=UP.CartesianLocation | UP.GeodeticLocation)


def close(a: float, b: float) -> bool:
    """Test if two numbers are close.

    Args:
        a (float): number
        b (float): other number

    Returns:
        bool: if they are close
    """
    d = abs(a - b)
    return d <= 1e-8


class DummySensor(Generic[LOC]):
    """A simple sensor for testing purposes."""

    def __init__(self, env: SIM.Environment, location: LOC, radius: float = 1.0) -> None:
        self.env = env
        self.data: list[tuple[Any, float, str]] = []
        self._location = location
        self._radius = radius

    def entity_entered_range(self, mover: Any) -> None:
        self.data.append((mover, self.env.now, "detect"))
        if hasattr(mover, "loc"):
            # call the location to record it
            mover.loc

    def entity_exited_range(self, mover: Any) -> None:
        self.data.append((mover, self.env.now, "end detect"))
        if hasattr(mover, "loc"):
            # call the location to record it
            mover.loc

    @property
    def location(self) -> LOC:
        return self._location

    @property
    def radius(self) -> float:
        return self._radius


class BadSensor:
    """An incomplete sensor for testing purposes."""

    def __init__(self, env: SIM.Environment, location: tuple[float, ...], radius: float) -> None:
        self.env = env
        self._location = UP.CartesianLocation(*location)
        self._radius = radius

    @property
    def location(self) -> UP.CartesianLocation:
        return self._location

    @property
    def radius(self) -> float:
        return self._radius


class DummyMover:
    """A simple mover for testing purposes."""

    def __init__(self, env: SIM.Environment) -> None:
        self.env = env
        self.detect = True

    def _get_detection_state(self) -> str:
        return "detect"


class RealMover(UP.Actor):
    """A more realistic mover that moves in Cartesian Space."""

    loc = UP.CartesianLocationChangingState(recording=True)
    speed = UP.State[float]()
    detect = UP.DetectabilityState()


class RealGeodeticMover(UP.Actor):
    """A more realistic mover that moves in Geodetic Space."""

    loc = UP.GeodeticLocationChangingState(recording=True)
    speed = UP.State[float]()
    detect = UP.DetectabilityState()


# This is not best practices, but it works for testing
class DoMove(UP.Task):
    """A task for movers to move."""

    waypoints: list[UP.GeodeticLocation] | list[UP.CartesianLocation] = []

    def task(self, *, actor: RealGeodeticMover | RealMover) -> TASK_GEN:
        dist = 0.0
        wayps = [actor.loc] + list(self.waypoints)
        for i in range(len(wayps) - 1):
            dist += wayps[i + 1] - wayps[i]
        time = dist / actor.speed

        actor.activate_location_state(
            state="loc",
            task=self,
            speed=actor.speed,
            waypoints=self.waypoints,
        )
        yield UP.Wait(time)
        actor.deactivate_all_states(task=self)

    def on_interrupt(
        self, *, actor: RealGeodeticMover | RealMover, cause: Any
    ) -> UP.InterruptStates:
        if cause == "Become undetectable":
            actor.detect = False
            return self.INTERRUPT.IGNORE
        return self.INTERRUPT.END


L = TypeVar("L")


def _create_mover_and_waypoints(
    env: SIM.Environment,
    mover_type: type,
    location_type: type[L],
    *waypoints: tuple[float, ...],
) -> tuple[UP.Actor, list[L]]:
    mover = cast(UP.Actor, mover_type(env))
    waypoints = [location_type(*waypoint) for waypoint in waypoints]
    return mover, waypoints


def test_errors() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli)

        mover, waypoints = _create_mover_and_waypoints(
            env,
            DummyMover,
            UP.CartesianLocation,
            (0, 0, 0),
            (1, 1, 0),
        )

        bad_sensor = BadSensor(env, (0.9, 0.9), 0.5)

        with pytest.raises(UP.MotionAndDetectionError):
            motion._stop_mover(mover)

        motion._start_mover(mover, speed=1.0, waypoints=waypoints)
        with pytest.raises(UP.MotionAndDetectionError):
            motion._start_mover(mover, speed=1.0, waypoints=[[2, 2], [3, 3]])  # type: ignore [arg-type]

        with pytest.raises(NotImplementedError):
            motion.add_sensor(bad_sensor, "location", "radius")  # type: ignore [arg-type]


def test_no_interaction_cli() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli)
        mover, waypoints = _create_mover_and_waypoints(
            env,
            DummyMover,
            UP.CartesianLocation,
            (2, 0, 0),
            (2, -2, 0),
        )
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc)
        motion.add_sensor(
            sensor,
        )
        motion._start_mover(mover, 1.0, waypoints)
        env.run(until=5.0)

        assert abs(env.now - 5.0) < 1e-12

        assert len(sensor.data) == 0, (
            f"There should be no interaction events, but found: {sensor.data}"
        )
        assert not motion._events.get(mover, [])
        assert sensor not in motion._in_view.get(mover, {})
        assert motion._debug_log == [], "No log expected for no actions"


def test_enter_exit() -> None:
    with UP.EnvironmentContext() as env:
        motion = UP.SensorMotionManager(cli)
        mover, waypoints = _create_mover_and_waypoints(
            env,
            DummyMover,
            UP.CartesianLocation,
            (2, 2, 0),
            (-2, -2, 0),
        )
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc)
        motion.add_sensor(
            sensor,
        )
        motion._start_mover(mover, 1.0, waypoints)
        env.run()
        motion._stop_mover(mover)

        assert abs(env.now - 3.828427124746188) < 1e-12

        assert len(sensor.data) == 2, (
            f"For now, motion manager only has entry event recorded, {sensor.data}"
        )

        assert abs(sensor.data[0][1] - 1.8284271247461907) < 1e-12
        assert sensor.data[0][2] == "detect"
        assert abs(sensor.data[1][1] - 3.828427124746188) < 1e-12
        assert sensor.data[1][2] == "end detect"
        assert not motion._events.get(mover, [])
        assert sensor not in motion._in_view.get(mover, {})


def test_sensor_popup() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli)
        mover, waypoints = _create_mover_and_waypoints(
            env,
            DummyMover,
            UP.CartesianLocation,
            (2, 2, 0),
            (-2, -2, 0),
        )
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc)
        motion._start_mover(mover, 1.0, waypoints)
        env.run(until=2)

        motion.add_sensor(
            sensor,
        )
        env.run()
        motion._stop_mover(mover)

        assert abs(env.now - 3.828427124746188) < 1e-12

        assert len(sensor.data) == 2, (
            f"For now, motion manager only has entry event recorded, {sensor.data}"
        )

        assert abs(sensor.data[0][1] - 2) < 1e-12
        assert sensor.data[0][2] == "detect"
        assert abs(sensor.data[1][1] - 3.828427124746188) < 1e-12
        assert sensor.data[1][2] == "end detect"
        assert not motion._events.get(mover, [])
        assert sensor not in motion._in_view.get(mover, {})


def test_start_inside_exit() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli)
        mover, waypoints = _create_mover_and_waypoints(
            env,
            DummyMover,
            UP.CartesianLocation,
            (0.5, 0.5, 0),
            (-2, -2, 0),
        )
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc)
        motion.add_sensor(
            sensor,
        )
        motion._start_mover(mover, 1.0, waypoints)
        env.run()
        motion._stop_mover(mover)

        assert env.now == 1.7071067811865475

        assert len(sensor.data) == 2, "Need entry and exit events"

        assert abs(sensor.data[0][1] - 0) < 1e-12
        assert sensor.data[0][2] == "detect"
        assert abs(sensor.data[1][1] - 1.7071067811865475) < 1e-12
        assert sensor.data[1][2] == "end detect"
        assert not motion._events.get(mover, [])
        assert sensor not in motion._in_view.get(mover, {})


def test_enter_end_inside_then_leave() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli)
        mover, waypoints = _create_mover_and_waypoints(
            env,
            DummyMover,
            UP.CartesianLocation,
            (2, 2, 0),
            (-0.5, -0.5, 0),
        )
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc)
        motion.add_sensor(
            sensor,
        )
        motion._start_mover(mover, 1.0, waypoints)
        env.run()
        motion._stop_mover(mover)

        assert env.now == 1.8284271247461907

        assert len(sensor.data) == 1, "Ending inside means no exit event"

        assert abs(sensor.data[-1][1] - 1.8284271247461907) < 1e-12
        assert sensor in motion._in_view[mover]
        assert not motion._events.get(mover, [])

        # have the mover leave and run the clock a bit in case
        env.run(until=20)
        assert len(sensor.data) == 1, "No new events should be added to the log"
        assert abs(sensor.data[-1][1] - 1.8284271247461907) < 1e-12
        assert sensor in motion._in_view[mover]

        motion._start_mover(mover, 1.0, waypoints[::-1])
        env.run()
        assert env.now == 21.707106781186546
        assert len(sensor.data) == 2, "Wrong amount of sensor data"
        assert abs(sensor.data[-1][1] - 21.707106781186546) < 1e-12
        assert sensor not in motion._in_view[mover]


def test_start_inside_end_inside() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli)
        mover, waypoints = _create_mover_and_waypoints(
            env,
            DummyMover,
            UP.CartesianLocation,
            (0.5, 0.5, 0),
            (-0.5, -0.5, 0),
        )
        mover = cast(UP.Actor, mover)
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc)
        motion.add_sensor(
            sensor,
        )
        motion._start_mover(mover, 1.0, waypoints)
        env.run()

        assert env.now == 0

        assert len(sensor.data) == 1, f"Only need to see the start recorded: {sensor.data}"
        assert sensor.data[0][2] == "detect"
        assert sensor in motion._in_view[mover]


def test_motion_setup_cli() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=10.0)

        mover = cast(UP.Actor, DummyMover(env))
        mover_start = UP.CartesianLocation(*[8, 8, 2])
        waypoints = [
            mover_start,
            UP.CartesianLocation(*[-8, 8, 2]),
            UP.CartesianLocation(*[-8, -8, 2]),
            UP.CartesianLocation(*[8, -8, 0]),
        ]

        motion.add_sensor(sensor, "location", "radius")
        # This isn't how these things are normally called for movers, but
        # since it isn't going through a task, it's ok here.
        motion._start_mover(mover, 1.0, waypoints)
        assert len(motion._events) == 1
        assert len(motion._events[mover]) == 3
        env.run()
        assert len(sensor.data) == 6
        matches = [2.343145750507622, 18.343145750507624, 34.268912605325006]
        for datum, truth in zip(sensor.data[::2], matches):
            assert pytest.approx(truth) == datum[1]


def test_late_intersection() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=5.0)

        mover = cast(UP.Actor, DummyMover(env))
        mover_start = UP.CartesianLocation(*[0, 8, 0])
        waypoints = [
            mover_start,
            UP.CartesianLocation(*[0, 6, 0]),
        ]
        motion.add_sensor(sensor)
        # This isn't how these things are normally called for movers, but
        # since it isn't going through a task, it's ok here.
        motion._start_mover(mover, 1.0, waypoints)
        env.run()


def test_motion_coordination_cli() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)
        # Test that if the location is a changing state, that it matches up
        # when detections happen
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=10.0)

        mover_start = UP.CartesianLocation(*[8, 8, 2])
        mover = RealMover(name="A Mover", loc=mover_start, speed=1, detect=True)
        waypoints = [
            mover_start,
            UP.CartesianLocation(*[-8, 8, 2]),
            UP.CartesianLocation(*[-8, -8, 2]),
            UP.CartesianLocation(*[8, -8, 0]),
        ]
        task = DoMove()
        task.waypoints = waypoints[1:]
        task.run(actor=mover)

        motion.add_sensor(sensor)

        env.run()
        assert mover.loc == waypoints[-1]
        assert len(motion._debug_data[mover]) == 3
        for i, data in enumerate(motion._debug_data[mover]):
            sense, kinds, times, inters = data
            mover_at_time_0 = [x[1] for x in mover._state_histories["loc"] if close(x[0], times[0])]
            mover_at_time_1 = [x[1] for x in mover._state_histories["loc"] if close(x[0], times[1])]
            assert mover_at_time_0
            assert mover_at_time_1
            assert close(mover_at_time_0[0], inters[0])
            assert close(mover_at_time_1[0], inters[1])


def test_background_motion() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=10.0)

        mover_start = UP.CartesianLocation(*[8, 8, 2])
        mover = RealMover(name="A Mover", loc=mover_start, speed=1, detect=True)
        waypoints = [
            mover_start,
            UP.CartesianLocation(*[-8, 8, 2]),
            UP.CartesianLocation(*[-8, -8, 2]),
            UP.CartesianLocation(*[8, -8, 0]),
        ]
        task = DoMove()
        task.waypoints = waypoints[1:]
        task.run(actor=mover)

        motion.add_sensor(sensor)
        # no need to start the mover this time
        env.run()
        assert mover.loc == waypoints[-1]
        # The motion manager needs to see the mover 3 times, and
        # so does the sensor
        assert len(motion._debug_data[mover]) == 3
        assert len(sensor.data) == 6


def test_background_rehearse() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)

        # This is the key change relative to the above
        flyer_start = UP.CartesianLocation(*[8, 8, 2])
        flyer = RealMover(name="A Mover", loc=flyer_start, speed=1, detect=True)
        waypoints = [
            flyer_start,
            UP.CartesianLocation(*[-8, 8, 2]),
            UP.CartesianLocation(*[-8, -8, 2]),
            UP.CartesianLocation(*[8, -8, 0]),
        ]
        task = DoMove()
        task.waypoints = waypoints[1:]

        flyer_clone = task.rehearse(actor=flyer)

        env.run()
        assert env.now == 0, "No time should pass for rehearsal"
        assert flyer.loc == waypoints[0]
        # The motion manager shouldn't see anything
        assert flyer not in motion._debug_data
        assert flyer_clone not in motion._debug_data


def test_interrupt_clean() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=10.0)

        mover_start = UP.CartesianLocation(*[8, 8, 2])
        mover = RealMover(name="A Mover", loc=mover_start, speed=1, detect=True, debug_log=True)
        waypoints = [
            mover_start,
            UP.CartesianLocation(*[-8, 8, 2]),
            UP.CartesianLocation(*[-8, -8, 2]),
            UP.CartesianLocation(*[8, -8, 0]),
        ]
        task = DoMove()
        task.waypoints = waypoints[1:]
        proc = task.run(actor=mover)

        motion.add_sensor(sensor)
        # no need to start the mover this time
        env.run(until=25)
        proc.interrupt(cause="Stop")
        env.run()

        # The motion manager needs to see the mover 3 times, and
        # the sensor will see it double that for entry/exit
        assert len(motion._debug_data[mover]) == 3
        assert len(sensor.data) == 3
        # the two messages for cancelling the notifications
        assert len(motion._debug_log) == 5
        assert all(
            log_entry["event"] == "Scheduling sensor detecting mover"
            for log_entry in motion._debug_log[:3]
        )
        assert all(line["mover"] is mover for line in motion._debug_log)
        # the order of these two may switch..
        msgs = [
            "Detection of a mover cancelled before exit",
            "Detection of a mover cancelled before entry",
        ]
        events = [motion._debug_log[i]["event"] for i in [3, 4]]
        assert len(set(events)) == 2, "Need two unique event descriptions"
        assert all(x in msgs for x in events), "Need both types exactly"
        # the mover should be stopped
        assert mover not in motion._movers


def test_undetectable_cli() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=10.0)

        mover_start = UP.CartesianLocation(*[8, 8, 2])
        mover = RealMover(name="A Mover", loc=mover_start, speed=1, debug_log=True, detect=True)
        waypoints = [
            mover_start,
            UP.CartesianLocation(*[-8, 8, 2]),
            UP.CartesianLocation(*[-8, -8, 2]),
            UP.CartesianLocation(*[8, -8, 0]),
        ]
        task = DoMove()
        task.waypoints = waypoints[1:]
        proc = task.run(actor=mover)

        motion.add_sensor(sensor)
        # no need to start the mover this time
        env.run(until=25)

        # check that the motion manager has the right data
        assert mover in motion._in_view, "Mover not found in progress"
        proc.interrupt(cause="Become undetectable")
        env.run()

        assert sensor.data[-1] == (mover, 25, "end detect")


def test_redetectable() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=10.0)

        mover_start = UP.CartesianLocation(*[8, 8, 2])
        mover = RealMover(name="A Mover", loc=mover_start, speed=1, debug_log=True, detect=False)
        waypoints = [
            mover_start,
            UP.CartesianLocation(*[-8, 8, 2]),
            UP.CartesianLocation(*[-8, -8, 2]),
            UP.CartesianLocation(*[8, -8, 0]),
        ]
        task = DoMove()
        task.waypoints = waypoints[1:]
        task.run(actor=mover)

        motion.add_sensor(sensor)
        # no need to start the mover this time
        env.run(until=25)
        with pytest.warns(UserWarning, match="Setting DetectabilityState to True while*"):
            mover.detect = True


def test_undetectable_after() -> None:
    with UP.EnvironmentContext() as env:
        UP.add_stage_variable("distance_units", "m")
        motion = UP.SensorMotionManager(cli, debug=True)
        UP.add_stage_variable("motion_manager", motion)
        loc = UP.CartesianLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=10.0)

        mover_start = UP.CartesianLocation(*[8, 8, 2])
        mover = RealMover(name="A Mover", loc=mover_start, speed=1, debug_log=True, detect=True)
        waypoints = [
            mover_start,
            UP.CartesianLocation(*[-8, 8, 2]),
            UP.CartesianLocation(*[-8, -8, 2]),
            UP.CartesianLocation(*[8, -8, 0]),
        ]
        task = DoMove()
        task.waypoints = waypoints[1:]
        proc = task.run(actor=mover)

        motion.add_sensor(sensor)
        # no need to start the mover this time
        env.run(until=30)

        # check that the motion manager has the right data
        assert mover in motion._in_view, "Mover not found in progress"
        proc.interrupt(cause="Become undetectable")
        env.run()

        assert (mover, 30, "end detect") not in sensor.data
        assert len(sensor.data) == 4


def test_motion_setup_gi() -> None:
    with UP.EnvironmentContext() as env:
        motion = UP.SensorMotionManager(gi, debug=True)
        UP.add_stage_variable("stage_model", Spherical)
        UP.add_stage_variable("altitude_units", "m")
        UP.add_stage_variable("distance_units", "nmi")
        UP.add_stage_variable("intersection_model", get_intersection_locations)
        loc = UP.GeodeticLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=150.0)

        geo_mover = cast(UP.Actor, DummyMover(env))
        t = 2
        geo_mover_start = UP.GeodeticLocation(*[t, t, 4000])
        waypoints = [
            geo_mover_start,
            UP.GeodeticLocation(*[-t, t, 4000]),
            UP.GeodeticLocation(*[-t, -t, 4000]),
            UP.GeodeticLocation(*[t, -t, 0]),
        ]

        motion.add_sensor(sensor)
        motion._start_mover(geo_mover, 1.0, waypoints)
        assert len(motion._events) == 1
        assert len(motion._events[geo_mover]) == 3
        env.run()
        assert len(sensor.data) == 6
        matches = [30.59361210120766, 271.030439713508, 511.28446115022086]
        for datum, truth in zip(sensor.data[::2], matches):
            assert pytest.approx(truth, abs=0.001) == datum[1]


def test_no_interaction_gi() -> None:
    with UP.EnvironmentContext() as env:
        motion = UP.SensorMotionManager(gi, debug=True)
        UP.add_stage_variable("stage_model", Spherical)
        UP.add_stage_variable("altitude_units", "ft")
        UP.add_stage_variable("distance_units", "nmi")
        UP.add_stage_variable("intersection_model", get_intersection_locations)

        motion = UP.SensorMotionManager(gi)
        loc = UP.GeodeticLocation(*[90, 40, 0])
        sensor = DummySensor(env, loc, 1.0)

        mover = cast(UP.Actor, DummyMover(env))
        waypoints = [
            UP.GeodeticLocation(0, 10, 0),
            UP.GeodeticLocation(10, 10, 0),
        ]

        motion.add_sensor(
            sensor,
        )
        motion._start_mover(mover, 1.0, waypoints)
        env.run(until=5.0)

        assert abs(env.now - 5.0) < 1e-12

        assert len(sensor.data) == 0, (
            f"There should be no interaction events, but found: {sensor.data}"
        )

        motion._stop_mover(mover)


def test_motion_coordination_gi() -> None:
    with UP.EnvironmentContext() as env:
        motion = UP.SensorMotionManager(gi, debug=True)
        UP.add_stage_variable("stage_model", Spherical)
        UP.add_stage_variable("altitude_units", "m")
        UP.add_stage_variable("distance_units", "nmi")
        UP.add_stage_variable("intersection_model", get_intersection_locations)
        UP.add_stage_variable("motion_manager", motion)
        loc = UP.GeodeticLocation(0, 0, 0)
        sensor = DummySensor(env, loc, radius=150.0)

        t = 2
        geo_mover_start = UP.GeodeticLocation(*[t, t, 4000])
        geo_mover = RealGeodeticMover(name="Mover", loc=geo_mover_start, speed=1, detect=True)

        waypoints = [
            geo_mover_start,
            UP.GeodeticLocation(*[-t, t, 4000]),
            UP.GeodeticLocation(*[-t, -t, 4000]),
            UP.GeodeticLocation(*[t, -t, 0]),
        ]

        task = DoMove()
        task.waypoints = waypoints[1:]
        task.run(actor=geo_mover)

        motion.add_sensor(sensor)

        env.run()
        assert abs(geo_mover.loc - waypoints[-1]) <= 1e-12
        assert len(motion._debug_data[geo_mover]) == 3
        for i, data in zip([1, 3, 5], motion._debug_data[geo_mover]):
            sense, kinds, times, inters = data
            mover_at_time_0 = [
                x[1] for x in geo_mover._state_histories["loc"] if close(x[0], times[0])
            ]
            mover_at_time_1 = [
                x[1] for x in geo_mover._state_histories["loc"] if close(x[0], times[1])
            ]
            assert mover_at_time_0
            assert mover_at_time_1
            assert close(mover_at_time_0[0], inters[0])
            assert close(mover_at_time_1[0], inters[1])


def test_motion_setup_agi() -> None:
    with UP.EnvironmentContext() as env:
        motion = UP.SensorMotionManager(agi, debug=True)
        UP.add_stage_variable("stage_model", Spherical)
        UP.add_stage_variable("altitude_units", "m")
        UP.add_stage_variable("distance_units", "nmi")
        UP.add_stage_variable("intersection_model", get_intersection_locations)
        UP.add_stage_variable("motion_manager", motion)
        sensor = DummySensor(env, UP.GeodeticLocation(0, 0, 0), radius=150.0)

        geo_mover = cast(UP.Actor, DummyMover(env))
        t = 2
        geo_mover_start = UP.GeodeticLocation(*[t, t, 4000])
        waypoints = [
            geo_mover_start,
            UP.GeodeticLocation(*[-t, t, 4000]),
            UP.GeodeticLocation(*[-t, -t, 4000]),
            UP.GeodeticLocation(*[t, -t, 0]),
        ]

        motion.add_sensor(sensor)
        motion._start_mover(geo_mover, 1.0, waypoints)
        assert len(motion._events) == 1
        assert len(motion._events[geo_mover]) == 3
        env.run()
        assert len(sensor.data) == 6
        matches = [30.511, 270.967, 511.207]
        for datum, truth in zip(sensor.data[::2], matches):
            assert pytest.approx(truth, abs=0.1) == datum[1]


def test_no_interaction_agi() -> None:
    with UP.EnvironmentContext() as env:
        motion = UP.SensorMotionManager(agi, debug=True)
        UP.add_stage_variable("stage_model", Spherical)
        UP.add_stage_variable("altitude_units", "m")
        UP.add_stage_variable("distance_units", "nmi")
        UP.add_stage_variable("intersection_model", get_intersection_locations)
        UP.add_stage_variable("motion_manager", motion)

        motion = UP.SensorMotionManager(agi)
        sensor = DummySensor(env, UP.GeodeticLocation(0, 0, 0))
        UP.GeodeticLocation(*[0, 0, 0])

        mover = cast(UP.Actor, DummyMover(env))
        waypoints = [
            UP.GeodeticLocation(0, 10, 0),
            UP.GeodeticLocation(10, 10, 0),
        ]

        motion.add_sensor(
            sensor,
        )
        motion._start_mover(mover, 1.0, waypoints)
        env.run(until=5.0)

        assert abs(env.now - 5.0) < 1e-12

        assert len(sensor.data) == 0, (
            f"There should be no interaction events, but found: {sensor.data}"
        )

        motion._stop_mover(mover)


def test_motion_coordination_agi() -> None:
    with UP.EnvironmentContext() as env:
        motion = UP.SensorMotionManager(agi, debug=True)
        UP.add_stage_variable("stage_model", Spherical)
        UP.add_stage_variable("altitude_units", "m")
        UP.add_stage_variable("distance_units", "nmi")
        UP.add_stage_variable("intersection_model", get_intersection_locations)
        UP.add_stage_variable("motion_manager", motion)

        sensor = DummySensor(env, UP.GeodeticLocation(0, 0, 0), radius=150.0)

        t = 2
        geo_mover_start = UP.GeodeticLocation(*[t, t, 4000])
        geo_mover = RealGeodeticMover(name="Mover", loc=geo_mover_start, speed=1, detect=True)

        waypoints = [
            geo_mover_start,
            UP.GeodeticLocation(*[-t, t, 4000]),
            UP.GeodeticLocation(*[-t, -t, 4000]),
            UP.GeodeticLocation(*[t, -t, 0]),
        ]

        task = DoMove()
        task.waypoints = waypoints[1:]
        task.run(actor=geo_mover)

        motion.add_sensor(sensor)

        env.run()
        assert abs(geo_mover.loc - waypoints[-1]) <= 1e-12
        assert len(motion._debug_data[geo_mover]) == 3
        for i, data in zip([1, 3, 5], motion._debug_data[geo_mover]):
            sense, kinds, times, inters = data
            mover_at_time_0 = [
                x[1] for x in geo_mover._state_histories["loc"] if close(x[0], times[0])
            ]
            mover_at_time_1 = [
                x[1] for x in geo_mover._state_histories["loc"] if close(x[0], times[1])
            ]
            assert mover_at_time_0
            assert mover_at_time_1
            assert abs(mover_at_time_0[0] - inters[0]) <= 0.5  # nmi
            assert abs(mover_at_time_1[0] - inters[1]) <= 0.7  # nmi


def test_analytical_intersection() -> None:
    with UP.EnvironmentContext():
        UP.add_stage_variable("stage_model", Spherical)
        UP.add_stage_variable("altitude_units", "m")
        UP.add_stage_variable("distance_units", "nmi")

        start = UP.GeodeticLocation(33.67009544379275, -84.59178543542892, 5_000)
        finish = UP.GeodeticLocation(33.871012616336344, -84.16331866903882, 5_000)
        middle = UP.GeodeticLocation(33.7774620987044, -84.38304521590554, 4_000)

        res = agi(start, finish, 200.0, middle, 200.0)
        intersections, times, types, path_time = res
        assert types == ["START_INSIDE", "END_INSIDE"]
