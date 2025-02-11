# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from inspect import signature
from typing import Any

import pytest

import upstage_des.api as UP
from upstage_des.actor import Actor
from upstage_des.base import EnvironmentContext, SimulationError
from upstage_des.states import State


def test_actor_creation() -> None:
    """Ensure instantation of Actor."""
    with EnvironmentContext():
        name = "testing"
        actor = Actor(name=name)
        assert actor.__class__ == Actor
        assert hasattr(actor, "_state_defs")

    with EnvironmentContext():
        a = Actor(name="Three")
        actors = a.get_actors()
        assert len(actors) == 1
        assert a in actors


def test_actor_subclass(
    base_actors: tuple[tuple[UP.State, ...], tuple[type[UP.Actor], ...]],
) -> None:
    """Test subclasses of actor.

    A subclass of actor must have a proper signature and states in its
    dictionary.

    The names of the states also need to match up.

    Any functions must also be a part of the subclass.

    """
    states, actors = base_actors
    first_state, second_state, third_state, fourth_state = states
    ActorSubclass, DoubleSubclass = actors

    # is the new actor a subclass?
    assert issubclass(ActorSubclass, Actor)

    # does the init signature include the values we want?
    actor_signature = signature(ActorSubclass.__init__)
    expected_params = ["state_one", "state_two", "name"]
    for parameter in expected_params:
        assert parameter in actor_signature.parameters
    assert "kwargs" not in actor_signature.parameters

    # test making an instance without arguments raising an error
    with pytest.raises(Exception):
        ActorSubclass()  # type: ignore [call-arg]

    with EnvironmentContext():
        # create an instance
        instance = ActorSubclass(
            name="Testing",
            state_one=1,
            state_two=2,
        )

        assert instance.a_function(123) == (instance, 123)  # type: ignore [attr-defined]

        # test the state definitions
        assert hasattr(instance, "_state_defs")
        assert len(instance._state_defs) == 2
        assert instance._state_defs["state_one"] is first_state
        assert instance._state_defs["state_two"] is second_state
        assert repr(instance) == "ActorSubclass: Testing"
        sts = instance.state_values
        exp = {"state_one": 1, "state_two": 2}
        assert sts == exp

    # Test that copying a state name will cause a failure.
    with pytest.raises(ValueError):

        class _(DoubleSubclass):  # type: ignore [valid-type, misc]
            state_three = UP.State[float](default=1.2)


def test_multiple_inheritance(
    base_actors: tuple[tuple[UP.State, ...], tuple[type[UP.Actor], ...]],
) -> None:
    """Test actor subclasses but for an additional subclass."""
    states, actors = base_actors
    first_state, second_state, third_state, fourth_state = states
    ActorSubclass, DoubleSubclass = actors

    assert issubclass(DoubleSubclass, Actor)
    assert issubclass(DoubleSubclass, ActorSubclass)

    actor_signature = signature(DoubleSubclass.__init__)
    expected_params = ["state_one", "state_two", "state_three", "name"]
    for parameter in expected_params:
        assert parameter in actor_signature.parameters
    assert "kwargs" not in actor_signature.parameters

    with EnvironmentContext():
        instance = DoubleSubclass(
            name="Testing",
            state_one=1,
            state_two=2,
            state_three=3,
            state_four=4,
        )
        assert instance.b_function(123) == (instance, 123)  # type: ignore [attr-defined]

        # test the state definitions
        assert hasattr(instance, "_state_defs")
        assert len(instance._state_defs) == 4
        assert "state_three" in instance.states
        assert "state_one" in instance.states
        assert instance._state_defs["state_one"] is first_state
        assert instance._state_defs["state_three"] is third_state
        assert instance._state_defs["state_four"] is fourth_state


def test_get_knowledge() -> None:
    class TestActor(Actor):
        pass

    with EnvironmentContext():
        act = TestActor(name="A Test Actor")

        name = "new"
        other_name = "some data"
        value = {"A": 1, "B": 2}
        act.set_knowledge(name, value)

        returned_value = act.get_knowledge(name)
        assert value == returned_value, "Returned value is not the same knowledge"

        other_value = act.get_knowledge(other_name)
        assert other_value is None, "Empty knowledge returned something other than None"


