# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Tasks constitute the actions that Actors can perform."""

from collections.abc import Generator
from enum import IntFlag
from typing import Any, TypeVar
from warnings import warn

from simpy import Environment as SimpyEnv
from simpy import Event as SimpyEvent
from simpy import Interrupt, Process

from upstage_des.actor import Actor, ActorHelper
from upstage_des.base import SimulationError, UpstageBase, process
from upstage_des.events import BaseEvent, Event

__all__ = ("DecisionTask", "Task", "process", "TerminalTask", "InterruptStates")


NOT_IMPLEMENTED_MSG = "User must define the actions performed when executing this task"

TASK_GEN = Generator[BaseEvent, Any, None]


class InterruptStates(IntFlag):
    """Class that describes how to behave after an interrupt."""

    END = 0
    IGNORE = 1
    RESTART = 2


EVT = TypeVar("EVT", bound=BaseEvent)


class Task(UpstageBase, ActorHelper):
    """A Task is an action that can be performed by an Actor.

    Inherits ActorHelper to provide methods for tracing knowledge modification
    and other features on the Actor.
    """

    def __init__(self) -> None:
        """Create a task instance."""
        super().__init__()
        self._marker: str | None = None
        self._marked_time: float | None = None
        self._interrupt_action: InterruptStates = InterruptStates.END
        self._final_interrupt: bool = False

    def task(self, *, actor: Actor) -> TASK_GEN:
        """Define the process this task follows."""
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def on_interrupt(self, *, actor: Actor, cause: Any) -> InterruptStates:
        """Define any actions to take on the actor if this task is interrupted.

        Note:
            Custom Tasks can overwrite this method so they can handle being
            interrupted with a custom procedure. By default, interrupt ends the
            task.

        Args:
            actor (Actor): the actor using the task
            cause (Any): Optional data for the interrupt
        """
        actor.write_to_log(f"Interrupted while performing {self}. Reasons: {cause}")
        return self._interrupt_action

    def set_marker(
        self, marker: str, interrupt_action: InterruptStates = InterruptStates.END
    ) -> None:
        """Set a marker to help with inspection of interrupts.

        The interrupt_action is set for when no `on_interrupt` is implemented.

        Args:
            marker (str): String for the marker.
            interrupt_action (InterruptStates, optional): Action to take on interrupt.
            Defaults to InterruptStates.END.
        """
        self._marker = marker
        self._marked_time = self.env.now
        self._interrupt_action = interrupt_action

    def get_marker(self) -> str | None:
        """Get the current marker.

        Returns:
            str | None: Marker (or None if cleared)
        """
        return self._marker

    def get_marker_time(self) -> float | None:
        """The time the current marker was set.

        Returns:
            float | None: Marker set time (or None if cleared)
        """
        return self._marked_time

    def clear_marker(self) -> None:
        """Clear the marker and set that an interrupt ends the task."""
        self._marker = None
        self._marked_time = None
        self._interrupt_action = InterruptStates.END

    def _handle_interruption(
        self, actor: Actor, interrupt: Interrupt, next_event: BaseEvent | Process
    ) -> InterruptStates:
        """Clean up after an interrupt and perform interrupt checks/actions.

        Args:
            actor (Actor): _description_
            interrupt (Interrupt): _description_
            next_event (BaseEvent): _description_

        Returns:
            InterruptStates: action to take
        """
        # test the interrupt behavior:
        _interrupt_action = self.on_interrupt(
            actor=actor,
            cause=interrupt.cause,
        )
        if _interrupt_action is None and not self._final_interrupt:
            raise SimulationError("No interrupt behavior returned from `on_interrupt`")

        if (
            _interrupt_action in (InterruptStates.END, InterruptStates.RESTART)
            or self._final_interrupt
        ):
            actor.write_to_log(f"Interrupted by {interrupt}.")
            actor.deactivate_all_states(cause=self)
            if isinstance(next_event, BaseEvent):
                names = list(actor.knowledge.keys())
                for name in names:
                    if actor.knowledge[name] is next_event:
                        actor.clear_knowledge(name, caller=f"Clearing knowledge event {name}")
                next_event.cancel()
            elif isinstance(next_event, Process):
                next_event.interrupt(cause=interrupt.cause)
            else:
                raise SimulationError(f"Bad event passed: {next_event}")
        elif _interrupt_action != InterruptStates.IGNORE:
            raise SimulationError(f"Wrong interrupt action value: {_interrupt_action}")
        if self._final_interrupt:
            _interrupt_action = InterruptStates.END
        return _interrupt_action

    @process
    def run(self, *, actor: Actor) -> Generator[SimpyEvent | Process, Any, None]:
        """Execute the task.

        Args:
            actor (Actor): The actor using the task

        Returns:
            Generator[SimpyEvent, Any, None]
        """
        generators = [
            self.task(actor=actor),
        ]
        return_item = None
        stop_run = False
        back_from_interrupt = False
        event_to_yield: Process | SimpyEvent
        while not stop_run:
            try:
                while True:
                    if not back_from_interrupt:
                        try:
                            if return_item is None:
                                next_event = next(generators[-1])
                            else:
                                next_event = generators[-1].send(return_item)
                        except StopIteration as e:
                            generators.pop()
                            if e.value is not None:
                                return_item = e.value
                            if not generators:
                                stop_run = True
                                break
                            continue

                        if isinstance(next_event, Process):
                            warn(
                                f"Yielding a simpy.Process from {self}. "
                                f"This is dangerous, take care. ",
                                UserWarning,
                            )
                            event_to_yield = next_event
                        elif isinstance(next_event, BaseEvent):
                            event_to_yield = next_event.as_event()
                        else:
                            raise SimulationError(f"Unexpected yielded event type: {next_event}")
                    else:
                        back_from_interrupt = False
                    return_item = yield event_to_yield
                    # TODO: test if the return_item is for a multi-event
                    # that way we can return it as a more useful object

            except Interrupt as interrupt:
                action = self._handle_interruption(
                    actor,
                    interrupt,
                    next_event,
                )
                if action == InterruptStates.IGNORE:
                    back_from_interrupt = True
                else:
                    # This is restart or end; either way we have to cancel
                    # any routines in the stack.
                    while generators:
                        gen = generators.pop()
                        gen.close()
                    if action == InterruptStates.RESTART:
                        generators = [
                            self.task(actor=actor),
                        ]
                        return_item = None
                    else:
                        stop_run = True


