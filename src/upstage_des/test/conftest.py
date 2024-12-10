# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Fixtures for testing."""

from typing import Any

import pytest

import upstage_des.api as UP


@pytest.fixture
def base_actors() -> tuple[tuple[UP.State, ...], tuple[type[UP.Actor], ...]]:
    """State and Actor classes for testing.

    Returns:
        tuple[tuple[UP.State, ...], tuple[UP.Actor, ...]]: States and Actors.
    """
    first_state = UP.State[Any]()
    second_state = UP.State[Any]()
    third_state = UP.State[Any]()
    fourth_state = UP.State[Any]()

    class ActorSubclass(UP.Actor):
        state_one = first_state
        state_two = second_state

        def a_function(self, inp: Any) -> tuple[UP.Actor, Any]:
            return self, inp

    class DoubleSubclass(ActorSubclass):
        state_three = third_state
        state_four = fourth_state

        def b_function(self, inp: Any) -> tuple[UP.Actor, Any]:
            return self, inp

    states = (first_state, second_state, third_state, fourth_state)
    actors = (ActorSubclass, DoubleSubclass)

    return states, actors


@pytest.fixture
def task_objects() -> tuple[type[UP.TerminalTask], type[UP.TerminalTask], type[UP.Actor]]:
    """Example task objects for testing.

    Returns:
        tuple[UP.Task, UP.Task, UP.Actor]: The task objects.
    """

    class EndPoint(UP.TerminalTask):
        def log_message(self, *, actor: UP.Actor) -> str:
            return "The Message"

    class EndPointBase(UP.TerminalTask):
        pass

    class Dummy(UP.Actor):
        status = UP.State[Any]()

    return EndPoint, EndPointBase, Dummy
