"""Utilities for gathering all recorded simulation data."""

from dataclasses import asdict, is_dataclass
from typing import Any, cast

from upstage_des.actor import Actor
from upstage_des.base import UpstageBase
from upstage_des.data_types import CartesianLocation, GeodeticLocation
from upstage_des.states import (
    ActiveState,
    ActiveStatus,
    CartesianLocationChangingState,
    GeodeticLocationChangingState,
)

ACTUAL_LOCATION = GeodeticLocation | CartesianLocation
LOCATION_TYPES = ACTUAL_LOCATION | GeodeticLocationChangingState | CartesianLocationChangingState
STATIC_STATE = "Last Seen"

STATE_DATA_ROW = tuple[str, str, str, float, Any, str | None]
LOCATION_DATA_ROW = tuple[str, str, str, float, float, float, float, str | None]
COLUMN_NAMES = ["Entity Name", "Entity Type", "State Name", "Time"]
ACTIVATION_STATUS_COL = "Activation Status"


def _state_history_to_table(
    actor_name: str,
    actor_kind: str,
    state_name: str,
    is_active: bool,
    hist: list[tuple[float, Any]],
) -> list[STATE_DATA_ROW]:
    """Create a state history table from an actor.

    The final entry is a way to flag if a variable is becoming active or not.

    Args:
        actor_name (str): Actor name
        actor_kind (str): Actor kind
        state_name (str): State name
        is_active (bool): If the state is an active type
        hist (list[tuple[float, Any]]): History from _quantities or _state_histories

    Returns:
        list[STATE_DATA_ROW]: A long-form data table of state data.
    """
    data: list[STATE_DATA_ROW] = []
    active_value = "inactive" if is_active else None
    for time, value in hist:
        if isinstance(value, ActiveStatus):
            row = data.pop(-1)
            rows = [tuple(list(row[:-1]) + [value.name])]
            active_value = "active" if value.name == "activating" else "inactive"
        elif is_dataclass(value) and not isinstance(value, type):
            rows = [
                (actor_name, actor_kind, f"{state_name}.{k}", time, v, active_value)
                for k, v in asdict(value).items()
            ]
        elif isinstance(value, dict):
            rows = [
                (actor_name, actor_kind, f"{state_name}.{k}", time, v, active_value)
                for k, v in value.items()
            ]
        else:
            rows = [(actor_name, actor_kind, state_name, time, value, active_value)]
        data.extend(rows)
    return data


def _actor_state_data(
    actor: Actor,
    skip_locations: bool = True,
    save_static: bool = False,
) -> tuple[list[STATE_DATA_ROW], list[Any]]:
    """Gather actor recorded data.

    Args:
        actor (Actor): The actor.
        skip_locations (bool, optional): If location states should be ignored.
            Defaults to True.
        save_static (bool, optional): If non-recording states are saved.
            Defaults to False.

    Returns:
        list[STATE_INFO]: List of state information
        list[Any]: List of monitoring objects to ignore in a global search.
    """
    data: list[STATE_DATA_ROW] = []
    resources: list[Any] = []
    name, kind = actor.name, actor.__class__.__name__

    for state_name, state in actor._state_defs.items():
        if skip_locations and isinstance(state, LOCATION_TYPES):
            continue
        _value = actor.__dict__[state_name]
        is_active = isinstance(state, ActiveState)
        if state_name in actor._state_histories:
            data.extend(
                _state_history_to_table(
                    name, kind, state_name, is_active, actor._state_histories[state_name]
                )
            )
        elif hasattr(_value, "_quantities"):
            resources.append(_value)
            data.extend(_state_history_to_table(name, kind, state_name, False, _value._quantities))
        elif save_static:
            data.append((name, kind, state_name, 0.0, getattr(actor, state_name), STATIC_STATE))

    return data, resources