class DecisionTask(Task):
    """A task used for zero-time decision making."""

    DO_NOT_HOLD: bool = False

    def task(self, *, actor: Actor) -> TASK_GEN:
        """Define the process this task follows."""
        raise SimulationError("No need to call `task` on a DecisionTask")

    def make_decision(self, *, actor: Actor) -> None:
        """Define the process this task follows."""
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    @process
    def run(self, *, actor: Actor) -> Generator[SimpyEvent, None, None]:
        """Run the decision task.

        Args:
            actor (Actor): The actor making decisions

        Yields:
            Generator[SimpyEvent, None, None]: Generator for SimPy event queue.
        """
        self.make_decision(actor=actor)
        assert isinstance(self.env, SimpyEnv)
        yield self.env.timeout(0.0)

    def run_skip(self, *, actor: "Actor") -> None:
        """Run the decision task with no clock reference.

        Task networks will use this method if DO_NOT_HOLD is True.

        Args:
            actor (Actor): The actor making decisions
        """
        self.make_decision(actor=actor)


class TerminalTask(Task):
    """A task that cannot exit, i.e., it is terminal.

    Note:
        The user can re-implement the `log_message` method to return a custom
        message that will be appended to the actor's log through its `log`
        method.
    """

    _time_to_complete: float = 1e24

    def log_message(self, *, actor: Actor) -> str:
        """A message to save to a log when this task is reached.

        Args:
            actor (Actor): The actor using this task.

        Returns:
            str: A log message
        """
        return f"Entering terminal task: {self}"

    def on_interrupt(self, *, actor: Actor, cause: Any) -> InterruptStates:
        """Special case interrupt for terminal task.

        Args:
            actor (Actor): The actor
            cause (Any): Additional data sent to the interrupt.
        """
        if not self._final_interrupt:
            raise SimulationError(
                f"Cannot interrupt a terminal task {self} on {actor}. Kwargs sent: {cause}"
            )
        return InterruptStates.END

    def task(self, *, actor: Actor) -> TASK_GEN:
        """The terminal task.

        It's just a long wait.

        Args:
            actor (Actor): The actor
        """
        log_message = self.log_message(actor=actor)
        actor.write_to_log(log_message)
        the_long_event = Event(rehearsal_time_to_complete=self._time_to_complete)
        yield the_long_event
        raise SimulationError(f"A terminal task completed on {actor}")
