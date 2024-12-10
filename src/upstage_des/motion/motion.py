# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""This file contains a queueing motion manager for sensor/mover intersections."""

from collections.abc import Callable, Generator
from typing import Any, Protocol, TypeVar
from warnings import warn

from simpy import Event as SimpyEvent
from simpy import Interrupt, Process

from upstage_des.actor import Actor
from upstage_des.base import (
    MotionAndDetectionError,
    SimulationError,
    UpstageBase,
)
from upstage_des.data_types import CartesianLocation, GeodeticLocation
from upstage_des.states import CartesianLocationChangingState, GeodeticLocationChangingState

VALID = [
    ("ENTER", "END_INSIDE"),
    ("ENTER", "EXIT"),
    ("START_INSIDE", "END_INSIDE"),
    ("START_INSIDE", "EXIT"),
]

LOC_TYPES = CartesianLocation | GeodeticLocation
LOC_LIST = list[CartesianLocation] | list[GeodeticLocation]

LOC_INPUT = TypeVar("LOC_INPUT", "GeodeticLocation", "CartesianLocation")

INTERSECTION_TIMING_CALLABLE = Callable[
    [
        LOC_INPUT,
        LOC_INPUT,
        float,
        LOC_INPUT,
        float,
    ],
    tuple[
        list[LOC_INPUT],
        list[float],
        list[str],
        float,
    ],
]


class SensorType(Protocol):
    """Protocol class for sensor typing."""

    def entity_exited_range(
        self,
        entity: Any,
    ) -> None:
        """Entity exit range and does something."""

    def entity_entered_range(
        self,
        entity: Any,
    ) -> None:
        """Entity enters range and does something."""


