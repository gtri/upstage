# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

from upstage_des.actor import Actor
from upstage_des.api import Task, UpstageError, Wait
from upstage_des.base import EnvironmentContext
from upstage_des.states import LinearChangingState, State
from upstage_des.type_help import TASK_GEN


class Piggy(Actor):
    a_level = LinearChangingState(recording=True)
    location = State[str]()


class Rider(Actor):
    b_level = LinearChangingState(recording=True)
    location = State[str]()
    piggy = State[Piggy]()


class RiderTask(Task):
    def task(self, *, actor: Rider) -> TASK_GEN:
        piggy = actor.piggy
        actor.activate_mimic_state(
            self_state="b_level",
            mimic_state="a_level",
            mimic_actor=piggy,
            task=self,
        )
        yield Wait(1.0)
        actor.deactivate_mimic_state(
            self_state="b_level",
            task=self,
        )


class RiderTaskTwo(Task):
    def task(self, *, actor: Rider) -> TASK_GEN:
        actor.activate_state(
            state="b_level",
            rate=2,
            task=self,
        )
        yield Wait(5.0)
        actor.deactivate_all_states(task=self)


def test_simple() -> None:
    with EnvironmentContext() as env:
        pig = Piggy(name="Piggy", a_level=1, location="here")
        ride = Rider(name="Rider", b_level=2, location="there", piggy=pig)

        assert ride.location == "there"
        ride.activate_mimic_state(
            self_state="location",
            mimic_state="location",
            mimic_actor=pig,
            task="None",  # type: ignore [arg-type]
        )
        assert ride.location == "here"
        pig.location = "way over there"
        assert ride.location == "way over there"

        ride.deactivate_mimic_state(self_state="location", task="None")  # type: ignore [arg-type]
        assert ride.location == "way over there"

        # a later test will check this differently
        assert not hasattr(ride, "_location_history")

        assert ride.b_level == 2
        ride.activate_mimic_state(
            self_state="b_level",
            mimic_state="a_level",
            mimic_actor=pig,
            task="None",  # type: ignore [arg-type]
        )
        pig.activate_state(
            state="a_level",
            rate=2,
            task=None,  # type: ignore [arg-type]
        )
        assert ride.b_level == 1
        env.run(until=4)

        pig.deactivate_all_states(task=None)  # type: ignore [arg-type]

        assert ride.b_level == 9
        ride.deactivate_all_mimic_states(task="None")  # type: ignore [arg-type]
        assert ride.b_level == 9

        ride.activate_state(
            state="b_level",
            rate=1,
            task=None,  # type: ignore [arg-type]
        )
        env.run(until=5)
        assert ride.b_level == 10
        assert pig.a_level == 9


def test_rehearsing() -> None:
    with EnvironmentContext():
        pig = Piggy(name="Piggy", a_level=1, location="here")
        ride = Rider(name="Rider", b_level=2, location="there", piggy=pig)

        task = RiderTask()
        with pytest.raises(UpstageError):
            task.rehearse(actor=ride)


def test_rehearse_from_piggyback() -> None:
    with EnvironmentContext() as env:
        pig = Piggy(name="Piggy", a_level=1, location="here")
        ride = Rider(name="Rider", b_level=2, location="there", piggy=pig)

        assert ride.b_level == 2
        ride.activate_mimic_state(
            self_state="b_level",
            mimic_state="a_level",
            mimic_actor=pig,
            task="None",  # type: ignore [arg-type]
        )
        pig.activate_state(
            state="a_level",
            rate=2,
            task=None,  # type: ignore [arg-type]
        )
        assert ride.b_level == 1
        env.run(until=4)
        pig.deactivate_all_states(task=None)  # type: ignore [arg-type]

        # Do not deactivate, instead call RiderTaskTwo
        # Pig went a_level to 9
        task = RiderTaskTwo()
        new_ride = task.rehearse(actor=ride)
        assert new_ride.b_level == 19
        assert ride.b_level == 9
        assert pig.a_level == 9

        ride.deactivate_mimic_state(self_state="b_level", task="None")  # type: ignore [arg-type]
        pig.a_level = 12
        assert new_ride.b_level == 19
        assert ride.b_level == 9


def test_double_mimic() -> None:
    with EnvironmentContext():
        pig = Piggy(name="Piggy", a_level=1, location="here")
        ride = Rider(name="Rider", b_level=2, location="there", piggy=pig)

        ride.activate_mimic_state(
            self_state="b_level",
            mimic_state="a_level",
            mimic_actor=pig,
            task="None",  # type: ignore [arg-type]
        )

        with pytest.raises(UpstageError):
            ride.activate_mimic_state(
                self_state="b_level",
                mimic_state="a_level",
                mimic_actor=pig,
                task="None",  # type: ignore [arg-type]
            )


def test_interrupt_deactivate() -> None:
    with EnvironmentContext() as env:
        pig = Piggy(name="Piggy", a_level=1, location="here")
        ride = Rider(name="Rider", b_level=2, location="there", piggy=pig)

        ride.activate_mimic_state(
            self_state="b_level",
            mimic_state="a_level",
            mimic_actor=pig,
            task="None",  # type: ignore [arg-type]
        )
        task = RiderTaskTwo()
        task.run(actor=ride)
        env.run()


def test_record() -> None:
    with EnvironmentContext():
        pig = Piggy(name="Piggy", a_level=1, location="here")

        class Rec(Actor):
            state = State[int](recording=True)

        class Rec2(Actor):
            state = State[int](recording=False)

        ride = Rec(
            name="another rider",
            state=3,
        )
        ride1 = Rec(
            name="another rider a",
            state=3,
        )
        ride2 = Rec2(
            name="another rider 2",
            state=3,
        )

        ride.activate_mimic_state(
            self_state="state",
            mimic_state="a_level",
            mimic_actor=pig,
            task="None",  # type: ignore [arg-type]
        )

        ride1.activate_mimic_state(
            self_state="state",
            mimic_state="a_level",
            mimic_actor=pig,
            task="None",  # type: ignore [arg-type]
        )

        ride2.activate_mimic_state(
            self_state="state",
            mimic_state="a_level",
            mimic_actor=pig,
            task="None",  # type: ignore [arg-type]
        )

        pig.a_level = 23
        assert ride.state == 23
        assert ride1.state == 23
        assert ride2.state == 23
        assert "state" in ride._state_histories
        assert "state" in ride1._state_histories
        assert "state" not in ride2._state_histories
        assert ride._state_histories["state"][1] == (0, 23)
        assert ride1._state_histories["state"][1] == (0, 23)
