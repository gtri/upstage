# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test the active state"""

from collections import deque
from typing import Annotated

import pytest
from upstage_des.actor import Actor
from upstage_des.states import LinearChangingState
from upstage_des.base import EnvironmentContext, SimulationError
from upstage_des.tasks import Task

def test_linear_state() -> None:
    class MyActor(Actor):
        rate_state: float
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(
            name="Rated",
            rate_state=2.0,
            level=0.0,
        )
        env.run(1.0)
        act.level=1.
        env.run(1.5)
        act.activate_linear_state("level", act.rate_state, task=T)
        env.run(2.5)
        assert act.level == 3.0
        assert act._state_histories["level"] == deque([
            (0.0, 0.0),
            (1.0, 1.0),
            (1.5, 1.0, "ACTIVATING"),
            (2.5, 3.0),
        ])
        env.run(3.0)
        act.deactivate_state("level", task=T)
        env.run(4.0)
        assert act.level == 4.0
        env.run(5.0)
        act.level = 6.2
        assert act._state_histories["level"][4] == (3.0, 4.0, "DEACTIVATING")
        assert act._state_histories["level"][5] == (5.0, 6.2)
        assert len(act._state_histories["level"]) == 6


test_linear_state()

def test_linear_predict() -> None:
    class MyActor(Actor):
        rate_state: float
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(
            name="Rated",
            rate_state=2.0,
            level=0.0,
        )
        field = act.__model_fields__["level"]
        assert isinstance(field, LinearChangingState)
        assert field.predict_value_time(act, 6.4) is None
        env.run(0.5)
        act.activate_linear_state("level", rate=3.2, task=T)
        assert field.predict_value_time(act, 6.4) == 2.5
        env.run(1.5)
        assert field.predict_value_time(act, 6.4) == 2.5
        env.run(3.5)
        assert field.predict_value_time(act, 6.4) is None
        act.deactivate_linear_state("level", task=T)
        act.activate_linear_state("level", rate=-3.0, task=T)
        assert field.predict_value_time(act, 6.4) is not None


def test_linear_errors() -> None:
    class MyActor(Actor):
        rate_state: float
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(
            name="Rated",
            rate_state=2.0,
            level=0.0,
        )
        with pytest.raises(SimulationError):
            act.deactivate_linear_state("level", task=T)
        act.activate_linear_state("level", 1.3, task=T)
        with pytest.raises(SimulationError):
            act.activate_state("level", rate=3.4, task=T)


def test_linear_negative_rate() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Drainer", level=100.0)
        env.run(1.0)
        act.activate_linear_state("level", rate=-5.0, task=T)
        env.run(3.0)
        assert act.level == 90.0
        env.run(5.0)
        assert act.level == 80.0
        assert act._state_histories["level"] == deque([
            (0.0, 100.0),
            (1.0, 100.0, "ACTIVATING"),
            (3.0, 90.0),
            (5.0, 80.0),
        ])


def test_linear_multiple_activations() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()
    
    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Changer", level=0.0)
        act.activate_linear_state("level", rate=2.0, task=T)
        env.run(2.0)
        assert act.level == 4.0
        act.deactivate_linear_state("level", task=T)
        env.run(4.0)
        assert act.level == 4.0
        act.activate_linear_state("level", rate=3.0, task=T)
        env.run(6.0)
        assert act.level == 10.0


def test_linear_zero_rate() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Static", level=50.0)
        act.activate_linear_state("level", rate=0.0, task=T)
        env.run(10.0)
        assert act.level == 50.0
        env.run(20.0)
        assert act.level == 50.0


def test_linear_predict_negative_rate() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()
    
    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Predictor", level=100.0)
        act.activate_linear_state("level", rate=-2.0, task=T)
        field = act.__model_fields__["level"]
        assert isinstance(field, LinearChangingState)
        env.run(5.0)
        assert field.predict_value_time(act, 80.0) == 10.0
        assert field.predict_value_time(act, 50.0) == 25.0


def test_linear_predict_past_value() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Predictor", level=10.0)
        act.activate_linear_state("level", rate=5.0, task=T)
        env.run(2.0)
        field = act.__model_fields__["level"]
        assert isinstance(field, LinearChangingState)
        assert field.predict_value_time(act, 5.0) is None


def test_linear_state_history_deactivate() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Tracker", level=10.0)
        env.run(1.0)
        act.activate_linear_state("level", rate=5.0, task=T)
        env.run(3.0)
        act.deactivate_linear_state("level", task=T)
        history = act._state_histories["level"]
        assert history[0] == (0.0, 10.0)
        assert history[1] == (1.0, 10.0, "ACTIVATING")
        assert history[2] == (3.0, 20.0, "DEACTIVATING")


def test_linear_get_updates_value() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Getter", level=0.0)
        act.activate_linear_state("level", rate=10.0, task=T)
        env.run(1.0)
        val1 = act.level
        val2 = act.level
        assert val1 == 10.0
        assert val2 == 10.0
        assert len(act._state_histories["level"]) == 3


def test_linear_state_recording_false() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Untracked", level=5.0)
        act.activate_linear_state("level", rate=2.0, task=T)
        env.run(3.0)
        assert act.level == 11.0
        assert act._state_histories["level"] == deque([
            (0.0, 5.0),
            (0.0, 5.0, "ACTIVATING"),
            (3.0, 11),
        ])


def test_make_event_for_state_goal() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Tester", level=10.0)
        assert act.get_time_for_state_goal("level", 50.0) is None
        act.activate_linear_state("level", rate=5.0, task=T)
        env.run(2.0)
        goal_time = act.get_time_for_state_goal("level", 50.0)
        assert goal_time == 8.0
        env.run(goal_time)
        assert act.level == 50.0


def test_make_event_for_state_goal_negative_rate() -> None:
    class MyActor(Actor):
        level: float = LinearChangingState(recording=True).create()

    with EnvironmentContext() as env:
        T = Task()

        act = MyActor(name="Drainer", level=100.0)
        act.activate_linear_state("level", rate=-10.0, task=T)
        goal_time = act.get_time_for_state_goal("level", 50.0)
        assert goal_time == 5.0
        env.run(goal_time)
        assert act.level == 50.0
