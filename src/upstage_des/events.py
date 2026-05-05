# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Classes for UPSTAGE events that feed to simpy."""

from collections.abc import Callable
from contextlib import suppress
from typing import Any as tyAny
from warnings import warn

import simpy as SIM
from simpy.resources.container import ContainerGet, ContainerPut
from simpy.resources.resource import Release, Request
from simpy.resources.store import StoreGet, StorePut

from upstage_des.base import SIMPY_GEN, SimulationError, UpstageBase, UpstageError
from upstage_des.units import unit_convert

__all__ = (
    "All",
    "Any",
    "Event",
    "MultiEvent",
    "Wait",
)

SIM_REQ_EVTS = ContainerGet | ContainerPut | StoreGet | StorePut | Request | Release


class BaseEvent(UpstageBase):
    """Base class for framework events."""

    def __init__(self, *, rehearsal_time_to_complete: float = 0.0):
        """Create a base event with a notion of rehearsal time.

        Args:
            rehearsal_time_to_complete (float, optional): Time to simulate passing
                on rehearsal. Defaults to 0.0.
        """
        super().__init__()
        self._simpy_event: SIM.Event | None = None

        self.created_at: float = self.env.now
        self.rehearsal_time_to_complete = rehearsal_time_to_complete

    def as_event(self) -> SIM.Event:
        """Convert UPSTAGE event to a simpy Event.

        Returns:
            SIM.Event: The upstage event as a simpy event.
        """
        raise NotImplementedError(
            "Events must specify how to convert to :class:`simpy.events.Event`"
        )

    def is_complete(self) -> bool:
        """Is the event complete?

        Returns:
            bool: If it's complete or not.
        """
        if self._simpy_event is None:
            raise UpstageError("Event has no simpy equivalent made.")
        return self._simpy_event.processed

    def cancel(self) -> None:
        """Cancel an event."""
        raise NotImplementedError("Implement custom event cancelling")


class MultiEvent(BaseEvent):
    """A base class for evaluating multiple events.

    Note:
        Subclasses of MultiEvent must define these methods:
            * simpy_equivalent: simpy.Event

        For an example, refer to :class:`~Any` and :class:`~All`.
    """

    def __init__(self, *events: BaseEvent | SIM.Process) -> None:
        """Create a multi-event based on a list of events.

        Args:
            *events (BaseEvent): The events that comprise the multi-event.
        """
        super().__init__()

        for event in events:
            if not issubclass(event.__class__, BaseEvent):
                warn(
                    f"Event '{event}' is not an upstage Event. "
                    f"All events in a MultiEvent must be an "
                    f"instance of upstage BaseEvent if you are going "
                    f"to rehearse the task that contains this MultiEvent.",
                    UserWarning,
                )
        self.events = events
        self._simpy_event = None

    @staticmethod
    def simpy_equivalent(env: SIM.Environment, events: list[SIM.Event]) -> SIM.Event:
        """Return the simpy equivalent event.

        Args:
            env (SIM.Environment): The SimPy environment.
            events (list[BaseEvent]): Events to turn into multi-event.

        Returns:
            SIM.Event: The aggregate event.
        """
        raise NotImplementedError("Implement in subclass")

    def _make_event(self, event: BaseEvent | SIM.Process) -> SIM.Event:
        # handle a process in the MultiEvent for non-rehearsal uses
        if isinstance(event, SIM.Process):
            return event
        return event.as_event()

    def as_event(self) -> SIM.Event:
        """Convert the UPSTAGE event to simpy.

        Returns:
            SIM.Event: typically an Any or All
        """
        sub_events = [self._make_event(event) for event in self.events]
        assert isinstance(self.env, SIM.Environment)
        self._simpy_event = self.simpy_equivalent(self.env, sub_events)
        return self._simpy_event

    def cancel(self) -> None:
        """Cancel the multi event and propagate it to the sub-events."""
        if self._simpy_event is None:
            raise UpstageError("Can't cancel a nonexistent event.")
        self._simpy_event.defused = True
        self._simpy_event.fail(Exception("defused"))
        for event in self.events:
            if isinstance(event, BaseEvent):
                try:
                    event.cancel()
                except Exception as e:
                    msg = f"Event {event} in {self} failed to cancel\n\t:{e}"
                    raise SimulationError(msg)


