# Copyright (C) 2025 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for license terms.

from collections.abc import Generator
from typing import Any

import simpy as SIM

import upstage_des.api as UP

BREAK_TIME = 15.0


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
    current_task = UP.State[str](default="init", recording=True)

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
    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        times = [
            self.env.now + actor.time_until_break * b for b in range(1, actor.breaks_until_done + 1)
        ]
        for t in times:
            yield UP.Wait(t - self.env.now)
            actor.interrupt_network("CashierJob", cause=dict(reason="BREAK TIME"))


class InterruptibleTask(UP.Task):
    def on_interrupt(self, *, actor: Cashier, cause: dict[str, Any]) -> UP.InterruptStates:
        assert isinstance(cause, dict)
        job_list: list[str]

        if cause["reason"] == "BREAK TIME":
            job_list = ["Break"]
        elif cause["reason"] == "NEW JOB":
            job_list = cause["job_list"]
        else:
            raise UP.SimulationError("Unexpected interrupt cause")

        time_left = actor.time_left_to_break()
        if time_left <= 5.0 and "Break" not in job_list:
            job_list = ["Break"] + job_list

        marker = self.get_marker() or "none"
        if marker == "on break" and "Break" in job_list:
            job_list.remove("Break")

        self.clear_actor_task_queue(actor)
        self.set_actor_task_queue(actor, job_list)
        if marker == "cancellable":
            return self.INTERRUPT.END
        return self.INTERRUPT.IGNORE


class GoToWork(UP.Task):
    def on_enter(self, *, actor: Cashier) -> None:
        actor.current_task = "Going to Work"

    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        yield UP.Wait(15.0)


class TalkToBoss(UP.Task):
    """Zero-time setup: get lane assignment and start break timer.

    Uses on_enter instead of DecisionTask.
    """

    def on_enter(self, *, actor: Cashier) -> None:
        actor.current_task = "Talking to Boss"
        boss: StoreBoss = self.stage.boss
        lane = boss.get_lane(actor)
        actor.set_knowledge("checkout_lane", lane, overwrite=False)
        actor.breaks_taken = 0
        actor.set_knowledge("start_time", self.env.now, overwrite=True)
        CashierBreakTimer().run(actor=actor)

    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        yield UP.Wait(0.0)


class WaitInLane(InterruptibleTask):
    def on_enter(self, *, actor: Cashier) -> None:
        actor.current_task = "Waiting for Customer"

    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
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
    def on_enter(self, *, actor: Cashier) -> None:
        actor.current_task = "Checking out a Customer"

    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
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
        yield UP.Wait(2.0)


def _is_night_break(actor: Cashier) -> bool:
    """Guard: true when all breaks are used up."""
    return actor.breaks_taken >= actor.breaks_until_done


class Break(UP.Task):
    """Zero-time break decision — guards choose ShortBreak vs NightBreak.

    Uses on_enter to increment the counter instead of DecisionTask.
    """

    def on_enter(self, *, actor: Cashier) -> None:
        actor.current_task = "Break"
        actor.breaks_taken += 1

    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        yield UP.Wait(0.0)


class ShortBreak(InterruptibleTask):
    def on_enter(self, *, actor: Cashier) -> None:
        actor.current_task = "On Short Break"

    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        self.set_marker("on break")
        yield UP.Wait(BREAK_TIME)
        self.set_actor_knowledge(actor, "start_time", self.env.now, overwrite=True)


class NightBreak(UP.Task):
    def on_enter(self, *, actor: Cashier) -> None:
        actor.current_task = "Home for the Night"

    def on_exit(self, *, actor: Cashier) -> None:
        actor.clear_knowledge("checkout_lane")
        self.stage.boss.clear_lane(actor)

    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        yield UP.Wait(60 * 12.0)


class Restock(InterruptibleTask):
    def on_enter(self, *, actor: Cashier) -> None:
        actor.current_task = "Restock"

    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        self.set_marker("quick task")
        yield UP.Wait(10.0)


# --- Task Network (class-reference API with guards) ---

cashier_task_network = UP.TaskNetworkFactory(
    name="CashierJob",
    task_links={
        GoToWork: UP.TaskLinks(transitions=[(TalkToBoss, None, "arrived")]),
        TalkToBoss: UP.TaskLinks(transitions=[(WaitInLane, None, "lane assigned")]),
        WaitInLane: UP.TaskLinks(
            transitions=[(DoCheckout, None, "customer arrived")],
            allowed=[DoCheckout, Break],
        ),
        DoCheckout: UP.TaskLinks(
            transitions=[(WaitInLane, None, "checkout done")],
            allowed=[WaitInLane, Break],
        ),
        Break: UP.TaskLinks(
            transitions=[
                (NightBreak, _is_night_break, "all breaks used"),
                (ShortBreak, None, "breaks remaining"),
            ],
        ),
        ShortBreak: UP.TaskLinks(transitions=[(WaitInLane, None, "break over")]),
        NightBreak: UP.TaskLinks(transitions=[(GoToWork, None, "next day")]),
        Restock: UP.TaskLinks(
            transitions=[(WaitInLane, None, "restocked")],
            allowed=[WaitInLane, Break],
        ),
    },
)


class CashierMessages(UP.Task):
    def task(self, *, actor: Cashier) -> UP.TASK_GEN:
        getter = UP.Get(actor.messages)
        yield getter
        tasks_needed: list[str] | str = getter.get_value()
        tasks_needed = [tasks_needed] if isinstance(tasks_needed, str) else tasks_needed
        actor.interrupt_network("CashierJob", cause=dict(reason="NEW JOB", job_list=tasks_needed))


cashier_message_net = UP.TaskNetworkFactory.from_single_looping("Messages", CashierMessages)


def customer_spawner(
    env: SIM.Environment,
    lanes: list[CheckoutLane],
    max_wait: float = 30.0,
) -> Generator[SIM.Event, None, None]:
    stage = lanes[0].stage
    t_until = (8 * 60 + 1) - env.now
    t_until = max(t_until, 0.0)
    yield env.timeout(t_until)
    while True:
        hrs = env.now / 60
        days = hrs // 24
        time_of_day = hrs % 24
        if time_of_day >= 18.5:
            time_at_open = 24 * (days + 1) + 8
            mins_to_open = (time_at_open - hrs) * 60
            yield env.timeout(mins_to_open)

        lane_pick = stage.random.choice(lanes)
        number_pick = stage.random.randint(3, 17)
        yield lane_pick.customer_queue.put(number_pick)
        yield UP.Wait.from_random_uniform(5.0, max_wait).as_event()


def manager_process(boss: StoreBoss, cashiers: list[Cashier]) -> UP.SIMPY_GEN:
    while True:
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
