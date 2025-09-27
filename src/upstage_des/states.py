# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""A state defines the conditions of an actor over time."""

from abc import abstractmethod
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import fields, replace
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, cast, runtime_checkable

from simpy import Container, Environment, Store

from upstage_des.base import SimulationError, UpstageError
from upstage_des.data_types import CartesianLocation, GeodeticLocation
from upstage_des.math_utils import _vector_add, _vector_subtract
from upstage_des.resources.monitoring import SelfMonitoringStore
from upstage_des.state_proxies import _DataclassProxy, _DictionaryProxy
from upstage_des.task import Task

if TYPE_CHECKING:
    from upstage_des.actor import Actor


__all__ = (
    "ActiveState",
    "State",
    "LinearChangingState",
    "CartesianLocationChangingState",
    "GeodeticLocationChangingState",
    "ResourceState",
    "DetectabilityState",
    "CommunicationStore",
)

CALLBACK_FUNC = Callable[["Actor", Any], None]

ST = TypeVar("ST")

RECORD_FUNC = Callable[[float, ST], Any]


@runtime_checkable
class RecordClass(Protocol):
    @abstractmethod
    def __call__(self, time: float, value: ST) -> Any: ...


RECORD_TUPLES = tuple[RECORD_FUNC, str] | tuple[type, str]


class ActiveStatus(Enum):
    activating = "ACTIVATING"
    deactivating = "DEACTIVATING"


def _compare(a: Any, b: Any) -> bool:
    """Function for comparing any two objects.

    If an equality test fails, assume not equal.

    Args:
        a (Any): Anything
        b (Any): Also anything

    Returns:
        bool: Are they the same
    """
    try:
        return cast(bool, a == b)
    except Exception:
        return False


class State(Generic[ST]):
    """The particular condition that something is in at a specific time.

    The states are implemented as
    `Descriptors <https://docs.python.org/3/howto/descriptor.html>`_
    which are associated to :class:`upstage.actor.Actor`.

    Note:
        The classes that use this descriptor must contain an ``env`` attribute.

    States are aware

    """

    def __init__(
        self,
        *,
        default: ST | None = None,
        frozen: bool = False,
        valid_types: type | tuple[type, ...] | None = None,
        recording: bool = False,
        record_duplicates: bool = False,
        default_factory: Callable[[], ST] | None = None,
        allow_none_default: bool = False,
        recording_functions: list[RECORD_TUPLES] | None = None,
    ) -> None:
        """Create a state descriptor for an Actor.

        The default can be set either with the value or the factory. Use the factory if
        the default needs to be a list, dict, or similar type of object. The default
        is used if both are present (not the factory).

        Setting frozen to True will throw an error if the value of the state is changed.

        The valid_types input will type-check when you initialize an actor.

        Recording enables logging the values of the state whenever they change, along
        with the simulation time. This attempts to deepcopy the value.

        When a state is a mutable type, such as a dictionary or Counter, state
        changes won't be recorded because the descriptor itself won't be modified
        through the __set__ call.

        Args:
            default (Any | None, optional): Default value of the state. Defaults to None.
            frozen (bool, optional): If the state is allowed to change. Defaults to False.
            valid_types (type | tuple[type, ...] | None, optional): Types allowed. Defaults to None.
            recording (bool, optional): If the state records itself. Defaults to False.
            record_duplicates (bool, optional): If the state records duplicate values.
                Defaults to False.
            default_factory (Callable[[], type] | None, optional): Default from function.
                Defaults to None.
            allow_none_default (bool, optional): Consider a `None` default to be
                valid
            recording_functions (list[RECORD_TUPLES], optional):
                A list of functions or callable classes to use when the state records.
                The second entry in the tuple is a string of the name to use in
                `_state_histories`.
        """
        self._default = default
        self._default_factory = default_factory

        if self._default is not None and self._default_factory is not None:
            raise UpstageError("State needs to only use default or default factory.")

        self._frozen = frozen
        self._recording = recording
        self._record_duplicates = record_duplicates
        self._change_callbacks: dict[Any, CALLBACK_FUNC] = {}
        self._allow_none_default = allow_none_default
        self._recording_functions: list[tuple[RECORD_FUNC, str]] = []
        if recording_functions is not None:
            for thing, name in recording_functions:
                if isinstance(thing, type):
                    use = thing()
                    assert isinstance(use, RecordClass)
                    self._recording_functions.append((use, name))
                else:
                    self._recording_functions.append((thing, name))

        self._types: tuple[type, ...]

        if isinstance(valid_types, type):
            self._types = (valid_types,)
        elif valid_types is None:
            self._types = tuple()
        else:
            self._types = valid_types
        self.IGNORE_LOCK: bool = False

    def _do_record_funcs(self, instance: "Actor", now: float, value: ST) -> None:
        for func, name in self._recording_functions:
            result = func(now, value)
            new_append = (now, result)
            if name not in instance._state_histories:
                instance._state_histories[name] = [new_append]
            elif self._record_duplicates or not _compare(
                new_append, instance._state_histories[name][-1]
            ):
                instance._state_histories[name].append(new_append)

    def _do_record(self, instance: "Actor", value: ST, override: Any = None) -> None:
        """Record the value of the state.

        Args:
            instance (Actor): The actor holding the state
            value (ST): State value
            override (Any, optional): If given, record the override value
        """
        if not self._recording:
            return
        if getattr(instance, "env", None) is None:
            raise SimulationError(
                f"Actor {instance} does not have an `env` attribute for state {self.name}"
            )
        now = float(instance.env.now)
        use = value if override is None else override
        to_append = (now, deepcopy(use))
        if self.name not in instance._state_histories:
            instance._state_histories[self.name] = [to_append]
        elif self._record_duplicates or not _compare(
            to_append, instance._state_histories[self.name][-1]
        ):
            instance._state_histories[self.name].append(to_append)

        self._do_record_funcs(instance, *to_append)

    def _do_callback(self, instance: "Actor", value: ST) -> None:
        """Run callbacks for the state change.

        Args:
            instance (Actor): The actor holding the state
            value (Any): The value of the state
        """
        for _, callback in self._change_callbacks.items():
            callback(instance, value)

    def _broadcast_change(self, instance: "Actor", name: str, value: ST) -> None:
        """Send state change values to nucleus.

        Args:
            instance (Actor): The actor holding the state
            name (str): The state's name
            value (Any): The state's value
        """
        # broadcast changes to the instance
        if instance._state_listener is not None:
            instance._state_listener.send_change(name, value)

    # NOTE: A dictionary as a descriptor doesn't work well,
    # because all the operations seem to happen *after* the get
    # NOTE: Lists also have the same issue that
    def _type_check(self, value: Any, throw: bool = True) -> bool:
        """Check if a type matches this state."""
        if not self._types:
            return True
        ans = isinstance(value, self._types)
        if throw and not ans:
            raise TypeError(f"{value} is of type {type(value)} not of type {self._types}")
        return ans

    def __set__(self, instance: "Actor", value: Any) -> None:
        """Set the state's value.

        Args:
            instance (Actor): The actor holding the state
            value (Any): The state's value
        """
        if self._frozen:
            old_value = instance.__dict__.get(self.name, None)
            if old_value is not None:
                raise SimulationError(
                    f"State '{self}' on '{instance}' has already been frozen "
                    f"to value of {old_value}. It cannot be changed once set!"
                )

        self._type_check(value, throw=True)

        instance.__dict__[self.name] = value

        self._do_record(instance, value)
        self._do_callback(instance, value)

        self._broadcast_change(instance, self.name, value)

    def __get__(self, instance: "Actor", objtype: type | None = None) -> ST:
        if instance is None:
            # instance attribute accessed on class, return self
            return self  # pragma: no cover
        if self.name in instance._mimic_states:
            actor, name = instance._mimic_states[self.name]
            value = getattr(actor, name)
            self.__set__(instance, value)
        if self.name not in instance.__dict__:
            raise SimulationError(f"State {self.name} should have been set.")
        v = instance.__dict__[self.name]
        return cast(ST, v)

    def __set_name__(self, owner: "Actor", name: str) -> None:
        self.name = name

    def _set_default(self, instance: "Actor") -> None:
        """Set the state's value on the actor the default.

        For allowed None default, skip setting it. This will
        error on the get, which is expected.

        Args:
            instance (Actor): Actor holding the state.
        """
        # The default sits on the descriptor class, not on the instance.
        # If there's a factory we need to remake the default
        if self._default_factory is not None:
            value = self._default_factory()
            self.__set__(instance, value)
            return
        if self._default is None:
            if self._allow_none_default:
                return
            raise SimulationError(f"State {self.name} not allowed `None` default.")
        self.__set__(instance, self._default)

    def has_default(self) -> bool:
        """Check if a default exists.

        Returns:
            bool
        """
        if self._allow_none_default:
            return True
        return self._default is not None or self._default_factory is not None

    def _add_callback(self, source: Any, callback: CALLBACK_FUNC) -> None:
        """Add a recording callback.

        Args:
            source (Any): A key for the callback
            callback (Callable[[Actor, Any], None]): A function to call
        """
        self._change_callbacks[source] = callback

    def _remove_callback(self, source: Any) -> None:
        """Remove a callback.

        Args:
            source (Any): The callback's key
        """
        del self._change_callbacks[source]

    @property
    def is_recording(self) -> bool:
        """Check if the state is recording.

        Returns:
            bool
        """
        return self._recording


