# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""The task network class, and factory classes."""

from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from warnings import warn

if TYPE_CHECKING:
    from upstage_des.actor import Actor
    from upstage_des.tasks import Task, TerminalTask

from simpy import Process

from upstage_des.base import SimulationError, UpstageError, process
from upstage_des.tasks import DecisionTask

GUARD_FUNC = Callable[..., bool]


@dataclass
class TaskTransition:
    """A resolved transition in a task network.

    Users typically pass raw tuples to :class:`TaskLinks`; those are
    normalised to :class:`Transition` when the network is constructed.
    """

    target: str | type[Task]
    guard: GUARD_FUNC | None
    label: str | None = None


@dataclass
class TaskLinks:
    """Describes the transitions from one task to others in a network.

    There are two styles for defining transitions:

    **Preference style** (``default`` + ``allowed``)::

        TaskLinks(default="B", allowed=["B", "C"])

    **Guard style** (``transitions``) — an ordered list of
    ``(target, guard_or_None)`` or ``(target, guard, label)`` tuples.
    The first guard that returns ``True`` (or is ``None``, meaning
    unconditional) wins.  An optional third element provides a
    human-readable label for diagrams::

        TaskLinks(transitions=[
            TaskTransition(Break, lambda actor: actor.needs_break, "needs break"),
            TaskTransition(DoCheckout, None),  # fallback
        ])

    Both ``default``/``allowed`` and ``transitions`` accept task class
    references or string names.  Class references are resolved to their
    ``__name__`` when the network is constructed.
    """

    default: str | type[Task] | None = None
    allowed: Sequence[str | type[Task]] = field(default_factory=list)
    transitions: Sequence[TaskTransition] = field(default_factory=list)

    def _resolve(self) -> "TaskLinks":
        """Return a copy with all class references replaced by ``__name__`` strings."""
        default = self.default.__name__ if isinstance(self.default, type) else self.default
        allowed = [a.__name__ if isinstance(a, type) else a for a in self.allowed]
        resolved_trans: list[TaskTransition] = []
        for tr in self.transitions:
            target = tr.target.__name__ if isinstance(tr.target, type) else tr.target
            label = tr.label
            resolved_trans.append(TaskTransition(target=target, guard=tr.guard, label=label))
        return TaskLinks(default=default, allowed=allowed, transitions=resolved_trans)

    def _all_targets(self) -> list[str | type[Task]]:
        """Return every target referenced by this link (for validation/viz)."""
        targets: list[str | type[Task]] = list(self.allowed)
        if self.default is not None and self.default not in targets:
            targets.append(self.default)
        for tr in self.transitions:
            if tr.target not in targets:
                targets.append(tr.target)
        return targets


def _validate_network(
    task_classes: Mapping[str, type[Task]],
    task_links: Mapping[str, TaskLinks],
) -> None:
    """Check that all task-link references point to tasks that exist.

    Args:
        task_classes: Task name to class mapping.
        task_links: Task name to link mapping.

    Raises:
        UpstageError: If a referenced task name is not in *task_classes*.
    """
    known = set(task_classes.keys())
    missing: set[str] = set()
    for src, links in task_links.items():
        for target in links._all_targets():
            if isinstance(target, str) and target and target not in known:
                missing.add(target)
    if missing:
        raise UpstageError(
            f"Task link(s) reference unknown task name(s): {sorted(missing)}. "
            f"Known tasks: {sorted(known)}"
        )
    unlinked = known - set(task_links.keys())
    if unlinked:
        warn(
            f"Task(s) {sorted(unlinked)} are in task_classes but have no entry in task_links.",
            UserWarning,
            stacklevel=3,
        )


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
        _validate_network(task_classes, task_links)

    def is_feasible(self, curr: str, new: str) -> bool:
        """Determine if a task can follow another one.

        Args:
            curr (str): Current task name
            new (str): Potential next task name

        Returns:
            bool: If the new task can follow the current.
        """
        value = [x if isinstance(x, str) else x.__name__ for x in self.task_links[curr].allowed]
        return new in value

    def _next_task_name(
        self, curr_task_name: str, actor: "Actor", clear_queue: bool = False
    ) -> str:
        """Get the next task name.

        Priority:
        1. Actor's task queue (imperative override from interrupts etc.)
        2. Guard-based transitions (first ``True`` guard wins)
        3. ``default`` fallback

        Returns:
            str: Task name
        """
        # 1. Check the queue first (imperative override)
        task_from_queue = actor.get_next_task(self.name)
        if task_from_queue is not None:
            if clear_queue:
                actor._clear_task(self.name)
            return task_from_queue

        links = self.task_links[curr_task_name]

        # 2. Evaluate guards
        for tr in links.transitions:
            if tr.guard is None or tr.guard(actor):
                return tr.target if isinstance(tr.target, str) else tr.target.__name__

        # 3. Fall back to default
        default_next_task = links.default
        if default_next_task is None:
            raise SimulationError(
                f"No default task set for after {curr_task_name} on {actor} and no guard matched."
            )
        assert isinstance(default_next_task, str)
        return default_next_task

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
            actor.write_to_log("Outer: starting %s", task_name)
            actor._begin_next_task(self.name, task_name)
            task_cls = self.task_classes[task_name]
            task_instance: Task = task_cls()
            self._current_task_inst = task_instance
            self._current_task_inst._set_network_name(self.name)
            self._current_task_inst._set_network_ref(self)

            task_instance.on_enter(actor=actor)

            if (
                isinstance(self._current_task_inst, DecisionTask)
                and self._current_task_inst.DO_NOT_HOLD
            ):
                self._current_task_inst.run_skip(actor=actor)
            else:
                self._current_task_proc = self._current_task_inst.run(actor=actor)
                yield self._current_task_proc

            task_instance.on_exit(actor=actor)

            next_name = self._next_task_name(task_name, actor)
            self._current_task_name = next_name

    def _hook_suffix(self, task_name: str) -> str:
        """Return a parenthesized hook list, or empty string."""
        cls = self.task_classes.get(task_name)
        if cls is None:
            return ""
        hooks: list[str] = []
        if "on_enter" in cls.__dict__:
            hooks.append("on_enter")
        if "on_exit" in cls.__dict__:
            hooks.append("on_exit")
        if not hooks:
            return ""
        return f"({', '.join(hooks)})"

    def __repr__(self) -> str:
        return f"Task network: {self.name}"


