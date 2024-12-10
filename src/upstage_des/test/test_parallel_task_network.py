# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import simpy as SIM

import upstage_des.api as UP
from upstage_des.api import Task
from upstage_des.type_help import SIMPY_GEN, TASK_GEN


class ParallelTest(UP.Actor):
    comms = UP.State[SIM.Store]()
    logger = UP.State[list]()
    internal = UP.State[SIM.Store]()
    working = UP.State[bool]()


class TaskOne(Task):
    def task(self, *, actor: ParallelTest) -> TASK_GEN:
        actor.working = not actor.working
        actor._lock_state(state="working", task=self)
        thing = yield UP.Get(actor.internal)
        actor.logger.append((actor.env.now, thing, actor.working))
        actor._unlock_state(state="working", task=self)


class TaskTwo(Task):
    def task(self, *, actor: ParallelTest) -> TASK_GEN:
        other = yield UP.Get(actor.comms)
        actor.logger.append((actor.env.now, "Put the message", actor.working))
        yield UP.Put(actor.internal, other)


def test_parallel_looping() -> None:
    with UP.EnvironmentContext() as env:
        net_1_classes = {"Task": TaskOne}
        net_1_links = {"Task": UP.TaskLinks(default="Task", allowed=["Task"])}
        net_2_classes = {"Task": TaskTwo}
        net_2_links = {"Task": UP.TaskLinks(default="Task", allowed=["Task"])}

        tn1 = UP.TaskNetwork("InternalGet", net_1_classes, net_1_links)
        tn2 = UP.TaskNetwork("ExternalGet", net_2_classes, net_2_links)

        def proc(env: SIM.Environment, actor: ParallelTest, thing: str) -> SIMPY_GEN:
            yield env.timeout(1.3)
            yield actor.comms.put(thing)
            yield env.timeout(2.2)
            yield actor.comms.put(thing)

        pt = ParallelTest(
            name="Parallel_Actor",
            comms=SIM.Store(env),
            internal=SIM.Store(env),
            logger=[],
            working=False,
        )

        pt.add_task_network(tn1)
        pt.add_task_network(tn2)

        pt.start_network_loop("InternalGet", init_task_name="Task")
        pt.start_network_loop("ExternalGet", init_task_name="Task")
        env.process(proc(env, pt, "the msg"))
        env.run(until=1.0)
        running = pt.get_running_tasks()
        assert len(running) == 2
        assert "InternalGet" in running
        assert running["InternalGet"].name == "Task"
        assert "ExternalGet" in running
        assert running["ExternalGet"].name == "Task"

        tqs = pt.get_all_task_queues()
        assert "InternalGet" in tqs
        assert "ExternalGet" in tqs

        env.run()

        assert len(pt.logger) == 4
        expected_log = [
            (1.3, "Put the message", True),
            (1.3, "the msg", True),
            (3.5, "Put the message", False),
            (3.5, "the msg", False),
        ]
        for el, al in zip(expected_log, pt.logger):
            assert el == al
