# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""State descriptor for actor attributes with interception hooks."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypeVar, Union, cast, get_args, get_origin

import simpy as SIM

from upstage_des.base import SimulationError, UpstageError

if TYPE_CHECKING:
    from upstage_des.actor import _BaseActor as Actor

T = TypeVar("T")


def check_type(value: Any, annotation: Any) -> bool:
    """Check if a value matches the given type annotation.

    Args:
        value: The value to check
        annotation: The type annotation to check against

    Returns:
        True if the value matches the annotation, False otherwise
    """
    origin = get_origin(annotation)

    if origin is None:
        try:
            return isinstance(value, annotation)
        except TypeError:
            # Some things, like TypedDict, would fail here.
            return True

    if origin is Union:
        return any(check_type(value, arg) for arg in get_args(annotation))

    if origin in (list, dict, set, tuple):
        return isinstance(value, origin)
    if origin is Literal:
        return value in get_args(annotation)

    return True


class State[T]:
    """A descriptor for actor state with interception hooks for get/set operations.

    States are class-level descriptors that manage per-instance values on Actors.
    They provide hooks for recording, validation, and side effects during state changes.

    Usage:
        >>> class MyActor(Actor):
        ...     fuel: float
        ...     position: tuple[float, float] = State(default_factor=lambda: (0.0, 0.0))

        >>> actor = MyActor(position=(0.0, 0.0), fuel=100.0)
        >>> actor.fuel = 200.0

    The State descriptor is automatically created by the Actor class for all annotations.
    You can call it explicitly to set its properties and behaviors
    """

    def __init__(
        self,
        *,
        default: Any = None,
        default_factory: Callable[[], Any] | None = None,
        recording: bool = True,
        validator: Callable[[Any, Any], None] | None = None,
        type_check_first: bool = False,
        type_check_each: bool = False,
        validate_each: bool = True,
    ) -> None:
        """Create a State descriptor.

        Args:
            default: Default value for the state.
            default_factory: Factory function for default values (for mutable defaults).
            recording: Whether to record state changes.
            validator: Optional validator function that raises on invalid values.
            type_check_first: Optional control for type checking on init only.
            type_check_each: Optional control for when to type check on a set.
            validate_each: Optional control for when to validate on a set.

        Raises:
            ValueError: If both default and default_factory are provided.
        """
        if default is not None and default_factory is not None:
            raise ValueError("Cannot specify both default and default_factory")

        self.name: str = ""
        self._default = default
        self._default_factory = default_factory
        self._recording = recording
        self._validator = validator
        self._unchecked = True
        self._given_type = ...
        self._type_check_first = type_check_first
        self._type_check_each = type_check_each
        self._validate_each = validate_each

    def __get__(self, obj: Union["Actor", None], objtype: type) -> T:
        """Get the state value from an actor instance.

        Args:
            obj: The actor instance (None if accessed from class).
            objtype: The actor class.

        Returns:
            The State descriptor if accessed from class, otherwise the state value.

        Raises:
            AttributeError: If the state has not been set and has no default.
        """
        if obj is None:
            raise SimulationError("State value access didn't have an actor.")

        value = obj._state_data[self.name]["value"]

        return value  # type: ignore[no-any-return]

    def _record_change(self, obj: "Actor", new_value: Any) -> None:
        """Record a state change.

        Args:
            obj: The actor instance.
            old_value: The previous value.
            new_value: The new value.
        """
        if hasattr(obj, "_record_state_change"):
            obj._record_state_change(self.name, new_value)

    def __set__(self, obj: "Actor", value: T, no_record: bool = False) -> None:
        """Set the state value on an actor instance.

        Args:
            obj: The actor instance.
            value: The new value to set.
            no_record: If the state should record.

        Raises:
            ValueError: If the validator rejects the value.
        """
        do_validate = self._unchecked or self._validate_each
        do_type = self._unchecked and self._type_check_first
        do_type |= self._type_check_each
        self._unchecked = False
        if do_validate and self._validator is not None:
            self._validator(obj, value)
        if do_type and not check_type(value, self._given_type):
            raise TypeError(f"Input {value} for {self.name} doesn't match type {self._given_type}")

        obj._state_data[self.name]["value"] = value

        if self._recording and not no_record:
            self._record_change(obj, value)

    def __set_name__(self, owner: type, name: str) -> None:
        """Set the name of the state attribute.

        Called by Python when the descriptor is assigned to a class attribute.

        Args:
            owner: The class that owns this descriptor.
            name: The attribute name.
        """
        self.name = name

    def create(self) -> T:
        """Create the state in a way that mypy likes.

        This is optional, but if you are using `mypy` to check your simulation
        build, then:

        class Mover(Actor):
            distance_traveled: float = State(default=0.0)

        will fail. Using

        class Mover(Actor):
            distance_traveled: float = State(default=0.0).create()

        will make mypy happy.
        """
        return self  # type: ignore[return-value]

    def _add_type(self, typing: Any) -> None:
        self._given_type = typing

    def _set_default(self, obj: Any) -> None:
        if self.has_default:
            if self._default_factory is not None:
                value = self._default_factory()
            else:
                value = self._default
            self.__set__(obj, value)
        else:
            raise ValueError("No default given")

    @property
    def has_default(self) -> bool:
        """Whether this state has a default value.

        Returns:
            True if default or default_factory is provided.
        """
        return self._default is not None or self._default_factory is not None


