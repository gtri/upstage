# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""This module contains utility functions.

Note:
    Some of the functions included in this module directly support UPSTAGE's
    other modules, and some are there for the user's convenience.

"""

import inspect
from collections.abc import Sequence
from sys import _getframe as get_frame  # pylint: disable=protected-access
from typing import Any, TypeVar

from .data_types import Location

__all__ = (
    "debug_assert",
    "debug_pause",
    "get_caller_info",
)


SKIP: bool = True


def debug_assert(test: bool, msg: str = "") -> None:
    """Coalesces breakpoints for any failing assert to a single line.

    Coalesces all potential lines where the code may fail into one
    single line that can be marked as a breakpoint.

    Args:
        test (bool): The boolean statement to test, i.e., must evaluate to ``true`` or ``false``.
        msg (str): The message to display if the test is false.

    Note:
        This is necessary because ``pdb`` sometimes does not work well when
        running ``simpy`` due to the way that ``simpy`` handles exceptions.

        This is also helpful when debugging complex behaviors that run the same
        code multiple times.  Instead of manually writing a ``try/except``
        statement, you can use ``debug_assert`` to do that for you, and ignore
        all of them from a single control point.


    Example:
        >>> # 1. Add a ``debug_assert`` statement in your code, e.g.:
        >>> from upstage.utils import debug_assert
        >>> ...
        >>> bar, foo = 0, 1  # <<< change foo to be less than bar to raise
        >>> debug_assert(foo > bar, "foo is not greater than bar")
        >>> # 2. Put a break point on the ``raise error`` line to see why the assert failed.

    """
    if SKIP:
        return

    try:
        assert test, msg
    except AssertionError as error:
        raise error  # <<< ADD BREAKPOINT HERE


def debug_pause(test: bool | None = None) -> None:
    """Call function to pause IDE on debug mode with single breakpoint.

    A helper function to pause the execution of the interpreter when running
    the code from an IDE (e.g., PyCharm).

    Args:
        test (bool, optional): A boolean statement to pause on when it evaluates to ``true``.

    Note:
        This is necessary because ``pdb`` sometimes does not work well when
        running ``simpy`` due to the way that ``simpy`` handles exceptions.

    Note:
        Put a break point on the ``pass`` line to pause the IDE.

    """
    if SKIP:
        return

    if test is not None and test:
        pass  # <<< ADD BREAKPOINT HERE


def get_caller_object(caller_level: int = 2) -> Any:
    """Inspect the stack to see who called you.

    Args:
        caller_level (int, optional): Number of hops up in the stack. Defaults to 2.

    Returns:
        Any: The task object
    """
    try:
        task_frame = inspect.stack()[caller_level]
        task_object = task_frame.frame.f_locals["self"]
        return task_object
    except Exception:
        return None


def get_caller_info(caller_level: int = 1) -> str:
    """Get information from the object that called the function.

    Parameters
    ----------
    caller_level : str, optional
        The number of frames to go back in the call stack.

    """
    try:
        frame = get_frame(caller_level + 1)
        if frame.f_code.co_name == "task":
            try:
                caller = frame.f_code.co_qualname
                if caller:
                    return caller
            except (AttributeError, IndexError):
                ...
        return frame.f_code.co_name
    except ValueError as exc:
        if any("call stack is not deep enough" in arg for arg in exc.args):
            return "Unknown caller"
        raise
    except Exception:
        raise


T = TypeVar("T")


def iterable_convert(item: T | list[T] | tuple[T, ...]) -> list[T]:
    """Convert single objects or tuples into a list.

    Args:
        item (T | list[T] | tuple[T,...]): Object, list, or tuple to convert.

    Returns:
        list[T]: The list version of the input.
    """
    if not isinstance(item, list | tuple):
        return [item]
    return list(item)


def waypoint_time_and_dist(
    start: Location,
    waypoints: Sequence[Location],
    speed: float,
) -> tuple[float, float]:
    """Get the time and distance of a series of locations.

    Args:
        start (Location): Starting point
        waypoints (Sequence[Location]): Waypoints after the start
        speed (float): Travel speed

    Returns:
        tuple[float, float]: Time and Distance over the waypoints.
    """
    dist = 0.0
    current = start
    for wypt in waypoints:
        dist += wypt - current
        current = wypt
    time = dist / speed
    return time, dist
