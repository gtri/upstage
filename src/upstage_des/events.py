# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Classes for UPSTAGE events that feed to simpy."""

from collections.abc import Callable
from typing import Any as tyAny
from warnings import warn

import simpy as SIM
from simpy.resources.container import ContainerGet, ContainerPut
from simpy.resources.resource import Release, Request
from simpy.resources.store import StoreGet, StorePut

from .base import SimulationError, UpstageBase, UpstageError
from .constants import PLANNING_FACTOR_OBJECT
from .units import unit_convert

__all__ = (
    "All",
    "Any",
    "BaseEvent",
    "Event",
    "Get",
    "FilterGet",
    "MultiEvent",
    "Put",
    "ResourceHold",
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
        self._rehearsing: bool = False
        self._done_rehearsing: bool = False

        self.created_at: float = self.now
        self.rehearsal_time_to_complete = rehearsal_time_to_complete

    @property
    def now(self) -> float:
        """Current sim time.

        Returns:
            float: sim time
        """
        return self.env.now

    def calculate_time_to_complete(self) -> float:
        """Calculate the time elapsed until the event is triggered.

        Returns:
            float: The time until the event triggers.
        """
        return self.rehearsal_time_to_complete

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
        if self._rehearsing:
            return self._done_rehearsing
        if self._simpy_event is None:
            raise UpstageError("Event has no simpy equivalent made.")
        return self._simpy_event.processed

    def cancel(self) -> None:
        """Cancel an event."""
        raise NotImplementedError("Implement custom event cancelling")

    @property
    def rehearsing(self) -> bool:
        """If the event is rehearsing.

        Returns:
            bool
        """
        return self._rehearsing

    @property
    def done_rehearsing(self) -> bool:
        """If the event is done rehearsing.

        Returns:
            bool
        """
        return self._done_rehearsing

    def _start_rehearsal(self) -> None:
        """Set the event to testing mode."""
        self._rehearsing = True
        self._done_rehearsing = False

    def _finish_rehearsal(self, complete: bool) -> None:
        """Finish rehearsing the event.

        Args:
            complete (bool): Indicates if the event was successful during the test.
        """
        if not self._rehearsing:
            raise SimulationError(
                "Trying to finish testing event but event testing was not started`"
            )
        self._done_rehearsing = complete

    def rehearse(self) -> tuple[float, tyAny | None]:
        """Run the event in 'rehearsal' mode without changing the real environment.

        This is used by the task rehearsal functions.

        Returns:
            tuple[float, Any | None]: The time to complete and the event's response.
        """
        self._start_rehearsal()
        time_advance = self.calculate_time_to_complete()
        self._finish_rehearsal(complete=True)

        event_response = None

        return time_advance, event_response


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
        base_unit = self.stage.get("time_unit")
        if base_unit is not None and unit is not None:
            return unit_convert(time, unit, base_unit)
        return time

    def __init__(
        self,
        timeout: float | int,
        timeout_unit: str | None = None,
        *,
        rehearsal_time_to_complete: float | int | None = None,
    ) -> None:
        """Create a timeout event.

        If timeout_unit is specified, UPSTAGE will try to convert it to the
        time_unit set in the stage. Otherwise, it defaults to that time unit.

        Args:
            timeout (float | int): Time to wait.
            timeout_unit (str, optional): Units of time
            rehearsal_time_to_complete (float | int, optional): The rehearsal time
                to complete. Defaults to None (the timeout given).

        """
        if not isinstance(timeout, float | int):
            raise SimulationError("Bad timeout. Did you mean to use from_random_uniform?")
        timeout = self._convert_time(timeout, timeout_unit)
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
        timeout_unit: str | None = None,
        *,
        rehearsal_time_to_complete: float | int | None = None,
    ) -> "Wait":
        """Create a wait from a random uniform time.

        If timeout_unit is specified, UPSTAGE will try to convert it to the
        time_unit set in the stage. Otherwise, it defaults to that time unit.

        Args:
            low (float): Lower bounds of random draw
            high (float): Upper bounds of random draw
            timeout_unit (str, optional): Units of time
            rehearsal_time_to_complete (float | int, optional): The rehearsal time
                to complete. Defaults to None - meaning the random value drawn.

        Returns:
            Wait: The timeout event
        """
        rng = UpstageBase().stage.random
        timeout = rng.uniform(low, high)
        return cls(timeout, timeout_unit, rehearsal_time_to_complete=rehearsal_time_to_complete)

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
        self._request_event: SIM_REQ_EVTS | None = None

    def cancel(self) -> None:
        """Cancel the Request."""
        if self._request_event is None:
            return
        if not self.is_complete():
            self._request_event.cancel()
        # TODO: Do we put it back?

    def is_complete(self) -> bool:
        """Test if the request is finished.

        Returns:
            bool
        """
        if self.rehearsing:
            if self.done_rehearsing is None:
                raise SimulationError(
                    f"Event '{self}' rehearsal started, but completion was"
                    "not set as incomplete, i.e., to `False`!"
                )
            return self.done_rehearsing
        assert self._request_event is not None
        return self._request_event.processed


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
        self._request_event: ContainerPut | StorePut | None = None

    def as_event(self) -> ContainerPut | StorePut:
        """Convert event to a ``simpy`` Event.

        Returns:
        ---------
        :obj:`simpy.events.Event`
            Put request as a simpy event.

        """
        if self._request_event is None:
            self._request_event = self.put_location.put(self.put_object)
        return self._request_event


