# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test the upstage events."""

import pytest
import simpy as SIM
from simpy.resources import base
from simpy.resources.container import ContainerGet, ContainerPut
from simpy.resources.store import StoreGet, StorePut

from upstage_des.api import (
    EnvironmentContext,
    SimulationError,
)
from upstage_des.events import (
    AllOf,
    AnyOf,
    Event,
    Timeout,
    _cancel_event,
    get_event_value,
    is_event_complete,
    make_timeout,
    make_timeout_until,
    make_random_timeout,
)
from upstage_des.base import SIMPY_GEN, Stage


def test_base_event() -> None:
    init_time = 1.23
    with EnvironmentContext(initial_time=init_time) as env:
        base = Event()
        assert base._created_at == init_time, "Problem in environment time being stored in event"
        assert base.env is env, "Problem in environment being stored in event"


def test_timeout_event() -> None:
    init_time = 1.23
    with EnvironmentContext(initial_time=init_time) as env:
        timeout = 1

        wait = Timeout(delay=timeout)
        assert wait._created_at == init_time, "Problem in environment time being stored in event"
        assert wait.env is env, "Problem in environment being stored in event"

    stage = Stage(time_unit="minutes")
    with EnvironmentContext(stage=stage) as env:
        wait = Timeout(delay=1.1, time_units="hours")
        assert wait._delay == pytest.approx(66)

    with EnvironmentContext(initial_time=init_time) as env:
        timeout_2 = [1, 3]
        wait2 = make_random_timeout(timeout_2[0], timeout_2[1])
        assert isinstance(wait2, SIM.Timeout), "Wait doesn't return a simpy timeout"
        assert timeout_2[0] <= wait2._delay <= timeout_2[1], "Incorrect timeout time"


def test_wait_until_event() -> None:
    init_time = 1.23
    with EnvironmentContext(initial_time=init_time) as env:
        timeout = 1
        until = init_time+timeout
        wait = make_timeout_until(until_time=until)
        assert wait._created_at == init_time, "Problem in environment time being stored in event"
        assert wait.env is env, "Problem in environment being stored in event"
        assert wait._delay == timeout

    stage = Stage(time_unit="minutes")
    with EnvironmentContext(stage=stage) as env:
        wait = make_timeout_until(until_time=1.1, time_units="hours")
        assert wait._delay == pytest.approx(66)


def test_put_event_with_stores() -> None:
    with EnvironmentContext() as env:
        store = SIM.Store(env, capacity=1)
        put_object = ("A Test Object", 1.0)
        put_event = store.put(put_object)

        env.run()
        assert put_event.item is put_object, "Wrong object put"
        assert put_object in store.items

        put_object = ("A Second Test Object", 2.0)
        put_event = store.put(put_object)
        env.run()
        assert not put_event.triggered, "Event shouldn't have completed"
        assert put_event in store.put_queue, "Event is not waiting"
        _cancel_event(put_event)
        env.run()
        assert not put_event.triggered, "Event shouldn't have completed"
        assert put_event not in store.put_queue, "Event is still in the store's queue"


def test_put_event_with_containers() -> None:
    with EnvironmentContext() as env:
        container = SIM.Container(env, capacity=1)
        put_arg = 1.0
        put_event = container.put(put_arg)

        env.run()
        assert container.level == put_arg

        put_arg = 2
        put_event = container.put(put_arg)
        env.run()
        assert not put_event.triggered, "Event shouldn't have completed"
        assert put_event in container.put_queue, "Event is not waiting"
        put_event.cancel()
        env.run()
        assert not put_event.triggered, "Event shouldn't have completed"
        assert put_event not in container.put_queue, "Event is still in the store's queue"


def test_get_event_with_stores() -> None:
    with EnvironmentContext() as env:
        store = SIM.Store(env, capacity=1)
        put_object = ("A Test Object", 1.0)
        store.put(put_object)
        env.run()

        event = store.get()

        env.run()
        item = event.value
        assert item is put_object, "Returned item is not the original item"

        event = store.get()
        env.run()
        assert event in store.get_queue, "Event not in queue"
        _cancel_event(event)
        assert event not in store.get_queue, "Event is still in queue"


def test_get_event_with_containers() -> None:
    with EnvironmentContext() as env:
        container = SIM.Container(env, capacity=1)
        put_arg = 1.0
        container.put(put_arg)
        env.run()

        get_arg = 1.0
        event = container.get(get_arg)

        env.run()
        amount = event.amount
        assert amount == get_arg, "Returned item is not the original item"

        with pytest.raises(SimulationError):
            get_event_value(event)

        # Now get on the container that is empty.
        event = container.get(get_arg)
        env.run()
        assert container.level == 0
        _cancel_event(event)
        assert event not in container.get_queue, "Event is still in queue"
        env.run()
        assert container.level == 0

test_get_event_with_containers()

def test_and_event() -> None:
    with EnvironmentContext() as env:

        def run(env: SIM.Environment, data: dict[str, float]) -> SIMPY_GEN:
            event1 = Timeout(1.0)
            event2 = Timeout(1.5)

            event = AllOf([event1, event2])
            yield event
            data["time"] = env.now

        data: dict[str, float] = {}
        env.process(run(env, data))
        env.run()
        assert data["time"] == 1.5


