# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""The task network class, and factory classes."""

from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from upstage_des.actor import Actor

from simpy import Process

from upstage_des.base import SimulationError
from upstage_des.task import DecisionTask, Task, TerminalTask, process

REH_ACTOR = TypeVar("REH_ACTOR", bound="Actor")


@dataclass
class TaskLinks:
    """Type hinting for task link dictionaries."""

    default: str | None
    allowed: Sequence[str]


class TaskNetwork:
    """A means to represent, execute, and rehearse interdependent tasks."""

    def __init__(
        self,
        name: str,
        task_classes: Mapping[str, type[Task]],
        task_links: Mapping[str, TaskLinks],
    ) -> None:
        """Create a task network.

        Task links are defined as:
            {task_name: TaskLinks(default= task_name | None, allowed= list[task_names]}
        where each task has a default next task (or None), and tasks that could follow it.

        Args:
            name (str): Network name
            task_classes (Mapping[str, Task]): Task names to Task object mapping.
            task_links (Mapping[str, TaskLinks]): Task links.
        """
        self.name = name
        self.task_classes = task_classes
        self.task_links = task_links
        self._current_task_name: str | None = None
        self._current_task_inst: Task | None = None
        self._current_task_proc: Process | None = None

    def is_feasible(self, curr: str, new: str) -> bool:
        """Determine if a task can follow another one.

        Args:
            curr (str): Current task name
            new (str): Potential next task name

        Returns:
            bool: If the new task can follow the current.
        """
        value = self.task_links[curr].allowed
        return new in value

    def _next_task_name(
        self, curr_task_name: str, actor: "Actor", clear_queue: bool = False
    ) -> str:
        """Get the next task name.

        Returns:
            str: Task name
        """
        task_from_queue = actor.get_next_task(self.name)
        default_next_task = self.task_links[curr_task_name].default
        if task_from_queue is None:
            if default_next_task is None:
                raise SimulationError(  # pramga: no cover
                    f"No default task set for after {curr_task_name} on {actor}."
                )
            next_name = default_next_task
        else:
            next_name = task_from_queue
            # once we have the name, pop it from the queue
            if clear_queue:
                actor._clear_task(self.name)
        return next_name

    @process
    def loop(
        self, *, actor: "Actor", init_task_name: str | None = None
    ) -> Generator[Process, None, None]:
        """Start a task network running its loop.

        If no initial task name is given, it will default to following the queue.

        Args:
            actor (Actor): The actor to run the loop on.
            init_task_name (Optional[str], optional): Optional task to start running.
            Defaults to None.
        """
        next_name = actor.get_next_task(self.name)
        if next_name is None:
            if init_task_name is None:
                raise SimulationError(
                    f"Actor {actor} wasn't supplied an initial task"
                )  # pramga: no cover
            next_name = init_task_name

        self._current_task_name = next_name

        while True:
            task_name = self._current_task_name
            assert isinstance(task_name, str)
            actor.log(f"Outer: starting {task_name}")
            actor._begin_next_task(self.name, task_name)
            task_cls = self.task_classes[task_name]
            task_instance: Task = task_cls()
            self._current_task_inst = task_instance
            self._current_task_inst._set_network_name(self.name)
            self._current_task_inst._set_network_ref(self)

            if (
                isinstance(self._current_task_inst, DecisionTask)
                and self._current_task_inst.DO_NOT_HOLD
            ):
                self._current_task_inst.run_skip(actor=actor)
            else:
                self._current_task_proc = self._current_task_inst.run(actor=actor)
                yield self._current_task_proc

            next_name = self._next_task_name(task_name, actor)
            self._current_task_name = next_name

    def rehearse_network(
        self,
        *,
        actor: REH_ACTOR,
        task_name_list: list[str],
        knowledge: dict[str, Any] | None = None,
        end_task: str | None = None,
    ) -> REH_ACTOR:
        """Rehearse a path through the task network.

        Args:
            actor (Actor): The actor to perform the task rehearsal withs
            task_name_list (list[str]): The tasks to be performed in order
            knowledge (dict[str, Any], optional): Knowledge to give to the cloned/rehearsing actor
            end_task (str, optional): A task name to end on

        Returns:
            Actor: A copy of the original actor with state changes associated with the network.
        """
        _old_name = self._current_task_name
        _old_inst = self._current_task_inst
        _old_proc = self._current_task_proc
        knowledge = {} if knowledge is None else knowledge
        num_tasks = len(task_name_list)
        # pre-clone the actor to get a hold of the new environment
        new_actor = actor.clone(knowledge=knowledge)
        task_idx = 0
        while True:
            if task_idx < num_tasks:
                task_name = task_name_list[task_idx]
            elif end_task is None:
                break
            else:
                # Grab the default or one from the queue, clearing the queue to prevent loops
                task_name = self._next_task_name(task_name, new_actor, clear_queue=True)
            if end_task is not None and end_task == task_name:
                break  # pragma: no cover
            self._current_task_name = task_name
            self._current_task_inst = self.task_classes[task_name]()
            self._current_task_inst._set_network_name(self.name)
            new_actor = self._current_task_inst.rehearse(
                actor=new_actor,
                cloned_actor=True,
            )
            # The next name should be feasible
            if task_idx < num_tasks - 1:
                follow_on = task_name_list[task_idx + 1]
                if not self.is_feasible(task_name, follow_on):
                    raise SimulationError(  # pragma: no cover
                        f"Task {follow_on} not allowed after '{task_name}' in network"
                    )
            task_idx += 1
        # reset the internal parameters
        self._current_task_name = _old_name
        self._current_task_inst = _old_inst
        self._current_task_proc = _old_proc
        return new_actor

    def __repr__(self) -> str:
        return f"Task network: {self.name}"


