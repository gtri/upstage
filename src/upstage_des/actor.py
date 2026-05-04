# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Actor system with dataclass-like field transformation and State descriptors."""

import logging
from collections import OrderedDict, defaultdict, deque
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Self, dataclass_transform

from simpy import Process

from upstage_des._logging import get_actor_logger
from upstage_des.base import (
    SimulationError,
    UpstageBase,
)
from upstage_des.root_types import StateDataDict
from upstage_des.states import LinearChangingState, State, _ActiveState

EMPTY_KNOWLEDGE = object()


@dataclass
class TaskData:
    """Data about a task process on an Actor."""

    name: str
    process: Process


def _process_model_class(cls: type[Any]) -> None:
    """Apply dataclass-like behavior + ModelField descriptors to the class."""
    model_fields: OrderedDict[str, State] = OrderedDict()
    my_fields: list[str] = []
    for base in reversed(cls.__mro__):
        if base is object:
            continue
        annotations = getattr(base, "__annotations__", {})
        for name in annotations:
            if name.startswith("_") or name in {"__weakref__", "__dict__", "__model_fields__"}:
                continue

            # Use State if defined, else create one
            if name in base.__dict__ and isinstance(base.__dict__[name], State):
                field_obj = base.__dict__[name]
            else:
                default = base.__dict__.get(name, ...)
                if default is ...:
                    field_obj = State()
                    if name == "knowledge":
                        field_obj._default_factory = dict
                else:
                    field_obj = State(default=default)
            # In all cases, drop the type info into the data
            field_obj._add_type(annotations[name])

            if not getattr(field_obj, "name", None):
                field_obj.__set_name__(cls, name)

            model_fields[name] = field_obj
            if base is cls:
                my_fields.append(name)
    # set attrs _after_, which helps inheritence
    model_fields_dict: dict[str, State[Any]] = {}
    for name, field_obj in model_fields.items():
        model_fields_dict[name] = field_obj
        setattr(cls, name, field_obj)
    cls.__model_fields__ = model_fields_dict

    def __init__(self: Any, **kwargs: Any) -> None:
        # Set up the data storage
        self._state_histories = {}
        self._log = deque()
        self._is_clone = False
        self._state_data = {}
        self._states_by_cause = defaultdict(set)
        self._causes_by_state = {}

        for name in model_fields.keys():
            value = kwargs.pop(name, ...)
            field = self.__model_fields__[name]
            self._state_data[name] = {}
            if value is ...:
                if not field.has_default:
                    raise ValueError(f"No input supplied for state: {name}")
                field._set_default(self)
            else:
                field.__set__(self, value)
        UpstageBase.__init__(self, **kwargs)
        if hasattr(cls, "__post_init__"):
            cls.__post_init__(self)

        # logging need `name`, so it comes later.
        self._logger = get_actor_logger(self)

    cls.__init__ = __init__


