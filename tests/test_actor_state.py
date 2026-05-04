# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test state features."""

import pytest

from upstage_des.actor import Actor
from upstage_des.base import EnvironmentContext
from upstage_des.states import State


def test_basic_state_creation() -> None:
    class MyActor(Actor):
        fuel: float

    with EnvironmentContext():
        actor = MyActor(name="test", fuel=100.0)
        assert actor.fuel == 100.0


def test_state_with_default() -> None:
    class MyActor(Actor):
        fuel: float = 50.0

    with EnvironmentContext():
        actor = MyActor(name="test")
        assert actor.fuel == 50.0


def test_state_modification() -> None:
    class MyActor(Actor):
        fuel: float

    with EnvironmentContext():
        actor = MyActor(name="test", fuel=100.0)
        actor.fuel = 75.0
        assert actor.fuel == 75.0


def test_name_field() -> None:
    class MyActor(Actor):
        fuel: float

    with EnvironmentContext():
        actor = MyActor(name="car", fuel=100.0)
        assert actor.name == "car"
        assert actor.fuel == 100.0


def test_name_field_inherited() -> None:
    class MyActor(Actor):
        fuel: float

    with EnvironmentContext():
        actor = MyActor(name="default_name", fuel=100.0)
        assert actor.name == "default_name"


def test_inheritance_basic() -> None:
    class Vehicle(Actor):
        fuel: float

    class Car(Vehicle):
        passengers: int

    with EnvironmentContext():
        car = Car(name="sedan", fuel=100.0, passengers=4)
        assert car.name == "sedan"
        assert car.fuel == 100.0
        assert car.passengers == 4


def test_state_validator() -> None:
    def validate_positive(obj: object, value: float) -> None:
        if value < 0:
            raise ValueError("Must be positive")

    class MyActor(Actor):
        fuel: float = State(default=100.0, validator=validate_positive)

    with EnvironmentContext():
        actor = MyActor(name="test")
        actor.fuel = 50.0

        with pytest.raises(ValueError, match="Must be positive"):
            actor.fuel = -10.0


def test_state_default_factory() -> None:
    class MyActor(Actor):
        items: list[int] = State(default_factory=list)

    with EnvironmentContext():
        actor1 = MyActor(name="test1")
        actor2 = MyActor(name="test2")

        actor1.items.append(1)
        assert len(actor1.items) == 1
        assert len(actor2.items) == 0


def test_mixed_fields() -> None:
    class MyActor(Actor):
        fuel: float
        position: tuple[float, float] = (0.0, 0.0)

    with EnvironmentContext():
        actor = MyActor(name="vehicle", fuel=100.0)
        assert actor.name == "vehicle"
        assert actor.fuel == 100.0
        assert actor.position == (0.0, 0.0)


def test_multiple_instances_independent() -> None:
    class MyActor(Actor):
        fuel: float | int = 100.0

    with EnvironmentContext():
        actor1 = MyActor(name="test1")
        actor2 = MyActor(name="test2", fuel=50.0)

        assert actor1.fuel == 100.0
        assert actor2.fuel == 50.0

        actor1.fuel = 75.0
        assert actor1.fuel == 75.0
        assert actor2.fuel == 50.0


def test_bad_type() -> None:
    class MyActor(Actor):
        fuel: float
        position: tuple[float, float] = (0.0, 0.0)

    with EnvironmentContext():
        with pytest.raises(TypeError, match="doesn't match type"):
            MyActor(name="vehicle", fuel=100)


def test_recording() -> None:
    class MyActor(Actor):
        fuel: float | int = 100.0

    with EnvironmentContext() as env:
        actor1 = MyActor(name="test1")
        assert actor1._state_histories["fuel"][0] == (0.0, 100.0)
        assert len(actor1._state_histories) == 1
        actor1.fuel = 200
        assert actor1._state_histories["fuel"][1] == (0.0, 200.0)
        assert len(actor1._state_histories["fuel"]) == 2
        env.run(until=2)
        actor1.fuel = 231.2
        assert actor1._state_histories["fuel"][2] == (2.0, 231.2)


def test_post_init() -> None:
    var = []
    class MyActor(Actor):
        def __post_init__(self) -> None:
            var.append(self.name)

    class Next(MyActor):
        def __post_init__(self) -> None:
            super().__post_init__()
            print('ok')

    with EnvironmentContext():
        MyActor(name="test")
        assert len(var) == 1
        Next(name="test2")
        assert var == ["test", "test2"]