class DetectabilityState(State[bool]):
    """A state whose purpose is to indicate True or False.

    For consideration in the motion manager's <>LocationChangingState checks.
    """

    def __init__(self, *, default: bool = False, recording: bool = False) -> None:
        """Create the detectability state.

        Args:
            default (bool, optional): If the state starts on/off. Defaults to False.
            recording (bool, optional): If the state records. Defaults to False.
        """
        super().__init__(
            default=default,
            frozen=False,
            valid_types=(bool,),
            recording=recording,
        )

    def __set__(self, instance: "Actor", value: bool) -> None:
        """Set the detectability.

        Args:
            instance (Actor): The actor
            value (bool): The value to set
        """
        # Setting the default value shouldn't trigger the callback
        # to the motion manager.
        was_set = True
        if self.name not in instance.__dict__:
            was_set = False
        super().__set__(instance, value)
        if hasattr(instance.stage, "motion_manager") and was_set:
            mgr = instance.stage.motion_manager
            if not value:
                mgr._mover_not_detectable(instance)
            else:
                mgr._mover_became_detectable(instance)


class ActiveState(State, Generic[ST]):
    """Base class for states that change over time according to some rules.

    This class must be subclasses with an implemented `active` method.

    """

    def _active(self, instance: "Actor") -> Any:
        """Determine if the instance has an active state.

        Note:
            The instance must have two methods: ``get_active_state_data`` and
            ``_set_active_state_data``.

        Note:
            When you call ``activate_state`` from an actor, that is where
            you define the activity data. It is up to the Actor's subclass to
            make sure the activity data meet its needs.

            The first entry in the active data is always the time.
            Alternatively, you can call ``self.get_activity_data`` for some
            more data.

        """
        raise NotImplementedError("Method active not implemented.")

    def __get__(self, instance: "Actor", owner: type | None = None) -> ST:
        if instance is None:
            # instance attribute accessed on class, return self
            return self  # pragma: no cover
        if self.name in instance._mimic_states:
            actor, name = instance._mimic_states[self.name]
            value = getattr(actor, name)
            self.__set__(instance, value)
            return cast(ST, value)
        # test if this instance is active or not
        res = self._active(instance)
        # comes back as None (not active), or if it can be obtained from dict
        if res is None:
            res = instance.__dict__[self.name]
        return cast(ST, res)

    def get_activity_data(self, instance: "Actor") -> dict[str, Any]:
        """Get the data useful for updating active states.

        Returns:
            dict[str, Any]: A dictionary with the state's pertinent data. Includes the actor's
                environment current time (``'now'``) and the value of the actor's
                state (``'state'``).

        """
        res = instance.get_active_state_data(self.name, without_update=True)
        res["now"] = instance.env.now
        res["value"] = instance.__dict__[self.name]
        return res

    def activate(self, instance: "Actor", task: Task | None = None) -> None:
        """Method to run when a state is activated.

        Used to help record the right data about the active state.

        Use this with __super__ for motion states to deactivate their motion from
        the motion manager.
        """
        self._do_record(instance, None, override=ActiveStatus.activating)

    def deactivate(self, instance: "Actor", task: Task | None = None) -> bool:
        """Optional method to override that is called when a state is deactivated.

        Useful for motion states to deactivate their motion from
        the motion manager.

        Defaults to any deactivation removing active state data.
        """
        # Returns if the state should be ignored
        # A False means the state is completely deactivated
        self._do_record(instance, None, override=ActiveStatus.deactivating)
        return False


