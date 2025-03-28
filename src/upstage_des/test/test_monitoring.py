# Copyright (C) 2025 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Tests for a bug where bad queue order keeps Monitoring*Stores from working."""

from simpy import Container, Environment, FilterStore, Store

from upstage_des.base import EnvironmentContext
from upstage_des.events import Get, Put
from upstage_des.resources.monitoring import (
    SelfMonitoringContainer,
    SelfMonitoringFilterStore,
    SelfMonitoringSortedFilterStore,
    SelfMonitoringStore,
)
from upstage_des.type_help import SIMPY_GEN


def _container_check(container: Container, env: Environment) -> dict[str, tuple[float, float]]:
    """Run a procedure against a container."""
    data: dict[str, tuple[float, float]] = {}

    def _get_proc() -> SIMPY_GEN:
        yield env.timeout(1.5)
        yield Get(container, 1.0).as_event()
        data["one"] = (env.now, 1.0)

    def _put_one() -> SIMPY_GEN:
        yield env.timeout(1)
        yield Put(container, 1.0).as_event()
        data["put one"] = (env.now, 1.0)

    def _put_two() -> SIMPY_GEN:
        yield env.timeout(1)
        yield Put(container, 0.8).as_event()
        data["put two"] = (env.now, 1.0)

    env.process(_get_proc())
    env.process(_put_one())
    env.process(_put_two())

    env.run()

    return data


def test_monitoring_container_get() -> None:
    # The container outputs "True" if a put is successful (to the trigger),
    # so our original failure to output True should cause a successful
    # follow-on put to not happen.

    with EnvironmentContext() as env:
        smc = Container(env, init=1.1, capacity=2)
        data = _container_check(smc, env)

        assert data.get("one", 0.0) == (1.5, 1.0)
        assert data.get("put one", 0.0) == (1.5, 1.0)
        assert data.get("put two", 0.0) == (1.5, 1.0)

    with EnvironmentContext() as env:
        smc = SelfMonitoringContainer(env, init=1.1, capacity=2)
        data2 = _container_check(smc, env)

        assert data2 == data


def _store_process(
    store: Store, env: Environment, filter: bool = True
) -> dict[str, tuple[float, int] | list[int]]:
    """Run a filtering store process."""
    store.items.append(2)

    data: dict[str, tuple[float, int] | list[int]] = {}

    def _proc_one() -> SIMPY_GEN:
        if filter:
            res = yield Get(store, filter=lambda x: x == 3).as_event()
        else:
            res = yield Get(store).as_event()
        data["one"] = (env.now, res)

    def _proc_two() -> SIMPY_GEN:
        if filter:
            res = yield Get(store, filter=lambda x: x == 4).as_event()
        else:
            res = yield Get(store).as_event()
        data["two"] = (env.now, res)

    # The bug is that if you stack the requests in an order where the
    # first one fails, it's not going to succeed later
    def _proc_three() -> SIMPY_GEN:
        yield env.timeout(2.0)
        yield Put(store, 4).as_event()
        yield env.timeout(0.5)
        yield Put(store, 3).as_event()

    env.process(_proc_one())
    env.process(_proc_two())
    env.process(_proc_three())

    env.run()

    data["final"] = list(store.items)
    return data


def test_monitoring_store_get() -> None:
    # This should not be an issue because simpy Store _do_get|put always
    # returns None
    with EnvironmentContext() as env:
        smst = SelfMonitoringStore(env)
        data = _store_process(smst, env, filter=False)
        assert data.get("one", 0.0) == (0.0, 2)
        assert data.get("two", 0.0) == (2.0, 4)
        assert smst.items == [3]


def test_monitoring_filter_store_get() -> None:
    with EnvironmentContext() as env:
        smfst = FilterStore(env)
        data = _store_process(smfst, env)
        assert data.get("one", 0.0) == (2.5, 3)
        assert data.get("two", 0.0) == (2.0, 4)
        assert data.get("final", [1]) == [2]

    with EnvironmentContext() as env:
        smfst = SelfMonitoringFilterStore(env)
        data2 = _store_process(smfst, env)
        assert data2 == data


def test_monitoring_sorted_filter_store_get() -> None:
    with EnvironmentContext() as env:
        smsfst = SelfMonitoringSortedFilterStore(env)

        data = _store_process(smsfst, env)
        assert data.get("one", 0.0) == (2.5, 3)
        assert data.get("two", 0.0) == (2.0, 4)
        assert data.get("final", [1]) == [2]


if __name__ == "__main__":
    test_monitoring_container_get()
