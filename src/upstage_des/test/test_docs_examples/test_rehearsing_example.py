# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

import pytest

import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN
from upstage_des.utils import waypoint_time_and_dist


class Plane(UP.Actor):
    speed = UP.State[float]()
    location = UP.CartesianLocationChangingState()
    fuel = UP.LinearChangingState()
    fuel_burn = UP.State[float]()


class Fly(UP.Task):
    def task(self, *, actor: Plane) -> TASK_GEN:
        fly_to: list[UP.CartesianLocation] = self.get_actor_knowledge(
            actor, "destination", must_exist=True
        )
        time, dist = waypoint_time_and_dist(actor.location, fly_to, actor.speed)
        print(f"Rehearsing the task: {self._rehearsing}")
        print(f"\tFlying {dist:.2f} units over {time:.2f} hrs")
        actor.activate_linear_state(
            state="fuel",
            rate=-actor.fuel_burn,
            task=self,
        )
        actor.activate_location_state(
            state="location",
            speed=actor.speed,
            waypoints=fly_to,
            task=self,
        )
        yield UP.Wait(time)
        actor.deactivate_all_states(task=self)


class Search(UP.Task):
    def task(self, *, actor: Plane) -> TASK_GEN:
        search_event = actor.create_knowledge_event(
            name="FOUND SURVIVOR",
            rehearsal_time_to_complete=0.5,
        )
        actor.activate_linear_state(
            state="fuel",
            rate=-actor.fuel_burn,
            task=self,
        )
        yield search_event
        actor.deactivate_all_states(task=self)


class Land(UP.Task):
    def task(self, *, actor: Plane) -> TASK_GEN:
        # Do a landing of some kind
        event = actor.create_knowledge_event(name="DONE", rehearsal_time_to_complete=10.0)
        yield event


def some_preference_function(
    spots: list[UP.CartesianLocation],
) -> UP.CartesianLocation | None:
    """Choose a spot. bvv z

    Args:
        spots (list[UP.CartesianLocation]): List of spots to search at

    Returns:
        UP.CartesianLocation | None: A spot to search or None if we should go home
    """
    return spots[0]


class Planner(UP.DecisionTask):
    def make_decision(self, *, actor: Plane) -> None:
        go_to_loc = some_preference_function(self.stage.search_spots)
        if go_to_loc is None:  # implies we are done with searching
            self.set_actor_task_queue(actor, ["Fly", "Land"])
        else:
            self.set_actor_knowledge(actor, "destination", go_to_loc, overwrite=True)
            self.set_actor_task_queue(actor, ["Fly", "Search"])

    def rehearse_decision(self, *, actor: Plane) -> None:
        # Pop off a destination from the queue, or go "home"
        next_dests: list[list[UP.CartesianLocation]] | None = self.get_actor_knowledge(
            actor, "destination_plan", must_exist=False
        )
        dests: list[UP.CartesianLocation]
        task_queue: list[str]
        if not next_dests:  # fly home
            dests = [UP.CartesianLocation(0, 0)]
            task_queue = ["Fly", "Land"]
        else:  # pop a location from the plan
            dests = next_dests.pop(0)
            self.set_actor_knowledge(actor, "destination_plan", next_dests, overwrite=True)
            task_queue = ["Fly", "Search"]

        self.set_actor_knowledge(actor, "destination", dests, overwrite=True)
        self.set_actor_task_queue(actor, task_queue)


task_classes = {"Fly": Fly, "Search": Search, "Planner": Planner, "Land": Land}
task_links = {
    "Fly": UP.TaskLinks(default="Search", allowed=["Fly", "Land", "Search"]),
    "Search": UP.TaskLinks(default="Planner", allowed=["Planner"]),
    "Planner": UP.TaskLinks(default="Fly", allowed=["Fly"]),
    "Land": UP.TaskLinks(default=None, allowed=["Fly"]),
}
search_network = UP.TaskNetworkFactory("SearchNet", task_classes, task_links)


def test_model() -> None:
    with UP.EnvironmentContext() as env:
        search_locs = [
            [UP.CartesianLocation(x, y)]
            for x, y in [
                (10, 20),
                (30, 10),
                (15, 15),
            ]
        ]

        plane = Plane(
            name="searcher",
            speed=2,
            fuel=200,
            fuel_burn=5.0,
            location=UP.CartesianLocation(20, 10),
            debug_log=True,
        )
        net = search_network.make_network()
        plane.add_task_network(net)

        new_plane = plane.rehearse_network(
            net.name,
            task_name_list=["Planner", "Fly", "Search"],
            knowledge={"destination_plan": search_locs},
            end_task="Land",
        )
        print(f"Fuel left: {new_plane.fuel}")
        print(f"Time passed: {new_plane.env.now}")
        print(f"Actual time passed: {env.now}")
        assert pytest.approx(new_plane.fuel) == 6.18148
        assert pytest.approx(new_plane.env.now) == 38.76370356758358
        assert plane.fuel == 200
        assert env.now == 0
