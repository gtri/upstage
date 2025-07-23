# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Base classes and exceptions for UPSTAGE."""

from collections import defaultdict
from collections.abc import Generator, Iterable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from functools import wraps
from math import floor
from random import Random
from time import gmtime, strftime
from typing import TYPE_CHECKING, Any, Protocol, Union
from warnings import warn

from simpy import Environment as SimpyEnv
from simpy import Event as SimEvent

from upstage_des.geography import INTERSECTION_LOCATION_CALLABLE, EarthProtocol
from upstage_des.units.convert import STANDARD_TIMES, TIME_ALTERNATES, unit_convert

CONTEXT_ERROR_MSG = "Undefined context variable: use EnvironmentContext"


if TYPE_CHECKING:
    from upstage_des.actor import Actor
    from upstage_des.resources.monitoring import MonitoringMixin


SIMPY_GEN = Generator[SimEvent, Any, Any]


class DotDict(dict):
    """A dictionary that supports dot notation as well as dictionary access notation.

    Usage: d = DotDict({'val1':'first'})
    set attributes: d.val2 = 'second' or d['val2'] = 'second'
    get attributes: d.val2 or d['val2'] would both produce 'second'
    """

    def __getattr__(self, key: str) -> Any:
        """Getattr with error for stage.

        Args:
            key (str): The key

        Returns:
            Any: The value
        """
        if key not in self:
            raise AttributeError(f"No key `{key}` found in stage. Use `UP.add_stage_variable`")
        return self.get(key)

    def __setattr__(self, key: str, value: Any) -> None:
        """Set the attribute.

        Typing is upset at a simple pass-through.

        Args:
            key (str): Key
            value (Any): Value
        """
        if key in self:
            raise AttributeError(f"Key {key} is already set.")
        self.__setitem__(key, value)

    def __delattr__(self, key: str) -> None:
        """Delete an attribute.

        Args:
            key (str): Key
        """
        del self[key]


class StageProtocol(Protocol):
    """Protocol for typing the minimum entries in the Stage."""

    @property
    def altitude_units(self) -> str:
        """Units of altitude."""

    @property
    def distance_units(self) -> str:
        """Units of distance."""

    @property
    def stage_model(self) -> EarthProtocol:
        """Model for geodetics."""

    @property
    def intersection_model(self) -> INTERSECTION_LOCATION_CALLABLE:
        """Callable for geodetic intersections."""

    @property
    def time_unit(self) -> str:
        """Time unit, Treated as 'hr' if not set.

        This value modifies ``pretty_now`` from ``UpstageBase``,
        and can be used to modfy ``Wait`` timeouts.
        """

    @property
    def random(self) -> Random:
        """Random number generator."""

    @property
    def daily_time_count(self) -> float | int:
        """The number of time_units in a "day".

        This value only modifies ``pretty_now`` from ``UpstageBase``.

        This is only used if the time_unit is not
        s, min, or hr. In that case, 24 hour days are
        assumed.
        """

    @property
    def debug_log_time(self) -> bool:
        """Whether or not times are logged as a string in the debug logs.

        Can be modified at the individual actor level with debug_log_time.

        Returns:
            bool: If time is logged.
        """

    if TYPE_CHECKING:

        def __getattr__(self, key: str) -> Any: ...

        def __setattr__(self, key: str, value: Any) -> None: ...

        def __delattr__(self, key: str) -> None: ...


class UpstageError(Exception):
    """Raised when an UPSTAGE error happens or expectation is not met."""


class SimulationError(UpstageError):
    """Raised when a simulation error occurs."""

    def __init__(self, message: str, time: float | None = None):
        """Create an informative simulation error.

        Args:
            message (str): Error message
            time (float | None, optional): Time of the error. Defaults to None.
        """
        msg = "Error in the simulation: "
        if msg in message:
            msg = ""
        msg += f" at time {time}: " if time is not None else ""
        self.message = msg + message
        super().__init__(self.message)


class MotionAndDetectionError(SimulationError):
    """A simulation error raised during motion detection."""


class RulesError(UpstageError):
    """Raised by the user when a simulation rule is violated."""


class MockEnvironment:
    """A fake environment that holds the ``now`` property and all-caps attributes."""

    def __init__(self, now: float):
        """Create the mock environment.

        Args:
            now (float): The time the environment is at.
        """
        self.now = now

    @classmethod
    def mock(cls, env: Union[SimpyEnv, "MockEnvironment"]) -> "MockEnvironment":
        """Create a mock environment from another environment.

        Args:
            env (SimpyEnv | MockedEnvironment): The simpy environments

        Returns:
            MockEnvironment: The mocked environment (time only)
        """
        mock_env = cls(now=env.now)
        # copy over any attributes if they are all-caps
        for k, v in env.__dict__.items():
            if k.upper() == k and not k.startswith("_"):
                setattr(mock_env, k, v)
        return mock_env

    @classmethod
    def run(cls, until: float | int) -> None:
        """Method stub for playing nice with rehearsal.

        Args:
            until (float | int): Placeholder
        """
        raise UpstageError("You tried to use `run` on a mock environment")


