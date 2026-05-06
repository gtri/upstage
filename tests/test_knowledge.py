# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test knowledge."""

from dataclasses import dataclass
from typing import Any, TypedDict

import pytest
from upstage_des.actor import EMPTY_KNOWLEDGE, Actor, Knowledge
from upstage_des.base import EnvironmentContext, SimulationError
from upstage_des.states import State
from upstage_des.tasks import Task


def test_knowledge() -> None:
    @dataclass
    class TD(Knowledge):
        number: int
        message: float

    class MyActor(Actor):
        fuel: float = 120.
        knowledge: TD = State(default_factory=TD.make_blank).create()

    class NoKnow(Actor):...

    with EnvironmentContext():
        ma_blank = MyActor(name="empty")
        assert ma_blank.knowledge.number is EMPTY_KNOWLEDGE
        assert ma_blank.knowledge.message is EMPTY_KNOWLEDGE

        ma = MyActor(
            name="act",
            knowledge=TD(number=2, message=3.0)
        )
        assert ma.knowledge.message == 3.0
        assert ma.knowledge["number"] == 2
        nk = NoKnow(name="no knowledge")
        v = ma.get_knowledge("message")
        assert v == 3.0
        v = ma.get_knowledge("number", must_exist=True)
        assert v == 2
        with pytest.raises(SimulationError, match="does not exist on"):
            ma.get_knowledge("foo", must_exist=True)
        assert ma.get_knowledge("foo") is EMPTY_KNOWLEDGE
        assert nk.get_knowledge("foo") is EMPTY_KNOWLEDGE
        with pytest.raises(SimulationError, match="does not exist on"):
            nk.get_knowledge("foo", must_exist=True)

        ma.clear_knowledge("number")
        v = ma.get_knowledge("number")
        assert v is EMPTY_KNOWLEDGE
        ma.set_knowledge("number", 12.0, caller="The Test")
        assert ma.get_and_clear_knowledge("number") == 12.0
        assert len(ma.get_log()) == 3
        assert ma.knowledge.number is EMPTY_KNOWLEDGE

        # add back knowledge
        ma.knowledge.number = 3
        ma.knowledge.message = 4.2
        # Clear it all w/ a task
        t = Task()
        assert ma.knowledge.number is not EMPTY_KNOWLEDGE
        assert ma.knowledge.message is not EMPTY_KNOWLEDGE
        t.clear_actor_bulk_knowledge(ma, ["number", "message"])
        assert ma.knowledge.number is EMPTY_KNOWLEDGE
        assert ma.knowledge.message is EMPTY_KNOWLEDGE


test_knowledge()