class SensorMotionManager(UpstageBase):
    """Schedules the interaction of moving and detectable entities against non-moving 'sensors'.

    Movable objects must be Actors with:
    1. GeodeticLocationChangingState OR CartesianLocationChangingState
    2. DetectabilityState

    Sensor objects MUST implement these two methods:
    1. `entity_entered_range(mover)`
    2. `entity_exited_range(mover)`

    The first is called when a mover enters the sensor's visiblity.
    The second is called when a mover leaves the visibility or becomes undetectable.

    The motion manager will learn about sensor objects with:

    sensor_motion_manager.add_sensor(sensor_object, location, radius)

    Where location is a location object found in upstage.data_types and radius
    is a distance in the units defined in upstage.STAGE.

    """

    def __init__(
        self, intersection_model: INTERSECTION_TIMING_CALLABLE, debug: bool = False
    ) -> None:
        """Create a sensor motion manager for queueing intersection events.

        Args:
            intersection_model (INTERSECTION_TIMING_CALLABLE): The odel to calculate
                intersections.
            debug (bool, optional): Allow debug logging to _debug_log. Defaults to False.
        """
        super().__init__()
        self._sensors: dict[SensorType, tuple[str, str]] = {}
        self._movers: dict[Actor, tuple[float, LOC_LIST, float]] = {}
        self._events: dict[Actor, list[tuple[SensorType, Process]]] = {}
        self._in_view: dict[Actor, set[SensorType]] = {}
        self._debug: bool = debug
        self._debug_data: dict[Actor, list[Any]] = {}
        self._debug_log: list[Any] = []
        self.intersection = intersection_model

    def _test_detect(self, mover: Actor) -> str | None:
        detect_state = mover._get_detection_state()
        return detect_state

    def _stop_mover(self, mover: Actor, from_not_detectable: bool = False) -> None:
        """Stop a mover.

        Args:
            mover (Actor): The moving actor.
            from_not_detectable (bool, optional): Is this was called from detectability state.
                Defaults to False.
        """
        detect_state = self._test_detect(mover)
        if detect_state is None:
            return None

        detectable: bool = getattr(mover, detect_state)
        if mover not in self._movers and not detectable:
            return None

        # Call this when a mover stops its motion
        if mover not in self._movers and not from_not_detectable:
            raise MotionAndDetectionError(f"Mover {mover} wasn't moving yet")
        elif mover not in self._movers:
            return None
        # It's possible for a mover to have no events when it stops
        # since it has no intersections. But we need the mover to exist
        # in case a new sensor pops up
        if mover in self._events:
            for _, proc in self._events.get(mover, []):
                if proc.is_alive:
                    proc.interrupt()
            del self._events[mover]

        # clear the mover references
        del self._movers[mover]
        return None

    def _mover_not_detectable(self, mover: Actor) -> None:
        """Called via DetectabilityState when a mover becomes undectable.

        Could be called for any reason; use this feature to alert sensors that
        a mover should no longer be considered by that sensor.

        Args:
            mover (Actor): The mover.
        """
        if mover in self._in_view:
            for sensor in self._in_view[mover]:
                # This will cause some old data to stick around, but that's
                # instead of making new events to clear it out and then having
                # to end those clearing events if this happens
                sensor.entity_exited_range(mover)
            del self._in_view[mover]
        # It is unsure if the user will stop the motion via a task first
        # or change detectability first
        self._stop_mover(mover, from_not_detectable=True)

    def _mover_became_detectable(self, mover: Actor) -> None:
        """Called via DetectabilityState when a mover becomes detectable.

        The actor calls this in its movement states.

        Args:
            mover (Actor): The mover.
        """
        # Before a mover is 'restarted' when becoming detectable,
        # we have to know if it's still moving
        move_states = (
            GeodeticLocationChangingState,
            CartesianLocationChangingState,
        )
        # find if there is a location changing state that is active
        locations = [
            name
            for name in mover._active_states
            if isinstance(mover._state_defs[name], move_states)
        ]
        if locations:
            msg = (
                "Setting DetectabilityState to True while "
                "locations states are active won't affect the"
                "SensorMotionManager."
            )
            warn(msg, UserWarning)

    # TODO: remove sensor or 'not active'?

    def _process_mover_sensor_pair(
        self, mover: Actor, sensor: SensorType
    ) -> list[tuple[tuple[str, float, LOC_TYPES], tuple[str, float, LOC_TYPES]]]:
        """Find the intersections (if any) b/w mover and sensor.

        Args:
            mover (Actor): The mover
            sensor (SensorType): The sensor

        Returns:
            list[tuple[str, float]]: What the movement events are are and their times
        """
        # Get pairs of "Inside/entering - Leaving/staying" to send
        # to the probability model and scheduler
        speed, waypoints, start_time = self._movers[mover]
        location_name, radius_name = self._sensors[sensor]
        location: LOC_TYPES = getattr(sensor, location_name)
        radius: float = getattr(sensor, radius_name)

        # Since waypoints connect, don't keep 'finish_in' unless
        # it's the last point in the series
        elapsed_time: float = 0.0
        inter_data: list[tuple[str, float, LOC_TYPES]] = []
        for i in range(len(waypoints) - 1):
            start, finish = waypoints[i : i + 2]
            # These times are relative to the start of the path
            intersections, times, types, path_time = self.intersection(
                start,
                finish,
                speed,
                location,
                radius,
            )

            for (
                inter,
                t,
                typ,
            ) in zip(intersections, times, types):
                if inter_data and inter_data[-1][0] == "END_INSIDE":
                    # drop that one since we are continuing on from that point
                    # and ignore this current one since it's inside already
                    if typ != "START_INSIDE":
                        raise SimulationError("START_INSIDE must follow END_INSIDE")

                    inter_data.pop()
                    continue
                inter_data.append((typ, start_time + elapsed_time + t, inter))
            elapsed_time += path_time

        # pair off the in/out
        if len(inter_data) % 2 != 0:
            raise SimulationError(f"Intersections should pair in/out or in/in, found: {inter_data}")
        pairs = [(inter_data[i], inter_data[i + 1]) for i in range(0, len(inter_data), 2)]
        if not all((a[0], b[0]) in VALID for a, b in pairs):
            raise SimulationError(f"Bad pairing of intersections: {pairs}")
        return pairs

    def _add_to_view(self, mover: Actor, sensor: SensorType) -> bool:
        """Add a mover to a sensor's view.

        Args:
            mover (Actor): Mover
            sensor (Actor): Sensor

        Returns:
            bool: If it was already in view.
        """
        if mover not in self._in_view:
            self._in_view[mover] = set()
        was_in = sensor in self._in_view[mover]
        self._in_view[mover].add(sensor)
        return was_in

    def _remove_from_view(self, mover: Actor, sensor: SensorType) -> None:
        """Remove a mover from a sensor's view.

        Args:
            mover (Actor): Mover
            sensor (Actor): Sensor
        """
        if mover not in self._in_view:
            raise MotionAndDetectionError(f"{mover} isn't in view of anything to remove.")
        if sensor not in self._in_view[mover]:
            raise MotionAndDetectionError(f"{mover} isn't in view of {sensor} to allow clearing.")
        self._in_view[mover].remove(sensor)

    def _end_notify(self, mover: Actor, sensor: SensorType, event: str) -> None:
        """End notification and give a reason.

        Args:
            mover (Actor): Mover
            sensor (Actor): Sensor
            event (str): Reason
        """
        if self._debug:
            msg = {
                "time": self.env.now,
                "event": f"Detection of a mover cancelled {event}",
                "mover": mover,
                "sensor": sensor,
            }
            self._debug_log.append(msg)

    def _notify(
        self,
        mover: Actor,
        sensor: SensorType,
        first_time: float,
        second_time: float,
        first_kind: str,
        second_kind: str,
    ) -> Generator[SimpyEvent, Any, None]:
        """Notify a sensor about a mover.

        Handles entry to exit in one go, making interrupts easier.

        Args:
            mover (Actor): Mover
            sensor (Actor): Sensor
            first_time (float): Time of the first notification
            second_time (float): Time of the second
            first_kind (str): Kind of the first
            second_kind (str): Kind of the second
        """
        # times are absolute on input to this method
        notify_time_from_now = first_time - self.env.now

        if first_kind == "START_INSIDE" or notify_time_from_now <= 0:
            was_in = self._add_to_view(mover, sensor)
            if not was_in:
                sensor.entity_entered_range(mover)
        else:
            assert first_kind == "ENTER"
            try:
                yield self.env.timeout(notify_time_from_now)
            except Interrupt:
                self._end_notify(mover, sensor, "before entry")
                return None

            sensor.entity_entered_range(mover)
            self._add_to_view(mover, sensor)

        if second_kind != "EXIT":
            return None

        end_time_from_now = second_time - self.env.now
        if end_time_from_now <= 0:
            raise MotionAndDetectionError("Detection end time is less than detection start")

        try:
            yield self.env.timeout(end_time_from_now)
        except Interrupt:
            self._end_notify(mover, sensor, "before exit")
            return None

        sensor.entity_exited_range(mover)
        self._remove_from_view(mover, sensor)
        return None

    def _schedule(
        self,
        mover: Actor,
        sensor: SensorType,
        events: tuple[tuple[str, float, LOC_TYPES], tuple[str, float, LOC_TYPES]],
    ) -> None:
        """Schedule events based on entry/exit into sensor range.

        Args:
            mover (Actor): The mover
            sensor (SensorType): The sensor
            events (list[tuple[str, float]]): Crossing events (ENTER and EXIT)
        """
        if not events:
            return
        first_kind, first_time, first_loc = events[0]
        second_kind: str = ""
        second_time: float = first_time
        second_loc: LOC_TYPES | None = None
        if len(events) > 1:
            second_kind, second_time, second_loc = events[1]

        # If both times are in the past, then the segment has already occurred
        # and we can skip it.
        if first_time <= self.env.now and second_time < self.env.now:
            return

        if self._debug:
            self._debug_data[mover].append(
                (
                    sensor,
                    [first_kind, second_kind],
                    [first_time, second_time],
                    [first_loc, second_loc],
                )
            )
            msg = {
                "time": self.env.now,
                "event": "Scheduling sensor detecting mover",
                "mover": mover,
                "sensor": sensor,
            }
            self._debug_log.append(msg)

        proc = self.env.process(
            self._notify(mover, sensor, first_time, second_time, first_kind, second_kind)
        )
        if mover not in self._events:
            self._events[mover] = [
                (sensor, proc),
            ]
        else:
            self._events[mover].append((sensor, proc))

    def _find_intersections(
        self,
        mover_list: list[Actor] | None = None,
        sensor_list: list[SensorType] | None = None,
    ) -> None:
        """Find all paired intersections and schedule them.

        Optionally, use a reduced list of either movers or sensors.

        Args:
            mover_list (list[Actor] | None, optional): Movers to consider.
                Defaults to None (all movers).
            sensor_list (list[SensorType] | None, optional): Sensors to consider.
                Defaults to None (all sensors).
        """
        movers = list(self._movers.keys()) if mover_list is None else mover_list
        sensors = list(self._sensors.keys()) if sensor_list is None else sensor_list
        for m in movers:
            for s in sensors:
                inter_pairs = self._process_mover_sensor_pair(m, s)
                for pair in inter_pairs:
                    self._schedule(m, s, pair)

    def _start_mover(self, mover: Actor, speed: float, waypoints: LOC_LIST) -> None:
        """Start a mover's motion and find intersections with sensors.

        Args:
            mover (Actor): The mover
            speed (float): Speed (in model units)
            waypoints (LOC_LIST): Waypoint of travel.
        """
        detect_state = self._test_detect(mover)
        if detect_state is None:
            return

        detectable = getattr(mover, detect_state)
        # Since this class examines self._movers when mover stops, we need to put in
        # some data about that so we get the right errors if new motion starts
        # when this motion hasn't ended.
        if not detectable:
            self._movers[mover] = (0.0, [], 0.0)
            return None

        if mover in self._movers:
            raise MotionAndDetectionError(
                f"Mover: {mover} is already known to be on a path. Did you forget to stop it?"
            )

        if self._debug and mover not in self._debug_data:
            self._debug_data[mover] = []
        # TODO: Waypoints need to start with the movers current location
        self._movers[mover] = (speed, waypoints, self.env.now)
        self._find_intersections(mover_list=[mover], sensor_list=None)
        return None

    def add_sensor(
        self,
        sensor: SensorType,
        location_attr_name: str = "location",
        radius_attr_name: str = "radius",
    ) -> None:
        """Add a sensor to the motion manager.

        Args:
            sensor (SensorType): The sensor object
            location_attr_name (str, optional): Name of the location attribute.
                Defaults to "location".
            radius_attr_name (str, optional): Name of the radius attribute. Defaults to "radius".
        """
        # test the sensor for earlier errors about improperly-defined methods
        required_methods = ["entity_entered_range", "entity_exited_range"]
        for req in required_methods:
            if not hasattr(sensor, req):
                raise NotImplementedError(f"Sensor {sensor} does not have '{req}' method!")
        for attr in [location_attr_name, radius_attr_name]:
            _attr = getattr(sensor, attr, None)
            if _attr is None:
                raise SimulationError(f"Sensor {sensor} has no attribute: {attr}")

        self._sensors[sensor] = (location_attr_name, radius_attr_name)
        self._find_intersections(mover_list=None, sensor_list=[sensor])
