# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""This file contains the fundamental Actor class for UPSTAGE."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from copy import copy, deepcopy
from dataclasses import dataclass
from inspect import Parameter, signature
from typing import TYPE_CHECKING, Any, Self

from simpy import Process

from upstage_des.events import Event

from .base import (
    SPECIAL_ENTITY_CONTEXT_VAR,
    MockEnvironment,
    NamedUpstageEntity,
    SettableEnv,
    SimulationError,
    UpstageError,
)
from .data_types import CartesianLocation, GeodeticLocation
from .states import (
    ActiveState,
    CartesianLocationChangingState,
    DetectabilityState,
    GeodeticLocationChangingState,
    ResourceState,
    State,
)
from .task import Task
from .task_network import TaskNetwork, TaskNetworkFactory
from .utils import get_caller_info, get_caller_object

__all__ = ("Actor",)

if TYPE_CHECKING:
    from .nucleus import TaskNetworkNucleus

LOC_STATE = GeodeticLocationChangingState | CartesianLocationChangingState
LOCATIONS = GeodeticLocation | CartesianLocation
LOC_LIST = list[GeodeticLocation] | list[CartesianLocation]


@dataclass
class TaskData:
    name: str
    process: Process


class Actor(SettableEnv, NamedUpstageEntity):
    """Actors perform tasks and are composed of states.

    You can subclass, but do not overwrite __init_subclass__.

    Always super().__init__().

    Parameters
    ----------
    name : str
        The name of the actor.  This is a required attribute.
    debug_log : bool, optional
        Run the debug logger which captures runtime information about the
        actor.
    **states
        Keyword arguments to set the values of the actor's states.

    Raises:
    ------
    ValueError
        If the keys of the states passed as keyword arguments do not match the
        names of the actor's states.

    """

    def __init_states(self, **states: Any) -> None:
        seen = set()
        for state, value in states.items():
            if state in self._state_defs:
                seen.add(state)
                setattr(self, state, value)
            else:
                raise UpstageError(f"Input to {self} was not expected: {state}={value}")
        exist = set(self._state_defs.keys())
        unseen = exist - seen
        for state_name in unseen:
            _state = self._state_defs[state_name]
            if _state.has_default():
                seen.add(state_name)
                _state._set_default(self)
        if len(seen) != len(exist):
            raise UpstageError(
                f"Missing values for states! These states need values: "
                f"{exist - seen} to be specified for '{self.name}'."
            )
        if "log" in seen:
            raise UpstageError("Do not name a state `log`")

    def __init__(
        self,
        *,
        name: str,
        debug_log: bool = True,
        debug_log_time: bool | None = None,
        **states: Any,
    ) -> None:
        """Create an Actor.

        Args:
            name (str): The name of the actor.
            debug_log (bool, optional): Whether to write to debug log. Defaults to True.
            debug_log_time (bool, optional): If time is logged in debug messages.
                Defaults to None (uses Stage value), otherwise local value is used.
            states (Any): Values for each state as kwargs.
        """
        self.name = name
        super().__init__()

        self._active_states: dict[str, dict[str, Any]] = {}
        self._num_clones: int = 0
        self._state_defs: dict[str, State] = getattr(self.__class__, "_state_defs", {})

        self._mimic_states: dict[str, tuple[Actor, str]] = {}  # has to be before other calls
        self._mimic_states_by_task: dict[Task, set[str]] = defaultdict(set)

        self._states_by_task: dict[Task, set[str]] = defaultdict(set)
        self._tasks_by_state: dict[str, set[Task]] = defaultdict(set)

        self._task_networks: dict[str, TaskNetwork] = {}
        self._task_queue: dict[str, list[str]] = {}

        self._knowledge: dict[str, Any] = {}
        self._is_rehearsing: bool = False

        self._debug_logging: bool = debug_log
        self._debug_log_time = debug_log_time
        self._debug_log: list[tuple[float | int, str]] = []

        self._state_histories: dict[str, list[tuple[float, Any]]] = {}

        # Task Network Nucleus hook-ins
        self._state_listener: TaskNetworkNucleus | None = None

        self.__init_states(**states)

    def __init_subclass__(
        cls,
        *args: Any,
        entity_groups: Iterable[str] | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init_subclass__(entity_groups=entity_groups)
        # get the states
        states = {}
        all_states = {}
        # This ensures that newer classes overwrite older states
        for base_class in cls.mro()[::-1]:
            for state_name, state in base_class.__dict__.items():
                if isinstance(state, State):
                    if base_class == cls:
                        states[state_name] = state
                        state.name = state_name
                    all_states[state_name] = state
        cls._state_defs = all_states

        nxt = cls.mro()[1]
        if nxt is object:
            raise UpstageError(f"Actor has bad inheritance, MRO: {cls.mro()}")

        sig = signature(cls.__init__)
        params = list(sig.parameters.values())
        # Find the "states=" parameter of the signature and remove it.
        state_parameter = [x for x in params if x.name == "states"]
        if state_parameter:
            params.remove(state_parameter[0])
        for state in states:
            params.insert(-1, Parameter(state, Parameter.KEYWORD_ONLY))
        try:
            setattr(cls.__init__, "__signature__", sig.replace(parameters=params))
        except ValueError as e:
            e.add_note("Failure likely due to repeated state name in inherited actor")
            raise e

    def _add_special_group(self) -> None:
        """Add self to the actor context list.

        Called by the NamedUpstageEntity on group inits.
        """
        ans = SPECIAL_ENTITY_CONTEXT_VAR.get().actors
        if self in ans:
            return
        ans.append(self)

    def _lock_state(self, *, state: str, task: Task) -> None:
        """Lock one of the actor's states by a given task.

        Args:
            state (str): The name of the state to lock
            task (Task): The task that is locking the state
        """
        the_state = self._state_defs[state]
        if not the_state.IGNORE_LOCK:
            # single-task only, so no task should
            # be associated with this state
            if self._tasks_by_state[state]:
                raise SimulationError(
                    f"State '{state}' cannot be used by '{task}' because it is "
                    f"locked by {self._tasks_by_state[state]}"
                )
        else:
            # We can have multiple locks, but make sure we are repeating a lock
            if task in self._tasks_by_state[state]:
                raise SimulationError(
                    f"State '{state}' already locked by '{task}'. "
                    "Did you forget to unlock/deactivate it?"
                )
        self._states_by_task[task].add(state)
        self._tasks_by_state[state].add(task)

    def _set_active_state_data(
        self,
        state_name: str,
        started_at: float | None = None,
        **data: Any,
    ) -> None:
        """Set the data for an active state.

        Args:
            state_name (str): Name of the state
            started_at (Optional[float], optional): Time the data is set at. Defaults to None.
            **data (Any): key:values as kwargs for the state data.
        """
        # Rule: underscored active data will get remembered
        started_at = self.env.now if started_at is None else started_at
        old_data = self._active_states.get(state_name, {})
        new_data = {"started_at": started_at, **data}
        keep_old = {k: v for k, v in old_data.items() if k not in new_data and "_" == k[0]}
        new_data.update(keep_old)
        self._active_states[state_name] = new_data

    def activate_state(
        self,
        *,
        state: str,
        task: Task,
        **kwargs: Any,
    ) -> None:
        """Set a state as active.

        Note:
            This method is used by the tasks for activating states they use/modify.

        TODO: on init, create `activate_<statename>` methods that type-hint the inputs

        Args:
            state (str): The name of the state to set as active.
            task (Task): The task that is activating the state.
            **kwargs (Any): key:values as kwargs for the state activation.
        """
        if state not in self._state_defs:
            raise SimulationError(f"No state named '{state}' to activate")
        self._lock_state(state=state, task=task)
        self._set_active_state_data(state_name=state, started_at=self.env.now, task=task, **kwargs)
        # any initialization in the state needs to be called via attribute access
        getattr(self, state)
        # The activation handles getattr
        _state = self._state_defs[state]
        assert isinstance(_state, ActiveState)
        _state.activate(self, task=task)

    def activate_linear_state(self, *, state: str, rate: float, task: Task) -> None:
        """Shortcut for activating a LinearChangingState.

        Args:
            state (str): The name of the LinearChangingState to set as active.
            rate (float): The rate of the change
            task (Task): The task that is activating
        """
        self.activate_state(state=state, task=task, rate=rate)

    def activate_location_state(
        self, *, state: str, speed: float, waypoints: LOC_LIST, task: Task
    ) -> None:
        """Shortcut for activating a (Cartesian|Geodetic)LocationChangingState.

        Args:
            state (str): State name
            speed (float): The speed to move at
            waypoints (LOC_LIST): Waypoints to move over
            task (Task): The task that the state is activated during.
        """
        self.activate_state(
            state=state,
            speed=speed,
            waypoints=waypoints,
            task=task,
        )

    def _unlock_state(self, *, state: str, task: Task) -> None:
        """Release a task's lock of a state.

        Args:
            state (str): The name of the state to lock
            task (Task): The task that is locking the state
        """
        the_state = self._state_defs[state]
        if not the_state.IGNORE_LOCK:
            # single-task only, so only one task should
            # be associated with this state
            if task not in self._tasks_by_state[state]:
                raise SimulationError(
                    f"State `{state}` isn't locked by '{task}', but it's trying to be unlocked."
                )
            self._states_by_task[task].remove(state)
            self._tasks_by_state[state].remove(task)
        elif task in self._tasks_by_state[state]:
            self._states_by_task[task].remove(state)
            self._tasks_by_state[state].remove(task)
        else:
            raise UpstageError(f"State '{state}' was not activated by '{task}', cannot deactivate")

    def deactivate_states(self, *, states: str | Iterable[str], task: Task) -> None:
        """Set a list of active states to not active.

        Args:
            states (str | Iterable[str]): The names of the states to deactivate.
            task (Task): The task that is deactivating the states.
        """
        if isinstance(states, str):
            states = [states]

        for state in states:
            self.deactivate_state(state=state, task=task)

    def deactivate_state(self, *, state: str, task: Task) -> None:
        """Deactivate a specific state.

        Args:
            state (str): The name of the state to deactivate.
            task (Task): The task that is deactivating the state.
        """
        self._unlock_state(state=state, task=task)

        # the deactivated state may need to be updated
        getattr(self, state)
        # and then deactivate it, only if it was unlocked
        the_state = self._state_defs[state]
        if not isinstance(the_state, ActiveState):
            raise UpstageError(f"Stage {state} is not an active type state.")
        ignore = the_state.deactivate(self, task=task)
        if state in self._active_states and not ignore:
            del self._active_states[state]

    def deactivate_all_states(self, *, task: Task) -> None:
        """Deactivate all states in the actor for a given task.

        Args:
            task (Task): The task that is deactivating the states.
        """
        state_names = list(self._states_by_task[task])
        self.deactivate_states(states=state_names, task=task)

    def get_active_state_data(
        self, state_name: str, without_update: bool = False
    ) -> dict[str, Any]:
        """Get the data for a specific state.

        Args:
            state_name (str): The name of the state for which to retrieve the data.
            without_update (bool): Whether or not to update the state to the current
                sim time. Defaults to True

        Returns:
            dict[str, Any]: The state data.
        """
        if not without_update:
            getattr(self, state_name)
        ans: dict[str, Any] = self._active_states.get(state_name, {})
        return ans

    def _mimic_state_name(self, self_state: str) -> str:
        """Create a mimic state name.

        Args:
            self_state (str): The name of the state

        Returns:
            str: Mimic-safe name
        """
        return f"{id(self)}-{self_state}"

    def activate_mimic_state(
        self,
        *,
        self_state: str,
        mimic_state: str,
        mimic_actor: "Actor",
        task: Task,
    ) -> None:
        """Activate a state to mimic a state on another actor.

        Args:
            self_state (str): State name to be the mimic
            mimic_state (str): State on the other actor to be mimiced
            mimic_actor (Actor): The other actor.
            task (Task): The task during which the state is mimiced.
        """
        caller = get_caller_object()
        if isinstance(caller, Task) and caller._rehearsing:
            raise UpstageError("Mimic state activated on rehearsal. This is unsupported/unstable")
        if self_state in self._mimic_states:
            raise UpstageError(f"{self_state} already mimicked")
        self._mimic_states[self_state] = (mimic_actor, mimic_state)
        self._mimic_states_by_task[task].add(self_state)

        state = self._state_defs[self_state]
        self_state_name = self._mimic_state_name(self_state)
        if state.is_recording:

            def recorder(instance: Actor, value: Any) -> None:
                if instance is mimic_actor:
                    state._do_record(self, value)

            mimic_actor._add_callback_to_state(self_state_name, recorder, mimic_state)

    def deactivate_mimic_state(self, *, self_state: str, task: Task) -> None:
        """Deactivate a mimicking state.

        Args:
            self_state (str): State name
            task (Task): Task it's running in.
        """
        getattr(self, self_state)
        mimic_actor, mimic_state = self._mimic_states[self_state]
        state = self._state_defs[self_state]
        self_state_name = self._mimic_state_name(self_state)
        if state.is_recording:
            mimic_actor._remove_callback_from_state(self_state_name, mimic_state)
        del self._mimic_states[self_state]
        self._mimic_states_by_task[task].remove(self_state)

    def deactivate_all_mimic_states(self, *, task: Task) -> None:
        """Deactivate all mimicking states in the actor for a given task.

        Args:
            task (Task): The task where states are mimicking others.
        """
        for state in list(self._mimic_states):
            self.deactivate_mimic_state(self_state=state, task=task)

    def _add_callback_to_state(
        self,
        source: Any,
        callback: Callable[["Actor", Any], Any],
        state_name: str,
    ) -> None:
        """Add a callback to a state for recording.

        Args:
            source (Any): The source for keying the callback (unused, but for the key)
            callback (Callable[[Actor, Any], Any]): Takes the actor and state value
            state_name (str): _description_
        """
        state: State = self._state_defs[state_name]
        state._add_callback(source, callback)

    def _remove_callback_from_state(
        self,
        source: Any,
        state_name: str,
    ) -> None:
        """Remove a state callback based on the source key.

        Args:
            source (Any): Callback key
            state_name (str): Name of the state with the callback.
        """
        state = self._state_defs[state_name]
        state._remove_callback(source)

    def get_knowledge(self, name: str, must_exist: bool = False) -> Any:
        """Get a knowledge value from the actor.

        Args:
            name (str):  The name of the knowledge
            must_exist (bool): Raise an error if the knowledge isn't present. Defaults to false.

        Returns:
            Any: The knowledge value. None if the name doesn't exist.
        """
        if must_exist and name not in self._knowledge:
            raise SimulationError(f"Knowledge '{name}' does not exist in {self}")
        return self._knowledge.get(name, None)

    def get_and_clear_knowledge(self, name: str, caller: str | None = None) -> Any:
        """Get knowledge and clear it.

        Clearing knowledge implies it must exist in the direct methods, so the
        same assumption holds here.

        Args:
            name (str): Knowledge name.
            caller (str): The name of the calling process for logging. Defaults to None.

        Returns:
            Any: The knowledge value.
        """
        know = self.get_knowledge(name, must_exist=True)
        self.clear_knowledge(name, caller)
        return know

    def _log_caller(
        self,
        method_name: str = "",
        caller_level: int = 1,
        caller_name: str | None = None,
    ) -> None:
        """Log information about who is calling this method.

        If no caller_name is given, it is searched for in the stack.

        Args:
            method_name (str, optional): Method name for logging. Defaults to "".
            caller_level (int, optional): Level to look up for the caller. Defaults to 1.
            caller_name (Optional[str], optional): Name of the caller. Defaults to None.
        """
        if caller_name is None:
            info = get_caller_info(caller_level=caller_level + 1)
        else:
            info = caller_name
        self.log(f"method '{method_name}' called by '{info}'")

    def set_knowledge(
        self,
        name: str,
        value: Any,
        overwrite: bool = False,
        caller: str | None = None,
    ) -> None:
        """Set a knowledge value.

        Raises an error if the knowledge exists and overwrite is False.

        Args:
            name (str): The name of the knowledge item.
            value (Any): The value to store for the knowledge.
            overwrite (bool, Optional): Allow the knowledge to be changed if it exits.
                Defaults to False.
            caller (str, Optional): The name of the object that called the method.
        """
        self._log_caller(f"set_knowledge '{name}={value}'", caller_name=caller)
        if name in self._knowledge and not overwrite:
            raise SimulationError(
                f"Actor {self} overwriting existing knowledge {name} "
                f"without override permission. \n"
                f"Current: {self._knowledge[name]}, New: {value}"
            )
        else:
            self._knowledge[name] = value

    def clear_knowledge(self, name: str, caller: str | None = None) -> None:
        """Clear a knowledge value.

        Raises an error if the knowledge does not exist.

        Args:
            name (str): The name of the knowledge item to clear.
            caller (str):  The name of the Task that called the method.
                Used for debug logging purposes.

        """
        self._log_caller(f"clear_knowledge '{name}'", caller_name=caller)
        if name not in self._knowledge:
            raise SimulationError(f"Actor {self} does not have knowledge: {name}")
        else:
            del self._knowledge[name]

    def set_bulk_knowledge(
        self, know: dict[str, Any], overwrite: bool = False, caller: str | None = None
    ) -> None:
        """Set multiple knowledge entries at once.

        Args:
            know (dict[str, Any]): Dictionary of key:value pairs of knowledge.
            overwrite (bool, optional): If overwrite is allowed. Defaults to False.
            caller (str | None, optional): The name of the Task that called the method.
                Defaults to None.
        """
        for k, v in know.items():
            self.set_knowledge(k, v, overwrite, caller)

    def clear_bulk_knowledge(self, names: Iterable[str], caller: str | None = None) -> None:
        """Clear a list of knowledge entries.

        Args:
            names (Iterable[str]): Knowledge names.
            caller (str | None, optional): The name of the Task that called the method.
                Defaults to None.
        """
        for name in names:
            self.clear_knowledge(name, caller)

    def get_bulk_knowledge(self, names: Iterable[str], must_exist: bool = False) -> dict[str, Any]:
        """Get multiple knowledge items.

        Args:
            names (Iterable[str]): Names of the knowledge
            must_exist (bool, optional): If all entires must exist. Defaults to False.

        Returns:
            dict[str, Any]: The knowledge values. None if not present.
        """
        return {name: self.get_knowledge(name, must_exist) for name in names}

    def get_and_clear_bulk_knowledge(
        self, names: Iterable[str], caller: str | None = None
    ) -> dict[str, Any]:
        """Get and clear multiple knowledge entries.

        Args:
            names (Iterable[str]): The knowledge to retrieve and delete.
            caller (str | None, optional): The name of the caller. Defaults to None.

        Returns:
            dict[str, Any]: The retrieved knowledge.
        """
        return {name: self.get_and_clear_knowledge(name, caller) for name in names}

    def add_task_network(self, network: TaskNetwork) -> None:
        """Add a task network to the actor.

        Args:
            network (TaskNetwork): The task network to add to the actor.
        """
        network_name = network.name
        if network_name in self._task_networks:
            raise SimulationError(f"Task network{network_name} already in {self}")
        self._task_networks[network_name] = network
        self._task_queue[network_name] = []

    def clear_task_queue(self, network_name: str) -> None:
        """Empty the actor's task queue.

        This will cause the task network to be used for task flow.

        Args:
            network_name (str): The name of the network to clear the task queue.
        """
        self._log_caller("clear_task_queue")
        self._task_queue[network_name] = []

    def set_task_queue(self, network_name: str, task_list: list[str]) -> None:
        """Initialize an actor's empty task queue.

        Args:
            network_name (str): Task Network name
            task_list (list[str]): List of task names to queue.

        Raises:
            SimulationError: _description_
        """
        self._log_caller("set_task_queue")
        if self._task_queue[network_name]:
            raise SimulationError(f"Task queue on {self.name} is already set. Use append or clear.")
        self._task_queue[network_name] = list(task_list)

    def get_task_queue(self, network_name: str) -> list[str]:
        """Get the actor's task queue on a single network.

        Args:
            network_name (str): The network name

        Returns:
            list[str]: List of task names in the queue
        """
        return self._task_queue[network_name]

    def get_all_task_queues(self) -> dict[str, list[str]]:
        """Get the task queues for all running networks.

        Returns:
            dict[str, list[str]]: Task names, keyed on task network name.
        """
        queues: dict[str, list[str]] = {}
        for name in self._task_networks.keys():
            queues[name] = self.get_task_queue(name)
        return queues

    def get_next_task(self, network_name: str) -> None | str:
        """Return the next task the actor has been told if there is one.

        This does not clear the task, it's information only.

        Args:
            network_name (str): The name of the network

        Returns:
            None | str: The name of the next task, None if no next task.
        """
        queue = self._task_queue[network_name]
        queue_length = len(queue)
        return None if queue_length == 0 else queue[0]

    def _clear_task(self, network_name: str) -> None:
        """Clear a task from the queue.

        Useful for rehearsal.
        """
        self._task_queue[network_name].pop(0)

    def _begin_next_task(self, network_name: str, task_name: str) -> None:
        """Clear the first task in the task queue.

        The task name is required to check that the next task follows the actor's plan.

        Args:
            network_name (str): The task network name
            task_name (str): The name of the task to start
        """
        queue = self._task_queue.get(network_name)
        if queue and queue[0] != task_name:
            raise SimulationError(
                f"Actor {self.name} commanded to perform '{task_name}' but '{queue[0]}' is expected"
            )
        elif not queue:
            self.set_task_queue(network_name, [task_name])
        self.log(f"begin_next_task: Starting {task_name} task")
        self._task_queue[network_name].pop(0)

    def start_network_loop(
        self,
        network_name: str,
        init_task_name: str | None = None,
    ) -> None:
        """Start a task network looping/running on an actor.

        If no task name is given, it will default to following the queue.

        Args:
            network_name (str): Network name.
            init_task_name (str, optional): Task to start with. Defaults to None.
        """
        network = self._task_networks[network_name]
        network.loop(actor=self, init_task_name=init_task_name)

    def get_running_task(self, network_name: str) -> TaskData | None:
        """Return name and process reference of a task on this Actor's task network.

        Useful for finding a process to call interrupt() on.

        Args:
            network_name (str): Network name.

        Returns:
            TaskData: Dataclass of name and process for the current task.
                {"name": Name, "process": the Process simpy is holding.}
        """
        if network_name not in self._task_networks:
            raise SimulationError(f"{self} does not have a task networked named {network_name}")
        net = self._task_networks[network_name]
        if net._current_task_proc is not None:
            assert net._current_task_name is not None
            assert net._current_task_proc is not None
            task_data = TaskData(name=net._current_task_name, process=net._current_task_proc)
            return task_data
        return None

    def get_running_tasks(self) -> dict[str, TaskData]:
        """Get all running task data.

        Returns:
            dict[str, dict[str, TaskData]]: Dictionary of all running tasks.
                Keyed on network name, then {"name": Name, "process": ...}
        """
        tasks: dict[str, TaskData] = {}
        for name, net in self._task_networks.items():
            if net._current_task_proc is not None:
                assert net._current_task_name is not None
                tasks[name] = TaskData(name=net._current_task_name, process=net._current_task_proc)
        return tasks

    def interrupt_network(self, network_name: str, **interrupt_kwargs: Any) -> None:
        """Interrupt a running task network.

        Args:
            network_name (str): The name of the network.
            interrupt_kwargs (Any): kwargs to pass to the interrupt.
        """
        data = self.get_running_task(network_name)
        if data is None:
            raise UpstageError(f"No processes named {network_name} is running.")
        data.process.interrupt(**interrupt_kwargs)

    def has_task_network(self, network_id: Any) -> bool:
        """Test if a network id exists.

        Args:
            network_id (Any): Typically a string for the network name.

        Returns:
            bool: If the task network is on this actor.
        """
        return network_id in self._task_networks

    def suggest_network_name(self, factory: TaskNetworkFactory) -> str:
        """Deconflict names of task networks by suggesting a new name.

        Used for creating multiple parallel task networks.

        Args:
            factory (TaskNetworkFactory): The factory from which you will create the network.

        Returns:
            str: The network name to use
        """
        new_name = factory.name
        if new_name not in self._task_networks:
            return new_name
        i = 0
        while new_name in self._task_networks:
            i += 1
            new_name = f"{factory.name}_{i}"
        return new_name

    def delete_task_network(self, network_id: Any) -> None:
        """Deletes a task network reference.

        Be careful, the network may still be running!

        Do any interruptions on your own.

        Args:
            network_id (Any): Typically a string for the network name.
        """
        if not self.has_task_network(network_id):
            raise SimulationError(f"No networked with id: {network_id} to delete")
        del self._task_networks[network_id]

    def rehearse_network(
        self,
        network_name: str,
        task_name_list: list[str],
        knowledge: dict[str, Any] | None = None,
        end_task: str | None = None,
    ) -> Self:
        """Rehearse a network on this actor.

        Supply the network name, the tasks to rehearse from this state, and
        any knowledge to apply to the cloned actor.

        Args:
            network_name (str): Network name
            task_name_list (list[str]): Tasks to rehearse on the network.
            knowledge (dict[str, Any], optional): knowledge to give to the cloned
                actor. Defaults to None.
            end_task (str, optional): A task to end on once reached.

        Returns:
            Actor: The cloned actor after rehearsing the network.
        """
        knowledge = {} if knowledge is None else knowledge
        net = self._task_networks[network_name]
        understudy = net.rehearse_network(
            actor=self,
            task_name_list=task_name_list,
            knowledge=knowledge,
            end_task=end_task,
        )
        return understudy

    def clone(
        self,
        new_env: MockEnvironment | None = None,
        knowledge: dict[str, Any] | None = None,
        **new_states: Any,
    ) -> Self:
        """Clones an actor and assigns it a new environment.

        Note:
            This function is useful when testing if an actor can accomplish a
            task.

            In general, cloned actor are referred to as ``understudy``
            to keep with the theater analogy.

            The clones' names are appended with the label ``'[CLONE #]'`` where
            ``'#'`` indicates the number of clones of the actor.

        Args:
            new_env (Optional[MockEnvironment], optional): Environment for cloning.
                Defaults to None.
            knowledge (Optional[dict[str, Any]], optional): Knowledge for the clone.
                Defaults to None.
            new_states (Any): New states to add to the actor when cloning.

        Returns:
            Actor: The cloned actor of the same type
        """
        knowledge = {} if knowledge is None else knowledge
        new_env = MockEnvironment.mock(self.env) if new_env is None else new_env

        states: dict[str, Any] = {}
        for state in self.states:
            state_obj = self._state_defs[state]
            if isinstance(state_obj, ResourceState):
                states[state] = state_obj._make_clone(self, getattr(self, state))
            else:
                states[state] = copy(getattr(self, state))
        states.update(new_states)

        self._num_clones += 1

        clone = self.__class__(
            name=self.name + f" [CLONE {self._num_clones}]",
            debug_log=self._debug_logging,
            debug_log_time=self._debug_log_time,
            **states,
        )
        clone.env = new_env

        ignored_attributes = list(states.keys()) + ["env", "stage"]

        for attribute_name, attribute in self.__class__.__dict__.items():
            if not any(
                (
                    attribute_name in ignored_attributes,
                    attribute_name.startswith("_"),
                    callable(attribute),
                )
            ):
                setattr(clone, attribute_name, attribute)

        # update the state histories
        for state_name in self._state_defs:
            if state_name in self._state_histories:
                clone._state_histories[state_name] = deepcopy(self._state_histories[state_name])

        clone._knowledge = {}
        for name, data in self._knowledge.items():
            clone._knowledge[name] = copy(data)

        for name, data in knowledge.items():
            clone._knowledge[name] = copy(data)

        clone._task_queue = copy(self._task_queue)
        clone._task_networks = copy(self._task_networks)

        if clone._debug_logging:
            clone._debug_log = list(self._debug_log)

        clone._is_rehearsing = True
        return clone

    def log(self, msg: str | None = None) -> list[tuple[float | int, str]] | None:
        """Add to the log or return it.

        Only adds to log if debug_logging is True.

        Args:
            msg (str, Optional): The message to log.

        Returns:
            list[str] | None: The log if no message is given. None otherwise.
        """
        if msg is None:
            return self._debug_log
        elif self._debug_logging:
            dlt = self._debug_log_time
            do_time = dlt if dlt is not None else self.stage.get("debug_log_time", True)
            if do_time:
                ts = self.pretty_now
                msg = f"{ts} {msg}"
            self._debug_log += [(self.env.now, msg)]
        return None

    def get_log(self) -> list[tuple[float | int, str]]:
        """Get the debug log.

        Returns:
            list[str]: List of log messages.
        """
        return self._debug_log

    @property
    def states(self) -> tuple[str, ...]:
        """Get the names of the actor's states.

        Returns:
            tuple[str]: State names
        """
        return tuple(self._state_defs.keys())

    @property
    def state_values(self) -> dict[str, Any]:
        """Get the state names and values.

        Returns:
            dict[str, Any]: State name:value pairs.
        """
        return {k: getattr(self, k) for k in self.states}

    def _get_detection_state(self) -> None | str:
        """Find the name of a state is of type DetectabilityState.

        Returns:
            None | str: The name of the state (None if none found).
        """
        detection = [k for k, v in self._state_defs.items() if isinstance(v, DetectabilityState)]
        if len(detection) > 1:
            raise NotImplementedError("Only 1 state of type DetectabilityState allowed for now")
        return None if not detection else detection[0]

    def _match_attr(self, name: str) -> str | None:
        """Test if self has a matching attribute name.

        Args:
            name (str): The attribute to find

        Returns:
            str | None: The name if it has it, None otherwise.
        """
        if not hasattr(self, name):
            return None
        return name

    def _get_matching_state(
        self,
        state_class: type[State],
        attr_matches: dict[str, Any] | None = None,
    ) -> str | None:
        """Find a state that matches the class and optional attributes and return its name.

        For multiple states with the same class, this returns the first available.

        Args:
            state_class (State): The class of state to search for
            attr_matches (Optional[dict[str, Any]], optional): Attributes and values
                to match. Defaults to None.

        Returns:
            str | None: The name of the state (for getattr)
        """

        def match_tester(nm: str, val: Any, state: State) -> bool:
            if hasattr(state, nm):
                matching: bool = getattr(state, nm) == val
                return matching
            return False

        for name, state in self._state_defs.items():
            if not isinstance(state, state_class):
                continue

            if attr_matches is None:
                return self._match_attr(name)

            has_attribute_matches = all(
                match_tester(nm, val, state) for nm, val in attr_matches.items()
            )
            if has_attribute_matches:
                return self._match_attr(name)
        return None

    def create_knowledge_event(
        self,
        *,
        name: str,
        rehearsal_time_to_complete: float = 0.0,
    ) -> Event:
        """Create an event and store it in knowledge.

        Useful for creating simple hold points in Tasks that can be succeeded by
        other processes.

        Example:
            >>> def task(self, actor):
            >>>     evt = actor.create_knowledge_event(name="hold")
            >>>     yield evt
            >>>     ... # do things
            ...
            >>> def other_task(self, actor):
            >>>     if condition:
            >>>         actor.succeed_knowledge_event(name="hold")

        Args:
            name (str): Name of the knowledge slot to store the event in.
            rehearsal_time_to_complete (float, optional): The event's expected
                time to complete. Defaults to 0.0.

        Returns:
            Event: The event to yield on
        """
        event = Event(rehearsal_time_to_complete=rehearsal_time_to_complete)
        # Rehearsals on this method won't clear the event, so save the user some trouble.
        overwrite = True if self._is_rehearsing else False
        self.set_knowledge(name, event, overwrite=overwrite)
        return event

    def succeed_knowledge_event(self, *, name: str, **kwargs: Any) -> None:
        """Succeed and clear an event stored in the actor's knowledge.

        See "create_knowledge_event" for usage example.

        Args:
            name (str): Event knowledge name.
            **kwargs (Any): Any payload to send to the event. Defaults to None
        """
        event = self.get_knowledge(name)
        if event is None:
            raise SimulationError(f"No knowledge named {name} to succeed")
        if not isinstance(event, Event):
            raise SimulationError(f"Knowledge {name} is not an Event.")
        self.clear_knowledge(name, "actor.succeed_knowledge_event")
        event.succeed(**kwargs)

    def get_remaining_waypoints(
        self, location_state: str
    ) -> list[GeodeticLocation] | list[CartesianLocation]:
        """Convenience method for interacting with LocationChangingStates.

        Primary use case is when restarting a Task that has a motion element to
        allow updating waypoint knowledge easily.

        Args:
            location_state (str): The name of the <LocationChangingState>

        Returns:
            list[Location]: List of waypoints yet to be reached
        """
        loc_state = self._state_defs[location_state]
        assert isinstance(loc_state, GeodeticLocationChangingState | CartesianLocationChangingState)
        wypts = loc_state._get_remaining_waypoints(self)
        return wypts

    def get_nucleus(self) -> "TaskNetworkNucleus":
        """Return the actor's nucleus.

        Returns:
            TaskNetworkNucleus: The nucleus on the actor.
        """
        if self._state_listener is None:
            raise SimulationError("Expected a nucleus, but none found.")
        return self._state_listener

    def record_state(self, state_name: str) -> None:
        """Record a state by its name.

        Useful for states that have attributes that aren't set
        via the descriptor, such as dictionaries or dataclasses.

        Args:
            state_name (str): The name of the state.
        """
        if state_name not in self.states:
            raise SimulationError(f"No state '{state_name}' to record.")
        v = getattr(self, state_name)
        self._state_defs[state_name]._do_record(self, v)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: {self.name}"