TR = SIM.Store | SIM.Container


class ResourceState[TR](State):
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
        >>>     shelf: Store = ResourceState(default=Store).create()
        >>>     bucket: Container = ResourceState(
        >>>         default=Container,
        >>>         valid_types=(Container, SelfMonitoringContainer),
        >>>     )
        >>>     charger: Store = ResourceState(
        >>>         default=Store,
        >>>         default_kwargs={"capacity": 5},
        >>>     )
        >>>
        >>> wh = Warehouse(
        >>>     name='Depot',
        >>> )
        >>> wh.update_resource("shelf", capacity=10)
        >>> wh.update_resource("bucket", kind=SelfMonitoringContainer, initial=30)
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
                if not isinstance(v, type) or not issubclass(v, SIM.Store | SIM.Container):
                    raise UpstageError(f"Bad valid type for {self}: {v}")
        else:
            valid_types = (SIM.Store, SIM.Container)

        if default is not None and (
            not isinstance(default, type) or not issubclass(default, SIM.Store | SIM.Container)
        ):
            raise UpstageError(f"Bad default type for {self}: {default}")

        super().__init__(
            default=default,
            recording=False,
        )
        self._default_kwargs = default_kwargs.copy() if default_kwargs is not None else {}
        self._been_set: set[Actor] = set()
        self._types = valid_types

    def __set__(self, obj: "Actor", value: dict, no_record: bool = True) -> None:
        """Set the state value.

        Args:
            obj (Actor): The actor instance
            value (dict | Any): Either a dictionary of resource data OR an actual resource
            no_record (bool): Ignored input for type consistency.
        """
        if obj in self._been_set:
            raise UpstageError(
                f"State '{self}' on '{obj}' has already been created It cannot be changed once set!"
            )

        env = getattr(obj, "env", None)
        if env is None:
            raise UpstageError(
                f"Actor {obj} does not have an `env` attribute for state {self.name}"
            )
        kwargs = self._default_kwargs.copy()

        if not isinstance(value, dict):
            # we've been passed an actual resource, so save it and leave
            if isinstance(value, type):
                new = value(env, **kwargs)
                if not isinstance(new, self._types):
                    raise UpstageError(f"Resource object: '{value}' is not an expected type.")
                obj._state_data[self.name]["value"] = new
            elif not isinstance(value, self._types):
                raise UpstageError(f"Resource object: '{value}' is not an expected type.")
            else:
                obj._state_data[self.name]["value"] = value
            self._been_set.add(obj)
            return

        resource_type = value.get("kind", self._default)
        if resource_type is None:
            raise UpstageError(f"No resource type (Store, e.g.) specified for {obj}")

        if self._types and not issubclass(resource_type, self._types):
            raise UpstageError(
                f"{resource_type} is of type {type(resource_type)} not of type {self._types}"
            )

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

        obj._state_data[self.name]["value"] = resource_obj
        self._been_set.add(obj)

    def _set_default(self, instance: "Actor") -> None:
        """Set the default conditions.

        The empty dictionary input forces default to happen the right way.

        Args:
            instance (Actor): The actor holding this state.
        """
        self.__set__(instance, {})

    def __get__(self, obj: Union["Actor", None], objtype: type) -> TR:
        if obj is None:
            raise SimulationError(f"Unexpected get in state {self.name}")
        if self.name not in obj._state_data:
            self._set_default(obj)
        obj = obj._state_data[self.name]["value"]
        if not issubclass(type(obj), SIM.Store | SIM.Container):
            raise UpstageError("Bad type of ResourceStatee")
        return cast(TR, obj)

    def _modify_init(
        self,
        obj: "Actor",
        *,
        kind: type[SIM.Store] | type[SIM.Container] | None = None,
        capacity: int | float | None = None,
        init: int | float | None = None,
    ) -> None:
        """Modify capacity and initial amounts for stores/containers.

        Args:
            obj: The actor
            kind: The kind of store, optional.
            capacity (int | float | None, optional): _description_. Defaults to None.
            init (int | float | None, optional): _description_. Defaults to None.
        """
        # Remove the _been_set for manual override
        value: dict[str, Any] = {}
        if kind is not None:
            value["kind"] = kind
        if capacity is not None:
            value["capacity"] = capacity
        if init is not None:
            value["init"] = init

        if obj in self._been_set:
            self._been_set.remove(obj)
        self.__set__(obj, value)


