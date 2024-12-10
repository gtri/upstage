# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""This file contains a ContinuousContainer."""

from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any

from simpy import Environment, Event, Interrupt, Process
from simpy.core import BoundClass

__all__ = (
    "ContinuousContainer",
    "ContainerEmptyError",
    "ContainerError",
    "ContainerFullError",
)

EMPTY_STATUS: str = "empty"
FULL_STATUS: str = "full"


class ContainerError(Exception):
    """The container is in an invalid state."""

    @property
    def cause(self) -> Any:
        """Get the exception's cause.

        Returns:
            Any: The cause.
        """
        return self.args[0]


class ContainerFullError(ContainerError):
    """The container has reach or exceeded its capacity."""

    pass


class ContainerEmptyError(ContainerError):
    """The container is empty or has a negative level."""

    pass


class _ContinuousEvent(Event):
    def _run(self, runtime: float) -> Generator[Event, None, None]:
        self.container.add_user(self)
        do_remove = True
        try:
            evt = self.env.timeout(runtime)
            yield evt
        except Interrupt as interruption:
            if interruption.cause == self.stop_cause:
                # The container will handle this for us
                do_remove = False
                for callback in self.custom_callbacks:
                    callback()
            elif interruption.cause != "stop":
                raise Interrupt(interruption)
        if do_remove:
            self.container.remove_user(self)

    def __init__(
        self,
        container: "ContinuousContainer",
        rate: float,
        time: float,
        stop_cause: str | None,
        custom_callbacks: list[Callable[[], None]] | None = None,
    ) -> None:
        super().__init__(container.env)
        self.container = container
        self.rate = rate
        self.custom_callbacks = custom_callbacks or []
        self.stop_cause = stop_cause
        time = float("inf") if time is None else time
        self.process = self.env.process(self._run(time))

    def cancel(self) -> None:
        """Cancel this request.

        This method has to be called if the put request must be aborted, for
        example if a process needs to handle an exception like an
        :class:`~simpy.events.Interrupt`.

        If the put request was created in a :keyword:`with` statement, this
        method is called automatically.

        """
        if self.process.is_alive:
            self.process.interrupt("stop")


class ContinuousPut(_ContinuousEvent):
    """An event that puts *rate* per unit time into the *container*.

    Raise a :exc:`ValueError` if ``rate <= 0``.
    """

    def __init__(
        self,
        container: "ContinuousContainer",
        rate: float,
        time: float,
        custom_callbacks: list[Callable[[], None]] | None = None,
    ) -> None:
        """Create a put event that is continuous.

        Args:
            container (ContinuousContainer): Container to add to.
            rate (float): Rate to add at.
            time (float): Time to run the event.
            custom_callbacks (list[Callable[[], None]] | None, optional): Callbacks
                for completion. Defaults to None.
        """
        if rate <= 0:
            raise ValueError(
                "Rates must be greater than zero. Put means 'positive'."
            )  # pragma: no cover
        super().__init__(container, rate, time, FULL_STATUS, custom_callbacks)


class ContinuousGet(_ContinuousEvent):
    """An event that gets *amount* from the *container*."""

    def __init__(
        self,
        container: "ContinuousContainer",
        rate: float,
        time: float,
        custom_callbacks: list[Callable[[], None]] | None = None,
    ) -> None:
        """Create a get event that is continuous.

        Args:
            container (ContinuousContainer): Container to take from.
            rate (float): Rate to remote at.
            time (float): Time to run the event.
            custom_callbacks (list[Callable[[], None]] | None, optional): Callbacks
                for completion. Defaults to None.
        """
        if rate <= 0:
            raise ValueError(
                "Rates must be greater than zero. Get means 'negative'."
            )  # pragma: no cover
        super().__init__(container, -rate, time, EMPTY_STATUS, custom_callbacks)


