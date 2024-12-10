# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest
import simpy as SIM

import upstage_des.api as UP
from upstage_des.type_help import SIMPY_GEN

from .flyer import Flyer, flyer_refuel_factory, mission_plan_net
from .mothership import Mothership, crew_factory, give_fuel_factory
from .mover import fly_end_factory


def build_sim() -> tuple[float, Mothership]:
    MEETING_POINT = UP.CartesianLocation(0, 0)
    TRAVERSE_TO_POINT = UP.CartesianLocation(200, 0)
    START_POINT = UP.CartesianLocation(200, 200)

    mothership = Mothership(
        name="Fuel Giver",
        fuel=1000.0,
        fuel_burn=-100.0,
        speed=200.0,
        location=START_POINT,
        fuel_ports_in_use=0,
        fuel_ports_max=4,
    )
    fly_net = fly_end_factory.make_network()
    give_fuel_net = give_fuel_factory.make_network()
    crew_net = crew_factory.make_network()
    for net in [fly_net, give_fuel_net, crew_net]:
        mothership.add_task_network(net)
        # assume that the first entered task name is the one we want
        mothership.start_network_loop(
            net.name,
            list(net.task_classes.keys())[0],
        )

    # give some knowledge
    mothership.set_knowledge(
        "destinations",
        [MEETING_POINT, TRAVERSE_TO_POINT, START_POINT],
    )

    # nucleus
    mothership_nucleus = UP.TaskNetworkNucleus(actor=mothership)
    mothership_nucleus.add_network(
        fly_net,
        [
            "speed",
        ],
    )
    mothership_nucleus.add_network(give_fuel_net, ["fuel_ports_in_use"])

    total_dist = (
        (START_POINT - TRAVERSE_TO_POINT)
        + (TRAVERSE_TO_POINT - MEETING_POINT)
        + (START_POINT - MEETING_POINT)
    )
    return total_dist, mothership


def speed_change(
    env: SIM.Environment,
    vehicle: Mothership,
    new_speed: float,
    time: float,
) -> SIMPY_GEN:
    yield env.timeout(time)
    vehicle.speed = new_speed


def add_draw(
    env: SIM.Environment,
    vehicle: Mothership,
    amount: float,
    time_to: float,
    time_on: float,
) -> SIMPY_GEN:
    class Dummy(UP.Actor):
        messages = UP.ResourceState[SIM.Store](default=SIM.Store)

    d = Dummy(name="a_vehicle")
    yield env.timeout(time_to)
    yield vehicle.messages.put((d, amount))
    yield env.timeout(time_on)
    yield vehicle.messages.put((d, 0))


def test_nothing_added() -> None:
    with UP.EnvironmentContext() as env:
        total_dist, mothership = build_sim()
        t = total_dist / 200
        env.run()
        assert pytest.approx(env.now) == t
        assert pytest.approx(mothership.fuel) == 1000 - 100 * t


def test_fueling() -> None:
    with UP.EnvironmentContext() as env:
        _, mothership = build_sim()

        env.process(speed_change(env, mothership, 150, 1.3))
        env.process(add_draw(env, mothership, -100, 0.5, 1.5))
        env.process(add_draw(env, mothership, -200, 1.0, 2))

        env.run()

        # final time must be larger (~3.4 for no speed change)
        assert pytest.approx(4.1189514164974605) == env.now

        # final fuel level
        assert pytest.approx(63.104858350253835) == mothership.fuel


# Fake mothership
class Dummy(UP.Actor):
    messages = UP.ResourceState[SIM.Store](default=SIM.Store)


def figher_build() -> tuple[Flyer, Dummy]:
    MEETING_POINT = UP.CartesianLocation(0, 0)
    TRAVERSE_TO_POINT = UP.CartesianLocation(200, 0)
    START_POINT = UP.CartesianLocation(-200, -200)

    flyer = Flyer(
        name="Flyer Thing",
        fuel=1000.0,
        fuel_capacity=1500.0,
        fuel_burn=-100.0,
        fuel_draw=500,
        speed=300.0,
        location=START_POINT,
        debug_log=True,
    )

    fly_net = fly_end_factory.make_network()
    get_fuel_net = flyer_refuel_factory.make_network()
    plan_net = mission_plan_net.make_network()
    for net in [fly_net, get_fuel_net, plan_net]:
        flyer.add_task_network(net)
        # assume that the first entered task name is the one we want
        flyer.start_network_loop(
            net.name,
            list(net.task_classes.keys())[0],
        )

    # give some knowledge
    flyer.set_knowledge(
        "destinations",
        [MEETING_POINT, TRAVERSE_TO_POINT, START_POINT],
    )

    d = Dummy(name="the_mothership")
    # env.process(dummy_mothership_proc(env, d))

    flyer.set_knowledge("mothership", d)
    flyer.set_knowledge("refuel_speed", 150)
    flyer.set_knowledge("meetup", MEETING_POINT)

    # nucleus
    flyer_nucleus = UP.TaskNetworkNucleus(actor=flyer)
    flyer_nucleus.add_network(
        fly_net,
        [
            "speed",
        ],
    )
    flyer_nucleus.add_network(get_fuel_net, ["approach"])
    return flyer, d


