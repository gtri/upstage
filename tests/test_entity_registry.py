# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test the entity registration."""

from upstage_des.actor import Actor
from upstage_des.base import EnvironmentContext, UpstageBase, get_entities_by_class, get_entity_registry


def test_entity_registry_basic() -> None:
    class MyActor(Actor):
        fuel: float

    with EnvironmentContext():
        actor1 = MyActor(name="test1", fuel=100.0)
        actor2 = MyActor(name="test2", fuel=50.0)
        
        registry = get_entity_registry()
        assert "MyActor" in registry
        assert len(registry["MyActor"]) == 2
        assert actor1 in registry["MyActor"]
        assert actor2 in registry["MyActor"]


def test_entity_registry_inheritance() -> None:
    class Vehicle(Actor):
        fuel: float

    class Car(Vehicle):
        passengers: int

    with EnvironmentContext():
        car = Car(name="sedan", fuel=100.0, passengers=4)
        
        registry = get_entity_registry()
        assert "Car" in registry
        assert "Vehicle" in registry
        assert "Actor" in registry
        assert "UpstageBase" in registry
        
        assert car in registry["Car"]
        assert car in registry["Vehicle"]
        assert car in registry["Actor"]
        assert car in registry["UpstageBase"]


def test_get_entities_by_class() -> None:
    class MyActor(Actor):
        fuel: float

    with EnvironmentContext():
        actor1 = MyActor(name="test1", fuel=100.0)
        actor2 = MyActor(name="test2", fuel=50.0)
        
        actors = get_entities_by_class("MyActor")
        assert len(actors) == 2
        assert actor1 in actors
        assert actor2 in actors


def test_entity_registry_property() -> None:
    class MyActor(Actor):
        fuel: float

    with EnvironmentContext():
        actor = MyActor(name="test", fuel=100.0)
        
        registry = actor.entity_registry
        assert "MyActor" in registry
        assert actor in registry["MyActor"]


def test_multiple_classes() -> None:
    class Vehicle(Actor):
        fuel: float

    class Building(UpstageBase):
        pass

    class BigBuilding(Actor, Building):
        pass

    with EnvironmentContext():
        vehicle = Vehicle(name="car", fuel=100.0)
        building = Building()
        big = BigBuilding(name="here")
        
        registry = get_entity_registry()
        assert "Vehicle" in registry
        assert "Building" in registry
        assert "BigBuilding" in registry
        assert vehicle in registry["Vehicle"]
        assert building in registry["Building"]
        assert big in registry["Building"]


def test_empty_registry() -> None:
    with EnvironmentContext():
        registry = get_entity_registry()
        assert isinstance(registry, dict)
        assert len(registry) == 0


def test_no_duplicates() -> None:
    class MyActor(Actor):
        fuel: float

    with EnvironmentContext():
        actor = MyActor(name="test", fuel=100.0)
        
        registry = get_entity_registry()
        assert len(registry["MyActor"]) == 1
        
        actor._register_entity()
        assert len(registry["MyActor"]) == 1
