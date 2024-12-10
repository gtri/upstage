# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import simpy as SIM
from simpy import Environment, Process

from upstage_des.actor import Actor
from upstage_des.base import EnvironmentContext, MockEnvironment
from upstage_des.constants import PLANNING_FACTOR_OBJECT
from upstage_des.events import Any, Get, Put, ResourceHold, Wait
from upstage_des.states import LinearChangingState, State
from upstage_des.task import Task
from upstage_des.type_help import SIMPY_GEN, TASK_GEN


class ActorForTest(Actor):
    dummy = State[list]()


class StateActor(Actor):
    fuel = LinearChangingState(recording=True)
    fuel_burn = State[float](recording=True)


class Flight:
    def __init__(self, code: int) -> None:
        self.code = code
        self.dummy: list = []


class AirplaneTask(Task):
    limit: float
    rate: float
    store: SIM.Store
    orders_time: float
    reason: list

    def task(self, *, actor: StateActor) -> TASK_GEN:
        # this task could be thought of as loitering, waiting for a get
        # request, interrupt, or prescribed failure
        time_to_leave = (actor.fuel - self.limit) / self.rate

        leave_event = Wait(time_to_leave)
        orders_event = Get(self.store, rehearsal_time_to_complete=self.orders_time)

        actor.activate_linear_state(state="fuel", task=self, rate=-self.rate)
        any_event = Any(leave_event, orders_event)
        yield any_event
        actor.deactivate_state(state="fuel", task=self)

        if orders_event.is_complete():
            self.reason.append(orders_event.get_value())
        else:
            orders_event.cancel()
        if leave_event.is_complete():
            self.reason.append("LEAVE")


class BigTask(Task):
    time: float
    maintenance_bay: SIM.Resource
    broken_vehicle_depot: SIM.Store
    fixed_vehicle_depot: SIM.Store

    def task(
        self,
        *,
        actor: Flight,
    ) -> TASK_GEN:
        # a function to mimic extra code needed to perform a task
        # TODO: This should be wrapped to handle the planning answer
        def test_flight(flight: Flight, planning_answer: float = 3.0) -> float:
            if flight is PLANNING_FACTOR_OBJECT:
                return planning_answer
            return flight.code * 1.5

        yield Wait(self.time)
        actor.dummy.append(self.time)

        # wait for a resource, then do stuff, then give it back
        # get a bay for the actor to do work in
        resource_event = ResourceHold(self.maintenance_bay)
        yield resource_event

        # get a vehicle to fix
        vehicle_to_fix = yield Get(self.broken_vehicle_depot)

        # fix it
        time_to_fix = test_flight(vehicle_to_fix, planning_answer=6.0)
        yield Wait(time_to_fix)
        actor.dummy.append(time_to_fix)

        # put it in fixed
        yield Put(self.fixed_vehicle_depot, vehicle_to_fix)

        # leave the job site
        yield resource_event


def interrupting_task(*, env: Environment, time: float, other_task: Process) -> SIMPY_GEN:
    yield env.timeout(time)
    if other_task.is_alive:
        other_task.interrupt("cancelling")


def test_event_store_returns() -> None:
    with EnvironmentContext() as env:
        store = SIM.Store(env, capacity=1)
        put_object = ("A Test Object", 1.0)
        store.put(put_object)
        env.run()

        class DoARun(Task):
            def task(self, *, actor: ActorForTest) -> TASK_GEN:
                return_value = yield Get(store)
                actor.dummy.append(return_value)

        actor = ActorForTest(name="testing", dummy=[])
        actor_2 = DoARun().rehearse(
            actor=actor,
        )

        assert actor_2.dummy[0] is PLANNING_FACTOR_OBJECT

        _ = DoARun().run(
            actor=actor,
        )
        env.run()
        assert actor.dummy[0] is put_object, "Object returned is not the correct object"


def test_task_with_all_events() -> None:
    with EnvironmentContext() as env:
        store = SIM.Store(env, capacity=2)
        store2 = SIM.Store(env, capacity=2)
        resource = SIM.Resource(env)

        f = Flight(2)
        f2 = Flight(3)
        store.put(f)
        store.put(f2)
        env.run()

        actor = ActorForTest(name="maintenance person", dummy=[])

        # test the task
        bt = BigTask()
        bt.time = 2.0
        bt.broken_vehicle_depot = store
        bt.maintenance_bay = resource
        bt.fixed_vehicle_depot = store2
        test_actor = bt.rehearse(
            actor=actor,
        )

        # check that the returned test actor has the expected entries in its state
        assert test_actor.dummy[0] == 2.0, "Wrong result in test actor"
        assert test_actor.dummy[1] == 6.0, "Wrong result in test actor for fake store object"
        assert f in store.items, "Item was removed when it shouldn't have been"
        assert f2 in store.items, "Item was removed when it shouldn't have been"
        # run the process for real
        bt = BigTask()
        bt.time = 2.0
        bt.broken_vehicle_depot = store
        bt.maintenance_bay = resource
        bt.fixed_vehicle_depot = store2
        _ = bt.run(
            actor=actor,
        )

        env.run()
        assert actor.dummy[0] == 2.0, "Wrong result in test actor"
        assert actor.dummy[1] == f.code * 1.5, "Wrong result in test actor for fake store object"
        assert f not in store.items, "Item wasn't removed when it should have been"
        assert f2 in store.items, "Item was removed when it shouldn't have been"
        assert f in store2.items, "Item wasn't moved to the next store"


