# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for license terms.

from collections.abc import Generator
from typing import Any

import simpy as SIM

import upstage_des.api as UP
from upstage_des.task import InterruptStates
from upstage_des.type_help import SIMPY_GEN, TASK_GEN


class Cashier(UP.Actor):
    scan_speed = UP.State[float](
        valid_types=(float,),
        frozen=True,
    )
    time_until_break = UP.State[float](
        default=120.0,
        valid_types=(float,),
        frozen=True,
    )
    breaks_until_done = UP.State[int](default=2, valid_types=int)
    breaks_taken = UP.State[int](default=0, valid_types=int, recording=True)
    items_scanned = UP.State[int](
        default=0,
        valid_types=(int,),
        recording=True,
    )
    time_scanning = UP.LinearChangingState(
        default=0.0,
        valid_types=(float,),
    )
    messages = UP.ResourceState[UP.SelfMonitoringStore](
        default=UP.SelfMonitoringStore,
    )

    def time_left_to_break(self) -> float:
        elapsed = self.env.now - float(self.get_knowledge("start_time", must_exist=True))
        return self.time_until_break - elapsed


class CheckoutLane(UP.Actor):
    customer_queue = UP.ResourceState[UP.SelfMonitoringStore](
        default=UP.SelfMonitoringStore,
    )


class StoreBoss(UP.UpstageBase):
    def __init__(self, lanes: list[CheckoutLane]) -> None:
        self.lanes = lanes
        self._lane_map: dict[CheckoutLane, Cashier] = {}

    def get_lane(self, cashier: Cashier) -> CheckoutLane:
        possible = [lane for lane in self.lanes if lane not in self._lane_map]
        lane = self.stage.random.choice(possible)
        self._lane_map[lane] = cashier
        return lane

    def clear_lane(self, cashier: Cashier) -> None:
        to_del = [name for name, cash in self._lane_map.items() if cash is cashier]
        for name in to_del:
            del self._lane_map[name]


class CashierBreakTimer(UP.Task):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        yield UP.Wait(actor.time_until_break)
        actor.interrupt_network("CashierJob", cause=dict(reason="BREAK TIME"))


class InterruptibleTask(UP.Task):
    def on_interrupt(self, *, actor: Cashier, cause: dict[str, Any]) -> InterruptStates:
        # We will only interrupt with a dictionary of data
        assert isinstance(cause, dict)
        job_list: list[str]

        if cause["reason"] == "BREAK TIME":
            job_list = ["Break"]
        elif cause["reason"] == "NEW JOB":
            job_list = cause["job_list"]
        else:
            raise UP.SimulationError("Unexpected interrupt cause")

        # determine time until break
        time_left = actor.time_left_to_break()
        # if there are only five minutes left, take the break and queue the task.
        if time_left <= 5.0 and "Break" not in job_list:
            job_list = ["Break"] + job_list

        # Ignore the interrupt, unless we've marked it to know otherwise
        marker = self.get_marker() or "none"
        if marker == "on break":
            if "Break" in job_list:
                job_list.remove("Break")

        self.clear_actor_task_queue(actor)
        self.set_actor_task_queue(actor, job_list)
        if marker == "cancellable":
            return self.INTERRUPT.END
        return self.INTERRUPT.IGNORE


class GoToWork(UP.Task):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Go to work"""
        yield UP.Wait(15.0)


class TalkToBoss(UP.DecisionTask):
    def make_decision(self, *, actor: Cashier) -> None:
        """Zero-time task to get information."""
        boss: StoreBoss = self.stage.boss
        lane = boss.get_lane(actor)
        self.set_actor_knowledge(actor, "checkout_lane", lane, overwrite=False)
        actor.breaks_taken = 0
        self.set_actor_knowledge(actor, "start_time", self.env.now, overwrite=True)
        # Convenient spot to run the timer.
        CashierBreakTimer().run(actor=actor)


class WaitInLane(InterruptibleTask):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Wait until break time, or a customer."""
        lane: CheckoutLane = self.get_actor_knowledge(
            actor,
            "checkout_lane",
            must_exist=True,
        )
        customer_arrival = UP.Get(lane.customer_queue)

        self.set_marker(marker="cancellable")
        yield customer_arrival

        customer: int = customer_arrival.get_value()
        self.set_actor_knowledge(actor, "customer", customer, overwrite=True)


class DoCheckout(InterruptibleTask):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Do the checkout"""
        items: int = self.get_actor_knowledge(
            actor,
            "customer",
            must_exist=True,
        )
        per_item_time = actor.scan_speed / items
        actor.activate_linear_state(
            state="time_scanning",
            rate=1.0,
            task=self,
        )
        for _ in range(items):
            yield UP.Wait(per_item_time)
            actor.items_scanned += 1
        actor.deactivate_all_states(task=self)
        # assume 2 minutes to take payment
        yield UP.Wait(2.0)


class Break(UP.DecisionTask):
    def make_decision(self, *, actor: Cashier) -> None:
        """Decide what kind of break we are taking."""
        actor.breaks_taken += 1

        # we might have jobs queued
        queue = self.get_actor_task_queue(actor) or []
        if "Break" in queue:
            raise UP.SimulationError("Odd task network state")
        self.clear_actor_task_queue(actor)

        if actor.breaks_taken == actor.breaks_until_done:
            self.set_actor_task_queue(actor, ["NightBreak"])
        elif actor.breaks_taken > actor.breaks_until_done:
            raise UP.SimulationError("Too many breaks taken")
        else:
            self.set_actor_task_queue(actor, ["ShortBreak"] + queue)


class ShortBreak(InterruptibleTask):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Take a short break."""
        self.set_marker("on break")
        yield UP.Wait(15.0)
        self.set_actor_knowledge(actor, "start_time", self.env.now, overwrite=True)
        CashierBreakTimer().run(actor=actor)