class Any(MultiEvent):
    """An event that requires one event to succeed before succeeding."""

    @staticmethod
    def simpy_equivalent(env: SIM.Environment, events: list[SIM.Event]) -> SIM.Event:
        """Return the SimPy version of the UPSTAGE Any event.

        Args:
            env (SIM.Environment): SimPy Environment.
            events (list[SIM.Event]): List of events.

        Returns:
            SIM.Event: A simpy AnyOf event.
        """
        return SIM.AnyOf(env, events)


class Event(BaseEvent):
    """An UPSTAGE version of the standard SimPy Event.

    Returns a planning factor object on rehearsal for user testing against in rehearsals, in case.

    When the event is succeeded, a payload can be added through kwargs.

    This Event assumes that it might be long-lasting, and will auto-reset when yielded on.
    """

    def __init__(
        self,
        rehearsal_time_to_complete: float = 0.0,
        auto_reset: bool = True,
    ) -> None:
        """Create an event.

        Args:
            rehearsal_time_to_complete (float, optional): Expected time to complete.
                Defaults to 0.0.
            auto_reset (bool, optional): Whether to auto-reset on yield. Defaults to True.
        """
        super().__init__(rehearsal_time_to_complete=rehearsal_time_to_complete)
        # The usage is sometimes that events might succeed before being
        # yielded on
        self._payload: dict[str, Any] = {}
        self._auto_reset = auto_reset
        assert isinstance(self.env, SIM.Environment)
        self._simpy_event: SIM.Event = SIM.Event(self.env)

    def as_event(self) -> SIM.Event:
        """Get the Event as a simpy type.

        This resets the event if allowed.

        Returns:
            SIM.Event
        """
        if self.is_complete():
            if self._auto_reset:
                self.reset()
            else:
                raise UpstageError("Event not allowed to reset on yield.")
        return self._simpy_event

    def succeed(self, **kwargs: tyAny) -> None:
        """Succeed the event and store any payload.

        Args:
            **kwargs (Any): key:values to store as payload.
        """
        if self.is_complete():
            raise SimulationError("Event has already completed")
        self._payload = kwargs
        self._simpy_event.succeed()

    def get_payload(self) -> dict[str, tyAny]:
        """Get any payload from the call to succeed().

        Returns:
            dict[str, Any]: The payload left by the succeed() caller.
        """
        return self._payload

    def reset(self) -> None:
        """Reset the event to allow it to be held again."""
        assert isinstance(self.env, SIM.Environment)
        self._simpy_event = SIM.Event(self.env)

    def cancel(self) -> None:
        """Cancel the event.

        Cancelling doesn't mean much, since it's still going to be yielded on.
        """
        try:
            self._simpy_event.defused = True
            self._simpy_event.succeed()
        except RuntimeError as exc:
            exc.add_note(f"Runtime error when cancelling '{self}'")
            raise exc