class MultiEvent(BaseEvent):
    """A base class for evaluating multiple events.

    Note:
        Subclasses of MultiEvent must define these methods:
            * aggregation_function: Callable[[list[float]], float]
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
    def aggregation_function(times: list[float]) -> float:
        """Aggregate event times to one single time.

        Args:
            times (list[float]): Event rehearsal times

        Returns:
            float: The aggregated time
        """
        raise NotImplementedError("Implement in subclass")

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

    def calculate_time_to_complete(
        self,
    ) -> float:
        """Compute time required to complete the multi-event.

        Args:
            return_sub_events (bool, Optional): Whether to return all times or not.
                Defaults to False.
        """
        event_times = {
            event: event.calculate_time_to_complete()
            for event in self.events
            if isinstance(event, BaseEvent)
        }

        time_to_complete = self.aggregation_function(list(event_times.values()))

        return time_to_complete

    def calc_time_to_complete_with_sub(self) -> tuple[float, dict[BaseEvent, float]]:
        """Compute time required for MultiEvent and get sub-event times.

        Returns:
            tuple[float, dict[BaseEvent, float]]: Aggregate and individual times.
        """
        event_times = {
            event: event.calculate_time_to_complete()
            for event in self.events
            if isinstance(event, BaseEvent)
        }
        time_to_complete = self.aggregation_function(list(event_times.values()))

        return time_to_complete, event_times

    def _start_rehearsal(self) -> None:
        """Start rehearsing all the sub-events."""
        super()._start_rehearsal()
        for event in self.events:
            if not hasattr(event, "_start_rehearsal"):
                raise SimulationError(
                    f"Event '{event}' is not an upstage Event. "
                    f"All events in a MultiEvent must be an "
                    f"instance of upstage BaseEvent if you are going"
                    f"to rehearse the task that contains this MultiEvent."
                )
            event._start_rehearsal()

    def rehearse(self) -> tuple[float, tyAny]:
        """Run the event in 'trial' mode without changing the real environment.

        Returns:
            tuple[float, Any]: The time to complete and the event's response.

        Note:
            This is used by the task rehearsal functions.
        """
        self._start_rehearsal()

        event_response = None
        time_to_finish, event_times = self.calc_time_to_complete_with_sub()

        for event, event_end_time in event_times.items():
            event._finish_rehearsal(complete=event_end_time <= time_to_finish)

        self._finish_rehearsal(complete=True)

        return time_to_finish, event_response


class Any(MultiEvent):
    """An event that requires one event to succeed before succeeding."""

    @staticmethod
    def aggregation_function(times: list[float]) -> float:
        """Aggregation function for rehearsal time.

        Args:
            times (list[float]): List of rehearsal times

        Returns:
            float: Aggregated time (the minimum)
        """
        return min(times)

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
                (blank for Store and Container)
            get_kwargs (Any): optional keyword args for the get request
                (blank for Store and Container)
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
        self.__is_store = issubclass(get_location.__class__, SIM.Store)
        self._request_event: ContainerGet | StoreGet | None = None

    def calculate_time_to_complete(self) -> float:
        """Calculate time elapsed until the event is triggered.

        Returns:
            float: Estimated time until the event triggers.

        """
        return self.rehearsal_time_to_complete

    def as_event(self) -> ContainerGet | StoreGet:
        """Convert get to a ``simpy`` Event.

        Returns:
            ContainerGet | StoreGet
        """
        # TODO: optional checking for container types for feasibility
        if self._request_event is None:
            self._request_event = self.get_location.get(
                *self.get_args,
                **self.get_kwargs,
            )
        return self._request_event

    def get_value(self) -> tyAny:
        """Get the value returned when the request is complete.

        Returns:
            Any: The amount or item requested.
        """
        if self.__is_store:
            if self.rehearsing and self.done_rehearsing:
                return PLANNING_FACTOR_OBJECT
            if self._request_event is not None and self._request_event.value is not None:
                return self._request_event.value
            else:
                raise SimulationError("Requested item from an unfinished Get request.")
        else:
            raise SimulationError(
                "'get_value' is not supported for Containers. Check is_"
                "complete and use the amount you requested."
            )

    def rehearse(self) -> tuple[float, tyAny]:
        """Mock the event to test if it is feasible.

        Note:
            The function does not fully test the conditions to satisfy the
            get request, but this method can be called as part of a more
            complex rehearse run.

        Returns:
            float: The time it took to do the request
            Any: The value of the request.
        """
        time_advance, _ = super().rehearse()
        event_response = None
        if self.__is_store:
            event_response = PLANNING_FACTOR_OBJECT
        return time_advance, event_response


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
        self._request: Request | Release | None = None

    def calculate_time_to_complete(self) -> float:
        """Time to complete, based on waiting for getting or giving back.

        Returns:
            float: Time
        """
        if self._stage == "request":
            # assume the stage will switch on the next call
            self._stage = "release"
            return self.rehearsal_time_to_complete
        elif self._stage == "release":
            return 0.0
        raise UpstageError(f"Resource request stage is wrong: {self._stage}")

    def as_event(self) -> Request | Release:
        """Create the simpy event for the right state of Resource usage.

        Returns:
            Request | Release: The simpy event.
        """
        if self._stage == "request":
            self._request = self.resource.request(*self.resource_args, **self.resource_kwargs)

            self._request_event = self._request
            self._stage = "release"
            return self._request_event
        elif self._stage == "release":
            if not self._request or not self._request.processed:
                raise SimulationError(
                    "Resource release requested when the "
                    "resource hasn't been given. Did you cancel?"
                )
            assert isinstance(self._request, Request)
            self._request_event = self.resource.release(self._request)
            self._stage = "completed"
            return self._request_event
        raise UpstageError(f"Bad stage for Resource Hold: {self._stage}")


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


class All(MultiEvent):
    """An event that requires all events to succeed before succeeding."""

    @staticmethod
    def aggregation_function(times: list[float]) -> float:
        """Aggregate event times for rehearsal.

        Args:
            times (list[float]): List of rehearsing times.

        Returns:
            float: Aggregated (maximum) time.
        """
        return max(times)

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
        self._event = SIM.Event(self.env)

    def calculate_time_to_complete(self) -> float:
        """Return the time to complete.

        Returns:
            float: Time to complete estimate.
        """
        return self.rehearsal_time_to_complete

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
        return self._event

    def succeed(self, **kwargs: tyAny) -> None:
        """Succeed the event and store any payload.

        Args:
            **kwargs (Any): key:values to store as payload.
        """
        if self.is_complete():
            raise SimulationError("Event has already completed")
        self._payload = kwargs
        self._event.succeed()

    def is_complete(self) -> bool:
        """Is the event done?

        Returns:
            bool
        """
        return self._event.processed

    def get_payload(self) -> dict[str, tyAny]:
        """Get any payload from the call to succeed().

        Returns:
            dict[str, Any]: The payload left by the succeed() caller.
        """
        return self._payload

    def reset(self) -> None:
        """Reset the event to allow it to be held again."""
        assert isinstance(self.env, SIM.Environment)
        self._event = SIM.Event(self.env)

    def cancel(self) -> None:
        """Cancel the event.

        Cancelling doesn't mean much, since it's still going to be yielded on.
        """
        try:
            self._event.defused = True
            self._event.succeed()
        except RuntimeError as exc:
            exc.add_note(f"Runtime error when cancelling '{self}'")
            raise exc

    def rehearse(self) -> tuple[float, tyAny]:
        """Run the event in 'trial' mode without changing the real environment.

        Returns:
            tuple[float, Any]: The time to complete and the event's response.
        """
        time_advance, _ = super().rehearse()
        return time_advance, PLANNING_FACTOR_OBJECT