class NightBreak(UP.Task):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Go home and rest."""
        self.clear_actor_knowledge(actor, "checkout_lane")
        self.stage.boss.clear_lane(actor)
        yield UP.Wait(60 * 12.0)


class Restock(UP.Task):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Restock."""
        yield UP.Wait(10.0)


task_classes = {
    "GoToWork": GoToWork,
    "TalkToBoss": TalkToBoss,
    "WaitInLane": WaitInLane,
    "DoCheckout": DoCheckout,
    "Break": Break,
    "ShortBreak": ShortBreak,
    "NightBreak": NightBreak,
    "Restock": Restock,
}

task_links = {
    "GoToWork": UP.TaskLinks(default="TalkToBoss", allowed=["TalkToBoss"]),
    "TalkToBoss": UP.TaskLinks(default="WaitInLane", allowed=["WaitInLane"]),
    "WaitInLane": UP.TaskLinks(default="DoCheckout", allowed=["DoCheckout", "Break"]),
    "DoCheckout": UP.TaskLinks(default="WaitInLane", allowed=["WaitInLane", "Break"]),
    "Break": UP.TaskLinks(default="ShortBreak", allowed=["ShortBreak", "NightBreak"]),
    "ShortBreak": UP.TaskLinks(default="WaitInLane", allowed=["WaitInLane"]),
    "NightBreak": UP.TaskLinks(default="GoToWork", allowed=["GoToWork"]),
    "Restock": UP.TaskLinks(default="WaitInLane", allowed=["WaitInLane", "Break"]),
}

cashier_task_network = UP.TaskNetworkFactory(
    name="CashierJob",
    task_classes=task_classes,
    task_links=task_links,
)


class CashierMessages(UP.Task):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        getter = UP.Get(actor.messages)
        yield getter
        tasks_needed: list[str] | str = getter.get_value()
        tasks_needed = [tasks_needed] if isinstance(tasks_needed, str) else tasks_needed
        actor.interrupt_network("CashierJob", cause=dict(reason="NEW JOB", job_list=tasks_needed))


cashier_message_net = UP.TaskNetworkFactory.from_single_looping("Messages", CashierMessages)


def customer_spawner(
    env: SIM.Environment,
    lanes: list[CheckoutLane],
) -> Generator[SIM.Event, None, None]:
    # sneaky way to get access to stage
    stage = lanes[0].stage
    while True:
        hrs = env.now / 60
        time_of_day = hrs // 24
        if time_of_day <= 8 or time_of_day >= 15.5:
            time_until_open = (24 - time_of_day) + 8
            yield env.timeout(time_until_open)

        lane_pick = stage.random.choice(lanes)
        number_pick = stage.random.randint(3, 17)
        yield lane_pick.customer_queue.put(number_pick)
        yield UP.Wait.from_random_uniform(5.0, 30.0).as_event()


def manager_process(boss: StoreBoss, cashiers: list[Cashier]) -> SIMPY_GEN:
    while True:
        # Use the random uniform feature, but convert the UPSTAGE event to simpy
        # because this is a simpy only process
        yield UP.Wait.from_random_uniform(30.0, 90.0).as_event()
        possible = [
            cash
            for cash in cashiers
            if getattr(cash.get_running_task("CashierJob"), "name", "") != "NightBreak"
        ]
        if not possible:
            return
        cash = boss.stage.random.choice(possible)
        yield cash.messages.put(["Restock"])


def test_cashier_example() -> None:
    with UP.EnvironmentContext(initial_time=8 * 60) as env:
        UP.add_stage_variable("time_unit", "min")
        cashier = Cashier(
            name="Bob",
            scan_speed=1.0,
            time_until_break=120.0,
            breaks_until_done=4,
            debug_log=True,
        )
        lane_1 = CheckoutLane(name="Lane 1")
        lane_2 = CheckoutLane(name="Lane 2")
        boss = StoreBoss(lanes=[lane_1, lane_2])

        UP.add_stage_variable("boss", boss)

        net = cashier_task_network.make_network()
        cashier.add_task_network(net)
        cashier.start_network_loop(net.name, "GoToWork")

        net = cashier_message_net.make_network()
        cashier.add_task_network(net)
        cashier.start_network_loop(net.name, "CashierMessages")

        customer_proc = customer_spawner(env, [lane_1, lane_2])
        _ = env.process(customer_proc)

        _ = env.process(manager_process(boss, [cashier]))

        env.run(until=20 * 60)

    for line in cashier.get_log():
        if "Interrupt" in line:
            print(line)

    print(cashier.items_scanned)


if __name__ == "__main__":
    test_cashier_example()