class LinearChangingState(ActiveState[float]):
    """A state whose value changes linearly over time.

    When activating:

    >>> class Lin(Actor):
    >>>     x = LinearChangingState()
    >>>
    >>> def task(self, actor: Lin):
    >>>     actor.activate_state(
    >>>         name="x",
    >>>         task=self,
    >>>         rate=3.2,
    >>>     )
    """

    def _active(self, instance: "Actor") -> float | None:
        """Return a value to set based on time or some other criteria."""
        data = self.get_activity_data(instance)
        now: float = data["now"]
        current: float = data["value"]
        started: float | None = data.get("started_at", None)
        if started is None:
            # it's not currently active
            return None
        # The user needs to know what their active data looks like.
        # Alternatively, it could be defined in the state or the actor.
        rate: float = data["rate"]
        if now < started:
            raise SimulationError(
                f"Cannot set state '{self.name}' start time after now. "
                f"This probably happened because the active state was "
                f"set incorrectly."
            )
        value = (now - started) * rate
        return_value = current + value
        self.__set__(instance, return_value)
        instance._set_active_state_data(
            state_name=self.name,
            started_at=now,
            rate=rate,
        )
        return return_value


class CartesianLocationChangingState(ActiveState[CartesianLocation]):
    """A state that contains the location in 3-dimensional Cartesian space.

    Movement is along straight lines in that space.

    For activating:
        >>> actor.activate_state(
        >>>     state=<state name>,
        >>>     task=self, # usually
        >>>     speed=<speed>,
        >>>     waypoints=[
        >>>         List of CartesianLocation
        >>>     ]
        >>> )
    """

    def __init__(self, *, recording: bool = False):
        """Set a Location changing state.

        Defaults are disabled due to immutability of location objects.
        (We could copy it, but it seems like better practice to force inputting it at runtime.)

        Args:
            recording (bool, optional): Whether to record. Defaults to False.
        """
        super().__init__(
            default=None,
            frozen=False,
            default_factory=None,
            valid_types=(CartesianLocation,),
            recording=recording,
        )

    def _setup(self, instance: "Actor") -> None:
        """Initialize data about a path.

        Args:
            instance (Actor): The actor
        """
        data = self.get_activity_data(instance)
        current: CartesianLocation = data["value"]
        speed: float = data["speed"]
        waypoints: list[CartesianLocation] = data["waypoints"]
        # get the times, distances, and bearings from the waypoints
        times: list[float] = []
        distances: list[float] = []
        starts: list[CartesianLocation] = []
        vectors: list[list[float]] = []
        for wypt in waypoints:
            dist = wypt - current
            time = dist / speed
            times.append(time)
            distances.append(dist)
            starts.append(current.copy())
            vectors.append(_vector_subtract(wypt._as_array(), current._as_array()))
            current = wypt

        path_data = {
            "times": times,
            "distances": distances,
            "starts": starts,
            "vectors": vectors,
        }
        instance._set_active_state_data(
            self.name,
            started_at=data["now"],
            origin=data["value"],
            speed=speed,
            waypoints=waypoints,
            path_data=path_data,
        )
        # if there is a motion manager, notify it
        if hasattr(instance.stage, "motion_manager"):
            if not getattr(instance, "_is_rehearsing", False):
                instance.stage.motion_manager._start_mover(
                    instance,
                    speed,
                    [data["value"]] + waypoints,
                )

    def _get_index(self, path_data: dict[str, Any], time_elapsed: float) -> tuple[int, float]:
        """Find out how far along waypoints the state is.

        Args:
            path_data (dict[str, Any]): Data about the movement path
            time_elapsed (float): Time spent moving

        Returns:
            int: index in waypoints
            float: time spent on path
        """
        sum_t = 0.0
        t: float
        for i, t in enumerate(path_data["times"]):
            sum_t += t
            if time_elapsed <= (sum_t + 1e-12):
                return i, sum_t - t
        raise SimulationError(
            "CartesianLocation active state exceeded travel time: "
            f"elapsed: {time_elapsed}, maximum: {sum_t}"
        )

    def _get_remaining_waypoints(self, instance: "Actor") -> list[CartesianLocation]:
        """Convenience for getting waypoints left.

        Args:
            instance (Actor): The owning actor.

        Returns:
            list[CartesianLocation]: The waypoints left
        """
        data = self.get_activity_data(instance)
        current_time: float = data["now"]
        path_start_time: float = data["started_at"]
        elapsed = current_time - path_start_time
        idx, _ = self._get_index(data["path_data"], elapsed)
        return list(data["waypoints"][idx:])

    def _active(self, instance: "Actor") -> CartesianLocation | None:
        """Get the current value while active.

        Args:
            instance (Actor): The owning actor

        Returns:
            CartesianLocation | None: The current value
        """
        data = self.get_activity_data(instance)
        path_start_time: float | None = data.get("started_at", None)
        if path_start_time is None:
            # it's not active
            return None

        path_data: dict[str, Any] | None = data.get("path_data", None)
        if path_data is None:
            self._setup(instance)
            data = self.get_activity_data(instance)

        path_data: dict[str, Any] = data["path_data"]
        current_time: float = data["now"]
        elapsed = current_time - path_start_time
        if elapsed < 0:
            # Can probably only happen if active state is set incorrectly
            raise SimulationError(f"Cannot set state '{self.name}' start time in the future!")
        elif elapsed == 0:
            return_value: CartesianLocation = data["value"]  # pragma: no cover
        else:
            # Get the location along the waypoint path
            wypt_index, wypt_start = self._get_index(path_data, elapsed)
            time_along = elapsed - wypt_start
            path_time: float = path_data["times"][wypt_index]
            path_start: CartesianLocation = path_data["starts"][wypt_index]
            path_vector: list[float] = path_data["vectors"][wypt_index]
            time_frac = time_along / path_time
            direction_amount = [time_frac * v for v in path_vector]
            new_point = _vector_add(path_start._as_array(), direction_amount)

            # make the right kind of location object
            new_location = CartesianLocation(
                x=new_point[0],
                y=new_point[1],
                z=new_point[2],
            )
            return_value = new_location

            self.__set__(instance, return_value)

            # No new data needs to be added
            # Only the current time is needed once we run _setup()
            data["value"] = return_value
            instance._set_active_state_data(
                state_name=self.name,
                **data,
            )

        return return_value

    def deactivate(self, instance: "Actor", task: Task | None = None) -> bool:
        """Deactivate the motion.

        Args:
            instance (Actor): The owning actor
            task (Task): The task calling the deactivation.

        Returns:
            bool: _description_
        """
        if hasattr(instance.stage, "motion_manager"):
            if not getattr(instance, "_is_rehearsing", False):
                instance.stage.motion_manager._stop_mover(instance)
        return super().deactivate(instance, task)


