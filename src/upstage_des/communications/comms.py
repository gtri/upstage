# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Comms message and commander classes."""

from collections.abc import Generator
from dataclasses import dataclass
from math import ceil
from typing import Any
from uuid import uuid4

from simpy import Event as SimpyEvent
from simpy import Store

from upstage_des.actor import Actor
from upstage_des.base import ENV_CONTEXT_VAR, SimulationError, UpstageBase
from upstage_des.events import Put
from upstage_des.states import CommunicationStore
from upstage_des.task import process
from upstage_des.type_help import SIMPY_GEN


@dataclass
class MessageContent:
    """Message content data object."""

    data: dict
    message: str | None = None


@dataclass
class Message:
    """A message data object."""

    sender: Actor
    content: MessageContent
    destination: Actor

    header: str | None = None
    time_sent: float | None = None
    time_received: float | None = None

    mode: str | None = None

    def __post_init__(self) -> None:
        self.uid = uuid4()
        self.time_created = ENV_CONTEXT_VAR.get().now

    def __hash__(self) -> int:
        return hash(self.uid)


class CommsManagerBase(UpstageBase):
    """A class to manage point to point transfer of communications.

    Works through simpy.Store or similar interfaces. Allows for degraded comms and comms retry.

    If an Actor contains a `CommunicationStore`, this object will detect that
    and use it as a destination. In that case, you also do not need to connect
    the actor to this object.

    Example:
        >>> class Talker(UP.Actor):
        >>>     comms = UP.ResourceState[SIM.Store](default=SIM.Store)
        >>>
        >>> talker1 = Talker(name='MacReady')
        >>> talker2 = Talker(name='Childs')
        >>>
        >>> comm_station = UP.CommsManager(name="Outpost 31", mode="voice")
        >>> comm_station.connect(talker1, talker1.comms)
        >>> comm_station.connect(talker2, talker2.comms)
        >>>
        >>> comm_station.run()
        >>>
        >>> # Typically, do this inside a task or somewhere else
        >>> putter = comm_station.make_put(
        >>>     message="Grab your flamethrower!",
        >>>     source=talker1,
        >>>     destination=talker2,
        >>>     rehearsal_time_to_complete=0.0,
        >>> )
        >>> yield putter
        ...
        >>> env.run()
        >>> talker2.comms.items
            [Message(sender=Talker: MacReady, message='Grab your flamethrower!',
            destination=Talker: Childs)]
    """

    def __init__(
        self,
        *,
        name: str,
        mode: str | None = None,
        init_entities: list[tuple[Actor, str]] | None = None,
        send_time: float = 0.0,
        retry_max_time: float = 1.0,
        retry_rate: float = 0.166667,
        debug_logging: bool = False,
    ) -> None:
        """Create a comms transfer manager.

        Parameters
        ----------
        name : str
            Give the instance a unique name for logging purposes
        mode: str
            The name of the mode comms are occurring over. Used for automated
            detection of actor comms interfaces.
            Default is None, which requires explicit connections.
        init_entities : List[Tuple(instance, str)], optional
            Entities who have a comms store to let the manager know about. The
            tuples are (entity_instance, entity's comms input store's name), by default None
        send_time : float, optional
            Time to send a message, by default 0.0
        retry_max_time : float, optional
            Amount of time (in sim units) to try resending a message, by default 1
        retry_rate : float, optional
            How often (in sim units) to try re-sending a message, by default 10/60
        debug_logging : bool, optional
            Turn on or off logging, by default False
        """
        super().__init__()
        self.name = name
        self.mode = mode
        self.comms_degraded: bool = False
        self.retry_max_time = retry_max_time
        self.retry_rate = retry_rate
        self.send_time = send_time
        self.incoming = Store(env=self.env)
        self.connected: dict[Actor, str] = {}
        self.blocked_links: list[tuple[Actor, Actor]] = []
        self.blocked_nodes: list[Actor] = []
        if init_entities is not None:
            for entity, comms_store_name in init_entities:
                self.connect(entity, comms_store_name)
        self.debug_log: list[dict[str, Any]] = []
        self.debug_logging: bool = debug_logging

    @staticmethod
    def clean_message(message: str | Message) -> MessageContent:
        """Test to see if an object is a message.

        If it is, return the message contents only. Otherwise return the message.

        Args:
            message (str | Message): The message to clean

        Returns:
            MessageContent: The message as a message content object.
        """
        if isinstance(message, Message):
            return message.content
        return MessageContent(data={"message": message})

    def connect(self, entity: Actor, comms_store_name: str) -> None:
        """Connect an actor and its comms store to this comms manager.

        Args:
            entity (Actor): The actor that will send/receive.
            comms_store_name (str): The store state name for receiving
        """
        self.connected[entity] = comms_store_name

    def _get_state(self, actor: Actor) -> str | None:
        """Get the comms store for the right mode."""
        for name, state in actor._state_defs.items():
            if not isinstance(state, CommunicationStore):
                continue
            mode_key = state._modename
            modes: set[str] = actor.__dict__.get(mode_key, set())
            if self.mode in modes:
                return name
        return None

    def store_from_actor(self, actor: Actor) -> Store:
        """Retrieve a communications store from an actor.

        Args:
            actor (Actor): The actor

        Returns:
            Store: A Comms store.
        """
        if actor not in self.connected:
            try:
                msg_store_name = self._get_state(actor)
            except SimulationError as e:
                e.add_note(f"No comms destination on actor {actor}")
                raise e
        else:
            msg_store_name = self.connected[actor]

        if msg_store_name is None:
            raise SimulationError(f"No comms store on {actor}")
        store: Store | None = getattr(actor, msg_store_name)
        if store is None:
            raise SimulationError(f"Bad comms store name: {msg_store_name} on {actor}")
        return store

    def make_put(
        self,
        message: str | Message | MessageContent | dict,
        source: Actor,
        destination: Actor,
        rehearsal_time_to_complete: float = 0.0,
    ) -> Put:
        """Create a Put request for a message into the CommsManager.

        Parameters
        ----------
        source :
            The message sender
        destination :
            The message receiver, who must be connected to the CommsManager
        message :
            Arbitrary data to send
        rehearsal_time_to_complete : float, optional
            Planning time to complete the event (see Put), by default 0.0

        Returns:
        -------
        Put
            UPSTAGE Put event object to yield from a task
        """
        use: Message
        if isinstance(message, Message):
            use = message
        elif isinstance(message, MessageContent):
            use = Message(sender=source, content=message, destination=destination, mode=self.mode)
        else:
            content = (
                MessageContent(data=message)
                if isinstance(message, dict)
                else MessageContent(data={}, message=message)
            )
            use = Message(sender=source, content=content, destination=destination, mode=self.mode)

        return Put(
            self.incoming,
            use,
            rehearsal_time_to_complete=rehearsal_time_to_complete,
        )

    @process
    def _do_transmit(
        self, message: Message, destination: Actor
    ) -> Generator[SimpyEvent, None, None]:
        # User implemented method for how to transmit a message
        raise NotImplementedError()

    @process
    def run(self) -> Generator[SimpyEvent, Any, None]:
        """Run the communications message passing.

        Yields:
            Generator[SimpyEvent, Any, None]: Simpy Process
        """
        while True:
            message = yield self.incoming.get()
            dest = message.destination
            self._do_transmit(message, dest)

    def _link_compare(self, a_test: Actor, b_test: Actor) -> bool:
        if a_test in self.blocked_nodes or b_test in self.blocked_nodes:
            return True
        for a, b in self.blocked_links:
            if a_test is a and b_test is b:
                return True
        return False

    def _test_if_link_is_blocked(self, source: Actor, destination: Actor) -> bool:
        """Test if a link is blocked.

        Args:
            source (Actor): Sender
            destination (Actor): Destination

        Returns:
            bool: If the link is blocked.
        """
        if self._link_compare(source, destination):
            return True
        return False

    def _log_attempt(
        self, message: Message, source: Actor, destination: Actor, status: str
    ) -> None:
        """Log an attempt to send a message."""
        if not self.debug_logging:
            return
        msg = {
            "time": self.env.now,
            "event": status,
            "message": message,
            "current": source,
            "destination": destination,
        }
        self.debug_log.append(msg)

    def _attempt(self, message: Message, source: Actor, destination: Actor) -> SIMPY_GEN:
        """Try to send a message.

        Implies some kind of acknowledgement system.
        """
        n_tries = ceil(self.retry_max_time / self.retry_rate)
        n_taken = 0
        while self.comms_degraded or self._test_if_link_is_blocked(source, destination):
            if n_taken == n_tries:
                self._log_attempt(message, source, destination, "Stopped trying to send")
                return False
            n_taken += 1
            self._log_attempt(message, source, destination, "Can't send, waiting")
            yield self.env.timeout(self.retry_rate)
        return True


