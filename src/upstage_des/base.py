# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Base classes and exceptions for upstage_des."""

from collections.abc import Callable, Generator
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from functools import wraps
from random import Random
from typing import Any
from warnings import warn

from simpy import Environment as SimpyEnv
from simpy import Event as SimpyEvent
from simpy import Process

CONTEXT_ERROR_MSG = "Undefined context variable: use EnvironmentContext"


SIMPY_GEN = Generator[SimpyEvent, Any, Any]


class UpstageError(Exception):
    """Raised when an UPSTAGE error happens or expectation is not met."""


class SimulationEnd(Exception):
    """Raised when you want to end the sim, but know it was a safe end."""


@dataclass
class Stage:
    """Simulation stage configuration and shared state.

    The Stage holds global simulation configuration (units, time settings) and shared
    state (RNG, custom data) accessible to all simulation components via context.

    Warnings are raised if you re-set a value.

    Attributes:
        random: Random number generator for simulation stochasticity.
        altitude_units: Units for altitude measurements (e.g., "ft", "m").
        distance_units: Units for distance measurements (e.g., "nmi", "km").
        time_unit: Base time unit for simulation (e.g., "hr", "min", "s").
            Affects `pretty_now` formatting and can be used in `Wait` timeouts.
        daily_time_count: Number of time_units in a "day" for time formatting.
            Only used when time_unit is not "s", "min", or "hr" (which assume 24-hour days).
        debug_log_time: Whether to log times as formatted strings in debug logs.
            Can be overridden at the individual actor level.
        userdata: A blank dictionary for runtime data
    """

    random: Random = field(default_factory=Random)
    altitude_units: str = "ft"
    distance_units: str = "nmi"
    time_unit: str = "hr"
    daily_time_count: float = 24.0
    debug_log_time: bool = False
    userdata: dict = field(default_factory=dict)
    managers: dict = field(default_factory=dict)

    _set: set = field(default_factory=set, init=False, repr=False)

    def __setattr__(self, name: str, value: object) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        if name == "userdata" or name == "managers":
            super().__setattr__(name, value)
            return
        if hasattr(self, "_set") and name in self._set:
            raise UpstageError(f"Stage attribute '{name}' can only be set once")
        super().__setattr__(name, value)
        if hasattr(self, "_set"):
            self._set.add(name)


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


ENV_CONTEXT_VAR: ContextVar[SimpyEnv] = ContextVar("Environment")
STAGE_CONTEXT_VAR: ContextVar[Stage] = ContextVar("Stage")
ENTITY_REGISTRY_CONTEXT_VAR: ContextVar[dict[str, list[Any]]] = ContextVar("EntityRegistry")


