# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""The file contains the Nucleus features of UPSTAGE."""

from collections import defaultdict
from typing import Any

from upstage_des.actor import Actor
from upstage_des.base import UpstageError
from upstage_des.task_network import TaskNetwork


class NucleusInterrupt:
    """A data container for interrupting nucleus events."""

    def __init__(self, name: str, value: Any) -> None:
        """A container for Nucleus interrupt data.

        Args:
            name (str): Name of the state causing the interrupt.
            value (Any): The state value
        """
        self.state_name = name
        self.value = value

    def __repr__(self) -> str:
        return f"NucleusInterrupt: {self.state_name} {self.value}"


class TaskNetworkNucleus:
    """The nucleus, for state-based task network signaling."""

    def _attach(self) -> None:
        """Attach the nucleus to an actor."""
        self._actor.log(f"Attaching {self} as a state listener!")
        if self._actor._state_listener is not None:
            raise UpstageError(f"{self._actor} already has a nucleus attached.")
        self._actor._state_listener = self

    def __init__(
        self,
        *,
        actor: Actor,
    ) -> None:
        """Create a task network nucleus on an Actor.

        Args:
            actor (Actor): The actor instance.
        """
        self._actor = actor
        self._state_map: dict[str, set[str]] = defaultdict(set)
        self._network_map: dict[str, set[str]] = defaultdict(set)
        self._attach()

    def add_network(
        self,
        network_name: str | TaskNetwork,
        watch_states: list[str],
    ) -> None:
        """Add a network to the nucleus for state management.

        Args:
            network_name (str | TaskNetwork):  A task network that works on this nucleus/actor
            watch_states (list[str]): States that - when changed - cause the network to change.
        """
        if isinstance(network_name, TaskNetwork):
            network_name = network_name.name
        if network_name not in self._actor._task_networks:
            raise UpstageError(f"No network {network_name} in {self._actor}")
        for state in watch_states:
            self._state_map[state].add(network_name)
            self._network_map[network_name].add(state)
            # if not hasattr(actor, state):
            #     raise SimulationError(f"State {state} does not exist on actor")

    def remove_network(
        self,
        network_name: str | TaskNetwork,
    ) -> None:
        """Remove a network from nucleus.

        Args:
            network_name (str | TaskNetwork): A task network that works on this nucleus/actor
        """
        if isinstance(network_name, TaskNetwork):
            network_name = network_name.name
        if network_name not in self._actor._task_networks:
            raise UpstageError(f"No network {network_name} in {self._actor}")
        for state in self._network_map[network_name]:
            self._state_map[state].remove(network_name)
        del self._network_map[network_name]

    def send_change(self, state_name: str, state_value: Any) -> None:
        """Send a change notification for a given state.

        Args:
            state_name (str): The state's name.
            state_value (Any): The value of the state.
        """
        for net_name in self._state_map.get(state_name, []):
            net: TaskNetwork | None = self._actor._task_networks.get(net_name, None)
            if net is None:
                raise UpstageError(f"No network {net_name} in {self._actor}")
            proc = net._current_task_proc
            if proc is not None:
                proc.interrupt(
                    cause=NucleusInterrupt(state_name, state_value),
                )
