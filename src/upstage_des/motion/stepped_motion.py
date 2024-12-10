# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""This file contains a motion manager that does time-stepping."""

from collections.abc import Callable, Generator
from typing import Any, cast

from simpy import Event as SimpyEvent

from upstage_des.actor import Actor
from upstage_des.base import SimulationError, UpstageBase
from upstage_des.motion.motion import LOC_TYPES, SensorType
from upstage_des.states import CartesianLocationChangingState, GeodeticLocationChangingState
from upstage_des.task import process


class SteppedMotionManager(UpstageBase):
    """Tests relative distances of objects with a location property.

    Reports to "sensor" objects when something enters or exits a range.

    Use this manager when the sensing entities are not static. If they are
    static, use `SensorMotionManager`.

    Detectable objects and sensor objects must have an attribute that is a GeodeticLocationState
    OR CartesianLocationState

    Detectable objects, if they aren't Actors, could implement _get_detection_state() -> bool:`
    to allow this class to ignore them sometimes. The default way is to use a `DetectabilityState`
    on the actor.

    Sensor objects MUST implement these two methods:
    1. `entity_entered_range(object)`
    2. `entity_exited_range(object)`

    The first is called when an entity enters the sensor's visiblity.
    The second is called when an entity leaves the visibility or becomes undetectable.

    The sensor object CAN implement a method called `detection_checker`.
    That method takes the location of an object to detect and returns True/False.

    The motion manager will learn about sensor objects with:

    sensor_motion_manager.add_sensor(sensor_object, radius)

    Where radius is a distance in the units defined in upstage.STAGE.

    Simple usage:
    >>> manager = SteppedMotionManager(timestep=0.1)
    >>> UP.STAGE.motion_manager = manager
    >>>  ...
    >>> manager.add_sensor(binoculars, 'vision_radius')
    >>> manager.add_detectable(bird, 'location')

    # TODO: Unify sensor and movable
    # TODO: Having only moving things be detectable/using `_start_mover`
    is easy, but this class lets us do static detection easier, so we may
    have to go about it differently.
    # TODO: Data structures for efficient distances
    """

    def __init__(self, timestep: float, max_empty_events: int = 3, debug: bool = False) -> None:
        """Create the Stepped motion manager.

        Args:
            timestep (float): Timestep to do all pairs distance checks.
            max_empty_events (int, optional): How many timesteps where no events causes a shutdown.
                Defaults to 3.
            debug (bool, optional): Record data or not. Defaults to False.
        """
        super().__init__()
        self._sensors: dict[SensorType, tuple[Callable[[], float], Callable[[], LOC_TYPES]]] = {}
        self._detectables: dict[Actor, Callable[[], LOC_TYPES]] = {}
        self._in_view: set[tuple[SensorType, Actor]] = set()
        self._timestep = timestep
        self._max_empty_events = max_empty_events
        self._debug = debug
        self._debug_log: list[Any] = []
        self._is_running = False

    def _do_log(self, msg: Any) -> None:
        """Write to a log list.

        Args:
            msg (Any): Anything to append.
        """
        if self._debug:
            self._debug_log.append(msg)

    def _update_awareness(self, sensor: SensorType, object: Actor, visible: bool) -> None:
        """Modify sensor/object awareness.

        Args:
            sensor (SensorType): Sensor
            object (Actor): The sensed
            visible (bool): If the sensed is visible.
        """
        if visible:
            if (sensor, object) not in self._in_view:
                self._in_view.add((sensor, object))
                sensor.entity_entered_range(object)
        else:
            if (sensor, object) in self._in_view:
                self._in_view.remove((sensor, object))
                sensor.entity_exited_range(object)

    def _test_detect(self, detectable: Actor) -> bool:
        """Is an actor detectable?

        Args:
            detectable (Actor): The detectable

        Returns:
            bool: If it can be detected
        """
        if not hasattr(detectable, "_get_detection_state"):
            return True
        detect_state = detectable._get_detection_state()
        if detect_state is None:
            return True
        visibility: bool = getattr(detectable, detect_state)
        return visibility

    @staticmethod
    def _detect_dist(loc1: LOC_TYPES, radius: float, loc2: LOC_TYPES, sensor: SensorType) -> bool:
        """Run a detectability check, including sensor custom function.

        Args:
            loc1 (LOC_TYPES): Sensor location
            radius (float): Sensor radius
            loc2 (LOC_TYPES): Target location
            sensor (SensorType): Sensor object

        Returns:
            bool: If it's detectable
        """
        if hasattr(sensor, "detection_checker"):
            visible = sensor.detection_checker(loc2)
        else:
            dist = loc1.straight_line_distance(loc2)
            visible = dist <= radius
        return cast(bool, visible)

    def _run_detectable(
        self,
        sensor_req: list[SensorType] | None = None,
        detectable_req: list[Actor] | None = None,
    ) -> None:
        """All pairs distance checking.

        Args:
            sensor_req (list[SensorType] | None, optional): Sensors. Defaults to None.
            detectable_req (list[Actor] | None, optional): Detectables. Defaults to None.
        """
        sensor_req = list(self._sensors) if sensor_req is None else sensor_req
        sensor_radii = [self._sensors[s][0]() for s in sensor_req]
        sensor_locs = [self._sensors[s][1]() for s in sensor_req]

        detectable_req = list(self._detectables) if detectable_req is None else detectable_req
        detectable_req = [d for d in detectable_req if self._test_detect(d)]
        detect_locs = [self._detectables[d]() for d in detectable_req]

        for sensor, radius, loc in zip(sensor_req, sensor_radii, sensor_locs):
            for detectable, d_loc in zip(detectable_req, detect_locs):
                if detectable is sensor:
                    continue
                visible = self._detect_dist(loc, radius, d_loc, sensor)
                self._do_log((self.env.now, sensor, loc, detectable, d_loc))
                self._update_awareness(sensor, detectable, visible)

    def _only_event_test(self) -> bool:
        """Determine if there are no events in the queue."""
        if len(self.env._queue) == 0:
            return True
        return False

    @process
    def run(self) -> Generator[SimpyEvent, None, None]:
        """Run the main stepped motion loop.

        Yields:
            Generator[SimpyEvent, None, None]: _description_
        """
        if self._is_running:
            # If run() is called later than a task is queued,
            # then this may be true already.
            return
        self._is_running = True
        n_empty = 0
        while True:
            timeout = self.env.timeout(self._timestep)
            yield timeout
            self._run_detectable()
            # prevents infinite simulations
            if self._only_event_test():
                n_empty += 1
                if n_empty >= self._max_empty_events:
                    return
            else:
                n_empty = 0

    @process
    def run_particular(self, rate: float, detectable: Actor) -> Generator[SimpyEvent, None, None]:
        """Run detections against a single target at a faster rate.

        Args:
            rate (float): Time rate to do detection checks.
            detectable (Actor): The actor to be detected by the known sensors.
        """
        while True:
            yield self.env.timeout(rate)
            self._run_detectable(sensor_req=None, detectable_req=[detectable])

    def add_sensor(
        self,
        sensor: SensorType,
        radius_attr_name: str = "radius",
        location_attr_name: str = "location",
    ) -> None:
        """Add a sensor the motion manager.

        Args:
            sensor (SensorType): The sensing object
            radius_attr_name (str): Radius attribute name. Defaults to "radius".
            location_attr_name (str): Location attribute name. Defaults to "location".
        """
        # test the sensor for earlier errors about improperly-defined methods
        required_methods = ["entity_entered_range", "entity_exited_range"]
        required_attrs = [radius_attr_name, location_attr_name]
        for req in required_methods:
            if not hasattr(sensor, req):
                raise NotImplementedError(f"Sensor {sensor} does not have '{req}' method!")
        for attr in required_attrs:
            if not hasattr(sensor, attr):
                raise SimulationError(f"Sensor {sensor} doesn't have attribute {attr}")

        def get_radius() -> float:
            return cast(float, getattr(sensor, radius_attr_name))

        def get_location() -> LOC_TYPES:
            return cast(LOC_TYPES, getattr(sensor, location_attr_name))

        self._sensors[sensor] = (get_radius, get_location)

    def add_detectable(
        self,
        detectable: Actor,
        location_attr_name: str = "location",
        new_rate: float | None = None,
    ) -> None:
        """Add an object that is detectable to the manager.

        The object must have an attribute that performs distance calculations.
        See the class docstring for more.

        Args:
            detectable (Actor): An object that has a location attribute
            location_attr_name (str): Name of the location attribute. Defaults to "location".
            new_rate (float | None): Optional new rate for a detectable
            (if it needs faster, most likely)
        """
        if not hasattr(detectable, location_attr_name):
            raise SimulationError(
                f"Detectable {detectable} doesn't have attribute {location_attr_name}"
            )
        try:
            self._test_detect(detectable)
        except Exception:
            raise SimulationError(f"Detectable {detectable} needs a detectable state.")

        def get_location() -> LOC_TYPES:
            return cast(LOC_TYPES, getattr(detectable, location_attr_name))

        self._detectables[detectable] = get_location

    def _mover_not_detectable(self, detectable: Actor) -> None:
        """Called via DetectabilityState state when an object becomes undetectable.

        Could be called for any reason; use this feature to alert sensors that
        an object should no longer be considered by that sensor.
        """
        # TODO: key on detectable may make it faster
        to_rem = set()
        for sensor, detect in self._in_view:
            if detect is detectable:
                sensor.entity_exited_range(detectable)
                to_rem.add((sensor, detect))
        self._in_view -= to_rem

    def _mover_became_detectable(self, detectable: Actor) -> None:
        """Called via DetectabilityState state when an object becomes detectable.

        Could be called for any reason; use this feature to alert sensors that
        an object should be considered by that sensor.
        """
        self._run_detectable(detectable_req=[detectable])

    def _start_mover(self, mover: Actor, speed: float, waypoints: list[LOC_TYPES]) -> None:
        # we don't need this method, except to hook into motion states
        if not self._is_running:
            self.run()
        if mover in self._detectables:
            return
        state_name_1 = mover._get_matching_state(GeodeticLocationChangingState)
        state_name_2 = mover._get_matching_state(CartesianLocationChangingState)

        use_state = state_name_1 or state_name_2
        if use_state is None:
            raise SimulationError(f"Mover {mover} doesn't have a Location state")

        self.add_detectable(mover, use_state)

    def _stop_mover(self, mover: Actor) -> None:
        # we don't need this method, except to hook into motion states
        # It may be useful for ending detections, but the user should
        # handle that themselves
        if mover in self._detectables:
            del self._detectables[mover]
