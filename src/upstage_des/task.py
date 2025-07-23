# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Tasks constitute the actions that Actors can perform."""

from collections.abc import Callable, Generator, Iterable
from enum import IntFlag
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar
from warnings import warn

from simpy import Environment as SimpyEnv
from simpy import Event as SimpyEvent
from simpy import Interrupt, Process

if TYPE_CHECKING:
    from .actor import Actor
    from .task_network import TaskNetwork

from .base import ENV_CONTEXT_VAR, MockEnvironment, SettableEnv, SimulationError
from .constants import PLANNING_FACTOR_OBJECT
from .events import BaseEvent, Event
from .routines import Routine

__all__ = ("DecisionTask", "Task", "process", "TerminalTask", "InterruptStates")


NOT_IMPLEMENTED_MSG = "User must define the actions performed when executing this task"

TASK_GEN = Generator[BaseEvent | Routine, Any, None]


class InterruptStates(IntFlag):
    """Class that describes how to behave after an interrupt."""

    END = 0
    IGNORE = 1
    RESTART = 2


def process(
    func: Callable[..., Generator[SimpyEvent, Any, None]],
) -> Callable[..., Process]:
    """Decorate a ``simpy`` process to schedule it as a callable.

    Allows users to decorate a generator, and when they want to schedule them
    as a ``simpy`` process, they can simply call it, e.g., instead of calling:

    Usage:

    >>> from upstage.api import process, Wait
    ...
    >>> @process
    >>> def generator(wait_period=1.0, msg="Finished Waiting"):
    >>>     # A simple process that periodically prints a statement
    >>>     while True:
    >>>         yield Wait(wait_period).as_event()
    >>>         print(msg)
    ...
    >>> @process
    >>> def another_process():
    >>>     # Some other process that calls the first one
    >>>     generator()

    Args:
        func (Callable[..., Generator[BaseEvent, None, None]]): The process function that is a
        generator of simpy events.

    Returns:
        Process: The generator as a ``simpy`` process.

    Note:
        The value of this decorator is that it reduces the chance of a user
        forgetting to call the generator as a process, which tends to produce
        behaviors that are difficult to troubleshoot because the code will
        build and can run, but the simulation will not work schedule the
        process defined by the generator.

    """

    @wraps(func)
    def wrapped_generator(*args: Any, **kwargs: Any) -> Process:
        """Wrap the generator with a function that calls it as a process."""
        try:
            environment = ENV_CONTEXT_VAR.get()
        except LookupError:
            raise SimulationError("No environment found on process call")
        return environment.process(func(*args, **kwargs))

    return wrapped_generator


EVT = TypeVar("EVT", bound=BaseEvent)
REH_ACTOR = TypeVar("REH_ACTOR", bound="Actor")