def test_task_with_get() -> None:
    with EnvironmentContext() as env:
        orders = SIM.Store(env)
        actor = StateActor(name="Airplane", fuel=100, fuel_burn=5.2)
        result = []
        order_time = 12.3

        class SimpleTask(Task):
            def task(self, *, actor: StateActor) -> TASK_GEN:
                event = Get(orders, rehearsal_time_to_complete=order_time)
                res = yield event
                result.append(res)
                result.append(self.env.now)
                result.append(event)
                result.append(self.env)

        SimpleTask().rehearse(
            actor=actor,
        )

        assert isinstance(result[3], MockEnvironment), f"Not a mock environment: {result[3]}"
        assert result[0] is PLANNING_FACTOR_OBJECT
        assert result[1] == 12.3
        assert result[2].is_complete, "Tested event believes it completed"


def test_task_rehearsal_with_cancels() -> None:
    with EnvironmentContext() as env:
        orders = SIM.Store(env)
        actor = StateActor(name="Airplane", fuel=100, fuel_burn=5.2)

        at = AirplaneTask()
        at.rate = 1.2
        at.limit = 5
        at.store = orders
        at.orders_time = 0.0
        at.reason = []

        tested_actor = at.rehearse(actor=actor)

        assert at.reason[0] == PLANNING_FACTOR_OBJECT
        assert len(at.reason) == 1, "Wrong number of values returned"
        assert tested_actor.fuel == 100

        at = AirplaneTask()
        at.rate = 1.2
        at.limit = 5
        at.store = orders
        at.orders_time = 90.0
        at.reason = []
        tested_actor = at.rehearse(
            actor=actor,
        )

        assert at.reason[0] == "LEAVE"
        assert len(at.reason) == 1, "Wrong number of values returned"
        assert tested_actor.fuel == 5


def test_task_with_cancels() -> None:
    with EnvironmentContext() as env:
        orders = SIM.Store(env)
        actor = StateActor(name="Airplane", fuel=100, fuel_burn=5.2)
        reason: list[str] = []

        at = AirplaneTask()
        at.rate = 1.2
        at.limit = 5
        at.store = orders
        at.orders_time = 0.0
        at.reason = reason

        at.run(
            actor=actor,
        )

        # run the task
        env.run()
        assert reason[0] == "LEAVE", "Wrong leave reason"
        assert env.now == (100 - 5) / 1.2, "Wrong environment time"
        assert actor.fuel == 5, "Wrong fuel"

        # test the task when orders are given
        def give_orders(env: SIM.Environment, time: float, orders: SIM.Store) -> SIMPY_GEN:
            yield env.timeout(time)
            yield orders.put("STOP WHAT YOU ARE DOING")

        ##############
    with EnvironmentContext() as env:
        orders = SIM.Store(env)
        actor = StateActor(name="Airplane", fuel=100, fuel_burn=5.2)

        at = AirplaneTask()
        at.rate = 1.2
        at.limit = 5
        at.store = orders
        at.orders_time = 0.0
        at.reason = []

        at.run(
            actor=actor,
        )
        _ = env.process(give_orders(env, 23.0, orders))
        env.run()
        assert at.reason[0] == "STOP WHAT YOU ARE DOING"

        ##############
        # test the task when orders are given, but it's interrupted beforehand
    with EnvironmentContext() as env:
        orders = SIM.Store(env)
        actor = StateActor(name="Airplane", fuel=100, fuel_burn=5.2)

        at = AirplaneTask()
        at.rate = 1.2
        at.limit = 5
        at.store = orders
        at.orders_time = 0.0
        at.reason = []

        task_proc = at.run(
            actor=actor,
        )

        _ = env.process(give_orders(env, 23.0, orders))
        _ = env.process(interrupting_task(env=env, time=16.5, other_task=task_proc))
        env.run(until=60)

        # no reason should be given
        assert not at.reason
        expected_fuel = 100 - (16.5 * 1.2)
        assert actor.fuel == expected_fuel
        assert len(env._queue) == 1, "End environment queue is too long"
        assert env._queue[0][3].callbacks == [], "Timeout had callbacks that should be cleared"
