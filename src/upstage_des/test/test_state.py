# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from typing import Any, cast

import pytest
from simpy import Container, Environment, Store

import upstage_des.api as UP
import upstage_des.resources.monitoring as monitor
from upstage_des.actor import Actor
from upstage_des.api import EnvironmentContext, SimulationError, UpstageError
from upstage_des.states import LinearChangingState, ResourceState, State
from upstage_des.task import TASK_GEN
from upstage_des.type_help import SIMPY_GEN


class StateTest:
    state_one = State[Any]()
    state_two = State[Any](recording=True)

    def __init__(self, env: Environment | None) -> None:
        cast(UP.Actor, self)
        self.env = env
        # including for compatibility
        self._mimic_states: dict[str, Any] = {}
        self._state_listener = None
        self._state_histories: dict[str, list[tuple[float, Any]]] = {}

    def set_one(self, val: Any) -> None:
        self.state_one = val  # type: ignore [arg-type]

    def set_two(self, val: Any) -> None:
        self.state_two = val  # type: ignore [arg-type]


class StateTestActor(Actor):
    state_one = State[Any]()
    state_two = State[Any](recording=True)
    state_three = LinearChangingState(recording=True)


class MutableDefaultActor(Actor):
    lister = State[list](default_factory=list)
    diction = State[dict](default_factory=dict)
    setstate = State[set](default_factory=set)


def test_state_fails_without_env() -> None:
    """Test that recording states need the class to have an env attribute"""
    tester = StateTest(None)
    # the first one should not raise an error
    tester.set_one(1)

    with pytest.raises(SimulationError):
        tester.set_two(1)


def test_state_values() -> None:
    """Test that we get the right state values we input"""
    with EnvironmentContext(initial_time=1.5) as env:
        tester = StateTest(env)
        tester.state_one = 1  # type: ignore [arg-type]
        assert tester.state_one == 1  # type: ignore [arg-type]
        tester.state_two = 2  # type: ignore [arg-type]
        assert tester.state_two == 2  # type: ignore [arg-type]


def test_state_recording() -> None:
    with EnvironmentContext(initial_time=1.5) as env:
        tester = StateTest(env)
        tester.state_two = 2  # type: ignore [arg-type]
        assert "state_two" in tester._state_histories
        env.run(until=2.5)
        tester.state_two = 3  # type: ignore [arg-type]
        assert len(tester._state_histories["state_two"]) == 2
        assert tester._state_histories["state_two"][0] == (1.5, 2)
        assert tester._state_histories["state_two"][1] == (2.5, 3)


def test_state_mutable_default() -> None:
    with EnvironmentContext(initial_time=1.5):
        tester = MutableDefaultActor(name="Example")
        tester2 = MutableDefaultActor(name="Example2")
        assert id(tester.lister) != id(tester2.lister)
        tester.lister.append(1)
        assert len(tester2.lister) == 0
        assert len(tester.lister) == 1

        assert id(tester.diction) != id(tester2.diction)
        tester2.diction[1] = 2
        assert len(tester.diction) == 0
        assert len(tester2.diction) == 1

        assert id(tester.setstate) != id(tester2.setstate)
        tester2.setstate.add(1)
        assert len(tester.setstate) == 0
        assert len(tester2.setstate) == 1


def test_state_values_from_init() -> None:
    with EnvironmentContext() as env:
        tester = StateTestActor(
            name="testing",
            state_one=1,
            state_two=2,
            state_three=4,
        )
        env.run(until=1.5)
        assert tester.state_one == 1
        assert tester.state_two == 2
        assert tester.state_three == 4
        tester.state_three = 3
        assert "state_three" in tester._state_histories
        assert tester._state_histories["state_three"] == [(0.0, 4), (1.5, 3)]


def test_state_none_allowed() -> None:
    class NoneActor(Actor):
        example = State[int](allow_none_default=True)

    with EnvironmentContext():
        ex = NoneActor(name="Example")

        with pytest.raises(SimulationError, match="State example should have been set"):
            ex.example

        ex.example = 3
        assert ex.example == 3