class GeodeticLocationChangingState(ActiveState[GeodeticLocation]):
    """A state that contains a location around an ellipsoid that follows great-circle paths.

    Requires a distance model class that implements:
    1. distance_and_bearing
    2. point_from_bearing_dist
    and outputs objects with .lat and .lon attributes


    For activating:

    >>> actor.activate_state(
    >>>     state=<state name>,
    >>>     task=self, # usually
    >>>     speed=<speed>,
    >>>     waypoints=[
    >>>         List of CartesianLocation
    >>>     ]
    >>> )
    """

    def __init__(self, *, recording: bool = False) -> None:
        """Create the location changing state.

        Defaults are disabled due to immutability of location objects.
        (We could copy it, but it seems like better practice to force inputting it at runtime.)

        Args:
            recording (bool, optional): If the location is recorded. Defaults to False.
        """
        super().__init__(
            default=None,
            frozen=False,
            valid_types=(GeodeticLocation,),
            recording=recording,
        )

    def _setup(self, instance: "Actor") -> None:
        """Initialize data about a path."""
        STAGE = instance.stage
        data = self.get_activity_data(instance)
        current: GeodeticLocation = data["value"]
        speed: float = data["speed"]
        waypoints: list[GeodeticLocation] = data["waypoints"]
        # get the times, distances, and bearings from the waypoints
        times: list[float] = []
        distances: list[float] = []
        bearings: list[float] = []
        starts: list[GeodeticLocation] = []
        for wypt in waypoints:
            dist, bear = STAGE.stage_model.distance_and_bearing(
                (current.lat, current.lon),
                (wypt.lat, wypt.lon),
                units=STAGE.distance_units,
            )
            time = dist / speed
            times.append(time)
            distances.append(dist)
            bearings.append(bear)
            starts.append(current.copy())
            current = wypt

        path_data = {
            "times": times,
            "distances": distances,
            "bearings": bearings,
            "starts": starts,
        }
        instance._set_active_state_data(
            self.name,
            started_at=data["now"],
            origin=data["value"],
            speed=speed,
            waypoints=waypoints,
            path_data=path_data,
        )

        # if there is a motion manager, notify it
        if hasattr(STAGE, "motion_manager"):
            if not getattr(instance, "_is_rehearsing", False):
                STAGE.motion_manager._start_mover(
                    instance,
                    speed,
                    [data["value"]] + waypoints,
                )

    def _get_index(self, path_data: dict[str, Any], time_elapsed: float) -> tuple[int, float]:
        """Get the index of the waypoint the path is on.

        Args:
            path_data (dict[str, Any]): Data about the motion
            time_elapsed (float): Time spent on motion

        Returns:
            int: Index of the waypoint
            float: time elapsed
        """
        sum_t = 0.0
        t: float
        for i, t in enumerate(path_data["times"]):
            sum_t += t
            if time_elapsed <= (sum_t + 1e-4):  # near one second allowed
                return i, sum_t - t
        raise SimulationError(
            f"GeodeticLocation active state exceeded travel time: Elapsed: {time_elapsed}, "
            "Actual: {sum_t}"
        )

    def _get_remaining_waypoints(self, instance: "Actor") -> list[GeodeticLocation]:
        """Get waypoints left in travel.

        Args:
            instance (Actor): The owning actor.

        Returns:
            list[GeodeticLocation]: Waypoint remaining
        """
        data = self.get_activity_data(instance)
        current_time: float = data["now"]
        path_start_time: float = data["started_at"]
        elapsed = current_time - path_start_time
        idx, _ = self._get_index(data["path_data"], elapsed)
        wypts: list[GeodeticLocation] = data["waypoints"]
        return wypts[idx:]

    def _active(self, instance: "Actor") -> GeodeticLocation | None:
        """Get the value of the location while in motion.

        Args:
            instance (Actor): The owning actor.

        Returns:
            GeodeticLocation | None: Location while in motion. None if still.
        """
        STAGE = instance.stage
        data = self.get_activity_data(instance)
        path_start_time: float | None = data.get("started_at", None)
        if path_start_time is None:
            # it's not active
            return None

        path_data: dict[str, Any] | None = data.get("path_data", None)
        if path_data is None:
            self._setup(instance)
            data = self.get_activity_data(instance)

        path_data: dict[str, Any] = data["path_data"]

        current_time: float = data["now"]
        path_start_time: float = data["started_at"]
        elapsed = current_time - path_start_time

        if elapsed < 0:
            # Can probably only happen if active state is set incorrectly
            raise SimulationError(f"Cannot set state '{self.name}' start time in the future!")
        elif elapsed == 0:
            return_value: GeodeticLocation = data["value"]  # pragma: no cover
        else:
            # Get the location along the waypoint path
            wypt_index, wypt_start = self._get_index(path_data, elapsed)
            time_along = elapsed - wypt_start
            path_time: float = path_data["times"][wypt_index]
            path_dist: float = path_data["distances"][wypt_index]
            path_bearing: float = path_data["bearings"][wypt_index]
            path_start: GeodeticLocation = path_data["starts"][wypt_index]
            moved_distance = (time_along / path_time) * path_dist
            new_point = STAGE.stage_model.point_from_bearing_dist(
                (path_start.lat, path_start.lon),
                path_bearing,
                moved_distance,
                STAGE.distance_units,
            )
            # update the altitude
            waypoint: GeodeticLocation = data["waypoints"][wypt_index]
            alt_shift = waypoint.alt - path_start.alt
            alt_shift *= time_along / path_time
            new_alt = path_start.alt + alt_shift
            # make the right kind of location object
            lat, lon = new_point[0], new_point[1]
            new_location = GeodeticLocation(
                lat,
                lon,
                new_alt,
            )
            return_value = new_location

            self.__set__(instance, return_value)

            # No new data needs to be added
            # Only the current time is needed once we run _setup()
            instance._set_active_state_data(
                state_name=self.name,
                **data,
            )

        return return_value

    def deactivate(self, instance: "Actor", task: Task | None = None) -> bool:
        """Deactivate the state.

        Args:
            instance (Actor): The owning actor
            task (Task): The task doing the deactivating

        Returns:
            bool: If the state is all done
        """
        STAGE = instance.stage
        if hasattr(STAGE, "motion_manager"):
            if not getattr(instance, "_is_rehearsing", False):
                STAGE.motion_manager._stop_mover(instance)
        return super().deactivate(instance, task)