def _actor_location_data(actor: Actor) -> tuple[list[LOCATION_DATA_ROW], list[str]]:
    """Get actor location data, if it exists.

    The actor needs to have recording Location states:
        * CartesianLocation(ChangingState)
        * GeodeticLocation(ChangingState)

    Args:
        actor (Actor): The actor.

    Returns:
        list[LOCATION_DATA_ROW]: Time and XYZ/LLA data.
        list[str]: name of XYZ/LLA
    """
    data: list[LOCATION_DATA_ROW] = []
    is_xyz = True
    name, kind = actor.name, actor.__class__.__name__
    for state_name, state_data in actor._state_histories.items():
        _state = actor._state_defs[state_name]
        if not isinstance(_state, LOCATION_TYPES):
            continue
        value: ACTUAL_LOCATION | ActiveStatus
        is_active = isinstance(_state, ActiveState)
        active_value = "inactive" if is_active else None
        for time, value in state_data:
            if isinstance(value, ActiveStatus):
                _row = data.pop(-1)
                row = tuple(list(_row[:-1]) + [value.name])
                active_value = "active" if value.name == "activating" else "inactive"
            elif isinstance(value, GeodeticLocation):
                row = (name, kind, state_name, time, value.lat, value.lon, value.alt, active_value)
                is_xyz = False
            elif isinstance(value, CartesianLocation):
                row = (name, kind, state_name, time, value.x, value.y, value.z, active_value)
            data.append(cast(LOCATION_DATA_ROW, row))
    cols = ["X", "Y", "Z"] if is_xyz else ["Lat", "Lon", "Alt"]
    return data, cols


def create_table(
    skip_locations: bool = True, save_static: bool = False
) -> tuple[list[STATE_DATA_ROW], list[str]]:
    """Create a data table of everything UPSTAGE has recorded.

    This uses the current environment context.

    The data columns are:
        Time, Entity Name, Entity Type, State Name, State Value

    For SelfMonitoring<> resources that are not part of an actor, the name
    is pulled from the name entry to the resource. The Entity Type is the
    class name, and the State Name is "Resource State".

    Usage:

    >>> import pandas as pd
    >>> with UP.EnvironmentContext() as env:
    >>>     ...
    >>>     env.run()
    >>>     table, cols = create_table()
    >>>     df = pd.DataFrame(table, cols)

    Args:
        skip_locations (bool, optional): If location states should be ignored.
            Defaults to True.
        save_static (bool, optional): If non-recording states are saved.
            Defaults to False.

    Returns:
        list[STATE_DATA_ROW]: Data table
        list[str]]: Column names.
    """
    _base = UpstageBase()
    data: list[tuple[Any, ...]] = []
    seen_resources: list[Any] = []
    for actor in _base.get_actors():
        name = actor.name
        kind = actor.__class__.__name__
        _data, _resources = _actor_state_data(
            actor, skip_locations=skip_locations, save_static=save_static
        )
        seen_resources.extend(_resources)
        data.extend(_data)

    for monitoring in _base.get_monitored():
        if monitoring in seen_resources:
            continue
        name = f"{monitoring.name}"
        kind = f"{monitoring.__class__.__name__}"
        rows = [(name, kind, "Resource", t, value, None) for t, value in monitoring._quantities]
        data.extend(rows)

    colnames = COLUMN_NAMES + ["Value", ACTIVATION_STATUS_COL]
    return data, colnames


def create_location_table() -> tuple[list[LOCATION_DATA_ROW], list[str]]:
    """Create a data table of every location UPSTAGE has recorded.

    Assumes that all location types are the same.

    This uses the current environment context.

    Usage:

    >>> import pandas as pd
    >>> with UP.EnvironmentContext() as env:
    >>>     ...
    >>>     env.run()
    >>>     table, cols = create_location_table()
    >>>     df = pd.DataFrame(table, cols)

    Returns:
        list[LOCATION_DATA_ROW]: Data table
        list[str]]: Column names.
    """
    _base = UpstageBase()
    data: list[LOCATION_DATA_ROW] = []
    for actor in _base.get_actors():
        _data, cols = _actor_location_data(actor)
        data.extend(_data)
    return data, COLUMN_NAMES + cols + [ACTIVATION_STATUS_COL]