class UpstageBase:
    """A base mixin class for everyone.

    Provides access to all context variables created by `EnvironmentContext`.

    >>> with EnvironmentContext(initial_time=0.0) as env:
    >>>     data = UpstageBase()
    >>>     assert data.env is env
    """

    def _register_entity(self) -> None:
        try:
            registry = ENTITY_REGISTRY_CONTEXT_VAR.get()
        except LookupError:
            return

        for cls in type(self).__mro__:
            if cls is object:
                continue
            class_name = cls.__name__
            if class_name not in registry:
                registry[class_name] = []
            if self not in registry[class_name]:
                registry[class_name].append(self)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Simple init to check if environment should be set."""
        try:
            _ = self.env
        except UpstageError:
            warn(f"Environment not created at instantiation of {self}")
        self._register_entity()
        super().__init__()

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
    def stage(self) -> Stage:
        """Return the stage context variable.

        Returns:
            StageProtocol: The stage, as defined in context.

        Raises:
            LookupError: If no stage context is available
        """
        return STAGE_CONTEXT_VAR.get()

    @property
    def entity_registry(self) -> dict[str, list[Any]]:
        """Return the entity registry.

        Returns:
            dict[str, list[Any]]: Dictionary mapping class names to lists of instances
        """
        try:
            registry = ENTITY_REGISTRY_CONTEXT_VAR.get()
        except LookupError:
            raise UpstageError("No entity registry found or set.")
        return registry


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
        stage: Stage | None = None,
    ) -> None:
        """Create an environment context.

        random_seed is ignored if random_gen is given. Otherwise random.Random is
        used. If stage is provided, it will be used instead of creating a new Stage.

        Args:
            initial_time (float, optional): Time to start the clock at. Defaults to 0.0.
            random_seed (int | None, optional): Seed for RNG. Defaults to None.
            random_gen (Any | None, optional): RNG object. Defaults to None.
            stage (Stage | None, optional): Stage instance to use. Defaults to None.
        """
        self.env_ctx = ENV_CONTEXT_VAR
        self.stage_ctx = STAGE_CONTEXT_VAR
        self.entity_registry_ctx = ENTITY_REGISTRY_CONTEXT_VAR
        self.env_token: Token[SimpyEnv]
        self.stage_token: Token[Stage]
        self.entity_registry_token: Token[dict[str, list[Any]]]
        self.rehearsal_token: Token[bool]
        self._env: SimpyEnv | None = None
        self._initial_time: float = initial_time
        self._random_seed: int | None = random_seed
        self._random_gen: Any = random_gen
        self._stage: Stage | None = stage

    def __enter__(self) -> SimpyEnv:
        """Create the environment context.

        Returns:
            SimpyEnv: Simpy Environment
        """
        self._env = SimpyEnv(initial_time=self._initial_time)
        self.env_token = self.env_ctx.set(self._env)

        if self._stage is not None:
            stage = self._stage
            if stage.random is not None:
                if self._random_seed is not None:
                    stage.random.seed(self._random_seed)
                elif self._random_gen is not None:
                    stage.random = self._random_gen
        else:
            if self._random_gen is None:
                random_gen = Random(self._random_seed)
            else:
                random_gen = self._random_gen

            stage = Stage(random=random_gen)

        self.stage_token = self.stage_ctx.set(stage)

        entity_registry: dict[str, list[Any]] = {}
        self.entity_registry_token = self.entity_registry_ctx.set(entity_registry)

        return self._env

    def __exit__(self, *_: Any) -> None:
        """Leave the context."""
        self.env_ctx.reset(self.env_token)
        self.stage_ctx.reset(self.stage_token)
        self.entity_registry_ctx.reset(self.entity_registry_token)
        self._env = None


def add_stage_variable(varname: str, value: Any) -> None:
    """Add a variable to the stage.

    Uses `userdata` if the variable doesn't exist.

    Args:
        varname (str): Name of the variable
        value (Any): Value to set it as
    """
    try:
        stage = STAGE_CONTEXT_VAR.get()
    except LookupError:
        raise ValueError("Stage should have been set.")
    if varname in stage.__dataclass_fields__:
        raise UpstageError(f"Variable '{varname}' already exists in the stage")
    # otherwise go to userdata
    if varname in stage.userdata:
        raise UpstageError(f"Variable '{varname}' already exists in the stage userdata")
    stage.userdata[varname] = value


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
    if varname not in stage.__dataclass_fields__:
        if varname in stage.userdata:
            return stage.userdata[varname]
        raise UpstageError(f"Variable '{varname}' does not exist in the stage or userdata")
    return getattr(stage, varname)


def get_stage() -> Stage:
    """Return the entire stage object.

    Returns:
        StageProtocol: The stage

    Raises:
        LookupError: If no stage context is available
    """
    return STAGE_CONTEXT_VAR.get()


def create_top_context(
    initial_time: float = 0.0,
    random_seed: int | None = None,
    random_gen: Any | None = None,
    stage: Stage | None = None,
) -> EnvironmentContext:
    """Create a stage at this level of context.

    Makes your current level the same as the context manager.

    Args:
        initial_time (float, optional): Time to start the clock at. Defaults to 0.0.
        random_seed (int | None, optional): Seed for RNG. Defaults to None.
        random_gen (Any | None, optional): RNG object. Defaults to None.
        stage (Stage | None, optional): Stage instance to use. Defaults to None.

    Returns:
        EnvironmentContext: The context
    """
    ctx = EnvironmentContext(initial_time, random_seed, random_gen, stage)
    ctx.__enter__()
    return ctx


def clear_top_context(ctx: EnvironmentContext) -> None:
    """Clear the context.

    Args:
        ctx (EnvironmentContext): The object made from create_stage()
    """
    ctx.__exit__()


def get_entity_registry() -> dict[str, list[Any]]:
    """Return the entity registry.

    Returns:
        dict[str, list[Any]]: Dictionary mapping class names to lists of instances
    """
    try:
        registry = ENTITY_REGISTRY_CONTEXT_VAR.get()
    except LookupError:
        raise ValueError("Entity registry should have been set.")
    return registry


def get_entities_by_class(class_name: str) -> list[Any]:
    """Get all entities of a specific class name.

    Args:
        class_name (str): The name of the class

    Returns:
        list[Any]: List of entity instances
    """
    registry = get_entity_registry()
    return registry.get(class_name, [])


PROC = Generator[SimpyEvent, Any, None]


def process(
    func: Callable[..., PROC],
) -> Callable[..., Process]:
    """Decorate a ``simpy`` process to schedule it as a callable.

    Allows users to decorate a generator, and when they want to schedule them
    as a ``simpy`` process, they can simply call it, e.g., instead of calling:

    Usage:

    >>> from upstage_des.api import process, Wait
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
        f = func(*args, **kwargs)
        return environment.process(f)

    return wrapped_generator