T = TypeVar("T", bound=Store | Container)


class ResourceState(State, Generic[T]):
    """A State class for States that are meant to be Stores or Containers.

    This should enable easier initialization of Actors with stores/containers or
    similar objects as states.

    No input is needed for the state if you define a default resource class in
    the class definition and do not wish to modify the default inputs of that
    class. You can also define default inputs for the resource instantiation.

    The input an Actor needs to receive for a ResourceState is a dictionary of:
    * 'kind': <class> (optional if you provided a default)
    * 'capacity': <numeric> (optional, works on stores and containers)
    * 'init': <numeric> (optional, works on containers)
    * key:value for any other input expected as a keyword argument by the resource class

    Note that the resource class given must accept the environment as the first
    positional argument. This is to maintain compatibility with simpy.

    Example:
        >>> class Warehouse(Actor):
        >>>     shelf = ResourceState[Store](default=Store)
        >>>     bucket = ResourceState[Container](
        >>>         default=Container,
        >>>         valid_types=(Container, SelfMonitoringContainer),
        >>>     )
        >>>     charger = ResourceState[Store](
        >>>         default=Store,
        >>>         default_kwargs={"capacity": 5},
        >>>     )
        >>>
        >>> wh = Warehouse(
        >>>     name='Depot',
        >>>     shelf={'capacity': 10},
        >>>     bucket={'kind': SelfMonitoringContainer, 'init': 30},
        >>> )
    """

    def __init__(
        self,
        *,
        default: Any | None = None,
        valid_types: type | tuple[type, ...] | None = None,
        default_kwargs: dict[str, Any] | None = None,
    ) -> None:
        """Create a resource State decorator.

        Args:
            default (Any | None, optional): Default store/container class. Defaults to None.
            valid_types (type | tuple[type, ...] | None, optional): Valid store/container
                classes. Defaults to None.
            default_kwargs (dict[str, Any], optional): Kwargs to pass to the creation
                of the default store/container class.
        """
        if isinstance(valid_types, type):
            valid_types = (valid_types,)

        if valid_types:
            for v in valid_types:
                if not isinstance(v, type) or not issubclass(v, Store | Container):
                    raise UpstageError(f"Bad valid type for {self}: {v}")
        else:
            valid_types = (Store, Container)

        if default is not None and (
            not isinstance(default, type) or not issubclass(default, Store | Container)
        ):
            raise UpstageError(f"Bad default type for {self}: {default}")

        super().__init__(
            default=default,
            frozen=False,
            recording=False,
            valid_types=valid_types,
        )
        self._default_kwargs = default_kwargs.copy() if default_kwargs is not None else {}
        self._been_set: set[Actor] = set()

    def __set__(self, instance: "Actor", value: dict | Any) -> None:
        """Set the state value.

        Args:
            instance (Actor): The actor instance
            value (dict | Any): Either a dictionary of resource data OR an actual resource
        """
        if instance in self._been_set:
            raise UpstageError(
                f"State '{self}' on '{instance}' has already been created "
                "It cannot be changed once set!"
            )

        if not isinstance(value, dict):
            # we've been passed an actual resource, so save it and leave
            if not isinstance(value, self._types):
                raise UpstageError(f"Resource object: '{value}' is not an expected type.")
            instance.__dict__[self.name] = value
            self._been_set.add(instance)
            return

        resource_type = value.get("kind", self._default)
        if resource_type is None:
            raise UpstageError(f"No resource type (Store, e.g.) specified for {instance}")

        if self._types and not issubclass(resource_type, self._types):
            raise UpstageError(
                f"{resource_type} is of type {type(resource_type)} not of type {self._types}"
            )

        env = getattr(instance, "env", None)
        if env is None:
            raise UpstageError(
                f"Actor {instance} does not have an `env` attribute for state {self.name}"
            )
        kwargs = self._default_kwargs.copy()
        kwargs.update({k: v for k, v in value.items() if k != "kind"})
        try:
            resource_obj = resource_type(env, **kwargs)
        except TypeError as e:
            raise UpstageError(
                f"Bad argument input to resource state {self.name}"
                f" resource class {resource_type} :{e}"
            )
        except Exception as e:
            raise UpstageError(f"Exception in ResourceState init: {e}")

        instance.__dict__[self.name] = resource_obj
        self._been_set.add(instance)
        # remember what we did for cloning
        instance.__dict__["_memory_for_" + self.name] = kwargs.copy()

        self._broadcast_change(instance, self.name, value)

    def _set_default(self, instance: "Actor") -> None:
        """Set the default conditions.

        The empty dictionary input forces default to happen the right way.

        Args:
            instance (Actor): The actor holding this state.
        """
        self.__set__(instance, {})

    def __get__(self, instance: "Actor", owner: type | None = None) -> T:
        if instance is None:
            # instance attribute accessed on class, return self
            return self  # pragma: no cover
        if self.name not in instance.__dict__:
            self._set_default(instance)
        obj = instance.__dict__[self.name]
        if not issubclass(type(obj), Store | Container):
            raise UpstageError("Bad type of ResourceStatee")
        return cast(T, obj)

    def _make_clone(self, instance: "Actor", copy: T) -> T:
        """Method to support cloning a store or container.

        Args:
            instance (Actor): The owning actor
            copy (T): The store or container to copy

        Returns:
            T: The copied store or container
        """
        base_class = type(copy)
        memory: dict[str, Any] = instance.__dict__[f"_memory_for_{self.name}"]
        new = base_class(instance.env, **memory)  # type: ignore [arg-type]
        if isinstance(copy, Store) and isinstance(new, Store):
            new.items = list(copy.items)
        if isinstance(copy, Container) and isinstance(new, Container):
            # This is a particularity of simpy containers
            new._level = float(copy.level)
        return cast(T, new)


