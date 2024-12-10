# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from random import uniform

import pytest

from upstage_des.base import EnvironmentContext
from upstage_des.resources.container import (
    ContainerEmptyError,
    ContainerError,
    ContinuousContainer,
)
from upstage_des.resources.monitoring import (
    SelfMonitoringContainer,
    SelfMonitoringContinuousContainer,
)
from upstage_des.type_help import SIMPY_GEN

CONTAINER_CAPACITY = 100
INITIAL_LEVEL = 50


def test_basics() -> None:
    with EnvironmentContext() as env:
        con = ContinuousContainer(
            capacity=CONTAINER_CAPACITY,
            env=env,
            init=INITIAL_LEVEL,
        )

        assert con.capacity == CONTAINER_CAPACITY
        assert con.level == INITIAL_LEVEL

        env.run(until=10)
        con._set_new_rate(-10.0)

        with pytest.raises(ContainerEmptyError) as err:
            env.run(until=30)
        assert err.value.cause == "Container is empty!"


def test_error() -> None:
    with EnvironmentContext() as env:
        con = ContinuousContainer(
            capacity=CONTAINER_CAPACITY,
            env=env,
            init=INITIAL_LEVEL,
        )
        con._set_new_rate(-20)
        with pytest.raises(ContainerError):
            env.run(until=30)

        with pytest.raises(ValueError):
            con.put(-20, 3)


def test_calculations() -> None:
    with EnvironmentContext() as env:
        con = ContinuousContainer(
            capacity=CONTAINER_CAPACITY,
            env=env,
            init=INITIAL_LEVEL,
        )
        con._set_new_rate(-20.0)

        assert con.time_until_level(0.0) == 2.5
        assert con.time_until_level(CONTAINER_CAPACITY) == float("inf")


def test_checking() -> None:
    with EnvironmentContext() as env:
        auto_started = ContinuousContainer(
            capacity=CONTAINER_CAPACITY,
            env=env,
            init=INITIAL_LEVEL,
        )
        auto_started._set_new_rate(-20.0)
        env.run(until=2)
        assert auto_started.level < INITIAL_LEVEL

        with pytest.raises(ContainerEmptyError):
            env.run(until=10)


def test_get_and_put() -> None:
    with EnvironmentContext() as env:
        tank = ContinuousContainer(env, capacity=1000.0, init=500.0)
        get_time = 10.0
        get_rate = 50.0
        tank.get(rate=get_rate, time=get_time)

        put_time = 12.0
        put_rate = 60.0
        tank.put(rate=put_rate, time=put_time)

        env.run(until=9)
        assert len(tank._active_puts) == 1
        assert len(tank._active_gets) == 1

        added = -get_rate * 9 + put_rate * 9
        assert tank.level == 500 + added

        env.run(until=11)
        assert len(tank._active_puts) == 1
        assert len(tank._active_gets) == 0

        env.run(until=13)
        added = -get_rate * get_time + put_rate * put_time
        assert tank.level == 720


def test_interrupting() -> None:
    with EnvironmentContext() as env:
        tank = ContinuousContainer(
            env,
            capacity=1000.0,
            init=500.0,
            error_empty=False,
            error_full=False,
        )

        msg = []

        def full_callback() -> None:
            msg.append("full")

        putter = tank.put(10.0, 100.0, custom_callbacks=[full_callback])
        env.run(until=51)

        assert len(msg) == 1
        assert putter not in tank._active_users

    with EnvironmentContext() as env:
        tank = ContinuousContainer(
            env,
            capacity=1000.0,
            init=500.0,
            error_empty=False,
            error_full=False,
        )

        putter = tank.put(10.0, 100.0)
        env.run(until=25)
        assert tank.level == 500 + 25 * 10
        assert putter in tank._active_users
        putter.cancel()
        env.run()
        assert tank.level == 500 + 25 * 10
        assert putter not in tank._active_users


