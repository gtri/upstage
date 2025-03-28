# Copyright (C) 2025 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Tests for a bug where bad queue order keeps Monitoring*Stores from working."""

from upstage_des.base import EnvironmentContext
from upstage_des.events import Get, Put
from upstage_des.resources.monitoring import (
    SelfMonitoringContainer,
    SelfMonitoringFilterStore,
    SelfMonitoringSortedFilterStore,
    SelfMonitoringStore,
)
from upstage_des.type_help import SIMPY_GEN


def test_monitoring_container_get() -> None:
    with EnvironmentContext() as env:
        smc = SelfMonitoringContainer(env, init=5)

        data: dict[str, float] = {}

        def _proc_one() -> SIMPY_GEN:
            yield Get(smc, 10.0).as_event()
            data["one"] = env.now

        def _proc_two() -> SIMPY_GEN:
            yield env.timeout(1.0)
            yield Get(smc, 3.0).as_event()
            data["two"] = env.now

        def _proc_three() -> SIMPY_GEN:
            yield env.timeout(2.0)
            yield Put(smc, 10.0).as_event()

        env.process(_proc_one())
        env.process(_proc_two())
        env.process(_proc_three())

        env.run()

        assert data.get("two", 0.0) == 1.0
        assert data.get("one", 0.0) == 2.0
        assert smc.level == 2


def test_monitoring_store_get() -> None:
    # This should not be an issue because simpy Store _do_get|put always
    # returns None
    with EnvironmentContext() as env:
        smst = SelfMonitoringStore(env)

        smst.items.append(2)

        data: dict[str, tuple[float, int]] = {}

        def _proc_one() -> SIMPY_GEN:
            res = yield Get(smst).as_event()
            data["one"] = (env.now, res)

        def _proc_two() -> SIMPY_GEN:
            yield env.timeout(1.0)
            res = yield Get(smst).as_event()
            data["two"] = (env.now, res)

        def _proc_three() -> SIMPY_GEN:
            yield env.timeout(2.0)
            yield Put(smst, 1).as_event()

        env.process(_proc_one())
        env.process(_proc_two())
        env.process(_proc_three())

        env.run()

        assert data.get("one", 0.0) == (0.0, 2)
        assert data.get("two", 0.0) == (2.0, 1)
        assert smst.items == []


def test_monitoring_filter_store_get() -> None:
    with EnvironmentContext() as env:
        smfst = SelfMonitoringFilterStore(env)

        smfst.items.append(2)

        data: dict[str, tuple[float, int]] = {}

        def _proc_one() -> SIMPY_GEN:
            res = yield Get(smfst, filter=lambda x: x == 3).as_event()
            data["one"] = (env.now, res)

        def _proc_two() -> SIMPY_GEN:
            res = yield Get(smfst, filter=lambda x: x == 4).as_event()
            data["two"] = (env.now, res)

        # The bug is that if you stack the requests in an order where the
        # first one fails, it's not going to succeed later
        def _proc_three() -> SIMPY_GEN:
            yield env.timeout(2.0)
            yield Put(smfst, 4).as_event()
            yield env.timeout(0.5)
            yield Put(smfst, 3).as_event()

        env.process(_proc_one())
        env.process(_proc_two())
        env.process(_proc_three())

        env.run()

        assert data.get("one", 0.0) == (2.5, 3)
        assert data.get("two", 0.0) == (2.0, 4)
        assert smfst.items == [2]


def test_monitoring_sorted_filter_store_get() -> None:
    with EnvironmentContext() as env:
        smsfst = SelfMonitoringSortedFilterStore(env)

        smsfst.items.append(2)

        data: dict[str, tuple[float, int]] = {}

        def _proc_one() -> SIMPY_GEN:
            res = yield Get(smsfst, filter=lambda x: x == 3).as_event()
            data["one"] = (env.now, res)

        def _proc_two() -> SIMPY_GEN:
            res = yield Get(smsfst, filter=lambda x: x == 4).as_event()
            data["two"] = (env.now, res)

        # The bug is that if you stack the requests in an order where the
        # first one fails, it's not going to succeed later
        def _proc_three() -> SIMPY_GEN:
            yield env.timeout(2.0)
            yield Put(smsfst, 4).as_event()
            yield env.timeout(0.5)
            yield Put(smsfst, 3).as_event()

        env.process(_proc_one())
        env.process(_proc_two())
        env.process(_proc_three())

        env.run()

        assert data.get("one", 0.0) == (2.5, 3)
        assert data.get("two", 0.0) == (2.0, 4)
        assert smsfst.items == [2]



if __name__ == "__main__":
    test_monitoring_filter_store_get()