@dataclass
class SpecialContexts:
    """Accessible lists of typed objects for contexts."""

    actors: list["Actor"] = field(default_factory=list)
    monitored: list["MonitoringMixin"] = field(default_factory=list)
    data_recorded: list[tuple[float, Any]] = field(default_factory=list)


ENV_CONTEXT_VAR: ContextVar[SimpyEnv] = ContextVar("Environment")
SPECIAL_ENTITY_CONTEXT_VAR: ContextVar[SpecialContexts] = ContextVar("SpecialContexts")
ENTITY_CONTEXT_VAR: ContextVar[dict[str, list["NamedUpstageEntity"]]] = ContextVar("Entities")
STAGE_CONTEXT_VAR: ContextVar[DotDict] = ContextVar("Stage")


SKIP_GROUPS: list[str] = ["Actor", "Task", "Location", "CartesianLocation", "GeodeticLocation"]


class UpstageBase:
    """A base mixin class for everyone.

    Provides access to all context variables created by `EnvironmentContext`.

    >>> with EnvironmentContext(initial_time=0.0) as env:
    >>>     data = UpstageBase()
    >>>     assert data.env is env
    """

    def __init__(self) -> None:
        """Simple init to check if environment should be set."""
        try:
            _ = self.env
        except UpstageError:
            warn(f"Environment not created at instantiation of {self}")

    @property
    def env(self) -> SimpyEnv:
        """Return the environment.

        Returns:
            SimpyEnv: SimPy environment.
        """
        try:
            env: SimpyEnv = ENV_CONTEXT_VAR.get()
        except LookupError:
            raise UpstageError("No environment found or set.")
        return env

    @property
    def stage(self) -> StageProtocol:
        """Return the stage context variable.

        Returns:
            StageProtocol: The stage, as defined in context.
        """
        try:
            stage = STAGE_CONTEXT_VAR.get()
        except LookupError:
            raise UpstageError("No stage found or set.")
        return stage

    def get_actors(self) -> list["Actor"]:
        """Return all actors that the director knows.

        Returns:
            list[NamedUpstageEntity]: List of actors in the simulation.
        """
        ans: list[Actor] = []
        try:
            ans = SPECIAL_ENTITY_CONTEXT_VAR.get().actors
        except LookupError:
            raise UpstageError(CONTEXT_ERROR_MSG)
        return ans

    def get_entity_group(self, group_name: str) -> list["NamedUpstageEntity"]:
        """Get a single entity group by name.

        Args:
            group_name (str): The name of the entity group.

        Returns:
            list[NamedUpstageEntity]: List of entities in the group.
        """
        ans: list[NamedUpstageEntity] = []
        try:
            grps: dict[str, list[NamedUpstageEntity]] = ENTITY_CONTEXT_VAR.get()
            ans = grps.get(group_name, [])
        except LookupError:
            raise UpstageError(CONTEXT_ERROR_MSG)
        return ans

    def get_monitored(self) -> list["MonitoringMixin"]:
        """Return entities that inherit from the MonitoringMixin.

        Returns:
            list[MonitoringMixin]: List of entitites that are monitoring.
        """
        ans: list[MonitoringMixin] = []
        try:
            ans = SPECIAL_ENTITY_CONTEXT_VAR.get().monitored
        except LookupError:
            raise UpstageError(CONTEXT_ERROR_MSG)
        return ans

    def get_recorded(self) -> list[tuple[float, Any]]:
        """Return custom recorded data.

        Returns:
            list[tuple[float, Any]]: Lists of time and data object
        """
        ans: list[tuple[float, Any]] = []
        try:
            ans = SPECIAL_ENTITY_CONTEXT_VAR.get().data_recorded
        except LookupError:
            raise UpstageError(CONTEXT_ERROR_MSG)
        return ans

    def get_all_entity_groups(self) -> dict[str, list["NamedUpstageEntity"]]:
        """Get all entity groups.

        Returns:
            dict[str, list[NamedUpstageEntity]]: Entity group names and associated
                entities.
        """
        grps: dict[str, list[NamedUpstageEntity]] = {}
        try:
            grps = ENTITY_CONTEXT_VAR.get()
        except LookupError:
            raise UpstageError(CONTEXT_ERROR_MSG)
        return grps

    @property
    def pretty_now(self) -> str:
        """A well-formatted string of the sim time.

        Tries to account for generic names for time, such as 'ticks'.

        Returns:
            str: The sim time
        """
        now = self.env.now
        time_unit = self.stage.get("time_unit", None)
        # If it's explicitly set to None, still treat it as hours.
        time_unit = "hr" if time_unit is None else time_unit
        standard = TIME_ALTERNATES.get(time_unit.lower(), time_unit)

        ts: str
        if standard in STANDARD_TIMES:
            now_hrs = unit_convert(now, time_unit, "hr")
            day = floor(now_hrs / 24)
            rem_hours = now_hrs - (day * 24)
            hms = strftime("%H:%M:%S", gmtime(rem_hours * 3600))
            ts = f"[Day {day:4.0f} - {hms:s}]"
        else:
            day_unit_count = self.stage.get("daily_time_count", None)
            if day_unit_count is None:
                ts = f"[{now:.3f} {time_unit}]"
            else:
                days = int(floor(now / day_unit_count))
                rem = now - (days * day_unit_count)
                ts = f"[Day {days:4d} - {rem:.3f} {time_unit}]"

        return ts