class ContinuousContainer:
    """A container that accepts continuous gets and puts."""

    def __init__(
        self,
        env: Environment,
        capacity: int | float,
        init: int | float = 0.0,
        error_empty: bool = True,
        error_full: bool = True,
    ):
        """Create a container that allows continuous gets and puts.

        Args:
            env (Environment): SimPy Environment.
            capacity (int | float): Capacity of the container
            init (int | float, optional): Initial amount. Defaults to 0.0.
            error_empty (bool, optional): Error when it gets empty. Defaults to True.
            error_full (bool, optional): Error when it gets full. Defaults to True.
        """
        self._capacity = capacity
        if init < 0 or capacity < 0:
            raise ValueError("Initial and capacity cannot be negative.")  # pragma: no cover
        self._level = init
        self.error_empty = error_empty
        self.error_full = error_full

        self._rate: float = 0.0
        self._env: Environment = env
        self._last: float = self._env.now
        self._active_users: list[_ContinuousEvent] = []
        self._checking: Process | None = None

    if TYPE_CHECKING:

        def put(
            self,
            rate: float,
            time: float,
            custom_callbacks: list[Callable[[], None]] | None = None,
        ) -> ContinuousPut:
            """Request to put *item* into the store."""
            return ContinuousPut(self, rate, time, custom_callbacks)

        def get(
            self, rate: float, time: float, custom_callbacks: list[Callable[[], None]] | None = None
        ) -> ContinuousGet:
            """Request to get an *item* out of the store."""
            return ContinuousGet(self, rate, time, custom_callbacks)

    else:
        put = BoundClass(ContinuousPut)
        get = BoundClass(ContinuousGet)

    def time_until_level(self, level: float, rate: float = 0.0) -> float:
        """Calculate the time until the containers reaches a value.

        Args:
            level (float): The value to reach.
            rate (float, optional): Additional rate. Defaults to 0.0.

        Returns:
            float: The time to reach the level.
        """
        rate += self._rate

        if self.level == level:
            return 0.0  # pragma: no cover
        elif rate == 0:
            return float("inf")  # pragma: no cover
        time = (level - self._level) / rate
        return time if time > 0 else float("inf")

    def time_until_done(self, rate: float = 0.0) -> float:
        """Calculate the time until the container is full or empty.

        Args:
            rate (float, optional): Additional rate. Defaults to 0.0.

        Returns:
            float: Time until the container reaches a limit.
        """
        rate += self._rate
        if rate > 0:
            return (self.capacity - self.level) / rate
        elif rate < 0:
            return -self.level / rate
        else:
            return float("inf")  # pragma: no cover

    @property
    def env(self) -> Environment:
        """Get the environment of the container.

        Returns:
            Environment: The SimPy environment.
        """
        return self._env

    @property
    def rate(self) -> float:
        """Get the current net rate.

        Returns:
            float: The net rate.
        """
        return self._rate

    @property
    def capacity(self) -> float:
        """Get the capacity of the container.

        Returns:
            float: The capacity.
        """
        return self._capacity

    @property
    def _active_puts(self) -> list[ContinuousPut]:
        puts = []
        for x in self._active_users:
            if x.rate > 0:
                assert isinstance(x, ContinuousPut)
                puts.append(x)
        return puts

    @property
    def _active_gets(self) -> list[ContinuousGet]:
        gets = []
        for x in self._active_users:
            if x.rate < 0:
                assert isinstance(x, ContinuousGet)
                gets.append(x)
        return gets

    def _set_level(self) -> float:
        """Set the level of the container based on the active gets/puts.

        Returns:
            float: The current level.
        """
        now = self._env.now
        if now > self._last:
            self._level += self._rate * (now - self._last)
            self._last = now
        return self._level

    def _check_empty(self) -> tuple[list[ContinuousGet], float]:
        level = self._level
        to_rem: list[ContinuousGet] = []
        rate = 0.0
        if level > 0:
            return to_rem, rate
        for get in tuple(self._active_gets):
            get.process.interrupt(EMPTY_STATUS)
            to_rem.append(get)
            rate += -get.rate
        if level == 0 and self.error_empty:
            raise ContainerEmptyError("Container is empty!")
        elif level < 0.0:
            raise ContainerError(f"Container level is less than 0 ({level:.3f})!")
        return to_rem, rate

    def _check_full(self) -> tuple[list[ContinuousPut], float]:
        level = self._level
        to_rem: list[ContinuousPut] = []
        rate: float = 0.0
        if level < self.capacity:
            return to_rem, rate
        for put in tuple(self._active_puts):
            put.process.interrupt(FULL_STATUS)
            to_rem.append(put)
            rate += -put.rate
        if level == self.capacity and self.error_full:
            raise ContainerFullError("Container is full!")
        elif level > self.capacity:
            msg = "Container level exceeds capacity by {:.3f}!"
            raise ContainerError(msg.format(level - self._capacity))
        return to_rem, rate

    def _check(self) -> Generator[Event, None, None]:
        if not self._rate or self._rate == 0:
            return  # pragma: no coverd

        level = self.level

        check_wait = ((self._capacity if self._rate > 0 else 0.0) - level) / self._rate

        try:
            yield self._env.timeout(check_wait)
        except Interrupt as interruption:
            if interruption.cause != "updated":
                raise  # pragma: no cover
        finally:
            to_rem: list[ContinuousGet] | list[ContinuousPut] = []
            rate: float
            self._set_level()
            if self._rate < 0:
                to_rem, rate = self._check_empty()
            elif self._rate > 0:
                to_rem, rate = self._check_full()
            if to_rem:
                for req in to_rem:
                    self._active_users.remove(req)
                self._add_rate(rate, interrupt=False)

    def _add_rate(self, rate_change: float | int, interrupt: bool = True) -> None:
        """Add a new rate to the existing rate."""
        if self._checking is not None and interrupt:
            self._checking.interrupt("updated")

        self._set_level()
        self._rate += rate_change

        if self._rate == 0.0:
            self._checking = None
        else:
            self._checking = self._env.process(self._check())

    def add_user(self, user: _ContinuousEvent) -> None:
        """Add a user to the container.

        Args:
            user (_ContinuousEvent): The user event
        """
        self._active_users.append(user)
        self._add_rate(user.rate)

    def remove_user(self, user: _ContinuousEvent) -> None:
        """Remove a user of the container.

        Args:
            user (_ContinuousEvent): The user event.
        """
        to_remove_rate = -1 * user.rate
        self._active_users.remove(user)
        self._add_rate(to_remove_rate)

    def _set_new_rate(self, rate: float | int) -> None:
        """Set a new rate.

        Args:
            rate (float | int): The new total rate.
        """
        curr_rate = self.rate
        diff = rate - curr_rate
        self._add_rate(diff)

    @property
    def level(self) -> float:
        """Get the level of the container.

        Returns:
            float: The current amount remaining.
        """
        return self._level + self._rate * (self._env.now - self._last)