class CommunicationStore(ResourceState[Store]):
    """A State class for communications inputs.

    Used for automated finding of communication inputs on Actors by the CommsTransfer code.

    Follows the same rules for defaults as `ResourceState`, except this
    defaults to a SelfMonitoringStore without any user input.

    Only resources inheriting from simpy.Store will work for this state.
    Capacities are assumed infinite.

    The input an Actor needs to receive for a CommunicationStore is a dictionary of:
        >>> {
        >>>     'kind': <class> (optional)
        >>>     'modes': <string> (optional)
        >>> }

    Example:
        >>> class Worker(Actor):
        >>>     walkie = CommunicationStore(modes="UHF")
        >>>     intercom = CommunicationStore(modes=None)
        >>>
        >>> worker = Worker(
        >>>     name='Billy',
        >>>     walkie={'kind': SelfMonitoringStore},
        >>>     intercom={"modes": "loudspeaker"},
        >>> )

    """

    def __init__(
        self,
        *,
        modes: str | list[str] | None,
        default: type | None = None,
        valid_types: type | tuple[type, ...] | None = None,
    ):
        """Create a comms store.

        Args:
            modes (str, list[str], optional): Modes to describe the comms channel.
            default (type | None, optional): Store class by default.
                Defaults to None.
            valid_types (type | tuple[type, ...] | None, optional): Valid store classes.
                Defaults to None.
        """
        if default is None:
            default = SelfMonitoringStore
        if valid_types is None:
            valid_types = (Store, SelfMonitoringStore)
        elif isinstance(valid_types, type):
            valid_types = (valid_types,)
        for v in valid_types:
            if not issubclass(v, Store):
                raise SimulationError("CommunicationStore must use a Store subclass")
        super().__init__(default=default, valid_types=valid_types)
        self._modes = modes

    @property
    def _modename(self) -> str:
        return "_" + self.name + "__mode_names_"

    def __set__(self, instance: "Actor", value: dict | Any) -> None:
        # See if the instance has any specific mode data to find.
        modes: str | list[str] | None = self._modes
        if isinstance(value, dict) and "modes" in value:
            modes = value.pop("modes")
        super().__set__(instance, value)
        if modes is None:
            raise SimulationError(
                f"CommunicationsStore {self.name} needs a mode defined"
                " by default or through the initialization."
            )
        if isinstance(modes, str):
            modes = [modes]
        if not isinstance(modes, list) and not all(isinstance(x, str) for x in modes):
            raise SimulationError("CommunicationsStore modes should be a list of strings.")
        instance.__dict__[self._modename] = set(modes)


