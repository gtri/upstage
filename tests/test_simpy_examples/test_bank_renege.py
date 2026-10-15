# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Copy this example: https://simpy.readthedocs.io/en/latest/examples/bank_renege.html into UPSTAGE."""

import upstage_des.api as UP
import simpy as SIM
from dataclasses import dataclass

from upstage_des.events import is_event_complete, make_random_timeout


@dataclass
class SimulationData:
    new_customers: int = 5
    interval_customers: float = 10.0
    min_patience: float = 15.0
    max_patience: float = 30.0
    counter_slots: int = 1


class Bank(UP.Actor):
    tellers: SIM.Resource = UP.ResourceState(
        default=SIM.Resource,
        default_kwargs={"capacity": 1},
    ).create()


class Customer(UP.Actor):
    bank: Bank
    time_in_bank: float = UP.State(default=0.0).create()
    status: str = UP.State(default="", recording=True).create()
    tolerance: tuple[float, float]


class CustomerTask(UP.Task):
    def task(self, *, actor: Customer) -> UP.TASK_GEN:
        actor.status = "Entering"
        # UPSTAGE's resource interface is a special object
        # that first yields on getting the resource. When you yield again,
        # it gives the resource back.
        get_teller = actor.bank.tellers.request()
        wait = make_random_timeout(*actor.tolerance)
        st = self.env.now
        yield get_teller | wait
        if is_event_complete(wait):
            actor.status = "Impatient"
            en = self.env.now
            actor.time_in_bank = en - st
        else:
            actor.status = "Teller"
            yield UP.Timeout(10, time_units="minutes")
        
        # No matter what, give the teller back
        actor.bank.tellers.release(get_teller)
        
        actor.status = "Leaving"

    def on_interrupt(self, *, actor: Customer, cause: str) -> UP.InterruptStates:
        actor.write_to_log("Interrupting for %s", cause)
        return UP.InterruptStates.RESTART


customer_net = UP.TaskNetworkFactory.from_single_terminating(
    "customer_net",
    task_class=CustomerTask,
)


def customer_leave_line(cust: Customer) -> UP.SIMPY_GEN:
    rng = UP.get_stage().random
    do_interrupt = rng.random() <= 0.5
    if do_interrupt:
        yield make_random_timeout(*cust.tolerance)
        task_data = cust.get_must_be_running_task("customer_net")
        if cust.status != "Leaving":
            task_data.process.interrupt("Go to the back of the line")


def spawn_customers(sd: SimulationData, bank: Bank, env: SIM.Environment) -> None:
    for i in range(sd.new_customers):
        cust = Customer(
            name=f"Customer {i}",
            bank=bank,
            tolerance=(sd.min_patience, sd.max_patience)
        )
        t = CustomerTask()
        t.run(actor=cust)
        env.process(customer_leave_line(cust))


def test_bank_example() -> None:
    sd = SimulationData()

    stage = UP.Stage(time_unit="minutes")
    with UP.EnvironmentContext(stage=stage, random_seed=2365867) as env:
        bank = Bank(
            name="First Bank of UPSTAGE",
            # If you ignored this line in typing, it would work.
            # tellers={"capacity": sd.counter_slots},
        )
        bank.update_resource("tellers", capacity=sd.counter_slots)
        spawn_customers(sd, bank, env)
        env.run()
        print(env.now)


test_bank_example()