class _ActiveState[T](State):
    """A state meant to change over time."""

    def __init__(
        self,
        *,
        default: Any = None,
        default_factory: Callable[[], Any] | None = None,
        recording: bool = True,
        validator: Callable[[Any, Any], None] | None = None,
        type_check_each: bool = False,
        validate_each: bool = True,
    ) -> None:
        """Create the state.

        Args:
            default (Any, optional): _description_. Defaults to None.
            default_factory (Callable[[], Any] | None, optional): _description_.
                Defaults to None.
            recording (bool, optional): _description_. Defaults to True.
            validator (Callable[[Any, Any], None] | None, optional): _description_.
                Defaults to None.
            type_check_each (bool, optional): _description_. Defaults to False.
            validate_each (bool, optional): _description_. Defaults to True.
        """
        super().__init__(
            default=default,
            default_factory=default_factory,
            recording=recording,
            validator=validator,
            type_check_each=type_check_each,
            validate_each=validate_each,
        )

    def __get__(self, obj: Union["Actor", None], objtype: type) -> T:
        if obj is None:
            raise SimulationError("Unexpected behavior in state value access")
        # Activate states calculate on a get
        update = obj._state_data[self.name].get("last_update")
        is_active = obj._state_data[self.name].get("is_active")
        if is_active and (update is None or update != obj.env.now):
            obj._state_data[self.name]["last_update"] = obj.env.now
            value = self.calculate_value(obj)
            self.__set__(obj, value)
            return value
        else:
            return cast(T, super().__get__(obj, objtype))

    def calculate_value(self, obj: "Actor") -> T:
        """Calculate the current value of the state.

        Args:
            time (float): The time this is called.
            obj (Any): Typically the actor.

        Returns:
            T: The value
        """
        raise NotImplementedError("Calling on a blank active state.")

    def predict_value_time(self, obj: "Actor", value: T) -> float | None:
        """Get the time when the state will equal a value.

        This is an optional implementation to support making events for when
        a state reaches a given value.

        Args:
            obj (ActorLike): The actor
            value (T): The goal value

        Returns:
            float | None: The time from now when the state will be that value.
        """
        return None

    def base_activate(self, obj: "Actor", curr_value: T, allow_active: bool = False) -> None:
        """Activate the state.

        This should store data about the activation to be used on a __get__ to
        update the value.

        When subclassing, this gets called after the data setup that goes in the
        new `activate`.

        Args:
            obj (Actor): The actor
            curr_value (T): The current value of the state.
            allow_active (bool, optional): Future proof to allow active states to
                mutally activate. Defaults to False.
        """
        # We can't be active already
        is_active = obj._state_data[self.name].get("is_active", False)
        if is_active and not allow_active:
            raise SimulationError(f"{self.name} state is already active.")
        # Get the value
        obj._record_state_change(self.name, curr_value, "ACTIVATING")
        obj._state_data[self.name]["is_active"] = True
        obj._state_data[self.name]["last_update"] = obj.env.now

    def activate(self, obj: "Actor", **kwargs: Any) -> None:
        """Activation function.

        Sets up the data and calls base_activate.

        Args:
            obj (Actor): The actor
            kwargs (Any): Arguments to activate.
        """
        raise NotImplementedError("You must create an activation method.")

    def base_deactivate(self, obj: "Actor", last_value: T) -> None:
        """Deactivate the state.

        A subclass should clean all the data out and supply this method with
        the last value.

        Args:
            obj (Actor): _description_
            last_value (T): _description_

        Raises:
            SimulationError: _description_
        """
        if not obj._state_data[self.name]["is_active"]:
            raise SimulationError(f"{self.name} state is already deactivated.")
        # do a final get
        self.__set__(obj, last_value, no_record=True)
        obj._record_state_change(self.name, last_value, "DEACTIVATING")
        obj._state_data[self.name]["is_active"] = False
        obj._state_data[self.name]["last_update"] = None

    def deactivate(self, obj: "Actor", **kwargs: Any) -> None:
        """Dectivation function.

        Sets up the data and calls base_activate.

        Args:
            obj (Actor): The actor
            kwargs (Any): Arguments to deactivate.
        """
        raise NotImplementedError("You must create a deactivation method.")


