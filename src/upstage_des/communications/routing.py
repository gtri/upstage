# Copyright (C) 2025 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Comms routing from a routing table lookup."""

from collections import defaultdict, deque

from upstage_des.actor import Actor
from upstage_des.base import SimulationError
from upstage_des.communications.comms import CommsManagerBase, Message
from upstage_des.task import process
from upstage_des.type_help import SIMPY_GEN


def _shortest_path(network: dict[str, set[str]], start: str, goal: str) -> list[str]:
    """Dijkstra for network path."""
    queue = deque([(start, [start])])
    visited = {start}

    while queue:
        node, path = queue.popleft()
        for neighbor in network.get(node, set()):
            if neighbor == goal:
                return path + [neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return []


class RoutingCommsManagerBase(CommsManagerBase):
    """A comms manager that routes messages according to a network."""

    def __init__(
        self,
        *,
        name: str,
        mode: str | None = None,
        send_time: float = 0.0,
        retry_max_time: float = 1.0,
        retry_rate: float = 0.166667,
        global_ignore: bool = False,
        debug_logging: bool = False,
    ) -> None:
        """Create a comms transfer manager.

        Args:
            name (str): Give the instance a unique name for logging purposes
            mode (str):  The name of the mode comms are occurring over. Used for automated
                detection of actor comms interfaces. Default is None, which requires
                explicit connections.
            send_time (float, optional): Time to send a message, by default 0.0
            retry_max_time (float, optional): Amount of time (in sim units) to try
                resending a message. Default is 1
            retry_rate (float, optional): How often (in sim units) to try re-sending
                a message. Default is 10/60
            global_ignore (bool, optional): If a bad node is ignored forever.
                Defautls to False.
            debug_logging : bool, optional
                Turn on or off logging, by default False
        """
        super().__init__(
            name=name,
            mode=mode,
            init_entities=None,
            send_time=send_time,
            retry_max_time=retry_max_time,
            retry_rate=retry_rate,
            debug_logging=debug_logging,
        )
        self.global_ignore = global_ignore

    def connect(self, entity: Actor, comms_store_name: str) -> None:
        """RoutingManagerBase doesn't allow this method."""
        raise SimulationError(
            "RoutingCommsManager doesn't use connect(). Use connect_nodes() instead."
        )

    def select_hop(
        self, source: Actor, dest: Actor, ignore_nodes: list[Actor] | None = None
    ) -> Actor | None:
        """Subclassable method for selecting the next hop in a route.

        Args:
            source (Actor): Current point
            dest (Actor): Message Destination
            ignore_nodes (list[Actor], optional): Nodes to exclude.

        Returns:
            Actor | None: Next hop to make. None if blocked path
        """
        raise NotImplementedError("Implement this method.")

    @process
    def _do_transmit(self, message: Message, destination: Actor) -> SIMPY_GEN:
        # Take the message through the routing table
        curr = message.sender
        failed_nodes: list[Actor] = []
        while curr is not destination:
            hop = self.select_hop(curr, destination, failed_nodes)
            if hop is None:
                self._log_attempt(message, curr, destination, "No message route available")
                return
            can_send = yield from self._attempt(message, curr, hop)
            # replan on fail
            if not can_send:
                failed_nodes.append(hop)
                # take this hop and see if we can send it
                continue
            # we can send it
            self._log_attempt(message, curr, hop, "Moved message")
            if self.send_time > 0:
                yield self.env.timeout(self.send_time)
            # Allow all nodes again
            if not self.global_ignore:
                failed_nodes = []
            # Update position in the network
            curr = hop
        # we've reached the destination
        self._log_attempt(message, curr, destination, "Destination reached")
        message.time_sent = self.env.now
        store = self.store_from_actor(destination)
        yield store.put(message)


class RoutingTableCommsManager(RoutingCommsManagerBase):
    """Route comms according to a pre-defined network.

    Nodes (Actors) must be explicitly connected, and this manager will
    route through shortest number of hops.

    Allows for degraded comms and comms retry. If a link is not degraded,
    after the retry fails the network will re-plan a route assuming the intermediate
    destination node is no longer available.

    The behavior is:

    1. Ask for transmit from SOURCE to DEST
    2. Set CURRENT to SOURCE
    3. Find the NEXT in the shortest path from CURRENT to DEST
    4. If there is no path, stop trying to send and end.
    5. Attempt to send to NEXT (this is the degraded comms/retry step)
    6. If it can send, do so. Set CURRENT = NEXT. If NEXT is DEST, Goto 8. Otherwise, Goto 3.
    7. If it can't send, drop NEXT from the route options. Goto 3
    8. Place message in DEST and end.

    Since this is time-based, a link can re-open during transmission. If the
    network has paths:

        A -> B -> C
        A -> D -> E -> F -> G -> H -> C
        E -> B -> C

    and we want to send from A to C, but B is blocked, a retry will have the
    network attempt to take the long way through DEFGHC. If B comes back online
    after the message gets to E, the routing will choose EBC instead.

    If B does not come back online, the router will still try to go to B from E
    since that is shorter. If B is still down, it will take longer due to the
    retry. Set the input ``global_ignore`` to ``True`` to ignore a bad node
    for the entire routing and avoid this behavior.

    Example:

    .. code-block:: python

        class CommNode(Actor):
            messages = CommunicationStore(modes=None)

        with EnvironmentContext() as env:
            nodes = {
                name: CommNode(name=name, messages={"modes":["cup-and-string"]})
                for name in "ABCDEFGH"
            }
            mgr = RoutingTableCommsManager(
                name="StaticManager",
                mode="cup-and-string",
                send_time=1/3600.,
                retry_max_time=20/3600.,
                retry_rate=4/3600.,
            )
            for u, v in ["AB", "BC", "AD", "DE", "EF", "FG", "GH", "HC", "EB"]:
                mgr.connect_nodes(nodes[u], nodes[v])

    """

    def __init__(
        self,
        *,
        name: str,
        mode: str | None = None,
        send_time: float = 0.0,
        retry_max_time: float = 1.0,
        retry_rate: float = 0.166667,
        global_ignore: bool = False,
        debug_logging: bool = False,
    ) -> None:
        """Create a static network structure for message routing.

        Args:
            name (str): Give the instance a unique name for logging purposes
            mode (str):  The name of the mode comms are occurring over. Used for automated
                detection of actor comms interfaces. Default is None, which requires
                explicit connections.
            send_time (float, optional): Time to send a message, by default 0.0
            retry_max_time (float, optional): Amount of time (in sim units) to try
                resending a message. Default is 1
            retry_rate (float, optional): How often (in sim units) to try re-sending
                a message. Default is 10/60
            global_ignore (bool, optional): If a bad node is ignored forever.
                Defautls to False.
            debug_logging : bool, optional
                Turn on or off logging, by default False
        """
        super().__init__(
            name=name,
            mode=mode,
            send_time=send_time,
            retry_max_time=retry_max_time,
            retry_rate=retry_rate,
            global_ignore=global_ignore,
            debug_logging=debug_logging,
        )
        self._nodes: dict[str, Actor] = {}
        self._network: dict[str, set[str]] = defaultdict(set)

    def connect_nodes(self, u: Actor, v: Actor, two_way: bool = False) -> None:
        """Connect node u to v (one-way).

        Make the connection two-way with the last argument.

        Args:
            u (Actor): The source actor
            v (Actor): Destination actor
            two_way (bool, optional): If the connection is two way. Defaults to False.
        """
        # test that the nodes have a store for comms on the mode of this manager
        for act in [u, v]:
            if self._get_state(act) is None:
                raise SimulationError(f"Actor {act} has no comms store on mode {self.mode}")

        self._nodes[u.name] = u
        self._nodes[v.name] = v
        self._network[u.name].add(v.name)
        if two_way:
            self._network[v.name].add(u.name)

    def select_hop(
        self, source: Actor, dest: Actor, ignore_nodes: list[Actor] | None = None
    ) -> Actor | None:
        """Method for selecting the next hop to make.

        This selects the shortest number of hops.

        Args:
            source (Actor): Starting or current point
            dest (Actor): Destination
            ignore_nodes (list[Actor], optional): Nodes to exclude.

        Returns:
            Actor | None: The next place to go or None if no route.
        """
        u, v = source.name, dest.name
        if u not in self._network:
            return None
        if v in self._network[u]:
            return dest
        ignore_names = [x.name for x in ignore_nodes] if ignore_nodes is not None else []
        net = {k: v - set(ignore_names) for k, v in self._network.items() if k not in ignore_names}
        path = _shortest_path(net, u, v)
        if not path:
            return None
        # return the next step
        return self._nodes[path[1]]