@dataclass_transform(
    kw_only_default=True,
    frozen_default=False,
    field_specifiers=(State,),
)
class _BaseActor(UpstageBase):
    """Base class for actors with automatic field processing and State support.

    Actors automatically process type annotations to create descriptors:
    - State[T] annotations become State descriptors with hooks and validation
    - Other annotations become ModelField descriptors with default value support

    Attributes:
        name: The actor's name
        debug_logging: Whether to enable debug logging
        is_clone: Whether this actor is a clone (set by clone() method)

    Example:
        >>> class MyActor(BaseAct):
        ...     name: str
        ...     fuel: State[float] = State(default=100.0)
        ...
        >>> actor = MyActor(name="vehicle")
        >>> actor.fuel
        100.0
    """

    name: str
    debug_logging: bool
    knowledge: dict[str, Any]

    _is_clone: bool
    _state_histories: dict[str, deque[tuple[float, Any] | tuple[float, Any, Any]]]
    _log: deque[tuple[float, str]]
    _state_data: dict[str, StateDataDict]
    __model_fields__: dict[str, State]
    _states_by_cause: dict[Any, set[str]]
    _causes_by_state: dict[str, Any]
    _logger: logging.Logger

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Apply the model transformation to every subclass
        _process_model_class(cls)

    @property
    def is_clone(self) -> bool:
        """Return whether this actor is a clone."""
        return getattr(self, "_is_clone", False)

    def _record_state_change(self, name: str, value: Any, extra: Any | None = None) -> None:
        if name in ["name", "debug_logging", "is_clone", "knowledge"]:
            return
        time = self.env.now
        if name not in self._state_histories:
            self._state_histories[name] = deque()
        to_append = (time, value) if extra is None else (time, value, extra)
        self._state_histories[name].append(to_append)

    ###########################################################
    ### Logging ##############################################
    def write_to_log(self, to_write: str, *args: Any, level: int = logging.INFO) -> None:
        """Write to the log.

        Args:
            to_write (str): The text to write
            args (Any): Objects to formate into the `to_write` string.
            level (int): Logging library level. Defaults to INFO.
        """
        logger = self._logger
        logger_wants = logger.isEnabledFor(level)

        if not self.debug_logging and not logger_wants:
            return None
        formatted = to_write % args if args else to_write
        if self.debug_logging:
            self._log.append((self.env.now, formatted))
        if logger_wants:
            logger.log(level, formatted)

    def get_log(self) -> deque[tuple[float, str]]:
        """Retrieve the log.

        Returns:
            deque[tuple[float, str]]: The log.
        """
        return self._log

    ###########################################################
    ### Knowledge Helpers #####################################
    def get_knowledge(self, name: str, must_exist: bool = False) -> Any:
        """Get a piece of knowledge by name.

        If the knowledge doesn't exist, and it must not exist, this return
        upstage_des.actor.EMPTY_KNOWLEDGE. Test equivalence using `is` to ensure
        you aren't getting a None you meant to set.

        Args:
            name (str): Name
            must_exist (bool, optional): If the knowledge must exist.
                Defaults to False.

        Raises:
            SimulationError: If the knowledge must exist, but doesn't

        Returns:
            Any: The value of the knowledge entry.
        """
        if name not in self.knowledge:
            if must_exist:
                raise SimulationError(f"Knowledge {name} does not exist on {self.name}")
            return EMPTY_KNOWLEDGE
        return self.knowledge[name]

    def set_knowledge(
        self, name: str, value: Any, overwrite: bool = True, caller: Any = ""
    ) -> None:
        """Set knowledge, checking for overwrite and logging who set it.

        Args:
            name (str): Knowledge name
            value (Any): Knowledge value
            caller (Any): This gets logged as the reason for setting knowledge.
            overwrite (bool, optional): Allow existing knowledge to be overwritten.
                Defaults to True.

        Raises:
            SimulationError: If existing knowledge would be overwritten without permission.
        """
        self.write_to_log(f"Setting {name} knowledge. Reason: {caller}")
        if self.get_knowledge(name) is EMPTY_KNOWLEDGE or overwrite:
            self.knowledge[name] = value
            return
        raise SimulationError(f"Knowledge {name} is already set, and overwrite is {overwrite}")

    def clear_knowledge(self, name: str, caller: Any = "") -> None:
        """Delete knowledge from the dictonary.

        Args:
            name (str): The name
            caller (str): Who is calling this method. Defaults to "".
        """
        self.write_to_log(f"Clearing {name} knowledge. Reason: {caller}")
        if name in self.knowledge:
            del self.knowledge[name]

    def get_and_clear_knowledge(self, name: str, caller: Any = "") -> Any:
        """Get a knowledge value and clear it.

        The knowledge is assumed to exist.

        Args:
            name (str): The name
            caller (str): Who is calling this method. Defaults to "".

        Raises:
            SimulationError: If the knowledge doesn't exist

        Returns:
            Any: Knowledge value
        """
        know = self.get_knowledge(name, must_exist=True)
        self.clear_knowledge(name, caller=caller)
        return know

    ###########################################################
    ### Activate States #######################################
    def _lock_state(self, *, state: str, cause: Any) -> None:
        """Lock one of the actor's states by a given cause.

        Args:
            state (str): The name of the state to lock
            cause (Task): The cause that is locking the state
        """
        # single-task only, so no task should
        # be associated with this state
        if state in self._causes_by_state:
            raise SimulationError(
                f"State '{state}' cannot be used by '{cause}' because it is "
                f"locked by {self._causes_by_state[state]}"
            )
        self._states_by_cause[cause].add(state)
        self._causes_by_state[state] = cause

    def _unlock_state(self, *, state: str, cause: Any) -> None:
        """Unlock one of the actor's states by a given cause.

        If the cause didn't lock the state, an error is raised.

        Args:
            state (str): The name of the state to lock
            cause (Task): The cause that is unlocking the state
        """
        if self._causes_by_state.get(state, None) is not cause:
            raise SimulationError(f"State '{state}' cannot was not used by '{cause}'")
        self._states_by_cause[cause].remove(state)
        del self._causes_by_state[state]

    def activate_state(self, state: str, *, cause: Any, **state_kwargs: Any) -> None:
        """Activate a state.

        Args:
            state (str): The name of the state to activate
            cause (Any): Unique identifier or object for who activated the state.
            state_kwargs (Any): Arguments to pass to the state activation.
        """
        _state = self.__model_fields__[state]
        assert isinstance(_state, _ActiveState)
        self._lock_state(state=state, cause=cause)
        _state.activate(self, **state_kwargs)

    def deactivate_state(self, state: str, *, cause: Any, **kwargs: Any) -> None:
        """Deactivate an already active state.

        Args:
            state (str): Name of the state
            cause (Any): Unique identifier or object for who activated the state.
            kwargs (Any): Arguments expected by the specific state.
        """
        _state = self.__model_fields__[state]
        assert isinstance(_state, _ActiveState)
        self._unlock_state(state=state, cause=cause)
        _state.deactivate(self, **kwargs)

    def deactivate_states(self, states: Iterable[str], *, cause: Any, **kwargs: Any) -> None:
        """Deactivate already active states.

        Args:
            states (Iterable[str]): Names of the states
            cause (Any): Unique identifier or object for who activated the state.
            kwargs (Any): Arguments expected by the specific state.
        """
        for name in states:
            self.deactivate_state(name, cause=cause, **kwargs)

    def deactivate_all_states(self, *, cause: Any, **kwargs: Any) -> None:
        """Deactivate all running states.

        This allows no states to be deactivated if none were activated by the cause.

        Args:
            cause (Any): Unique identifier or object for who activated the state.
            kwargs (Any): Arguments expected by the states to deactivate.
        """
        if cause not in self._states_by_cause:
            return
        state_names = list(self._states_by_cause[cause])
        self.deactivate_states(state_names, cause=cause, **kwargs)

    def activate_linear_state(self, state: str, rate: float, *, cause: Any) -> None:
        """Activate a linear changing state.

        Args:
            state (str): The state name
            rate (float): The rate to change the state
            cause (Any): Unique identifier or object for who is activating the state.
        """
        _state = self.__model_fields__[state]
        assert type(_state) is LinearChangingState
        self.activate_state(state, rate=rate, cause=cause)

    def deactivate_linear_state(self, state: str, *, cause: Any) -> None:
        """Deactivate a linear changing state.

        Exists as a pair to `activate_linear_state`.

        Args:
            state (str): The state name
            cause (Any): Unique identifier or object for who activated the state.
        """
        _state = self.__model_fields__[state]
        assert type(_state) is LinearChangingState
        self.deactivate_state(state, cause=cause)

    def make_event_for_state_goal(self, state: str, goal_value: float) -> float | None:
        """Get the time when a linear changing state will reach a goal value.

        Args:
            state (str): The state name
            goal_value (float): The target value

        Returns:
            float | None: The absolute time when the state will reach the goal value,
                or None if the state is not active or the goal is unreachable.
        """
        _state = self.__model_fields__[state]
        predict_method = getattr(_state, "predict_value_time", None)
        if predict_method is None:
            return None
        try:
            result = predict_method(self, goal_value)
            return result  # type: ignore[no-any-return]
        except Exception:
            return None

    ###########################################################
    ### Cloning ###############################################
    def clone(self) -> Self:
        """Create a deep copy of this actor with current state values.

        The clone:
        - Has all state values deep-copied from the current actor
        - Does not copy any state values that are actors
        - Has no state history
        - Is marked with is_clone=True
        - Is not registered in the entity registry

        Returns:
            Self: A cloned actor with the same state values
        """
        kwargs: dict[str, Any] = {}
        for field_name, field_obj in self.__model_fields__.items():
            current_value = getattr(self, field_name)
            if isinstance(current_value, Actor):
                kwargs[field_name] = current_value
            else:
                kwargs[field_name] = deepcopy(current_value)
        kwargs["name"] = kwargs["name"] + ".clone"
        cloned = type(self)(**kwargs)
        cloned._state_histories = {}
        cloned._is_clone = True

        return cloned

    def _clean(self) -> None:
        """Run to clean all memory from the actor."""
        self._state_histories = {}
        self._log = deque()
        self._state_data = {}
        self._states_by_cause = {}
        self._causes_by_state = {}