def test_linear_changing_state() -> None:
    state_three_init = 3
    init_time = 1.5
    rate = 3.1
    timestep = 1

    with EnvironmentContext(initial_time=init_time) as env:
        tester = StateTestActor(
            name="testing",
            state_one=1,
            state_two=2,
            state_three=state_three_init,
        )

        task = UP.Task()

        tester.activate_state(state="state_three", task=task, rate=rate)
        assert "state_three" in tester._active_states
        assert tester._active_states["state_three"] == tester.get_active_state_data(
            "state_three", without_update=True
        )
        env.run(until=init_time + timestep)
        # Test getting the value before it's ended
        assert tester.state_three == rate * timestep + state_three_init
        env.run(until=init_time + timestep * 2)
        state_data = tester.get_active_state_data("state_three", without_update=True)
        assert state_data["started_at"] == timestep + init_time
        assert state_data["rate"] == rate
        tester.deactivate_state(state="state_three", task=task)
        assert "state_three" not in tester._active_states
        assert tester.state_three == rate * timestep * 2 + state_three_init


def test_resource_state_valid_types() -> None:
    class Holder(Actor):
        res = ResourceState[Store](valid_types=Store)

    with EnvironmentContext():
        Holder(
            name="example",
            res={"kind": Store},
        )

        with pytest.raises(UpstageError):
            Holder(
                name="example",
                res={"kind": Container},
            )

        with pytest.raises(UpstageError):

            class _(Actor):
                res = ResourceState[Store](valid_types=(1,))  # type: ignore [arg-type]

        with pytest.raises(UpstageError):

            class _(Actor):  # type: ignore [no-redef]
                res = ResourceState[Store](valid_types=(Actor,))


def test_resource_state_set_protection() -> None:
    class Holder(Actor):
        res = ResourceState[Store](valid_types=(Store))

    with EnvironmentContext():
        h = Holder(
            name="example",
            res={"kind": Store},
        )
        with pytest.raises(UpstageError, match=".+It cannot be changed once set.+"):
            h.res = 1.0


def test_resource_state_no_default_init() -> None:
    class Holder(Actor):
        res = ResourceState[Store]()

    with EnvironmentContext():
        with pytest.raises(UpstageError, match="Missing values for states"):
            h = Holder(
                name="example",
            )

        with pytest.raises(UpstageError, match="No resource type"):
            h = Holder(
                name="example",
                res={},
            )

        h = Holder(
            name="example",
            res={"kind": Store},
        )
        assert isinstance(h.res, Store)


def test_resource_state_default_init() -> None:
    class Holder(Actor):
        res = ResourceState[Store](default=Store)
        res2 = ResourceState[Container](
            default=Container, default_kwargs={"capacity": 11, "init": 5}
        )

    class HolderBad(Actor):
        res = ResourceState[Store](default=Store)
        res2 = ResourceState[Container](default=Container, default_kwargs={"capa": 11, "init": 5})

    with EnvironmentContext():
        h = Holder(name="Example")
        assert isinstance(h.res, Store)
        assert h.res2.capacity == 11
        assert h.res2.level == 5

        h = Holder(name="Example", res={"capacity": 10}, res2={"capacity": 12})
        assert isinstance(h.res, Store)
        assert h.res.capacity == 10
        assert h.res2.capacity == 12
        assert h.res2.level == 5

        with pytest.raises(UpstageError):
            HolderBad(name="Bad one")


def test_resource_state_kind_init() -> None:
    class Holder(Actor):
        res = ResourceState[Store]()

    with EnvironmentContext():
        h = Holder(name="Example", res={"kind": Store, "capacity": 10})
        assert isinstance(h.res, Store)
        assert h.res.capacity == 10

        h = Holder(name="Example", res={"kind": Container, "capacity": 100, "init": 50})
        assert isinstance(h.res, Container)
        assert h.res.capacity == 100
        assert h.res.level == 50

        test_resources = [
            x
            for x in monitor.__dict__.values()
            if isinstance(x, type) and issubclass(x, Store | Container)
        ]
        for the_class in test_resources:
            h = Holder(name="Example", res={"kind": the_class, "capacity": 99})
            assert isinstance(h.res, the_class)
            assert h.res.capacity == 99