class _KeyValueBase(State):
    """A base state for holding key/value pairs.

    This is greatly simplified state meant for a runtime
    definition, rather than assuming defaults.

    Use either a dataclass or a dictionary for the value of
    the state when instantiating the Actor.
    """

    def __init__(
        self,
        *,
        valid_types: type | tuple[type, ...] | None = None,
        recording: bool = False,
        record_duplicates: bool = False,
        recording_functions: list[RECORD_TUPLES] | None = None,
    ) -> None:
        # Frozen, recording, and record duplicates are set so
        # that the overall state's value (a dictionary) is
        # never touched, and only its members are accessed.
        super().__init__(
            frozen=True,
            valid_types=valid_types,
            recording=False,
            record_duplicates=False,
            recording_functions=recording_functions,
        )
        self._record_indiv = recording
        self._record_indiv_dupe = record_duplicates

    def _record_single(self, instance: "Actor", time: float, key: str, value: Any) -> None:
        name = f"{self.name}.{key}"
        new = (time, value)
        if name not in instance._state_histories:
            instance._state_histories[name] = [new]
        elif self._record_duplicates or not _compare(new, instance._state_histories[name][-1]):
            instance._state_histories[name].append(new)

    def _get_keys_values(self, instance: "Actor") -> list[tuple[str, Any]]:
        raise NotImplementedError()

    def _get_value(self, instance: "Actor", key: str) -> Any:
        raise NotImplementedError

    def _record_state(self, instance: "Actor", key: str | None = None, all: bool = False) -> None:
        if not self._record_indiv:
            return

        if getattr(instance, "env", None) is None:
            raise SimulationError(
                f"Actor {instance} does not have an `env` attribute for state {self.name}"
            )
        now = float(instance.env.now)
        if all:
            for k, v in self._get_keys_values(instance):
                self._record_single(instance, now, k, v)
        elif key is not None:
            v = self._get_value(instance, key)
            self._record_single(instance, now, key, v)
        else:
            raise SimulationError(f"No key given for recording on {instance}")

        self._do_record_funcs(instance, now, instance.__dict__[self.name])

    def _make_clone(self, instance: "Actor") -> Any:
        raise NotImplementedError()


VT = TypeVar("VT")


class DictionaryState(_KeyValueBase, Generic[VT]):
    """A state that contains a {str: value} dictionary.

    This state provides features for holding a dictionary that is self-recording
    when attributes are set. Similar to States, recording functions can augment
    the recorded information on every key/value update. Recorded keys are
    given the variable name of <state name>.<key>

    For simplicity of data recording, this state expects all keys to be strings.
    If you supply a valid_type input, the state will type check your values
    against it.

    The dictionary state does not expect any default factories or settings, you
    must initialize it with at least a blank dictionary.

    The state is not actually a dictionary, but a proxy for the dictionary where
    get, set, contains, and iter operations are supported.

    Example:

    .. code-block:: python

        class VendingMachine(UP.Actor):
            inventory = UP.DictionaryState[int](valid_types=(int,), recording=True)
            requested = UP.DictionaryState[int](valid_types=(int,), recording=True)
            request = UP.ResourceState[Store](default=Store)

        class TrackRequests(UP.Task):
            def task(self, *, actor: VendingMachine) -> TASK_GEN:
                get = UP.Get(actor.request)
                yield get
                item_name = get.get_value()
                actor.requested.setdefault(item_name, 0)
                actor.requested[item_name] += 1
                if item_name in actor.inventory:
                    actor.inventory[item_name] -= 1
                else:
                    print(f"We have no items named {item_name}".)

        inventory = {"chips": 10, "cookies":10, "granola bars": 24}
        with UP.EnvironmentContext() as env:
            vend = VendingMachine(
                name="Machine",
                inventory=inventory,
                request={},
            )
            ...


    Args:
        Generic (_type_): The type information for the values
    """

    def __get__(self, instance: "Actor", objtype: type | None = None) -> dict[str, VT]:
        return cast(
            dict[str, VT], _DictionaryProxy[VT](self, instance, instance.__dict__[self.name])
        )

    def __set__(self, instance: "Actor", value: dict[str, VT]) -> None:
        if self.name in instance.__dict__:
            raise SimulationError(f"State {self.name} already set on {instance}.")

        instance.__dict__[self.name] = {}
        for k, v in value.items():
            self._type_check(v, throw=True)
            instance.__dict__[self.name][k] = v

        self._record_state(instance, all=True)

    def _get_keys_values(self, instance: "Actor") -> list[tuple[str, Any]]:
        return list(instance.__dict__[self.name].items())

    def _get_value(self, instance: "Actor", key: str) -> Any:
        return instance.__dict__[self.name][key]

    def _make_clone(self, instance: "Actor") -> dict[str, VT]:
        return cast(dict[str, VT], instance.__dict__[self.name].copy())


DCT = TypeVar("DCT")