class NamedUpstageEntity(UpstageBase):
    """A base class for naming entities, and retrieving them.

    This creates a record of every instance of a subclass of this class.

    Example:
        >>> class RocketCar(NamedUpstageEntity, entity_groups=["car", "fast"])
        >>>     ...
        >>> rc = RocketCar()
        >>> assert rc in rc.get_entity_group("car")
    """

    @classmethod
    def __init_subclass__(
        cls,
        entity_groups: Iterable[str] | str | None = None,
        add_to_entity_groups: bool = True,
        skip_classname: bool = False,
    ) -> None:
        if not add_to_entity_groups:
            return

        entity_groups = [] if entity_groups is None else entity_groups

        if isinstance(entity_groups, str):
            entity_groups = [entity_groups]

        entity_groups = list(entity_groups)

        if cls.__name__ not in entity_groups and not skip_classname:
            entity_groups.append(cls.__name__)

        entity_group = list(set(entity_groups))
        old_init = cls.__init__

        @wraps(old_init)
        def the_actual_init(inst: NamedUpstageEntity, *args: Any, **kwargs: Any) -> None:
            inst._add_entity(entity_group)
            old_init(inst, *args, **kwargs)

        setattr(cls, "__init__", the_actual_init)

    def _add_to_group(self, group_name: str) -> None:
        """Add to a single group.

        Args:
            group_name (str): Group name
        """
        try:
            ans = ENTITY_CONTEXT_VAR.get()
            ans.setdefault(group_name, [])
            if self in ans[group_name]:
                raise UpstageError(f"Entity: {self} already recorded in the environment")
            ans[group_name].append(self)
        except LookupError:
            entity_groups = {group_name: [self]}
            ENTITY_CONTEXT_VAR.set(entity_groups)

    def _add_special_group(self) -> None:
        """Add to a special group.

        Sub-classable for type help.

        Make sure that whatever entity group name this goes to is in SKIP_GROUPS.
        """
        ...

    def _add_entity(self, group_names: list[str]) -> None:
        """Add self to an entity group(s).

        Args:
            group_names (list[str]): Group names to add to
        """
        for group_name in group_names:
            if group_name in SKIP_GROUPS:
                continue
            self._add_to_group(group_name)
        self._add_special_group()


class SettableEnv(UpstageBase):
    """A mixin class for allowing the instance's environment to change."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Passthrough for the mixed classes."""
        self._new_env: MockEnvironment | None = None
        super().__init__(*args, **kwargs)

    @property  # type: ignore [override]
    def env(self) -> SimpyEnv | MockEnvironment:
        """Get the relevant environment.

        Returns:
            SimpyEnv | MockEnvironment: Real or mocked environment.
        """
        if self._new_env is not None:
            return self._new_env
        return super().env

    @env.setter
    def env(self, value: MockEnvironment) -> None:
        if isinstance(value, MockEnvironment):
            self._new_env = value
        else:
            # otherwise set new env back to none
            self._new_env = None