def test_set_knowledge() -> None:
    class TestActor(Actor):
        pass

    with EnvironmentContext():
        act = TestActor(name="A Test Actor")

        name = "new"
        value = {"A": 1, "B": 2}
        value2 = {"A": 5, "B": 6}
        act.set_knowledge(name, value)

        with pytest.raises(SimulationError):
            act.set_knowledge(name, value2)

        act.set_knowledge(name, value2, overwrite=True)
        returned_value = act.get_knowledge(name)
        assert value2 == returned_value, "Returned value is not the same knowldge"


def test_clear_knowledge() -> None:
    class TestActor(Actor):
        pass

    with EnvironmentContext():
        act = TestActor(name="A Test Actor")

        name = "new"
        value = {"A": 1, "B": 2}
        act.set_knowledge(name, value)

        act.get_knowledge(name)

        act.clear_knowledge(name)
        know = act.get_knowledge(name)
        assert know is None, "Knowledge was not cleared"


def test_get_and_clear() -> None:
    class TestActor(Actor):
        pass

    with EnvironmentContext():
        act = TestActor(name="Second test")
        act.set_knowledge("thing", {3: 1})
        v = act.get_and_clear_knowledge("thing")
        assert v == {3: 1}
        assert "thing" not in act._knowledge

        with pytest.raises(UP.SimulationError):
            act.get_and_clear_knowledge("thing")

        t = UP.Task()
        act.set_knowledge("other", {2: 3})
        v = t.get_and_clear_actor_knowledge(act, "other")
        assert v == {2: 3}
        assert "other" not in act._knowledge


def test_bulk_knowledge() -> None:
    class TestActor(Actor):
        pass

    with UP.EnvironmentContext():
        know = {"one": 1, "two": 2}
        act = TestActor(name="Example")
        act.set_bulk_knowledge(know)
        assert know == act._knowledge

        with pytest.raises(UP.SimulationError):
            act.set_bulk_knowledge({"one": 3, "three": 3})

        act.set_bulk_knowledge({"one": 11, "three": 3}, overwrite=True)
        v = act.get_bulk_knowledge(set(["one", "two", "three"]))
        assert v == {"one": 11, "two": 2, "three": 3}

        v = act.get_and_clear_bulk_knowledge(["two", "three"])
        assert v == {"two": 2, "three": 3}
        assert act._knowledge == {"one": 11}

        t = UP.Task()
        t.set_actor_bulk_knowledge(act, know, overwrite=True)
        assert act._knowledge == know
        v = t.get_actor_bulk_knowledge(act, ["one", "two"])
        assert v == know

        with pytest.raises(UP.SimulationError):
            t.set_actor_bulk_knowledge(act, {"one": 3, "three": 3})

        v = t.get_and_clear_actor_bulk_knowledge(act, ["one", "two"])
        assert v == know
        assert act._knowledge == {}


def test_knowledge_event() -> None:
    with EnvironmentContext() as env:
        act = Actor(name="A test actor")
        evt = act.create_knowledge_event(name="Waiter")
        assert act._knowledge.get("Waiter", None) is evt
        assert evt.is_complete() is False
        act.succeed_knowledge_event(name="Waiter")
        env.run()
        assert act._knowledge.get("Waiter", None) is None
        assert evt.is_complete()


def test_actor_copying() -> None:
    class SomeActor(Actor):
        kind = "a simple actor for testing"
        some_state = State[Any]()

    with EnvironmentContext():
        actor = SomeActor(name="some actor", some_state=True)

        clone = actor.clone(new_env=None, some_state=False)

        assert clone.some_state != actor.some_state

        assert actor.name in clone.name

        assert "[CLONE" in clone.name

        assert actor._num_clones == 1

        assert actor.kind == clone.kind


def test_actor_copy_with_knowledge() -> None:
    class SomeActor(Actor):
        kind = "a simple actor for testing"
        some_state = State[Any]()

    with EnvironmentContext():
        actor = SomeActor(name="some actor", some_state=True)
        d_values = {"A": 1, "B": 2}
        float_value = 1234.567

        actor.set_knowledge("new", d_values)
        actor.set_knowledge("other", float_value)

        clone = actor.clone(new_env=None, some_state=False)
        for name in ["new", "other"]:
            v1 = actor.get_knowledge(name)
            v2 = clone.get_knowledge(name)
            assert v1 == v2, "Copied knowledge is different"

        # we can't test for equal IDs or object equivalence because of how
        # Python handles memory for booleans, small integers, etc.

        d_values["A"] = 23
        v1 = actor.get_knowledge("new")
        assert v1["A"] == 23, "Input knowledge did not retain reference"

        v2 = clone.get_knowledge("new")
        assert v2["A"] == 1, "Cloned knowledge retained reference"
