# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Classes for UPSTAGE events that feed to simpy."""

from dataclasses import dataclass
from random import Random
from typing import Literal

import pytest

import upstage_des.api as UP
import simpy as SIM

from upstage_des.events import get_event_value, is_event_complete, make_random_timeout, make_timeout_until


class CheckoutLane(UP.Actor):
    customer_queue: SIM.Store = UP.ResourceState(default=SIM.Store).create()


@dataclass
class CashierKnow(UP.Knowledge):
    lane: CheckoutLane
    end_time: float


class Cashier(UP.Actor):
    scan_speed_per_item: float
    break_time: float
    work_until_break: float
    items_scanned: int = UP.State(default=0, recording=True).create()
    time_worked: float = UP.LinearChangingState(default=0.0).create()
    knowledge: CashierKnow = UP.State(default_factory=CashierKnow.make_blank).create()


class Manager(UP.Actor):
    doors_open_hrs: float = 8.
    doors_close_hrs: float = 17.0
    lanes: list[CheckoutLane] = UP.State(default_factory=list).create()


class Customer(UP.Actor):
    number_of_items: int
    events: str = UP.State(default="Creation", recording=True).create()
    payment_method: Literal["cash", "card"] = UP.State(
        default="card",
        type_check_each=True,
    ).create()


class Arrive(UP.DecisionTask):
    def make_decision(self, *, actor: Cashier) -> None:
        # find the manager and pick a lane
        manager: Manager = UP.get_entities_by_class("Manager")[0]
        lane = UP.get_stage().random.choice(manager.lanes)
        actor.knowledge.lane = lane
        actor.knowledge.end_time = manager.doors_close_hrs
        actor.time_worked = 0.0


class WaitInLane(UP.Task):
    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        lane = actor.knowledge.lane
        customer_get = lane.customer_queue.get()

        actor.activate_linear_state("time_worked", 1.0, task=self)
        time_of_break = actor.get_time_for_state_goal(
            "time_worked",
            actor.work_until_break,
        )
        assert time_of_break is not None

        timeout = make_timeout_until(until_time=time_of_break)
        evt = customer_get | timeout
        yield evt

        actor.deactivate_all_states(task=self)

        if is_event_complete(timeout):
            # go on break
            self.set_actor_task_queue(actor, ["Break"])
            return

        customer: Customer = get_event_value(customer_get)
        customer.events = "Starting"
        for _ in range(customer.number_of_items):
            yield UP.Timeout(actor.scan_speed_per_item)
            actor.items_scanned += 1
        actor.write_to_log(
            "%s used %s to pay",
            customer.name,
            customer.payment_method,
        )
        customer.events = "Ending"


class Break(UP.Task):
    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        # Reset time worked, wait for the break time to end.
        actor.time_worked = 0.0
        time_until_end = actor.knowledge.end_time - self.env.now
        
        if time_until_end < actor.break_time:
            # Closing time!
            self.set_actor_task_queue(actor, ["Close"])
        else:
            yield UP.Timeout(actor.break_time)


class Close(UP.Task):
    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        # Don't do anything, just be done.
        yield UP.Event()


cashier_network = UP.TaskNetworkFactory(
    "CashierNet",
    task_classes={
        Arrive: UP.TaskLinks(
            default=WaitInLane,
            allowed=[WaitInLane],
        ),
        WaitInLane: UP.TaskLinks(
            default=WaitInLane,
            allowed=[Break, WaitInLane],
        ),
        Break: UP.TaskLinks(
            default=WaitInLane,
            allowed=[WaitInLane, Close],
        ),
        Close: UP.TaskLinks(
            default=None,
            allowed=[],
        )
    },
)

# from upstage_des.utils.task_net_viz import to_mermaid

# mmd = to_mermaid(cashier_network)
# print(mmd)


def customer_spawning(
    n_cust: int,
    every: tuple[float, float],
    rng: Random,
    lane: CheckoutLane,
) -> UP.SIMPY_GEN:
    """Create customers."""
    for i in range(n_cust):
        yield make_random_timeout(*every)
        cust = Customer(
            name=f"Customer {i}",
            number_of_items=rng.randint(10, 60),
            payment_method=rng.choice(["cash", "card"])
        )
        # Turn the upstage event into the simpy event.
        yield lane.customer_queue.put(cust)


def test_the_customer_error() -> None:
    with UP.EnvironmentContext() as env:
        c = Customer(
            name="Billy",
            number_of_items=23,
            payment_method="cash",
        )

        with pytest.raises(TypeError):
            c.payment_method = "bitcoin" # type: ignore[assignment]

def test_cashier() -> None:
    # Run the simple model
    with UP.EnvironmentContext(random_seed=345871) as env:
        cashier = Cashier(
            name="Theoden",
            scan_speed_per_item=5 / 3600.,
            break_time=15.0 / 60,
            work_until_break=2.0,
        )
        assert cashier.knowledge.lane is UP.EMPTY_KNOWLEDGE

        line = CheckoutLane(
            name="Aise 1",
        )

        manager = Manager(
            name="Manage",
            doors_close_hrs=17.0,
            lanes=[line],
        )        

        net = cashier_network.make_network()
        cashier.add_task_network(net)
        cashier.start_network_loop(net.name, "Arrive")

        env.process(
            customer_spawning(
                n_cust=20,
                every=(0.1, 0.2),
                rng=UP.get_stage().random,
                lane=line
            )
        )
        env.run()
        print(f"Time of completion: {env.now}")
        print(f"Total items scanned: {cashier.items_scanned}")
        print(cashier._state_histories["items_scanned"])

test_cashier()