def test_resource_state_simpy_store_running() -> None:
    class Holder(Actor):
        res = ResourceState[Store]()

    with EnvironmentContext() as env:
        h = Holder(name="Example", res={"kind": Store, "capacity": 10})

        def put_process(entity: Holder) -> SIMPY_GEN:
            for i in range(11):
                yield env.timeout(1.0)
                yield entity.res.put(f"Item {i}")
            return "Done"

        def get_process(entity: Holder) -> SIMPY_GEN:
            res = yield entity.res.get()
            return res

        proc_1 = env.process(put_process(h))
        proc_2 = env.process(get_process(h))
        env.run()
        assert proc_2.value == "Item 0"
        assert proc_1.value == "Done"


def test_resource_clone() -> None:
    class Holder(Actor):
        res = ResourceState[Store](default=Store)

    class Holder2(Actor):
        res = ResourceState[Container](default=Container)

    with EnvironmentContext():
        holder = Holder(name="example")
        holder_2 = holder.clone()
        assert id(holder_2.res.items) != id(holder.res.items)

        holder = Holder2(name="example")
        holder_2 = holder.clone()
        assert id(holder_2.res.level) != id(holder.res.level)


class HelperCallback:
    def __init__(self) -> None:
        self.cbacks: list[tuple[Any, Any]] = []

    def _callbacker(self, instance: Any, value: Any) -> None:
        self.cbacks.append((instance, value))


def test_state_callback() -> None:
    class CbackActor(Actor):
        state_one = State[Any](recording=True)

    helper = HelperCallback()
    with EnvironmentContext():
        actor = CbackActor(
            name="Test",
            state_one=1,
        )

        actor._add_callback_to_state("source", helper._callbacker, "state_one")
        actor.state_one = 2
        assert len(helper.cbacks) == 1
        assert helper.cbacks[0][1] == 2
        actor._remove_callback_from_state("source", "state_one")

        actor.state_one = 3
        assert len(helper.cbacks) == 1


def test_matching_states() -> None:
    """Test the state matching code.
    At this time, state matching only works with CommunicationStore. It's the
    only state with a special attribute attached to it.
    """

    class Worker(UP.Actor):
        sleepiness = UP.State[float](default=0.0, valid_types=(float,))
        walkie = UP.CommunicationStore(mode="UHF")
        intercom = UP.CommunicationStore(mode="loudspeaker")

    with EnvironmentContext():
        worker = Worker(name="Billy")
        store_name = worker._get_matching_state(
            UP.CommunicationStore,
            {"_mode": "loudspeaker"},
        )
        assert store_name is not None
        store = getattr(worker, store_name, "")
        assert store is worker.intercom, "Wrong state retrieved"
        assert store is not worker.walkie, "Wrong state retrieved"

        # Show the FCFS behavior
        state_name = worker._get_matching_state(
            UP.State,
        )
        assert state_name is not None
        value = getattr(worker, state_name)
        assert value == worker.sleepiness, "Wrong state retrieved"

        # Show the FCFS behavior with state type
        state_name = worker._get_matching_state(
            UP.CommunicationStore,
        )
        assert state_name is not None
        value = getattr(worker, state_name)
        assert value is worker.walkie, "Wrong state retrieved"