class PointToPointCommsManager(CommsManagerBase):
    """A class to manage point to point transfer of communications.

    Works through simpy.Store or similar interfaces. Allows for degraded comms and comms retry.

    If an Actor contains a `CommunicationStore`, this object will detect that
    and use it as a destination. In that case, you also do not need to connect
    the actor to this object.

    Example:
        >>> class Talker(UP.Actor):
        >>>     comms = UP.ResourceState[SIM.Store](default=SIM.Store)
        >>>
        >>> talker1 = Talker(name='MacReady')
        >>> talker2 = Talker(name='Childs')
        >>>
        >>> comm_station = UP.CommsManager(name="Outpost 31", mode="voice")
        >>> comm_station.connect(talker1, talker1.comms)
        >>> comm_station.connect(talker2, talker2.comms)
        >>>
        >>> comm_station.run()
        >>>
        >>> # Typically, do this inside a task or somewhere else
        >>> putter = comm_station.make_put(
        >>>     message="Grab your flamethrower!",
        >>>     source=talker1,
        >>>     destination=talker2,
        >>>     rehearsal_time_to_complete=0.0,
        >>> )
        >>> yield putter
        ...
        >>> env.run()
        >>> talker2.comms.items
            [Message(sender=Talker: MacReady, message='Grab your flamethrower!',
            destination=Talker: Childs)]
    """

    @process
    def _do_transmit(
        self, message: Message, destination: Actor
    ) -> Generator[SimpyEvent, None, None]:
        can_send = yield from self._attempt(message, message.sender, destination)
        if not can_send:
            return

        if self.send_time > 0:
            yield self.env.timeout(self.send_time)

        self._log_attempt(message, message.sender, destination, "Sent message")

        # update the send time
        message.time_sent = self.env.now
        store = self.store_from_actor(destination)
        yield store.put(message)
