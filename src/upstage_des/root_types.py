# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""A place for types that are seen across upstage features.

Helps avoid circularity and if TYPE_CHECKING.
"""

from typing import Any, TypedDict

PLANNING_FACTOR_OBJECT = object()


class StateDataDict(TypedDict):
    """Type hinting for state data storage required on an actor."""

    value: Any
    active_data: Any | None
    is_active: bool | None
    last_update: float | None
