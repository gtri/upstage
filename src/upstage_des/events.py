# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Classes for UPSTAGE events that feed to simpy."""

from collections.abc import Iterable
from typing import Any as tyAny

import simpy as SIM
from simpy.resources.base import Get as SIMGet
from simpy.resources.base import Put as SIMPut
from simpy.resources.container import ContainerGet
from simpy.resources.resource import Request as SIMReq

from upstage_des.base import SimulationError, get_env, get_stage
from upstage_des.units import unit_convert

__all__ = (
    "make_timeout",
    "make_timeout_until",
    "make_random_timeout",
    "Timeout",
    "Event",
    "AnyOf",
    "AllOf",
)


def _convert_time(time: float | int, unit: str | None) -> float:
    """Convert a time to the stage time.

    Args:
        time (float | int): The current time
        unit (str): Units the time is in

    Returns:
        float: Time in stage units
    """
    base_unit = get_stage().time_unit
    if base_unit is not None and unit is not None:
        return unit_convert(time, unit, base_unit)
    return time


def _cancel_event(event: SIM.Event, cause: tyAny | None = None) -> None:
    """Cancel any simpy event."""
    if event.processed or event.triggered:
        return
    if isinstance(event, SIM.Process):
        if event.is_alive:
            event.interrupt(cause)
    elif isinstance(event, (SIMPut, SIMGet)):
        # TODO: is a triggered but unprocessed Get or Put a problem?
        event.cancel()
    elif isinstance(event, (SIM.AnyOf, SIM.AllOf)):
        for event in event._events:
            _cancel_event(event)
    elif isinstance(event, SIM.Timeout) or event.__class__ is SIM.Event:
        # Timeouts or bare events don't get cancelled.
        pass
    else:
        # If there's one we haven't thought of, flag it.
        raise ValueError(f"Unknown event type {event}")


def _event_has_resource_request(event: SIM.Event) -> list[tuple[SIMReq, SIM.Resource]]:
    """If the event is or holds a resource request, return the resource(s)."""
    if isinstance(event, SIMReq):
        return [(event, event.resource)]
    elif isinstance(event, SIM.AnyOf | SIM.AllOf):
        ans = sum((_event_has_resource_request(evt) for evt in event._events), start=[])
        return ans
    return []


class Timeout(SIM.Timeout):
    """Wrapped Timeout."""

    def __init__(
        self, delay: float, value: tyAny | None = None, time_units: str | None = None
    ) -> None:
        """UPSTAGE wrapper for env.timeout/simpy.Timeout, with units."""
        t = _convert_time(delay, time_units)
        super().__init__(get_env(), t, value)
        self._created_at = self.env.now


class Event(SIM.Event):
    """Wrapped Event."""

    def __init__(self) -> None:
        """UPSTAGE wrapper for simpy.Event."""
        super().__init__(get_env())
        self._created_at = self.env.now


class AnyOf(SIM.AnyOf):
    """Wrapped AnyOf."""

    def __init__(self, events: Iterable[SIM.Event]) -> None:
        """UPSTAGE wrapper for simpy.AnyOf."""
        super().__init__(get_env(), events)
        self._created_at = self.env.now


class AllOf(SIM.AllOf):
    """Wrapped AllOf."""

    def __init__(self, events: Iterable[SIM.Event]) -> None:
        """UPSTAGE wrapper for simpy.AllOf."""
        super().__init__(get_env(), events)
        self._created_at = self.env.now


def is_event_complete(event: SIM.Event) -> bool:
    """Test if an event is done.

    Args:
        event (Event): An event.

    Returns:
        bool: If the event is complete.
    """
    return event.processed


def get_event_value(event: Event | SIMGet) -> tyAny:
    """Get a value and assert it's not none.

    Args:
        event (SimGet): A get event.

    Returns:
        Any: The get's result
    """
    if isinstance(event, ContainerGet):
        raise SimulationError("Container Gets do not return an amount.")
    assert event.value is not None, f"{event} had unexpected None value."
    return event.value


def make_timeout(
    time: float,
    time_units: str | None = None,
    value: tyAny | None = None,
) -> Timeout:
    """Make a timeout, optionally adding time units.

    Args:
        time (float): The time to wait
        time_units (str | None, optional): Units to use for time,
            if not the stage sim time. Defaults to None.
        value (Any | None): A value to add to the timeout.

    Returns:
        Timeout: The timeout to yield
    """
    return Timeout(time, value, time_units)


def make_timeout_until(
    until_time: float,
    time_units: str | None = None,
    value: tyAny | None = None,
) -> Timeout:
    """Make a timeout that ends at a givent time, optionally adding time units.

    Args:
        until_time (float): The time to wait until
        time_units (str | None, optional): Units to use for time, if not the stage sim time.
            Defaults to None.
        value (Any | None): A value to add to the timeout.

    Returns:
        Timeout: The timeout to yield
    """
    t = _convert_time(until_time, time_units)
    env = get_env()
    delta = t - env.now
    return Timeout(delta, value)


def make_random_timeout(
    min_time: float,
    max_time: float,
    time_units: str | None = None,
    value: tyAny | None = None,
) -> Timeout:
    """Make a uniform random timeout.

    Args:
        min_time (float): Min time to timeout.
        max_time (float): Max time to timeout.
        time_units (str | None, optional): Units to use for time, if not the stage sim time.
            Defaults to None.
        value (Any | None, optional): Value to store on the timeout. Defaults to None.

    Returns:
        Timeout: The timeout, built from random.
    """
    t_random = get_stage().random.uniform(min_time, max_time)
    return make_timeout(t_random, time_units, value)


class EVENT_HELP:
    """A class for quickly getting event helper methods."""

    cancel_event = _cancel_event
    make_random_timeout = make_random_timeout
    make_timeout_until = make_timeout_until
    make_timeout = make_timeout
    is_complete = is_event_complete
    get_value = get_event_value
