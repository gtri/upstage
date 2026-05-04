# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Test knowledge."""

from typing import TypedDict

import pytest
from upstage_des.actor import EMPTY_KNOWLEDGE, Actor
from upstage_des.base import EnvironmentContext, SimulationError


def test_knowledge() -> None:
    class TD(TypedDict):
        number: int
        message: float

    class MyActor(Actor):
        fuel: float = 120.
        knowledge: TD

    class NoKnow(Actor):...

    with EnvironmentContext():
        ma = MyActor(
            name="act",
            knowledge={"number": 2, "message":3.0, "other":"string"}
        )
        assert ma.knowledge["message"] == 3.0
        assert ma.knowledge["number"] == 2
        assert ma.knowledge["other"] == "string"
        nk = NoKnow(name="no knowledge")
        assert len(nk.knowledge) == 0
        nk.knowledge["new data"] = 2.3
        assert len(nk.knowledge) == 1

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
        assert ma.get_knowledge("number", must_exist=True) == 12.0
        assert len(ma.get_log()) == 2


test_knowledge()
