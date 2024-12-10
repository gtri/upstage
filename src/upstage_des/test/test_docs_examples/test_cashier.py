# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from collections.abc import Generator

import simpy as SIM

import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN


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
        self.set_actor_knowledge(actor, "start_time", self.env.now)


class WaitInLane(UP.Task):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Wait until break time, or a customer."""
        lane: CheckoutLane = self.get_actor_knowledge(
            actor,
            "checkout_lane",
            must_exist=True,
        )
        customer_arrival = UP.Get(lane.customer_queue)

        start_time = self.get_actor_knowledge(
            actor,
            "start_time",
            must_exist=True,
        )
        break_start = start_time + actor.time_until_break
        wait_until_break = break_start - self.env.now
        if wait_until_break < 0:
            self.set_actor_task_queue(actor, ["Break"])
            return

        break_event = UP.Wait(wait_until_break)

        yield UP.Any(customer_arrival, break_event)

        if customer_arrival.is_complete():
            customer: int = customer_arrival.get_value()
            self.set_actor_knowledge(actor, "customer", customer, overwrite=True)
        else:
            customer_arrival.cancel()
            self.set_actor_task_queue(actor, ["Break"])


class DoCheckout(UP.Task):
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
        if actor.breaks_taken == actor.breaks_until_done:
            self.set_actor_task_queue(actor, ["NightBreak"])
        elif actor.breaks_taken > actor.breaks_until_done:
            raise UP.SimulationError("Too many breaks taken")
        else:
            self.set_actor_task_queue(actor, ["ShortBreak"])


class ShortBreak(UP.Task):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Take a short break."""
        yield UP.Wait(15.0)
        self.set_actor_knowledge(actor, "start_time", self.env.now, overwrite=True)


class NightBreak(UP.Task):
    def task(self, *, actor: Cashier) -> TASK_GEN:
        """Go home and rest."""
        self.clear_actor_knowledge(actor, "checkout_lane")
        yield UP.Wait(60 * 12.0)


task_classes = {
    "GoToWork": GoToWork,
    "TalkToBoss": TalkToBoss,
    "WaitInLane": WaitInLane,
    "DoCheckout": DoCheckout,
    "Break": Break,
    "ShortBreak": ShortBreak,
    "NightBreak": NightBreak,
}

task_links = {
    "GoToWork": UP.TaskLinks(default="TalkToBoss", allowed=["TalkToBoss"]),
    "TalkToBoss": UP.TaskLinks(default="WaitInLane", allowed=["WaitInLane"]),
    "WaitInLane": UP.TaskLinks(default="DoCheckout", allowed=["DoCheckout", "Break"]),
    "DoCheckout": UP.TaskLinks(default="WaitInLane", allowed=["WaitInLane"]),
    "Break": UP.TaskLinks(default="ShortBreak", allowed=["ShortBreak", "NightBreak"]),
    "ShortBreak": UP.TaskLinks(default="WaitInLane", allowed=["WaitInLane"]),
    "NightBreak": UP.TaskLinks(default="GoToWork", allowed=["GoToWork"]),
}


cashier_task_network = UP.TaskNetworkFactory(
    name="CashierJob",
    task_classes=task_classes,
    task_links=task_links,
)


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

        customer_proc = customer_spawner(env, [lane_1, lane_2])
        _ = env.process(customer_proc)

        env.run(until=20 * 60)

    for line in cashier.get_log():
        print(line)


if __name__ == "__main__":
    test_cashier_example()
