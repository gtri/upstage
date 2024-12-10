# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import upstage_des.api as UP


class Example(UP.Actor):
    a_value = UP.State[float](default=1.0)


class Example2(Example):
    b_value = UP.State[float](default=2.0)


class EnvHolder(UP.UpstageBase): ...


def test_actor_tracking() -> None:
    with UP.EnvironmentContext():
        env = EnvHolder()
        actor = Example(name="Example_1")

        actor2 = Example2(
            name="Example_2",
            b_value=3.0,
        )

        actors = env.get_actors()
        assert len(actors) == 2, "Wrong number of actors stored"
        assert actor in actors
        assert actor2 in actors

        actor_entities = env.get_entity_group("Example")
        assert actor in actor_entities
        assert len(actor_entities) == 2

        actor_entities = env.get_entity_group("Example2")
        assert actor2 in actor_entities
        assert len(actor_entities) == 1


def test_env_reset() -> None:
    with UP.EnvironmentContext():
        env = EnvHolder()
        actor = Example(name="Example_1")

        actors = env.get_actors()
        assert len(actors) == 1, "Wrong number of actors stored"
        assert actor in actors

    with UP.EnvironmentContext():
        env = EnvHolder()
        actors = env.get_actors()
        assert actor not in actors

        actors = env.get_actors()
        assert actor not in actors


def test_actor_multi_tracking() -> None:
    class Person(UP.Actor, entity_groups=("A Person", "VIP")):
        pass

    with UP.EnvironmentContext():
        env = EnvHolder()
        p = Person(name="some person")
        people = env.get_entity_group("A Person")
        assert len(people) == 1
        vips = env.get_entity_group("VIP")
        assert len(vips) == 1
        actors = env.get_actors()
        assert len(actors) == 1
        assert p in actors
        assert len(env.get_all_entity_groups()) == 3

        class Doctor(UP.Actor, entity_groups=("Hospital Worker")):
            pass

        d = Doctor(name="Doc Oc")
        assert len(env.get_all_entity_groups()) == 5
        assert d not in env.get_entity_group("Person")


class Sensor(UP.NamedUpstageEntity):
    def __init__(self, name: str, radius: float) -> None:
        self.name = name
        self.radius = radius


class RadarSensor(Sensor, entity_groups="RADAR"):
    pass


class LightSensor(Sensor):
    pass


class NextRadar(RadarSensor):
    pass


def test_entity_tracking() -> None:
    with UP.EnvironmentContext():
        env = EnvHolder()
        simple_sensor = Sensor(name="Sense1", radius=3)
        radar_sensor = RadarSensor(name="A Radar", radius=10)
        light_sensor = LightSensor(name="A Light", radius=4.5)

        sensors = env.get_entity_group("Sensor")
        radars = env.get_entity_group("RADAR")
        other_radars = env.get_entity_group("RadarSensor")
        lights = env.get_entity_group("LightSensor")

        assert len(sensors) == 3
        assert simple_sensor in sensors
        assert len(radars) == 1
        assert radar_sensor in radars
        assert len(lights) == 1
        assert light_sensor in lights
        assert len(other_radars) == 1

        assert len(env.get_all_entity_groups()) == 4

        # Check that we do inherit subclass and the defined ones.
        nxt = NextRadar(name="More testing", radius=6.45)
        assert nxt in env.get_entity_group("RADAR")
        assert nxt in env.get_entity_group("Sensor")
        assert nxt in env.get_entity_group("RadarSensor")


def test_multi_tracking() -> None:
    with UP.EnvironmentContext():
        env = EnvHolder()

        class LightSensor(RadarSensor, entity_groups=("MySensor", "Light")):
            pass

        LightSensor(name="A Light", radius=4.5)
        lights = env.get_entity_group("Light")
        sensors = env.get_entity_group("MySensor")
        assert len(lights) == 1
        assert len(sensors) == 1


def test_env_reset_tracking() -> None:
    with UP.EnvironmentContext():
        env = EnvHolder()
        simple_sensor = Sensor(name="Sense1", radius=3)
        sensors = env.get_entity_group("Sensor")
        assert len(sensors) == 1
        assert simple_sensor in sensors

    with UP.EnvironmentContext():
        env = EnvHolder()
        sensors = env.get_entity_group("Sensor")
        assert simple_sensor not in sensors

        sensors = env.get_entity_group("Sensor")
        assert simple_sensor not in sensors
        assert len(env.get_all_entity_groups()) == 0
