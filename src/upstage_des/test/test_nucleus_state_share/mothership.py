# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

from typing import Any

import simpy as SIM

import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN

from .mover import Mover


class Mothership(Mover):
    fuel_ports_in_use = UP.State[int](valid_types=(int,))
    fuel_ports_max = UP.State[int](valid_types=(int,), frozen=True)
    messages = UP.ResourceState[UP.SelfMonitoringStore](
        default=UP.SelfMonitoringStore, valid_types=(UP.SelfMonitoringStore, SIM.Store)
    )


class DispenseFuel(UP.Task):
    def task(self, *, actor: Mothership) -> TASK_GEN:
        draws = self.get_actor_knowledge(actor, "fuel_users", must_exist=False)
        draws = {} if draws is None else draws
        total_draw = sum(draws.values())
        actor.activate_state(
            state="fuel",
            task=self,
            rate=total_draw,
        )
        # Infinite wait!
        # We use Nucleus to go to the interrupt.
        yield UP.Event()

    def on_interrupt(self, *, actor: Mothership, cause: Any) -> UP.InterruptStates:
        # No matter what, restart
        return self.INTERRUPT.RESTART


give_fuel_factory = UP.TaskNetworkFactory.from_single_looping("GiveFuel", DispenseFuel)


class CrewMember(UP.Task):
    def _user_add(self, actor: Mothership, vehicle: Mover, add: float) -> int:
        know = self.get_actor_knowledge(actor, "fuel_users")
        know = {} if know is None else know
        know[vehicle] = add
        self.set_actor_knowledge(actor, "fuel_users", know, overwrite=True)
        return len(know)

    def _user_remove(self, actor: Mothership, vehicle: Mover) -> int:
        know = self.get_actor_knowledge(actor, "fuel_users")
        know = {} if know is None else know
        del know[vehicle]
        self.set_actor_knowledge(actor, "fuel_users", know, overwrite=True)
        return len(know)

    def task(self, *, actor: Mothership) -> TASK_GEN:
        # receive a message that someone is ready, then update fuel_users
        msg = yield UP.Get(actor.messages)
        vehicle, draw = msg
        if draw == 0:
            ports = self._user_remove(actor, vehicle)
        else:
            ports = self._user_add(actor, vehicle, draw)
            # kill some time to send a message back
            yield UP.Wait(5 / 60)
            yield UP.Put(vehicle.messages, "GO")
        actor.fuel_ports_in_use = ports


crew_factory = UP.TaskNetworkFactory.from_single_looping("crew", CrewMember)