def test_dictionary_state() -> None:
    """Test multi states."""

    class TheActor(UP.Actor):
        holder = UP.DictionaryState[int | str](valid_types=(int, str), recording=True)

    use = {"item": 0, "other": 4, "new": "A"}

    with UP.EnvironmentContext() as env:
        ta = TheActor(name="example", holder=use)
        ans = {k: v for k, v in ta.holder.items()}
        assert ans == use

        for k, v in use.items():
            assert ta.holder[k] == v

        # Making sure we are not using the original object
        use["newer"] = 4
        assert "newer" not in ta.holder

        ta.holder["newer"] = 5
        env.run(3)
        ta.holder["new"] = 1
        with pytest.raises(
            TypeError,
            match="Bad type for dictionary",
        ):
            ta.holder["item"] = 2.0  # type: ignore [assignment]
        ta.holder["item"] = 42
        res = ta.holder.setdefault("newest", "a value")
        assert res == "a value"
        res = ta.holder.setdefault("item", "xyz")
        # Since the error is skipped, it's still set as 2.0
        assert res == 42

        ks = ["item", "other", "new", "newer", "newest"]
        vs = [42, 4, 1, 5, "a value"]
        assert list(ta.holder.keys()) == ks
        assert list(ta.holder.values()) == vs
        assert list(ta.holder.items()) == [(k, v) for k, v in zip(ks, vs)]

        env.run(5)
        ta.holder["item"] = 10
        ta.holder["other"] = 11

        for key in ta.holder.keys():
            rec_key = f"holder.{key}"
            assert rec_key in ta._state_histories
        assert ta._state_histories["holder.item"] == [(0.0, 0), (3.0, 42), (5.0, 10)]
        assert ta._state_histories["holder.other"] == [(0.0, 4), (5.0, 11)]
        assert ta._state_histories["holder.new"] == [(0.0, "A"), (3.0, 1)]
        assert ta._state_histories["holder.newer"] == [(0.0, 5)]
        assert ta._state_histories["holder.newest"] == [(3.0, "a value")]


def test_dictionary_state_record() -> None:
    def total_recorder(time: float, value: dict[str, int]) -> int:
        return sum(value.values())

    class Usher(UP.Actor):
        people_seen = UP.DictionaryState[int](
            valid_types=int,
            recording=True,
            recording_functions=[(total_recorder, "total_customers")],
        )
        rando = UP.DictionaryState[Any](recording=True)

    class TicketTaking(UP.Task):
        def task(self, *, actor: Usher) -> TASK_GEN:
            for customer in ["adult", "adult", "child", "adult", "child", "vip"]:
                actor.people_seen.setdefault(customer, 0)
                actor.people_seen[customer] += 1
                yield UP.Wait(0.1)

    with UP.EnvironmentContext() as env:
        ush = Usher(name="Yeah", people_seen={"adult": 0, "child": 0}, rando={"stuff": {}})
        task = TicketTaking()
        task.run(actor=ush)
        env.run()
        ush.rando["stuff"]["here"] = 1
        assert env.now == 0.6
        assert "people_seen.adult" in ush._state_histories
        assert "people_seen.child" in ush._state_histories
        assert "people_seen.vip" in ush._state_histories
        assert "total_customers" in ush._state_histories


def test_dataclass_state() -> None:
    ...


