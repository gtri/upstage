# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from typing import Any

import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN


class Mover(UP.Actor):
    fuel = UP.SharedLinearChangingState(recording=True)
    fuel_burn = UP.State[float](valid_types=(float,), frozen=True)
    location = UP.CartesianLocationChangingState(recording=True)
    speed = UP.State[float](valid_types=(float, int), recording=True)

    def get_distance(
        self, waypoints: list[UP.GeodeticLocation] | list[UP.CartesianLocation]
    ) -> float:
        d = waypoints[0] - self.location
        for i in range(1, len(waypoints)):
            d += waypoints[i] - waypoints[i - 1]
        return d


class Fly(UP.Task):
    def task(self, *, actor: Mover) -> TASK_GEN:
        destinations = list(self.get_actor_knowledge(actor, "destinations"))
        self.clear_actor_knowledge(actor, "destinations")
        actor.activate_state(
            state="location",
            task=self,
            speed=actor.speed,
            waypoints=destinations,
        )
        actor.activate_state(
            state="fuel",
            task=self,
            rate=actor.fuel_burn,
        )
        dist = actor.get_distance(destinations)
        time = dist / actor.speed
        yield UP.Wait(time)
        actor.deactivate_all_states(task=self)

    def on_interrupt(self, *, actor: Mover, cause: Any) -> UP.InterruptStates:
        # Allow subclassing to run a check prior to this
        # and input "restart" if they want.
        reason = None
        if isinstance(cause, UP.NucleusInterrupt):
            if cause.state_name == "speed":
                reason = "restart"
        if reason == "restart":
            rem_wypts = actor.get_remaining_waypoints(
                location_state="location",
            )
            self.set_actor_knowledge(
                actor,
                "destinations",
                rem_wypts,
                overwrite=True,
            )
            return self.INTERRUPT.RESTART
        return self.INTERRUPT.END


fly_factory = UP.TaskNetworkFactory.from_single_looping("Fly", Fly)
fly_end_factory = UP.TaskNetworkFactory.from_single_terminating("Fly", Fly)
