# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)
# Licensed under the 3-Clause BSD License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
import multiprocessing as mp

import pytest
import simpy as SIM

from upstage_des.base import (
    STAGE_CONTEXT_VAR,
    EnvironmentContext,
    NamedUpstageEntity,
    UpstageBase,
    UpstageError,
    add_stage_variable,
)


def test_context() -> None:
    with EnvironmentContext() as env:
        assert isinstance(env, SIM.Environment)
        env.run(until=3)
        assert env.now == 3

    with EnvironmentContext(initial_time=3.1) as env:
        assert isinstance(env, SIM.Environment)
        assert env.now == 3.1


def test_entity_naming() -> None:
    class TestItem(NamedUpstageEntity): ...

    class Example(TestItem, entity_groups=["This"]): ...

    class Ignorable(NamedUpstageEntity, add_to_entity_groups=False): ...

    # This shows how the entity group ignorance doesn't cascade down.
    class Ignorable2(Ignorable): ...

    with pytest.warns(UserWarning, match="Environment not created*"):
        other = Example()

    with pytest.raises(UpstageError):
        other.env

    with EnvironmentContext() as env:
        # Note that due to the context, we can access the environment
        # even if we couldn't before.
        assert env is other.env

        t = TestItem()
        t2 = TestItem()
        e = Example()
        _ = Ignorable()
        _ = Ignorable2()

        items = t.get_entity_group("TestItem")
        assert len(items) == 3
        assert t in items
        assert t2 in items
        assert e in items

        items = t.get_entity_group("This")
        assert len(items) == 1
        assert e in items

        items = t.get_entity_group("Example")
        assert len(items) == 1
        assert e in items

        items = t.get_entity_group("Ignorable")
        assert len(items) == 0

        items = t.get_entity_group("Ignorable2")
        assert len(items) == 1


def test_stage() -> None:
    with EnvironmentContext():
        add_stage_variable("A variable", 3.14)
        ans = STAGE_CONTEXT_VAR.get()
        assert ans.get("A variable", 0.1) == 3.14
        assert ans.get("random") is not None
        assert len(ans) == 2
        with pytest.raises(UpstageError):
            add_stage_variable("A variable", 2)


def test_random() -> None:
    with EnvironmentContext(random_seed=1234986):
        cl = UpstageBase()
        num = cl.stage.random.uniform(1, 3)
        assert pytest.approx(num) == 2.348057489610457

    from random import Random

    rng = Random(1234986)
    with EnvironmentContext(random_gen=rng):
        cl = UpstageBase()
        num = cl.stage.random.uniform(1, 3)
        assert pytest.approx(num) == 2.348057489610457

    with EnvironmentContext():
        num = cl.stage.random.uniform(1, 3)


def a_simulation(t: float) -> float:
    with EnvironmentContext() as env:
        env.run(until=env.now + t)
        return env.now


def test_multiproc_stability() -> None:
    inputs = [1.2, 3.4, 5.6, 10.11, 74.31]

    with mp.Pool(3) as pool:
        res = pool.map(a_simulation, inputs)

    assert res == inputs


@pytest.mark.parametrize(
    ["unit", "mult"],
    [
        ("min", 60),
        ("Minutes", 60),
        ("s", 3600),
        ("second", 3600),
        ("hours", 1),
        ("hr", 1),
        (None, 1),
    ],
)
def test_pretty_times(unit: str, mult: int) -> None:
    """Test that if we do time in regular ways, we get standard logging."""
    times_in_hours = [3, 28, 24 * 15 + 6.5]
    times_in_hours = [x * mult for x in times_in_hours]
    with EnvironmentContext(initial_time=times_in_hours[0]) as env:
        add_stage_variable("time_unit", unit)
        base = UpstageBase()
        assert base.pretty_now == "[Day    0 - 03:00:00]"
        env.run(until=times_in_hours[1])
        assert base.pretty_now == "[Day    1 - 04:00:00]"
        env.run(until=times_in_hours[2])
        assert base.pretty_now == "[Day   15 - 06:30:00]"


@pytest.mark.parametrize("unit", ["ticks", "week", "day", "microseconds"])
def test_pretty_time_nonstandard(unit: str) -> None:
    with EnvironmentContext() as env:
        add_stage_variable("time_unit", unit)
        base = UpstageBase()
        assert base.pretty_now == f"[0.000 {unit}]"
        add_stage_variable("daily_time_count", 100)
        assert base.pretty_now == f"[Day    0 - 0.000 {unit}]"
        env.run(until=223)
        assert base.pretty_now == f"[Day    2 - 23.000 {unit}]"