class EnvironmentContext:
    """A context manager to create a safe, globally (in context) referenceable environment and data.

    The environment created is of type simpy.Environment

    This also sets context variables for actors, entities, and the stage.

    Usage:
        >>> with EnvironmentContext(initial_time=0.0) as env:
        >>>    env.run(until=3.0)

    This context manager is meant to be paired with inheritors of `UpstageBase`.

    that provides access to the context variables created in this manager.

    >>> class SimData(UpstageBase):
    >>>     ...
    >>>
    >>> with EnvironmentContext(initial_time=0.0) as env:
    >>>     data = SimData()
    >>>     assert data.env is env

    You may also provide a random seed, and a default Random() will be created with
    that seed.

    >>> with EnvironmentContext(random_seed=1234986) as env:
    >>>    UpstageBase().stage.random.uniform(1, 3)
    ...    2.348057489610457

    Or your own RNG:

    >>> rng = Random(1234986)
    >>> with EnvironmentContext(random_gen=rng) as env:
    >>>    UpstageBase().stage.random.uniform(1, 3)
    ...    2.348057489610457
    """

    def __init__(
        self,
        initial_time: float = 0.0,
        random_seed: int | None = None,
        random_gen: Any | None = None,
    ) -> None:
        """Create an environment context.

        random_seed is ignored if random_gen is given. Otherwise random.Random is
        used.

        Args:
            initial_time (float, optional): Time to start the clock at. Defaults to 0.0.
            random_seed (int | None, optional): Seed for RNG. Defaults to None.
            random_gen (Any | None, optional): RNG object. Defaults to None.
        """
        self.env_ctx = ENV_CONTEXT_VAR
        self.special_ctx = SPECIAL_ENTITY_CONTEXT_VAR
        self.entity_ctx = ENTITY_CONTEXT_VAR
        self.stage_ctx = STAGE_CONTEXT_VAR
        self.env_token: Token[SimpyEnv]
        self.special_token: Token[SpecialContexts]
        self.entity_token: Token[dict[str, list[NamedUpstageEntity]]]
        self.stage_token: Token[DotDict]
        self._env: SimpyEnv | None = None
        self._initial_time: float = initial_time
        self._random_seed: int | None = random_seed
        self._random_gen: Any = random_gen

    def __enter__(self) -> SimpyEnv:
        """Create the environment context.

        Returns:
            SimpyEnv: Simpy Environment
        """
        self._env = SimpyEnv(initial_time=self._initial_time)
        self.env_token = self.env_ctx.set(self._env)
        self.special_token = self.special_ctx.set(SpecialContexts())
        self.entity_token = self.entity_ctx.set(defaultdict(list))
        stage = DotDict()
        self.stage_token = self.stage_ctx.set(stage)
        if self._random_gen is None:
            random = Random(self._random_seed)
            stage.random = random
        else:
            stage.random = self._random_gen
        return self._env

    def __exit__(self, *_: Any) -> None:
        """Leave the context."""
        self.env_ctx.reset(self.env_token)
        self.special_ctx.reset(self.special_token)
        self.entity_ctx.reset(self.entity_token)
        self.stage_ctx.reset(self.stage_token)
        self._env = None


def add_stage_variable(varname: str, value: Any) -> None:
    """Add a variable to the stage.

    Will fail if it already exists.

    Args:
        varname (str): Name of the variable
        value (Any): Value to set it as
    """
    try:
        stage = STAGE_CONTEXT_VAR.get()
    except LookupError:
        raise ValueError("Stage should have been set.")
    if varname in stage:
        raise UpstageError(f"Variable '{varname}' already exists in the stage")
    setattr(stage, varname, value)


def get_stage_variable(varname: str) -> Any:
    """Get a variable from the context's stage.

    Args:
        varname (str): Name of the variable

    Returns:
        Any: The variable's value
    """
    try:
        stage = STAGE_CONTEXT_VAR.get()
    except LookupError:
        raise ValueError("Stage should have been set.")
    if varname not in stage:
        raise UpstageError(f"Variable '{varname}' does not exist in the stage")
    return getattr(stage, varname)


def get_stage() -> StageProtocol:
    """Return the entire stage object.

    Returns:
        StageProtocol: The stage
    """
    try:
        stage = STAGE_CONTEXT_VAR.get()
    except LookupError:
        raise ValueError("Stage should have been set.")
    return stage


def create_top_context(
    initial_time: float = 0.0,
    random_seed: int | None = None,
    random_gen: Any | None = None,
) -> EnvironmentContext:
    """Create a stage at this level of context.

    Makes your current level the same as the context manager.

    Returns:
        EnvironmentContext: The context
    """
    ctx = EnvironmentContext(initial_time, random_seed, random_gen)
    ctx.__enter__()
    return ctx


def clear_top_context(ctx: EnvironmentContext) -> None:
    """Clear the context.

    Args:
        ctx (EnvironmentContext): The object made from create_stage()
    """
    ctx.__exit__()