class Actor(_BaseActor):
    """The actor."""

    name: str
    debug_logging: bool = True
    knowledge: dict[str, Any]


class ActorHelper:
    """A mixin class for modifying an actor with logging help."""

    def set_actor_knowledge(
        self,
        actor: Actor,
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

    def clear_actor_knowledge(self, actor: Actor, name: str) -> None:
        """Clear knowledge from an actor.

        Convenience method for passing in the name of task for actor logging.

        Args:
            actor (Actor): The actor to clear knowledge from
            name (str): The name of the knowledge
        """
        cname = self.__class__.__qualname__
        actor.clear_knowledge(name, caller=cname)

    @staticmethod
    def get_actor_knowledge(actor: Actor, name: str, must_exist: bool = False) -> Any:
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

    def get_and_clear_actor_knowledge(self, actor: Actor, name: str) -> Any:
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
        self, actor: Actor, know: dict[str, Any], overwrite: bool = False
    ) -> None:
        """Set multiple knowledge entries at once.

        Args:
            actor (Actor): The actor to operate on.
            know (dict[str, Any]): Dictionary of key:value pairs of knowledge.
            overwrite (bool, optional): If overwrite is allowed. Defaults to False.
        """
        for k, v in know.items():
            self.set_actor_knowledge(actor, k, v, overwrite)

    def clear_actor_bulk_knowledge(self, actor: Actor, names: Iterable[str]) -> None:
        """Clear a list of knowledge entries.

        Args:
            actor (Actor): The actor to operate on.
            names (Iterable[str]): Knowledge names.
        """
        for name in names:
            self.clear_actor_knowledge(actor, name)

    def get_actor_bulk_knowledge(
        self, actor: Actor, names: Iterable[str], must_exist: bool = False
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
        self, actor: Actor, names: Iterable[str], caller: str | None = None
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