def test_or_event() -> None:
    with EnvironmentContext() as env:
        data = {
            "time": 0.0,
        }

        def run(env: SIM.Environment) -> SIMPY_GEN:
            event1 = Timeout(1.0)
            event2 = Timeout(1.5)

            event = AnyOf([event1, event2])
            yield event
            data["time"] = env.now

        env.process(run(env))
        env.run()
        # SimPy still runs the simulation long enough to finish the timeout
        assert data["time"] == 1.0


def test_composite() -> None:
    with EnvironmentContext() as env:
        data = {
            "time": 0.0,
            "result": 0,
        }

        def run(env: SIM.Environment) -> SIMPY_GEN:
            event1 = Timeout(1.0)
            event2 = Timeout(1.5)

            event3 = Timeout(2.1)
            event4 = Timeout(0.9)

            event_a = AnyOf([event1, event2])
            event_b = AllOf([event3, event4, event_a])
            result = yield event_b
            data["time"] = env.now
            data["result"] = len(result.events)

        env.process(run(env))
        env.run()
        assert data["time"] == 2.1
        assert data["result"] == 4


def run_one(env: SIM.Environment, event: Event) -> SIMPY_GEN:
    yield env.timeout(1.0)
    event.succeed(value="here")


def run_two(env: SIM.Environment, event: Event, data: dict[str, float]) -> SIMPY_GEN:
    yield event
    data["time_two"] = env.now


def run_three(env: SIM.Environment, event: Event, data: dict[str, float]) -> SIMPY_GEN:
    yield event
    data["time_three"] = env.now


def run_four(env: SIM.Environment, event: Event, data: dict[str, float]) -> SIMPY_GEN:
    # Timeout until after the event suceeded, but before its reset
    yield env.timeout(1.05)
    yield event
    data["time_four"] = env.now


def test_basic_usage() -> None:
    with EnvironmentContext() as env:
        event = Event()
        assert is_event_complete(event) is False

        env.process(run_one(env, event))
        data: dict[str, float] = {}
        env.process(run_two(env, event, data))
        env.run()
        assert data["time_two"] == 1.0
        assert is_event_complete(event)
        payload = event.value
        assert payload == "here"
        assert get_event_value(event) == "here"

        with pytest.raises(RuntimeError, match="has already been triggered"):
            event.succeed()


def test_conflicts() -> None:
    data: dict[str, float] = {}
    with EnvironmentContext() as env:
        event = Event()
        env.process(run_one(env, event))
        env.process(run_two(env, event, data))
        env.process(run_three(env, event, data))
        env.run()
        assert data["time_two"] == data["time_three"]

    data: dict[str, float] = {}
    with EnvironmentContext() as env:
        event = Event()
        env.process(run_one(env, event))
        env.process(run_two(env, event, data))
        env.process(run_three(env, event, data))
        env.process(run_four(env, event, data))
        env.run()
        assert data["time_two"] == data["time_three"]
        assert data["time_four"] == 1.05


def test_resubmit_get_put_events() -> None:
    # Make sure that get/put events don't hang.
    with EnvironmentContext() as env:
        store1 = SIM.Store(env)
        store2 = SIM.Store(env)

        def _put_stuff() -> SIMPY_GEN:
            yield Timeout(1.0)
            yield store1.put("thing")
            yield Timeout(1.0)
            yield store2.put("other")

        def _get_stuff() -> SIMPY_GEN:
            g1 = store1.get()
            g2 = store2.get()
            yield g1 | g2
            assert is_event_complete(g1)
            assert g1.value == "thing"
            assert env.now == 1.0
            yield g2
            assert env.now == 2.0
            assert is_event_complete(g2)
            assert g2.value == "other"

        env.process(_put_stuff())
        env.process(_get_stuff())
        env.run()

    # run the same through UPSTAGE
    with EnvironmentContext() as env:
        store1 = SIM.Store(env)
        store2 = SIM.Store(env)

        def _put_stuff() -> SIMPY_GEN:
            yield Timeout(1.0)
            yield store1.put("thing")
            yield Timeout(1.0)
            yield store2.put("other")

        def _get_stuff() -> SIMPY_GEN:
            g1 = store1.get()
            g2 = store2.get()
            yield AnyOf([g1, g2])
            assert is_event_complete(g1)
            assert g1.value == "thing"
            assert env.now == 1.0
            yield g2
            assert env.now == 2.0
            assert is_event_complete(g2)
            assert g2.value == "other"

        env.process(_put_stuff())
        env.process(_get_stuff())
        env.run()


def test_filter_store_events() -> None:
    with EnvironmentContext() as env:
        store1 = SIM.FilterStore(env)

        def _put_stuff() -> SIMPY_GEN:
            yield Timeout(1.0)
            yield store1.put("thing")
            yield Timeout(1.0)
            yield store1.put("other")

        def _get_stuff() -> SIMPY_GEN:
            g1 = store1.get(filter=lambda item: "oth" in item)
            yield g1
            assert g1.value == "other"
            assert "thing" in store1.items

        env.process(_put_stuff())
        env.process(_get_stuff())
        env.run()