class TaskNetworkFactory:
    """A factory for creating task network instances."""

    def __init__(
        self,
        name: str,
        task_classes: Mapping[str, type[Task]],
        task_links: Mapping[str, TaskLinks],
    ) -> None:
        """Create a factory for making instances of a task network.

        Task links are defined as:
            {task_name: TaskLinks(default= task_name | None, allowed= list[task_names]}
        where each task has a default next task (or None), and tasks that could follow it.

        Args:
            name (str): The network name
            task_classes (dict[str, Task]): Network task classes
            task_links (dict[str, dict[str, str  |  list[str]  |  None]]): Network links.
        """
        self.name = name
        self.task_classes = task_classes
        self.task_links = task_links

    @classmethod
    def from_single_looping(cls, name: str, task_class: type[Task]) -> "TaskNetworkFactory":
        """Create a network factory from a single task that loops.

        Args:
            name (str): Network name
            task_class (Task): The single task to loop

        Returns:
            TaskNetworkFactory: The factory for the single looping network.
        """
        taskname = task_class.__name__
        task_classes = {taskname: task_class}
        task_links: dict[str, TaskLinks] = {
            taskname: TaskLinks(default=taskname, allowed=[taskname])
        }
        return TaskNetworkFactory(name, task_classes, task_links)

    @classmethod
    def from_single_terminating(cls, name: str, task_class: type[Task]) -> "TaskNetworkFactory":
        """Create a network factory from a single task that terminates.

        Args:
            name (str): Network name
            task_class (Task): The single task to terminate after

        Returns:
            TaskNetworkFactory: The factory for the single terminating network.
        """
        taskname = task_class.__name__
        end_name = f"{taskname}_FINAL"
        task_classes = {taskname: task_class, end_name: TerminalTask}
        task_links: dict[str, TaskLinks] = {
            taskname: TaskLinks(default=end_name, allowed=[end_name])
        }
        return TaskNetworkFactory(name, task_classes, task_links)

    @classmethod
    def from_ordered_terminating(
        cls, name: str, task_classes: list[type[Task]]
    ) -> "TaskNetworkFactory":
        """Create a network factory from a list of tasks that terminates.

        Args:
            name (str): Network name
            task_classes (list[Task]): The tasks to run in order.

        Returns:
            TaskNetworkFactory: The factory for the ordered network.
        """
        task_class = {}
        task_links: dict[str, TaskLinks] = {}
        for i, tc in enumerate(task_classes):
            the_name = tc.__name__
            task_class[the_name] = tc
            try:
                nxt = task_classes[i + 1]
                nxt_name = nxt.__name__
            except IndexError:
                nxt = TerminalTask
                nxt_name = f"{name}_TERMINATING"
                task_class[nxt_name] = nxt
            task_links[the_name] = TaskLinks(default=nxt_name, allowed=[nxt_name])
        return TaskNetworkFactory(name, task_class, task_links)

    @classmethod
    def from_ordered_loop(cls, name: str, task_classes: list[type[Task]]) -> "TaskNetworkFactory":
        """Create a network factory from a list of tasks that loops.

        Args:
            name (str): Network name
            task_classes (list[Task]): The tasks to run in order.

        Returns:
            TaskNetworkFactory: The factory for the ordered network.
        """
        task_class = {}
        task_links: dict[str, TaskLinks] = {}
        for i, tc in enumerate(task_classes):
            the_name = tc.__name__
            task_class[the_name] = tc
            try:
                nxt = task_classes[i + 1]
            except IndexError:
                nxt = task_classes[0]
            nxt_name = nxt.__name__
            task_links[the_name] = TaskLinks(default=nxt_name, allowed=[nxt_name])
        return TaskNetworkFactory(name, task_class, task_links)

    def make_network(self, other_name: str | None = None) -> TaskNetwork:
        """Create an instance of the task network.

        By default, this uses the name defined on instantiation.

        Args:
            other_name (str, optional): Another name for the network. Defaults to None.

        Returns:
            TaskNetwork
        """
        use_name = other_name if other_name is not None else self.name
        return TaskNetwork(use_name, self.task_classes, self.task_links)