class Wait(BaseEvent):
    """Wait a specified or random uniformly distributed amount of time.

    Return a timeout. If time is a list of length 2, choose a random time
    between the interval given.

    Rehearsal time is given by the maximum time of the interval, if given.

    Parameters
    ----------
    timeout : int, float, list, tuple
        Amount of time to wait.  If it is a list or a tuple of length 2, a
        random uniform value between the two values will be used.

    """

    def _convert_time(self, time: float | int, unit: str | None) -> float:
        """Convert a time to the stage time.

        Args:
            time (float | int): The current time
            unit (str): Units the time is in

        Returns:
            float: Time in stage units
        """
        base_unit = self.stage.time_unit
        if base_unit is not None and unit is not None:
            return unit_convert(time, unit, base_unit)
        return time

    def __init__(
        self,
        timeout: float | int,
        time_unit: str | None = None,
        *,
        rehearsal_time_to_complete: float | int | None = None,
    ) -> None:
        """Create a timeout event.

        If time_unit is specified, UPSTAGE will try to convert it to the
        time_unit set in the stage. Otherwise, it defaults to that time unit.

        Args:
            timeout (float | int): Time to wait.
            time_unit (str, optional): Units of time
            rehearsal_time_to_complete (float | int, optional): The rehearsal time
                to complete. Defaults to None (the timeout given).

        """
        if not isinstance(timeout, float | int):
            raise SimulationError("Bad timeout. Did you mean to use from_random_uniform?")
        timeout = self._convert_time(timeout, time_unit)
        self._time_to_complete = timeout
        self.timeout = timeout
        if self._time_to_complete < 0:
            raise SimulationError(f"Negative timeout in Wait: {self._time_to_complete}")
        rehearse = timeout if rehearsal_time_to_complete is None else rehearsal_time_to_complete
        super().__init__(rehearsal_time_to_complete=rehearse)
        self._simpy_event: SIM.Timeout | None = None

    @classmethod
    def from_random_uniform(
        cls,
        low: float | int,
        high: float | int,
        time_unit: str | None = None,
        *,
        rehearsal_time_to_complete: float | int | None = None,
    ) -> "Wait":
        """Create a wait from a random uniform time.

        If time_unit is specified, UPSTAGE will try to convert it to the
        time_unit set in the stage. Otherwise, it defaults to that time unit.

        Args:
            low (float): Lower bounds of random draw
            high (float): Upper bounds of random draw
            time_unit (str, optional): Units of time
            rehearsal_time_to_complete (float | int, optional): The rehearsal time
                to complete. Defaults to None - meaning the random value drawn.

        Returns:
            Wait: The timeout event
        """
        rng = UpstageBase().stage.random
        timeout = rng.uniform(low, high)
        return cls(timeout, time_unit, rehearsal_time_to_complete=rehearsal_time_to_complete)

    def as_event(self) -> SIM.Timeout:
        """Cast Wait event as a simpy Timeout event.

        Returns:
            SIM.Timeout
        """
        assert isinstance(self.env, SIM.Environment)
        if self._simpy_event is None:
            self._simpy_event = self.env.timeout(self._time_to_complete)
        return self._simpy_event

    def cancel(self) -> None:
        """Cancel the timeout.

        There's no real meaning to cancelling a timeout. It sits in simpy's queue either way.
        """
        assert self._simpy_event is not None
        try:
            self._simpy_event.defused = True
        except RuntimeError as exc:
            warn(f"Runtime error when cancelling '{self}', Error: {exc}!")


class WaitUntil(BaseEvent):
    """Wait until a specific clock time.

    Rehearsal time is given by the maximum time of the interval, if given.

    Parameters
    ----------
    time : int, float
        Time to wait until
    """

    def _convert_time(self, time: float | int, unit: str | None) -> float:
        """Convert a time to the stage time.

        Args:
            time (float | int): The current time
            unit (str): Units the time is in

        Returns:
            float: Time in stage units
        """
        base_unit = self.stage.time_unit
        if base_unit is not None and unit is not None:
            return unit_convert(time, unit, base_unit)
        return time

    def __init__(
        self,
        until: float | int,
        time_unit: str | None = None,
        *,
        rehearsal_time_to_complete: float | int | None = None,
    ) -> None:
        """Create a timeout event.

        If timeout_unit is specified, UPSTAGE will try to convert it to the
        time_unit set in the stage. Otherwise, it defaults to that time unit.

        Args:
            until (float | int): Time to wait.
            time_unit (str, optional): Units of time
            rehearsal_time_to_complete (float | int, optional): The rehearsal time
                to complete. Defaults to None (the timeout given).

        """
        if not isinstance(until, float | int):
            raise SimulationError("Bad timeout. Must ve numeric")
        until_time = self._convert_time(until, time_unit)
        timeout = until_time - self.env.now
        self._time_to_complete = timeout
        self.timeout = timeout
        if self._time_to_complete < 0:
            raise SimulationError(f"Negative timeout in WaitUntil: {self._time_to_complete}")
        rehearse = timeout if rehearsal_time_to_complete is None else rehearsal_time_to_complete
        super().__init__(rehearsal_time_to_complete=rehearse)
        self._simpy_event: SIM.Timeout | None = None

    def as_event(self) -> SIM.Timeout:
        """Cast WaitUntil event as a simpy Timeout event.

        Returns:
            SIM.Timeout
        """
        assert isinstance(self.env, SIM.Environment)
        if self._simpy_event is None:
            self._simpy_event = self.env.timeout(self._time_to_complete)
        return self._simpy_event

    def cancel(self) -> None:
        """Cancel the timeout.

        There's no real meaning to cancelling a timeout. It sits in simpy's queue either way.
        """
        assert self._simpy_event is not None
        try:
            self._simpy_event.defused = True
        except RuntimeError as exc:
            warn(f"Runtime error when cancelling '{self}', Error: {exc}!")