def test_complex_behavior() -> None:
    times = []
    tanker_called = [False]

    with EnvironmentContext() as env:
        tank = SelfMonitoringContinuousContainer(
            env=env,
            capacity=1000.0,
            init=850.0,
        )
        tank._set_new_rate(-1.0)

        d: list[str] = []

        def tank_is_empty() -> None:
            d.append("empty")

        def tank_is_overflowing() -> None:
            d.append("overflowing")

        def call_refill() -> SIMPY_GEN:
            yield env.timeout(5.0)

            rate = 10.0
            until = min(0.95 * tank.time_until_done(rate=rate), 5.0)

            tank.put(rate=rate, time=until, custom_callbacks=[tank_is_overflowing])
            tanker_called[0] = False
            yield env.timeout(until)

        def draw_fuel() -> SIMPY_GEN:
            while True:
                wait = uniform(10.0, 15.0)

                yield env.timeout(wait)

                rate = uniform(1.0, 2.0)
                until = 0.5 * min(tank.time_until_done(rate * 0.99), uniform(20.0, 30.0))
                # print(f"{env.now:5.1f} - Random Draw (rate: {rate:.1f}, "
                #       f"until={until:.1f})")
                tank.get(rate=rate, time=until)
                yield env.timeout(until)
                # print("{:5.1f} - Random Draw Stopped".format(env.now, rate,
                #                                              until))

        def start_stop_getting() -> SIMPY_GEN:
            getter = tank.get(rate=1.0, time=1_000, custom_callbacks=[tank_is_empty])
            # print("{:5.1f} - Started constant getting".format(env.now))
            while True:
                wait = uniform(40.0, 60.0)
                yield env.timeout(wait)
                # print(f"{env.now:5.1f} - Stopped constant getting")

                getter.process.interrupt("stop")

                wait = uniform(40.0, 60.0)
                yield env.timeout(wait)

                getter = tank.get(rate=10.0, time=1_000, custom_callbacks=[tank_is_empty])
                # print("{:5.1f} - Restarted constant getting".format(env.now))

        def simulate() -> SIMPY_GEN:
            env.process(draw_fuel())
            env.process(start_stop_getting())
            while True:
                times.append(env.now)
                t = tank.time_until_level(0.4 * tank.capacity)
                if t == float("inf"):
                    t = tank.time_until_level(tank.capacity)
                if t == float("inf"):
                    t = tank.time_until_level(0.1 * tank.capacity)
                t = 1 if t == float("inf") else t
                yield env.timeout(t)
                if not tanker_called[0] and tank.level <= 0.5 * tank.capacity:
                    tanker_called[0] = True
                    env.process(call_refill())
                yield env.timeout(1.0)

        env.process(simulate())
        env.run(until=120)
        tank._set_level()


def test_basics_monitoring() -> None:
    with EnvironmentContext() as env:
        con = SelfMonitoringContinuousContainer(
            capacity=CONTAINER_CAPACITY,
            env=env,
            init=INITIAL_LEVEL,
        )

        assert con._capacity == CONTAINER_CAPACITY
        assert con.level == INITIAL_LEVEL

        env.run(until=10)
        con._set_new_rate(-10.0)

        with pytest.raises(ContainerEmptyError):
            env.run(until=30)

        assert len(con._quantities) == 3


def test_checking_monitoring() -> None:
    with EnvironmentContext() as env:
        auto_started = SelfMonitoringContinuousContainer(
            capacity=CONTAINER_CAPACITY,
            env=env,
            init=INITIAL_LEVEL,
        )
        auto_started._add_rate(-20.0)
        env.run(until=2)
        assert auto_started.level < INITIAL_LEVEL

        with pytest.raises(ContainerEmptyError):
            env.run(until=10)


def test_self_monitoring_container() -> None:
    """Test self-monitoring container"""
    with EnvironmentContext() as env:
        con = SelfMonitoringContainer(env=env, capacity=CONTAINER_CAPACITY, init=INITIAL_LEVEL)

        assert len(con._quantities) == 1
