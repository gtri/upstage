# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN


class Act(UP.Actor):
    state = UP.State[int](default=0)


class Do(UP.Task):
    def task(self, *, actor: Act) -> TASK_GEN:
        yield UP.Wait(2)
        actor.state = actor.state + 1


class Do2(UP.Task):
    def task(self, *, actor: Act) -> TASK_GEN:
        yield UP.Wait(3)
        actor.state = actor.state + 3


def test_single_loop_and_names() -> None:
    with UP.EnvironmentContext() as env:
        factory = UP.TaskNetworkFactory.from_single_looping("example", Do)

        actor = Act(name="a thing")

        suggest = actor.suggest_network_name(factory)
        assert suggest == "example"
        new_net = factory.make_network(other_name=suggest)
        actor.add_task_network(new_net)

        suggest = actor.suggest_network_name(factory)
        assert suggest == "example_1"
        new_net = factory.make_network(other_name=suggest)
        actor.add_task_network(new_net)

        actor.start_network_loop("example", init_task_name="Do")
        actor.start_network_loop("example_1", init_task_name="Do")

        env.run(until=3)

        assert actor.state == 2

        assert actor.has_task_network("example")
        assert actor.has_task_network("example_1")

        actor.delete_task_network("example")
        actor.delete_task_network("example_1")

        assert not actor.has_task_network("example")
        assert not actor.has_task_network("example_1")

        env.run(until=5)

        assert actor.state == 4


def test_other_inits() -> None:
    with UP.EnvironmentContext() as env:
        factory = UP.TaskNetworkFactory.from_ordered_terminating("example", [Do, Do2])
        actor = Act(name="a thing")

        new_net = factory.make_network()
        actor.add_task_network(new_net)

        actor.start_network_loop("example", init_task_name="Do2")

        env.run(until=4)

        assert actor.state == 3

        task = actor.get_running_task("example")
        assert task is not None and "TERMINATING" in task.name

    with UP.EnvironmentContext() as env:
        factory = UP.TaskNetworkFactory.from_ordered_loop("example", [Do, Do2])
        actor = Act(name="a thing")

        new_net = factory.make_network()
        actor.add_task_network(new_net)

        actor.start_network_loop("example", init_task_name="Do")

        env.run(until=6)

        assert actor.state == 4