class All(MultiEvent):
    """An event that requires all events to succeed before succeeding."""

    @staticmethod
    def simpy_equivalent(env: SIM.Environment, events: list[SIM.Event]) -> SIM.Event:
        """Return the SimPy version of the UPSTAGE All event.

        Args:
            env (SIM.Environment): SimPy Environment.
            events (list[SIM.Event]): List of events.

        Returns:
            SIM.Event: A simpy AllOf event.
        """
        return SIM.AllOf(env, events)


class BaseRequestEvent(BaseEvent):
    """Base class for Request Events.

    Requests are things like Get and Put that wait in a queue.
    """

    def __init__(self, rehearsal_time_to_complete: float = 0.0) -> None:
        """Create a request event.

        Args:
            rehearsal_time_to_complete (float, optional): Estimated time to complete.
                Defaults to 0.0.
        """
        super().__init__(rehearsal_time_to_complete=rehearsal_time_to_complete)
        self._simpy_event: SIM_REQ_EVTS | None = None

    def cancel(self) -> None:
        """Cancel the Request."""
        if self._simpy_event is None:
            return
        if not self.is_complete():
            self._simpy_event.cancel()
        # Note: inherited classes need to deal with put-backs.


class Put(BaseRequestEvent):
    """Wrap the ``simpy`` Put event.

    This is an event that puts an object into a ``simpy`` store or puts
    an amount into a container.

    """

    def __init__(
        self,
        put_location: SIM.Container | SIM.Store,
        put_object: float | int | tyAny,
        rehearsal_time_to_complete: float = 0.0,
    ) -> None:
        """Create a Put request for a store or container.

        Args:
            put_location (SIM.Container | SIM.Store): Any container, store, or subclass.
            put_object (float | int | Any): The amount (float | int) or object (Any) to put.
            rehearsal_time_to_complete (float, optional): Estimated time for the put to finish.
            Defaults to 0.0.
        """
        super().__init__(rehearsal_time_to_complete=rehearsal_time_to_complete)

        if not issubclass(put_location.__class__, SIM.Container | SIM.Store):
            raise SimulationError(
                f"put_location must be a subclass of Container "
                f"or Store, not {put_location.__class__}"
            )

        self.put_location = put_location
        self.put_object = put_object
        self._simpy_event: ContainerPut | StorePut | None = None

    def as_event(self) -> ContainerPut | StorePut:
        """Convert event to a ``simpy`` Event.

        Returns:
        ---------
        :obj:`simpy.events.Event`
            Put request as a simpy event.

        """
        if self._simpy_event is None:
            self._simpy_event = self.put_location.put(self.put_object)
        return self._simpy_event