def test_extra_recording() -> None:
    """Test that the extra recording works."""

    def recorder(time: float, value: float) -> float:
        return time * value

    def recorder2(time: float, value: float) -> float:
        return time * (value + 1)

    class FailingRecord(UP.Actor):
        a_state = UP.State[float](
            default=0.0,
            recording_functions=[(recorder, "time_mult")],
        )
        b_state = UP.State[float](
            default=0.0,
            recording_functions=[(recorder, "time_mult")],
        )

    class FailingRecord2(UP.Actor):
        a_state = UP.State[float](
            default=0.0,
            recording_functions=[(recorder, "time_mult")],
        )
        b_state = UP.State[float](
            default=0.0,
            recording_functions=[(recorder, "a_state")],
        )

    class RecordingStates(UP.Actor):
        a_state = UP.State[float](
            default=0.0,
            recording=True,
            recording_functions=[(recorder, "a_mult")],
        )
        b_state = UP.State[float](
            default=0.0,
            recording=True,
            recording_functions=[
                (recorder, "b_mult"),
                (recorder2, "b_mult2"),
            ],
        )

    with UP.EnvironmentContext() as env:
        with pytest.raises(SimulationError, match="Duplicated state or recording name"):
            FailingRecord(name="example")

        with pytest.raises(SimulationError, match="Duplicated state or recording name"):
            FailingRecord2(name="example")

        rs = RecordingStates(name="example")
        env.run(until=1)
        rs.a_state = 3
        rs.b_state = 4
        env.run(until=3)
        rs.a_state += 1
        rs.b_state += 1
        assert "a_state" in rs._state_histories
        assert "a_mult" in rs._state_histories
        assert "b_mult" in rs._state_histories
        assert "b_mult2" in rs._state_histories
        assert "b_state" in rs._state_histories
        assert len(rs._state_histories) == 5

        assert rs._state_histories["a_state"] == [(0.0, 0), (1.0, 3), (3.0, 4)]
        assert rs._state_histories["a_mult"] == [(0.0, 0), (1.0, 3), (3.0, 12)]
        assert rs._state_histories["b_state"] == [(0.0, 0), (1.0, 4), (3.0, 5)]
        assert rs._state_histories["b_mult"] == [(0.0, 0), (1.0, 4), (3.0, 15)]
        assert rs._state_histories["b_mult2"] == [(0.0, 0), (1.0, 5), (3.0, 18)]


def test_extra_recording_docs() -> None:
    """Test the recording example from the docs.

    This also checks the typing and loading from a class.
    """

    from collections import Counter

    class NameStorage:
        def __init__(self) -> None:
            self.seen: dict[str, int] = Counter()
            self.seen[""] = 0

        def __call__(self, time: float, value: str) -> float:
            if value:
                self.seen[value] += 1
            return max(self.seen.values())

    def first_letter(time: float, value: str) -> str:
        if value:
            return value[0]
        return ""

    class Cashier(UP.Actor):
        people_seen = UP.State[str](
            default="",
            recording=True,
            record_duplicates=True,
            recording_functions=[
                (NameStorage, "max_repeats"),
                (first_letter, "first_letter"),
            ],
        )

    with UP.EnvironmentContext():
        cash = Cashier(name="Ertha")
        cash2 = Cashier(name="Bertha")
        cash.people_seen = "James"
        cash.people_seen = "Bob"
        cash.people_seen = "James"
        cash.people_seen = "Fred"
        cash.people_seen = "James"

        assert cash._state_histories["max_repeats"] == [
            (0.0, 0),
            (0.0, 1),
            (0.0, 1),
            (0.0, 2),
            (0.0, 2),
            (0.0, 3),
        ]
        assert cash._state_histories["first_letter"] == [
            (0.0, ""),
            (0.0, "J"),
            (0.0, "B"),
            (0.0, "J"),
            (0.0, "F"),
            (0.0, "J"),
        ]

        assert cash2._state_histories["max_repeats"] == [(0.0, 0)]

    class CashierNonDup(UP.Actor):
        people_seen = UP.State[str](
            default="",
            recording=True,
            record_duplicates=False,
            recording_functions=[
                (NameStorage, "max_repeats"),
                (first_letter, "first_letter"),
            ],
        )

    with UP.EnvironmentContext():
        cash3 = CashierNonDup(name="Ertha")
        cash3.people_seen = "James"
        cash3.people_seen = "Bob"
        cash3.people_seen = "James"
        cash3.people_seen = "Fred"
        cash3.people_seen = "James"

        assert cash3._state_histories["max_repeats"] == [
            (0.0, 0),
            (0.0, 1),
            (0.0, 2),
            (0.0, 3),
        ]
        assert cash3._state_histories["first_letter"] == [
            (0.0, ""),
            (0.0, "J"),
            (0.0, "B"),
            (0.0, "J"),
            (0.0, "F"),
            (0.0, "J"),
        ]


if __name__ == "__main__":
    test_dictionary_state_record()
