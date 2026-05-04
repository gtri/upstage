# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test cloning actors."""

from upstage_des import Actor, EnvironmentContext, get_entities_by_class


def test_actor_clone_basic() -> None:
    class Vehicle(Actor):
        fuel: float = 100.0
        position: int = 0

    with EnvironmentContext():
        vehicle = Vehicle(name="car1", fuel=50.0, position=10)
        
        cloned = vehicle.clone()
        
        assert cloned.name == "car1"
        assert cloned.fuel == 50.0
        assert cloned.position == 10
        assert cloned.is_clone is True
        assert vehicle.is_clone is False


def test_actor_clone_deepcopy() -> None:
    class Robot(Actor):
        inventory: list[str]
        position: tuple[int, int]

    with EnvironmentContext():
        robot = Robot(name="bot1", inventory=["item1", "item2"], position=(5, 10))
        
        cloned = robot.clone()
        
        assert cloned.inventory == ["item1", "item2"]
        assert cloned.inventory is not robot.inventory
        
        cloned.inventory.append("item3")
        assert len(robot.inventory) == 2
        assert len(cloned.inventory) == 3
        robot._clean()
        assert len(cloned.inventory) == 3
        
        assert cloned.position == (5, 10)


def test_actor_clone_no_history() -> None:
    class Ship(Actor):
        speed: float = 0.0

    with EnvironmentContext() as env:
        ship = Ship(name="ship1", speed=10.0)
        
        assert "speed" in ship._state_histories
        assert len(ship._state_histories["speed"]) == 1
        
        ship.speed = 20.0
        assert len(ship._state_histories["speed"]) == 2
        
        cloned = ship.clone()
        
        assert cloned.speed == 20.0
        assert len(cloned._state_histories) == 0


def test_actor_clone_not_in_registry() -> None:
    class Drone(Actor):
        altitude: float = 0.0

    with EnvironmentContext():
        drone = Drone(name="drone1", altitude=100.0)
        
        entities = get_entities_by_class("Drone")
        assert len(entities) == 1
        assert drone in entities
        
        cloned = drone.clone()
        
        entities_after = get_entities_by_class("Drone")
        assert len(entities_after) == 2
        assert drone in entities_after
        assert cloned in entities_after


def test_actor_clone_inheritance() -> None:
    class Vehicle(Actor):
        fuel: float = 100.0

    class Car(Vehicle):
        passengers: int = 0

    with EnvironmentContext():
        car = Car(name="sedan", fuel=75.0, passengers=3)
        
        cloned = car.clone()
        
        assert cloned.name == "sedan"
        assert cloned.fuel == 75.0
        assert cloned.passengers == 3
        assert cloned.is_clone is True
        assert isinstance(cloned, Car)
        assert isinstance(cloned, Vehicle)


def test_actor_clone_modified_after_creation() -> None:
    class Tank(Actor):
        ammo: int = 100
        health: float = 100.0

    with EnvironmentContext() as env:
        tank = Tank(name="tank1", ammo=50, health=75.0)
        
        env.run(env.timeout(5))
        tank.ammo = 25
        tank.health = 50.0
        
        cloned = tank.clone()
        
        assert cloned.ammo == 25
        assert cloned.health == 50.0
        assert cloned.is_clone is True
        
        cloned.ammo = 100
        assert tank.ammo == 25
        assert cloned.ammo == 100


def test_actor_clone_complex_nested_state() -> None:
    class Agent(Actor):
        data: dict[str, list[int]]

    with EnvironmentContext():
        agent = Agent(name="agent1", data={"scores": [1, 2, 3], "levels": [10, 20]})
        
        cloned = agent.clone()
        
        assert cloned.data == {"scores": [1, 2, 3], "levels": [10, 20]}
        assert cloned.data is not agent.data
        
        cloned.data["scores"].append(4)
        assert agent.data["scores"] == [1, 2, 3]
        assert cloned.data["scores"] == [1, 2, 3, 4]