class Get(BaseRequestEvent):
    """Wrap the ``simpy`` Get event.

    Event that gets an object from a ``simpy`` store or gets an amount from a
    container.
    """

    def __init__(
        self,
        get_location: SIM.Store | SIM.Container,
        *get_args: tyAny,
        rehearsal_time_to_complete: float = 0.0,
        **get_kwargs: tyAny,
    ) -> None:
        """Create a Get request on a store, container, or subclass of those.

        Args:
            get_location (SIM.Store | SIM.Container): The place for the Get request
            rehearsal_time_to_complete (float, optional): _description_. Defaults to 0.0.
            get_args (Any): optional positional args for the get request
                (blank for Store, for container it will be the amount)
            get_kwargs (Any): optional keyword args for the get request
                (blank for Store and Container, other kinds may have more)
        """
        super().__init__(rehearsal_time_to_complete=rehearsal_time_to_complete)

        if not issubclass(get_location.__class__, SIM.Container | SIM.Store):
            raise SimulationError(
                "'put_location' must be a subclass of Container"
                f" or Store, not {get_location.__class__}"
            )

        self.get_location = get_location
        self.get_args = get_args
        self.get_kwargs = get_kwargs
        self._simpy_event: ContainerGet | StoreGet | None = None

    def as_event(self) -> ContainerGet | StoreGet:
        """Convert get to a ``simpy`` Event.

        Returns:
            ContainerGet | StoreGet
        """
        # TODO: optional checking for container types for feasibility
        if self._simpy_event is None:
            self._simpy_event = self.get_location.get(
                *self.get_args,
                **self.get_kwargs,
            )
        return self._simpy_event

    def get_value(self) -> tyAny:
        """Get the value returned when the request is complete.

        Returns:
            Any: The amount or item requested.
        """
        if isinstance(self._simpy_event, StoreGet):
            try:
                return self._simpy_event.value
            except AttributeError:
                raise SimulationError("Requested item from an unfinished Get request.")
        elif isinstance(self._simpy_event, ContainerGet):
            try:
                return self._simpy_event.amount
            except AttributeError:
                raise SimulationError("Requested item from an unfinished Get request.")
        else:
            raise SimulationError("Requested item from an unfinished Get request.")

    def cancel(self) -> None:
        """Cancel the get, and check if we got the item.

        There is an edge case where a Get request has the item, but
        isn't given back to the process because an interrupt sorts
        to first in the queue. This method handles that edge
        case, giving the item back.
        """
        super().cancel()
        # Return the item if we got it.
        if isinstance(self._simpy_event, ContainerGet | StoreGet):
            with suppress(SimulationError):
                value = self.get_value()

                def _putter() -> SIMPY_GEN:
                    yield self.get_location.put(value)

                self.env.process(_putter())


class FilterGet(Get):
    """A Get for a FilterStore."""

    def __init__(
        self,
        get_location: SIM.FilterStore,
        filter: Callable[[tyAny], bool],
        rehearsal_time_to_complete: float = 0.0,
    ) -> None:
        """Create a Get request on a FilterStore.

        The filter function returns a boolean (in/out of consideration).

        Args:
            get_location (SIM.Store | SIM.Container): The place for the Get request
            filter (Callable[[Any], bool]): The function that filters items in the store
            rehearsal_time_to_complete (float, optional): _description_. Defaults to 0.0.
        """
        super().__init__(
            get_location=get_location,
            rehearsal_time_to_complete=rehearsal_time_to_complete,
            filter=filter,
        )


class ResourceHold(BaseRequestEvent):
    """Wrap the ``simpy`` request resource event.

    This manages getting and giving back all in one object.

    Example:
        >>> resource = simpy.Resource(env, capacity=1)
        >>> hold = ResourceHold(resource)
        >>> # yield on the hold to get it
        >>> yield hold
        >>> # now that you have it, do things..
        >>> # give it back
        >>> yield hold
        >>> ...
    """

    def __init__(
        self,
        resource: SIM.Resource,
        *resource_args: tyAny,
        rehearsal_time_to_complete: float = 0.0,
        **resource_kwargs: tyAny,
    ) -> None:
        """Create an event to use twice to get and give back a resource.

        Args:
            resource (SIM.Resource): The simpy resource object.
            rehearsal_time_to_complete (float, optional): Expected time to wait to
                get the resource. Defaults to 0.0.
            *resource_args (Any): positional arguments to the resource
            **resource_kwargs (Any): keyword arguments to the resource
        """
        super().__init__(rehearsal_time_to_complete=rehearsal_time_to_complete)

        self.resource = resource
        self.resource_args = resource_args
        self.resource_kwargs = resource_kwargs
        self._stage = "request"
        self._simpy_event: Request | Release | None = None

    def as_event(self) -> Request | Release:
        """Create the simpy event for the right state of Resource usage.

        Returns:
            Request | Release: The simpy event.
        """
        if self._stage == "request":
            self._simpy_event = self.resource.request(*self.resource_args, **self.resource_kwargs)
            self._stage = "release"
            return self._simpy_event
        elif self._stage == "release":
            if not self._simpy_event or not self._simpy_event.processed:
                raise SimulationError(
                    "Resource release requested when the "
                    "resource hasn't been given. Did you cancel?"
                )
            assert isinstance(self._simpy_event, Request)
            self._simpy_event = self.resource.release(self._simpy_event)
            self._stage = "completed"
            return self._simpy_event
        raise UpstageError(f"Bad stage for Resource Hold: {self._stage}")
