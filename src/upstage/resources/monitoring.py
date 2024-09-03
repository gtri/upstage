# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Stores that monitor/record their items over time."""

from collections.abc import Callable
from typing import Any

from simpy import Container, Environment, Event, FilterStore, Store
from simpy.resources.container import ContainerGet, ContainerPut
from simpy.resources.store import FilterStoreGet, StoreGet, StorePut

from .container import ContinuousContainer
from .reserve import ReserveStore
from .sorted import SortedFilterStore, _SortedFilterStoreGet

__all__ = (
    "SelfMonitoringStore",
    "SelfMonitoringFilterStore",
    "SelfMonitoringContainer",
    "SelfMonitoringContinuousContainer",
    "SelfMonitoringSortedFilterStore",
    "SelfMonitoringReserveStore",
)

RECORDER_FUNC = Callable[[list[Any]], int]


class SelfMonitoringStore(Store):
    """A self-monitoring version of the SimPy Store."""

    def __init__(
        self,
        env: Environment,
        capacity: float | int = float("inf"),
        item_func: RECORDER_FUNC | None = None,
    ) -> None:
        """A monitoring version of the SimPy Store.

        Since Stores contain a list of objects, recording the mutable list is replaced
        by recording the length of the list by default. Otherwise, input the item_func
        to take the store items and return a recordable value.

        Args:
            env (Environment): SimpyEnvironment.
            capacity (float | int, optional): Capacity of the store. Defaults to float("inf").
            item_func (RECORDER_FUNC | None, optional): Function to create recorded values.
                Defaults to None.
        """
        super().__init__(env, capacity=capacity)
        self.item_func = item_func if item_func is not None else len
        self._quantities = [(self._env.now, self.item_func(self.items))]

    def _record(self, call: str) -> None:
        v = self.item_func(self.items)
        if v != self._quantities[-1][1] or call == "environment":
            self._quantities.append((self._env.now, v))

    def _trigger_put(self, event: Event) -> None:  # type: ignore [override]
        super()._trigger_put(event)
        self._record("put")

    def _trigger_get(self, event: Event) -> None:  # type: ignore [override]
        super()._trigger_get(event)
        self._record("get")

    def _do_put(self, event: StorePut) -> None:
        super()._do_put(event)
        if event.triggered:
            self._record("put")

    def _do_get(self, event: StoreGet) -> None:
        super()._do_get(event)
        if event.triggered:
            self._record("get")


class SelfMonitoringFilterStore(FilterStore):
    """A self-monitoring version of the SimPy FilterStore."""

    def __init__(
        self,
        env: Environment,
        capacity: float | int = float("inf"),
        item_func: RECORDER_FUNC | None = None,
    ) -> None:
        """A monitoring version of the SimPy FilterStore.

        Since Stores contain a list of objects, recording the mutable list is replaced
        by recording the length of the list by default. Otherwise, input the item_func
        to take the store items and return a recordable value.

        Args:
            env (Environment): SimpyEnvironment.
            capacity (float | int, optional): Capacity of the store. Defaults to float("inf").
            item_func (RECORDER_FUNC | None, optional): Function to create recorded values.
                Defaults to None.
        """
        super().__init__(env, capacity=capacity)
        self.item_func = item_func if item_func is not None else len
        self._quantities = [(self._env.now, self.item_func(self.items))]

    def _record(self, call: str) -> None:
        v = self.item_func(self.items)
        if v != self._quantities[-1][1] or call == "environment":
            self._quantities.append((self._env.now, v))

    def _trigger_put(self, event: Event) -> None:  # type: ignore [override]
        super()._trigger_put(event)
        self._record("put")

    def _trigger_get(self, event: Event) -> None:  # type: ignore [override]
        super()._trigger_get(event)
        self._record("get")

    def _do_put(self, event: StorePut) -> None:
        super()._do_put(event)
        if event.triggered:
            self._record("put")

    def _do_get(self, event: FilterStoreGet) -> None:  # type: ignore[override]
        super()._do_get(event)
        if event.triggered:
            self._record("get")