class TaskNetworkFactory:
    """A factory for creating task network instances.

    The constructor accepts two styles:

    **String-keyed (original API)**::

        TaskNetworkFactory("Net", {"A": ATask, "B": BTask},
                           {"A": TaskLinks("B", ["B"]), ...})

    **Class-keyed (new API)** — ``task_classes`` is derived automatically::

        TaskNetworkFactory("Net", task_links={
            ATask: TaskLinks(default=BTask, allowed=[BTask]),
            ...
        })
    """

    @staticmethod
    def _resolve_inputs(
        task_classes: Mapping[str, type[Task]] | Mapping[type[Task], TaskLinks] | None,
        task_links: Mapping[str, TaskLinks] | Mapping[type[Task], TaskLinks] | None,
    ) -> tuple[dict[str, type[Task]], dict[str, TaskLinks]]:
        """Normalise the two constructor styles into ``(str→class, str→TaskLinks)``."""
        if task_classes is None and task_links is None:
            raise UpstageError("At least one of task_classes or task_links must be provided.")

        # Detect the class-keyed style: keys are types, not strings
        class_keyed_map: Mapping[type[Task], TaskLinks] | None = None

        if task_links is not None and task_classes is None:
            # task_links only — must be class-keyed
            if all(isinstance(k, type) for k in task_links):
                class_keyed_map = task_links  # type: ignore[assignment]
            else:
                raise UpstageError(
                    "When task_classes is omitted, task_links keys must be Task classes."
                )
        elif task_links is None and task_classes is not None:
            # task_classes only — check if it's actually the class-keyed form
            if all(isinstance(k, type) for k in task_classes):
                class_keyed_map = task_classes  # type: ignore[assignment]
            else:
                raise UpstageError(
                    "When task_links is omitted, task_classes must be a "
                    "{TaskClass: TaskLinks} mapping."
                )
        elif task_links is not None and task_classes is not None:
            # Both provided — check if task_links uses class keys
            if all(isinstance(k, type) for k in task_links):
                class_keyed_map = task_links  # type: ignore[assignment]
            elif all(isinstance(k, str) for k in task_classes) and all(
                isinstance(k, str) for k in task_links
            ):
                # Traditional string-keyed API — resolve any class refs in TaskLinks values
                str_links: dict[str, TaskLinks] = {}
                for k, v in task_links.items():
                    assert isinstance(k, str)
                    str_links[k] = v._resolve()
                str_classes = {k: v for k, v in task_classes.items() if isinstance(k, str)}
                return str_classes, str_links  # type: ignore[return-value]
            else:
                raise UpstageError(
                    "Cannot mix class and string keys across task_classes/task_links."
                )

        # ---- resolve class-keyed form ----
        assert class_keyed_map is not None
        out_classes: dict[str, type[Task]] = {}
        out_links: dict[str, TaskLinks] = {}
        for cls, links in class_keyed_map.items():
            task_name = cls.__name__
            out_classes[task_name] = cls
            resolved = links._resolve()
            out_links[task_name] = resolved
            # Also collect classes referenced in defaults / allowed / transitions
            for target in links._all_targets():
                if isinstance(target, type):
                    out_classes.setdefault(target.__name__, target)

        return out_classes, out_links

    def __init__(
        self,
        name: str,
        task_classes: Mapping[str, type[Task]] | Mapping[type[Task], TaskLinks] | None = None,
        task_links: Mapping[str, TaskLinks] | Mapping[type[Task], TaskLinks] | None = None,
    ) -> None:
        """Create a factory for making instances of a task network.

        Args:
            name (str): The network name
            task_classes: ``{str: Task}`` mapping **or** ``{Task: TaskLinks}``
                mapping (class-keyed style).  May be *None* when *task_links*
                uses class keys.
            task_links: ``{str: TaskLinks}`` or ``{Task: TaskLinks}`` mapping.
                May be *None* when *task_classes* carries the class-keyed form.
        """
        self.name = name
        resolved_classes, resolved_links = self._resolve_inputs(task_classes, task_links)
        self.task_classes: Mapping[str, type[Task]] = resolved_classes
        self.task_links: Mapping[str, TaskLinks] = resolved_links
        _validate_network(self.task_classes, self.task_links)

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