class Task(SettableEnv):
    """A Task is an action that can be performed by an Actor."""

    INTERRUPT = InterruptStates

    def __init__(self) -> None:
        """Create a task instance."""
        super().__init__()
        self._network_name: str | None = None
        self._network_ref: TaskNetwork | None = None
        self._marker: str | None = None
        self._marked_time: float | None = None
        self._interrupt_action: InterruptStates = InterruptStates.END
        self._rehearsing: bool = False

    def task(self, *, actor: Any) -> TASK_GEN:
        """Define the process this task follows."""
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def on_interrupt(self, *, actor: Any, cause: Any) -> InterruptStates:
        """Define any actions to take on the actor if this task is interrupted.

        Note:
            Custom Tasks can overwrite this method so they can handle being
            interrupted with a custom procedure. By default, interrupt ends the
            task.

        Args:
            actor (Actor): the actor using the task
            cause (Any): Optional data for the interrupt
        """
        actor.log(f"Interrupted while performing {self}. Reasons: {cause}")
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

    def _set_network_ref(self, network: "TaskNetwork") -> None:
        """Set the reference to the task network object.

        Args:
            network (TaskNetwork): The network
        """
        if self._network_ref is not None:
            raise SimulationError(
                "Setting task network reference on task that already has a network"
            )
        self._network_ref = network

    def _set_network_name(self, network_name: str) -> None:
        """Set the name of the network this task is in.

        Args:
            network_name (str): Network name
        """
        if self._network_name is not None:
            raise SimulationError("Setting task network name on task that already has a network")
        self._network_name = network_name

    def clear_actor_task_queue(self, actor: "Actor") -> None:
        """Clear out the task queue on the network.

        Args:
            actor (Actor): The actor whose queue will be cleared
        """
        assert self._network_name is not None
        actor.clear_task_queue(self._network_name)

    def set_actor_task_queue(self, actor: "Actor", task_list: list[str]) -> None:
        """Set the task queue on the actor.

        This assumes an empty queue.

        Args:
            actor (Actor): The actor to modify the task queue of
            task_list (list[str]): The list of task names to queue.
        """
        assert self._network_name is not None
        actor.set_task_queue(self._network_name, task_list)

    def get_actor_task_queue(self, actor: "Actor") -> list[str]:
        """Get the task queue on the actor.

        Args:
            actor (Actor): The actor to modify the task queue of
        """
        assert self._network_name is not None
        return actor.get_task_queue(self._network_name)

    def get_actor_next_task(self, actor: "Actor") -> str | None:
        """Get the next queued task.

        Args:
            actor (Actor): The actor to get the next task from

        Returns:
            str | None: The next task name (or None if no task)
        """
        assert self._network_name is not None
        return actor.get_next_task(self._network_name)

    def set_actor_knowledge(
        self,
        actor: "Actor",
        name: str,
        value: Any,
        overwrite: bool = False,
    ) -> None:
        """Set knowledge on the actor.

        Convenience method for passing in the name of task for actor logging.

        Args:
            actor (Actor): The actor to set knowledge on.
            name (str): Name of the knowledge
            value (Any): Value of the knowledge
            overwrite (bool, optional): Allow overwrite or not. Defaults to False.
        """
        cname = self.__class__.__qualname__
        actor.set_knowledge(name, value, overwrite=overwrite, caller=cname)

    def clear_actor_knowledge(self, actor: "Actor", name: str) -> None:
        """Clear knowledge from an actor.

        Convenience method for passing in the name of task for actor logging.

        Args:
            actor (Actor): The actor to clear knowledge from
            name (str): The name of the knowledge
        """
        cname = self.__class__.__qualname__
        actor.clear_knowledge(name, caller=cname)

    @staticmethod
    def get_actor_knowledge(actor: "Actor", name: str, must_exist: bool = False) -> Any:
        """Get knowledge from the actor.

        Args:
            actor (Actor): The actor to get knowledge from.
            name (str): Name of the knowledge
            must_exist (bool, optional): Raise errors if the knowledge doesn't exist.
            Defaults to False.

        Returns:
            Any: The knowledge value, which could be None
        """
        return actor.get_knowledge(name, must_exist)

    def get_and_clear_actor_knowledge(self, actor: "Actor", name: str) -> Any:
        """Get and clear knowledge on an actor.

        The knowledge is assumed to exist.

        Args:
            actor (Actor): The actor to get knowledge from.
            name (str): The knowledge name.

        Returns:
            Any: The knowledge value.
        """
        cname = self.__class__.__qualname__
        return actor.get_and_clear_knowledge(name, caller=cname)

    def set_actor_bulk_knowledge(
        self, actor: "Actor", know: dict[str, Any], overwrite: bool = False
    ) -> None:
        """Set multiple knowledge entries at once.

        Args:
            actor (Actor): The actor to operate on.
            know (dict[str, Any]): Dictionary of key:value pairs of knowledge.
            overwrite (bool, optional): If overwrite is allowed. Defaults to False.
        """
        for k, v in know.items():
            self.set_actor_knowledge(actor, k, v, overwrite)

    def clear_actor_bulk_knowledge(self, actor: "Actor", names: Iterable[str]) -> None:
        """Clear a list of knowledge entries.

        Args:
            actor (Actor): The actor to operate on.
            names (Iterable[str]): Knowledge names.
        """
        for name in names:
            self.clear_actor_knowledge(actor, name)

    def get_actor_bulk_knowledge(
        self, actor: "Actor", names: Iterable[str], must_exist: bool = False
    ) -> dict[str, Any]:
        """Get multiple knowledge items.

        Args:
            actor (Actor): The actor to operate on.
            names (Iterable[str]): Names of the knowledge
            must_exist (bool, optional): If all entires must exist. Defaults to False.

        Returns:
            dict[str, Any]: The knowledge values. None if not present.
        """
        return {name: self.get_actor_knowledge(actor, name, must_exist) for name in names}

    def get_and_clear_actor_bulk_knowledge(
        self, actor: "Actor", names: Iterable[str], caller: str | None = None
    ) -> dict[str, Any]:
        """Get and clear multiple knowledge entries.

        Args:
            actor (Actor): The actor to operate on.
            names (Iterable[str]): The knowledge to retrieve and delete.
            caller (str | None, optional): The name of the caller. Defaults to None.

        Returns:
            dict[str, Any]: The retrieved knowledge.
        """
        return {name: self.get_and_clear_actor_knowledge(actor, name) for name in names}

    def _clone_actor(self, actor: REH_ACTOR, knowledge: dict[str, Any] | None) -> REH_ACTOR:
        """Create a clone of the actor.

        Args:
            actor (Actor): The actor to clone
            knowledge (dict[str, Any] | None): Additional knowledge to add.

        Returns:
            Actor: Cloned actor
        """
        mocked_env = MockEnvironment.mock(self.env)
        self.env = mocked_env
        understudy = actor.clone(
            new_env=mocked_env,
            knowledge=knowledge,
        )
        return understudy

    def rehearse(
        self,
        *,
        actor: REH_ACTOR,
        knowledge: dict[str, Any] | None = None,
        cloned_actor: bool = False,
        **kwargs: Any,
    ) -> REH_ACTOR:
        """Rehearse the task to evaluate its feasibility.

        Args:
            actor (Actor): The actor to rehearse in the task
            knowledge (dict[str, Any], optional): Knowledge to add to the actor. Defaults to None.
            cloned_actor (bool, optional): If the actor is a clone or not. Defaults to False.
            kwargs (Any): Optional args to send to the task.

        Returns:
            Actor: The cloned actor with a state reflecting the task flow.
        """
        knowledge = {} if knowledge is None else knowledge
        _old_env = self.env
        understudy = actor
        if not cloned_actor:
            understudy = self._clone_actor(actor, knowledge)
        if not isinstance(understudy.env, MockEnvironment):
            raise SimulationError("Bad actor cloning.")
        self.env = understudy.env
        mocked_env: MockEnvironment = understudy.env

        self._rehearsing = True
        generator = self.task(actor=understudy, **kwargs)
        returned_item = None
        while True:
            try:
                if returned_item is None:
                    next_event = next(generator)
                else:
                    next_event = generator.send(returned_item)
                    returned_item = None
                if not issubclass(next_event.__class__, BaseEvent | Routine):
                    msg = f"Task {self} event {next_event}"
                    if isinstance(next_event, Process):
                        raise SimulationError(msg + " cannot be a process during rehearsal.")
                    raise SimulationError(msg + " must be a subclass of BaseEvent or Routine.")
                time_advance, returned_item = next_event.rehearse()
                mocked_env.now += time_advance

            except StopIteration:
                # warn(f"Stopping rehearsal of task '{self.__class__.__name__}' "
                #      f"for actor '{actor}'! [Rehearsal duration: "
                #      f"{self.env.now - _old_env.now:.3g}]")
                break

        self.env = _old_env
        self._rehearsing = False
        return understudy

    def _handle_interruption(
        self, actor: "Actor", interrupt: Interrupt, next_event: BaseEvent | Process
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
        if _interrupt_action is None:
            raise SimulationError("No interrupt behavior returned from `on_interrupt`")

        if _interrupt_action in (InterruptStates.END, InterruptStates.RESTART):
            actor.log(f"Interrupted by {interrupt}.")
            actor.deactivate_all_states(task=self)
            actor.deactivate_all_mimic_states(task=self)
            if isinstance(next_event, BaseEvent):
                names = list(actor._knowledge.keys())
                for name in names:
                    if actor._knowledge[name] is next_event:
                        actor.clear_knowledge(name, caller=f"Clearing knowledge event {name}")
                next_event.cancel()
            elif isinstance(next_event, Process):
                next_event.interrupt(cause=interrupt.cause)
            else:
                raise SimulationError(f"Bad event passed: {next_event}")
        elif _interrupt_action != InterruptStates.IGNORE:
            raise SimulationError(f"Wrong interrupt action value: {_interrupt_action}")
        return _interrupt_action

    @process
    def run(self, *, actor: "Actor") -> Generator[SimpyEvent | Process, Any, None]:
        """Execute the task.

        Args:
            actor (Actor): The actor using the task

        Returns:
            Generator[SimpyEvent, Any, None]
        """
        generators = [
            self.task(actor=actor),
        ]
        gen_objs: list[Task | Routine] = [
            self,
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
                            gen_objs.pop()
                            if e.value is not None:
                                return_item = e.value
                            if not generators:
                                stop_run = True
                                break
                            continue

                        # A routine class gives us a generator, so go back to the
                        # start and run it as such.
                        if isinstance(next_event, Routine):
                            generators.append(next_event._run())
                            gen_objs.append(next_event)
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
                assert not isinstance(next_event, Routine)
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
                        gen_obj = gen_objs.pop()
                        if isinstance(gen_obj, Routine):
                            gen.close()
                            yield from gen_obj._run_cancel()
                    if action == InterruptStates.RESTART:
                        generators = [
                            self.task(actor=actor),
                        ]
                        gen_objs = [
                            self,
                        ]
                        return_item = None
                    else:
                        stop_run = True


class DecisionTask(Task):
    """A task used for decision processes."""

    DO_NOT_HOLD = False

    def task(self, *, actor: Any) -> TASK_GEN:
        """Define the process this task follows."""
        raise SimulationError("No need to call `task` on a DecisionTask")

    def rehearse_decision(self, *, actor: Any) -> None:
        """Define the process this task follows."""
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def make_decision(self, *, actor: Any) -> None:
        """Define the process this task follows."""
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def rehearse(
        self,
        *,
        actor: REH_ACTOR,
        knowledge: dict[str, Any] | None = None,
        cloned_actor: bool = False,
        **kwargs: Any,
    ) -> REH_ACTOR:
        """Rehearse the task to evaluate its feasibility.

        Args:
            actor (Actor): The actor to rehearse with
            knowledge (Optional[dict[str, Any]], optional): Knowledge to add. Defaults to None.
            cloned_actor (bool, optional): If the actor is a clone or not. Defaults to False.
            kwargs (Any): Kwargs for rehearsal. Kept for consistency to the base class.

        Returns:
            Actor: Cloned actor after rehearsing this task.
        """
        knowledge = {} if knowledge is None else knowledge
        _old_env = self.env
        understudy = actor
        if not cloned_actor:
            understudy = self._clone_actor(actor, knowledge)
        self.env = understudy.env

        self._rehearsing = True

        self.rehearse_decision(actor=understudy)
        self.env = _old_env
        self._rehearsing = False
        return understudy

    @process
    def run(self, *, actor: "Actor") -> Generator[SimpyEvent, None, None]:
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

        Task networks will use this method if SKIP_WAIT is True.

        Args:
            actor (Actor): The actor making decisions
        """
        self.make_decision(actor=actor)


class TerminalTask(Task):
    """A rehearsal-safe task that cannot exit, i.e., it is terminal.

    Note:
        The user can re-implement the `log_message` method to return a custom
        message that will be appended to the actor's log through its `log`
        method.
    """

    _time_to_complete: float = 1e24

    def log_message(self, *, actor: "Actor") -> str:
        """A message to save to a log when this task is reached.

        Args:
            actor (Actor): The actor using this task.

        Returns:
            str: A log message
        """
        return f"Entering terminal task: {self} on network {self._network_name}"

    def on_interrupt(self, *, actor: "Actor", cause: Any) -> InterruptStates:
        """Special case interrupt for terminal task.

        Args:
            actor (Actor): The actor
            cause (Any): Additional data sent to the interrupt.
        """
        raise SimulationError(
            f"Cannot interrupt a terminal task {self} on {actor}. Kwargs sent: {cause}"
        )
        return InterruptStates.END

    def task(self, *, actor: "Actor") -> TASK_GEN:
        """The terminal task.

        It's just a long wait.

        Args:
            actor (Actor): The actor
        """
        log_message = self.log_message(actor=actor)
        actor.log(log_message)
        the_long_event = Event(rehearsal_time_to_complete=self._time_to_complete)
        res = yield the_long_event
        if res is not PLANNING_FACTOR_OBJECT:
            raise SimulationError(f"A terminal task completed on {actor}")