class SelfMonitoringContainer(Container):
    """A self-monitoring version of the SimPy Container."""

    def __init__(self, env: Environment, capacity: float = float("inf"), init: float = 0.0) -> None:
        """A monitoring version of a SimPy container.

        Args:
            env (Environment): SimPy environment.
            capacity (float, optional): Capacity of the container. Defaults to float("inf").
            init (float, optional): Initial amount. Defaults to 0.0.
        """
        super().__init__(env, capacity=capacity, init=init)
        self._quantities: list[tuple[float, float]] = [(self._env.now, self._level)]

    def _record(self) -> None:
        reading = (self._env.now, self._level)
        if reading != self._quantities[-1]:
            self._quantities.append(reading)

    def _trigger_put(self, event: Event) -> None:  # type: ignore [override]
        super()._trigger_put(event)
        self._record()

    def _trigger_get(self, event: Event) -> None:  # type: ignore [override]
        super()._trigger_get(event)
        self._record()

    def _do_put(self, event: ContainerPut) -> None:
        super()._do_put(event)
        if event.triggered:
            self._record()

    def _do_get(self, event: ContainerGet) -> None:
        super()._do_get(event)
        if event.triggered:
            self._record()


class SelfMonitoringContinuousContainer(ContinuousContainer):
    """A self-monitoring version of the Continuous Container."""

    def __init__(
        self,
        env: Environment,
        capacity: int | float,
        init: int | float = 0.0,
        error_empty: bool = True,
        error_full: bool = True,
    ) -> None:
        """A monitoring version of the Continuous container.

        The container allows continuous gets and puts.

        Args:
            env (Environment): SimPy Environment.
            capacity (int | float): Capacity of the container
            init (int | float, optional): Initial amount. Defaults to 0.0.
            error_empty (bool, optional): Error when it gets empty. Defaults to True.
            error_full (bool, optional): Error when it gets full. Defaults to True.

        """
        super().__init__(env, capacity, init, error_empty, error_full)
        self._quantities = [(self._env.now, self._level)]

    def _set_level(self) -> float:
        """Set the level of the container based on the active gets/puts.

        Returns:
            float: The current level.
        """
        amt = super()._set_level()
        now = self._env.now
        if (now, amt) != self._quantities[-1]:
            self._quantities.append((now, amt))
        return amt


class SelfMonitoringSortedFilterStore(SortedFilterStore, SelfMonitoringStore):
    """A self-monitoring version of the SortedFilterStore."""

    def _do_get(self, event: _SortedFilterStoreGet) -> bool:  # type: ignore [override]
        ans = super()._do_get(event)
        if event.triggered:
            self._record("get")
        return ans


class SelfMonitoringReserveStore(ReserveStore):
    """A self-monitoring version of the ReserveStore."""

    def __init__(self, env: Environment, capacity: float = float("inf"), init: float = 0.0) -> None:
        """Create a store-like object that allows reservations, and records.

        Note that this store doesn't actually yield to SimPy when requesting.

        Use it to determine if anything is avaiable for reservation, but there is no
        queue for getting a reservation.

        Args:
            env (Environment): The SimPy Environment
            init (float, optional): Initial amount available. Defaults to 0.0.
            capacity (float, optional): Total capacity. Defaults to float("inf").
        """
        super().__init__(env, init, capacity)
        self._quantities = [(env.now, init)]

    def _record(self) -> None:
        """Record the level of the store."""
        now = self._env.now
        data = (now, self._real_level)
        if data != self._quantities[-1]:
            self._quantities.append(data)

    def take(self, requester: Any) -> float:
        """Take some amount from the store, by a requester.

        Args:
            requester (Any): The entity requesting the amount

        Returns:
            float: The aount requested.
        """
        amt = super().take(requester)
        self._record()
        return amt

    def put(self, amount: float, capacity_increase: bool = False) -> None:
        """Put some amount into the store.

        Args:
            amount (float): The amount to put
            capacity_increase (bool, optional): Allow capacity to increase. Defaults to False.
        """
        super().put(amount, capacity_increase)
        self._record()