class DataclassState(_KeyValueBase, Generic[DCT]):
    """A state that contains a dataclass.

    This state provides features for holding a dataclass that is self-recording
    when attributes are set. Similar to States, recording functions can augment
    the recorded information on every key/value update. Recorded keys are
    given the variable name of <state name>.<attribute name>

    If you supply a dataclass object to the valid_type input, the state will
    type check your values against it. These states are less flexible than
    dictionary states, but do provide more specific type information on a per-
    attribute basis. If you have common data structures that you might update
    frequently, a DataclassState can provide some structure that is more flexible
    than changing an actor's states. It also allows other models to be incorporated
    that are dependent on data only, and not the actors themselves.

    The dataclass state does not expect any default factories or settings, you
    must initialize it with a dataclass instance.

    The state is not actually a dataclass, but a proxy for the dataclass where
    get, set, contains, and iter operations are supported.

    Example:

    .. code-block:: python

        @dataclass
        class Properties:
            speed: float
            health: float
            damage: float
            armor: float = field(default=0.0)

        class Barbarian(UP.Actor):
            properties = UP.DataclassState[Properties](
                valid_types=(Properties,),
                recording=True,
            )

        def fight_model(fighter1: Properties, fighter2: Properties):
            ...

        class ArenaBattle(UP.Task):
            def task(self, *, actor: ArenaActor) -> TASK_GEN:
                get = UP.Get(actor.next_fight)
                yield get
                b1: Barbarian
                b2: Barbarian
                b1, b2 = get.get_value()
                winner = fight_model(b1.properties, b2.properties)

    Args:
        Generic (_type_): The type information for the values
    """

    def __get__(self, instance: "Actor", objtype: type | None = None) -> DCT:
        return cast(DCT, _DataclassProxy[DCT](self, instance, instance.__dict__[self.name]))

    def __set__(self, instance: "Actor", value: DCT) -> None:
        if self.name in instance.__dict__:
            raise SimulationError(f"State {self.name} already set on {instance}.")

        self._type_check(value, throw=True)
        instance.__dict__[self.name] = value

        self._record_state(instance, all=True)

    def _get_keys_values(self, instance: "Actor") -> list[tuple[str, Any]]:
        ans = []
        dc = instance.__dict__[self.name]
        for field in fields(dc):
            ans.append((field.name, getattr(dc, field.name)))
        return ans

    def _get_value(self, instance: "Actor", key: str) -> Any:
        return getattr(instance.__dict__[self.name], key)

    def _make_clone(self, instance: "Actor") -> DCT:
        return cast(DCT, replace(instance.__dict__[self.name]))


class MultiStoreState(DictionaryState[T]):
    """A state for holding stores or containers keyed by a string.

    Works best when all values are the same kind of container.

    This state follows rules similar to ResourceState, but for a dictionary
    of container/store objects.

    The input an Actor needs to receive for a MultiStoreState is a dictionary of:
    * 'kind': <class> (optional if you provided a default)
    * 'capacity': <numeric> (optional, works on stores and containers)
    * 'init': <numeric> (optional, works on containers)
    * key:value for any other input expected as a keyword argument by the resource class

    Types are enforced via `valid_types`, and if no `kind` is specified, the
    `default` input is used.

    The default kwargs will be applied to any input, so make sure they are
    compatible with different containers, or be more speficific with your typing.
    Arguments that don't apply will raise an error.

    Example:

    .. code-block:: python

        class Warehouse(Actor):
            storage = MultiStoreState[Store| Container](
                default=Store,
                valid_types=(Store, Container),
                default_kwargs={"capacity": 100},
            )

        wh = Warehouse(
            name='Depot',
            storage = {
                "shelf":{"capacity":10},
                "bucket":{"kind": SelfMonitoringContainer, "init": 30},
                "charger":{},
            }
        )
        wh.storage["shelf"].capacity == 10
        wh.storage["bucket"].level == 30
        wh.storage["charger"].capacity == 100
        wh.storage["charger"].items == []


    """

    def __init__(
        self,
        *,
        valid_types: type | tuple[type, ...] | None = None,
        default: type[Store] | type[Container] | None = None,
        default_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(valid_types=valid_types)
        self._default = default
        self._default_kwargs = {} if default_kwargs is None else default_kwargs.copy()

    def _type_checker(self, resource_type: Any) -> None:
        any_type = False
        for t in self._types:
            if not (issubclass(t, Store) or issubclass(t, Container)):
                raise UpstageError("Bad valid_type for MultiStoreState.")
            inst = isinstance(resource_type, t)
            typ = issubclass(resource_type, t) if type(resource_type) is type else True
            if inst or typ:
                any_type = True
        if self._types and not any_type:
            raise UpstageError(
                f"{resource_type} is of type {resource_type} not of type {self._types}"
            )

    def _make_resource(self, env: Environment, input: T | dict[str, Any]) -> T:
        if not isinstance(input, dict):
            # we've been passed an actual resource, so save it and leave
            self._type_checker(input)
            return input

        kwargs = self._default_kwargs.copy()
        kwargs.update({k: v for k, v in input.items() if k != "kind"})

        resource_type = input.get("kind", self._default)
        if resource_type is None:
            raise UpstageError("No default specified for MultiStoreState. Did you forget 'kind'?")
        self._type_checker(resource_type)
        try:
            resource_obj = resource_type(env, **kwargs)
        except TypeError as e:
            raise UpstageError(
                f"Bad argument input to resource state {self.name}"
                f" resource class {resource_type} :{e}"
            )
        except Exception as e:
            raise UpstageError(f"Exception in ResourceState init: {e}")
        return cast(T, resource_obj)

    def __set__(
        self, instance: "Actor", value: dict[str, T | dict[str, Any]] | Iterable[str]
    ) -> None:
        if self.name in instance.__dict__:
            raise SimulationError(f"State {self.name} already set on {instance}.")
        env = getattr(instance, "env", None)
        if env is None or not isinstance(env, Environment):
            raise UpstageError(
                f"Actor {instance} does not have the right `env` attribute for state {self.name}"
            )
        # process the values
        use: dict[str, T] = {}
        if not isinstance(value, dict):
            value = {name: {} for name in value}
        attrs: dict[str, Any] | T
        for name, attrs in value.items():
            use[name] = self._make_resource(env, attrs)

        super().__set__(instance, use)

    def has_default(self) -> bool:
        # Force the state to be defined.
        return False
