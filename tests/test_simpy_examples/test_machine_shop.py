# The machine shop example uses interrupts explicitly, as well as 
# pre-emption. That makes a good test case that UPSTAGE can run SimPy.
# https://simpy.readthedocs.io/en/latest/examples/machine_shop.html
# This example mixes UPSTAGE and SimPy, but it's sufficient for testing.
# In a bigger upstage model, the repairman would be an actor and receive a
# message about the new task, rather than using pre-emption directly through
# a resource (although that is simpler).
from dataclasses import dataclass, field
from random import Random

import simpy as SIM
import upstage_des.api as UP

# Parameters from the example
RANDOM_SEED = 42
PT_MEAN = 10.0         # Avg. processing time in minutes
PT_SIGMA = 2.0         # Sigma of processing time
MTTF = 300.0           # Mean time to failure in minutes
BREAK_MEAN = 1 / MTTF  # Param. for expovariate distribution
REPAIR_TIME = 30.0     # Time it takes to repair a machine in minutes
JOB_DURATION = 30.0    # Duration of other jobs in minutes
NUM_MACHINES = 10      # Number of machines in the machine shop
WEEKS = 4              # Simulation time in weeks
SIM_TIME = WEEKS * 7 * 24 * 60  # Simulation time in minutes


def time_per_part() -> float:
    """Return actual processing time for a concrete part."""
    random = UP.get_stage().random
    t = random.normalvariate(PT_MEAN, PT_SIGMA)
    # The normalvariate can be negative, but we want only positive times.
    while t <= 0:
        t = random.normalvariate(PT_MEAN, PT_SIGMA)
    return t


def time_to_failure() -> float:
    """Return time until next failure for a machine."""
    random = UP.get_stage().random
    return random.expovariate(BREAK_MEAN)


@dataclass
class MachineKnow(UP.Knowledge):
    repairman: SIM.PreemptiveResource
    part_time_left: float = field(default=-1.0)


class Machine(UP.Actor):
    parts_made: int = UP.State(default=0, recording=True).create()
    broken: bool = UP.State(default=False, recording=True).create()
    knowledge: MachineKnow = UP.State(default_factory=MachineKnow.make_blank).create()


class DoMachineWork(UP.Task):
    def _track_time_left(self, actor: Machine) -> float:
        time_left = actor.knowledge.part_time_left
        if time_left < 0:
            time_left = time_per_part()
            actor.knowledge.part_time_left = time_left
        return time_left

    def task(self, *, actor: Machine) -> UP.TASK_GEN:
        while True:
            time_left = self._track_time_left(actor)
            self.set_marker("starting work")
            yield UP.Timeout(time_left)
            actor.parts_made += 1
            # Reset the knowledge of time so it recalculates for a new part
            actor.knowledge.part_time_left = -1
        
    def on_interrupt(self, *, actor: Machine, cause: str) -> UP.InterruptStates:
        self.broken = True
        elapsed = self.env.now - self.get_marker_time()
        actor.knowledge.part_time_left -= elapsed
        return UP.InterruptStates.END


class GetFixed(UP.Task):
    def task(self, *, actor: Machine) -> UP.TASK_GEN:
        request = actor.knowledge.repairman.request()
        yield request
        yield UP.Timeout(REPAIR_TIME)
        actor.knowledge.repairman.release(request)
        actor.broken = False


class DoBreaking(UP.Task):
    def task(self, *, actor: Machine) -> UP.TASK_GEN:
        yield self.env.timeout(time_to_failure())
        if not actor.broken:
            actor.interrupt_network("MachineNetwork", cause="Breakage")


machine_net = UP.TaskNetworkFactory.from_ordered_loop(
    "MachineNetwork",
    task_classes=[DoMachineWork, GetFixed],
)

break_net = UP.TaskNetworkFactory.from_single_looping(
    "BreakNet",
    task_class=DoBreaking,
)


def other_jobs(env: SIM.Environment, repairman: SIM.PreemptiveResource) -> UP.SIMPY_GEN:
    """The repairman's other (unimportant) job."""
    while True:
        # Start a new job
        done_in = JOB_DURATION
        while done_in:
            # Retry the job until it is done.
            # Its priority is lower than that of machine repairs.
            with repairman.request(priority=2) as req:
                yield req
                start = env.now
                try:
                    yield env.timeout(done_in)
                    done_in = 0
                except SIM.Interrupt:
                    done_in -= env.now - start


def test_machine_shop_example() -> None:
    with UP.EnvironmentContext(random_seed=RANDOM_SEED) as env:
        repairman = SIM.PreemptiveResource(env, capacity=1)
        machines = [
            Machine(
                name=f'Machine {i}',
                knowledge=MachineKnow(repairman),
            )
            for i in range(NUM_MACHINES)
        ]
        for m in machines:
            net = machine_net.make_network()
            m.add_task_network(net)
            m.start_network_loop(net.name, DoMachineWork)
            net = break_net.make_network()
            m.add_task_network(net)
            m.start_network_loop(net, DoBreaking)

        env.process(
            other_jobs(env, repairman)
        )
        env.run(until=SIM_TIME)
        # print(f'Machine shop results after {WEEKS} weeks')
        for machine in machines:
            assert machine.parts_made > 3000
        #     print(f'{machine.name} made {machine.parts_made} parts.')

        # You can get data out!
        # machines[0]._state_histories["parts_made"]