def dummy_mothership_proc(mothership: Dummy) -> SIMPY_GEN:
    msg = yield mothership.messages.get()
    sendback = msg[0]
    yield sendback.messages.put("GO")


def test_flyer_nothing() -> None:
    with UP.EnvironmentContext() as env:
        flyer, _ = figher_build()
        env.run()
        t = 5.257566344915117
        assert pytest.approx(env.now) == t
        assert pytest.approx(flyer.fuel) == 1000 - 100 * t


def test_flyer_refuel() -> None:
    with UP.EnvironmentContext() as env:
        flyer, mothership = figher_build()
        env.process(dummy_mothership_proc(mothership))
        env.run()
        t = 5.257566344915117
        assert pytest.approx(env.now) == t
        assert pytest.approx(flyer.fuel) == 1068.5242696666946


def test_full_fuelinging() -> None:
    with UP.EnvironmentContext() as env:
        MEETING_POINT = UP.CartesianLocation(0, 0)
        TRAVERSE_TO_POINT = UP.CartesianLocation(200, 0)
        START_POINT = UP.CartesianLocation(200, 200)

        mothership = Mothership(
            name="Fuel Delivery",
            fuel=1000.0,
            fuel_burn=-100.0,
            speed=200.0,
            location=START_POINT,
            fuel_ports_in_use=0,
            fuel_ports_max=4,
        )
        fly_net = fly_end_factory.make_network()
        give_fuel_net = give_fuel_factory.make_network()
        crew_net = crew_factory.make_network()
        for net in [fly_net, give_fuel_net, crew_net]:
            mothership.add_task_network(net)
            # assume that the first entered task name is the one we want
            mothership.start_network_loop(
                net.name,
                list(net.task_classes.keys())[0],
            )

        # give some knowledge
        mothership.set_knowledge(
            "destinations",
            [MEETING_POINT, TRAVERSE_TO_POINT, START_POINT],
        )

        # nucleus
        mothership_nucleus = UP.TaskNetworkNucleus(actor=mothership)
        mothership_nucleus.add_network(
            fly_net,
            [
                "speed",
            ],
        )
        mothership_nucleus.add_network(give_fuel_net, ["fuel_ports_in_use"])

        MEETING_POINT = UP.CartesianLocation(0, 0)
        TRAVERSE_TO_POINT = UP.CartesianLocation(200, 0)
        START_POINT = UP.CartesianLocation(-200, -200)

        flyer = Flyer(
            name="Flying Thing",
            fuel=1000.0,
            fuel_capacity=1500.0,
            fuel_burn=-100.0,
            fuel_draw=500,
            speed=300.0,
            location=START_POINT,
            debug_log=True,
        )

        fly_net = fly_end_factory.make_network()
        get_fuel_net = flyer_refuel_factory.make_network()
        plan_net = mission_plan_net.make_network()
        for net in [fly_net, get_fuel_net, plan_net]:
            flyer.add_task_network(net)
            # assume that the first entered task name is the one we want
            flyer.start_network_loop(
                net.name,
                list(net.task_classes.keys())[0],
            )

        # give some knowledge
        flyer.set_knowledge(
            "destinations",
            [MEETING_POINT, TRAVERSE_TO_POINT, START_POINT],
        )

        flyer.set_knowledge("mothership", mothership)
        # This speed doesn't match the mothership, but
        # the test numbers are tuned for it
        flyer.set_knowledge("refuel_speed", 150)
        flyer.set_knowledge("meetup", MEETING_POINT)

        # nucleus
        flyer_nucleus = UP.TaskNetworkNucleus(actor=flyer)
        flyer_nucleus.add_network(
            fly_net,
            [
                "speed",
            ],
        )
        flyer_nucleus.add_network(get_fuel_net, ["approach"])

        env.run()

        # The total fuel to start is: 2000
        flyer_flight_t = 5.257566344915117
        flyer_burn = 100 * flyer_flight_t
        mothership_flight_t = 682.842712474619 / 200
        mothership_burn = 100 * mothership_flight_t
        total_burn = mothership_burn + flyer_burn
        fuel_left = mothership.fuel + flyer.fuel
        assert pytest.approx(fuel_left) == 2000 - total_burn