@dataclass
class _LinearData:
    start: float
    rate: float
    value: float


class LinearChangingState(_ActiveState[float]):
    """A state that changes linearly over time."""

    def predict_value_time(self, obj: "Actor", value: float) -> float | None:
        """Get the time when the state will equal a value.

        Args:
            obj (ActorLike): The actor
            value (T): The goal value

        Returns:
            float | None: The time from now when the state will be that value.
        """
        data: _LinearData | None = obj._state_data[self.name].get("active_data", None)
        if data is None:
            return None
        # curr + rate * time = value
        # rate * time = (value - curr)
        # time = (value - curr) / rate
        time = (value - data.value) / data.rate
        reach_time = time + data.start
        if reach_time > obj.env.now:
            return reach_time
        return None

    def calculate_value(self, obj: "Actor") -> float:
        """Linear change calculation.

        Args:
            obj (Actor): The actor.

        Returns:
            float: The new value.
        """
        time = obj.env.now
        data: _LinearData | None = obj._state_data[self.name].get("active_data", None)
        if data is None:
            raise SimulationError(f"Data for state {self.name} not found.")
        delta = time - data.start
        move = delta * data.rate
        return data.value + move

    def activate(self, obj: "Actor", rate: float = 0.0, **kwargs: Any) -> None:
        """Activate the linear state, supplying a rate.

        Args:
            obj (Actor): The actor
            rate (float): The rate of change
            kwargs (Any): Not used, just for typing.
        """
        value = self.__get__(obj, obj.__class__)
        data = _LinearData(start=obj.env.now, rate=rate, value=value)
        obj._state_data[self.name]["active_data"] = data
        self.base_activate(obj, value, allow_active=False)

    def deactivate(self, obj: "Actor", **kwargs: Any) -> None:
        """Deactivate the state.

        Args:
            obj (Actor): The actor.
            kwargs (Any): Unused kwargs, just for typing.
        """
        v = self.calculate_value(obj)
        obj._state_data[self.name]["active_data"] = None
        self.base_deactivate(obj, v)
