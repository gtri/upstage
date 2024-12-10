# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import simpy as SIM

import upstage_des.api as UP
from upstage_des.type_help import SIMPY_GEN, TASK_GEN


class CPU(UP.Actor):
    n_procs = UP.State[int](default=0, valid_types=int, recording=True)
    jobs = UP.ResourceState[SIM.Store](default=SIM.Store)

    @staticmethod
    def time_from_data(process_data: dict[str, float]) -> float:
        best_time = process_data["best time"]
        percent_complete = process_data["percent complete"]
        alloc = process_data["allocated"]
        work_left = best_time * (1 - percent_complete)
        time = work_left / alloc
        return time

    @staticmethod
    def left_from_partial(
        process_data: dict[str, float], start_time: float, curr_time: float
    ) -> float:
        alloc = process_data["allocated"]
        work_left = process_data["best time"] * (1 - process_data["percent complete"])
        elapsed = curr_time - start_time
        percent_of_left = 1 - (elapsed / (work_left / alloc))
        percent_left = (1 - process_data["percent complete"]) * percent_of_left
        return percent_left


class CPUProcessStart(UP.DecisionTask):
    def get_name(self) -> str:
        return f"{self._network_name}"

    def make_decision(self, *, actor: CPU) -> None:
        knowledge_name = self.get_name()
        process_data: dict[str, float] = self.get_actor_knowledge(
            actor, knowledge_name, must_exist=True
        )
        # the task takes some amount of time to finish based on its cpu amount
        assert process_data["percent complete"] == 0.0
        # Touch the nucleus variable before it affects this network
        actor.n_procs += 1
        # Now we can add ourselves to the nucleus
        nucleus = actor.get_nucleus()
        nucleus.add_network(knowledge_name, ["n_procs"])


class CPUProcess(UP.Task):
    def get_name(self) -> str:
        return f"{self._network_name}"

    def task(self, *, actor: CPU) -> TASK_GEN:
        knowledge_name = self.get_name()
        process_data: dict[str, float] = self.get_actor_knowledge(
            actor, knowledge_name, must_exist=True
        )
        # We know at this point we're part of the n_procs
        allocate_amount = 1 / (actor.n_procs)
        process_data["allocated"] = allocate_amount
        self.set_actor_knowledge(actor, knowledge_name, process_data, overwrite=True)
        self.set_marker("RUNNING")
        time = actor.time_from_data(process_data)
        print(
            f"{self.env.now:.2f}: Starting: {knowledge_name}\n\tAllocated: {allocate_amount:.2f}"
            f"\n\tTime Left: {time:.2f}"
        )
        yield UP.Wait(time)
        self.clear_actor_knowledge(actor, knowledge_name)
        actor.get_nucleus().remove_network(self.get_name())
        actor.n_procs -= 1
        print(f"{self.env.now:.2f}: Done with: {knowledge_name}")

    def on_interrupt(self, *, actor: CPU, cause: str | UP.NucleusInterrupt) -> UP.InterruptStates:
        if isinstance(cause, UP.NucleusInterrupt):
            assert cause.state_name == "n_procs"

            start_time = self.get_marker_time()
            assert start_time is not None
            knowledge_name = self.get_name()
            process_data: dict[str, float] = self.get_actor_knowledge(
                actor, knowledge_name, must_exist=True
            )
            perc = actor.left_from_partial(process_data, start_time, self.env.now)
            process_data["percent complete"] = perc
            self.set_actor_knowledge(actor, knowledge_name, process_data, overwrite=True)

            return self.INTERRUPT.RESTART
        raise UP.SimulationError("Unexpected interrupt state")


cpu_job_factory = UP.TaskNetworkFactory.from_ordered_terminating(
    name="SingleJob", task_classes=[CPUProcessStart, CPUProcess]
)


class CPUJobFarmer(UP.Task):
    def task(self, *, actor: CPU) -> TASK_GEN:
        job = yield UP.Get(actor.jobs)

        suggest = actor.suggest_network_name(cpu_job_factory)
        new_net = cpu_job_factory.make_network(other_name=suggest)
        actor.add_task_network(new_net)

        proc_know = {"best time": job, "percent complete": 0.0}
        self.set_actor_knowledge(actor, suggest, proc_know)
        actor.start_network_loop(suggest, init_task_name="CPUProcessStart")


cpu_farmer_factory = UP.TaskNetworkFactory.from_single_looping(
    name="Dispatch", task_class=CPUJobFarmer
)


def test_nucleus_sharing() -> None:
    job_time_list = [100.0, 10.0, 15.0, 13.0, 5.0, 25.0]
    job_start_delay = [0.0, 3.0, 5.0, 10.0, 10.0, 3.0]

    with UP.EnvironmentContext() as env:
        cpu = CPU(
            name="Magic Computer",
            n_procs=0,
        )
        _ = UP.TaskNetworkNucleus(actor=cpu)

        net = cpu_farmer_factory.make_network()
        cpu.add_task_network(net)
        cpu.start_network_loop(net.name, "CPUJobFarmer")

        def job_sender() -> SIMPY_GEN:
            for time, delay in zip(job_time_list, job_start_delay):
                yield env.timeout(delay)
                yield cpu.jobs.put(time)

        env.process(job_sender())
        env.run()
        print(env.now)
