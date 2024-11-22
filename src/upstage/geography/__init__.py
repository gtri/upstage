# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Geographical methods for intersections, distances, and locations."""

from .geo_types import (
    INTERSECTION_LOCATION_CALLABLE,
    LAT_LON,
    LAT_LON_ALT,
    EarthProtocol,
)
from .intersections import (
    CrossingCondition,
    get_intersection_locations,
)
from .spherical import Spherical
from .wgs84 import WGS84

__all__ = [
    "EarthProtocol",
    "Spherical",
    "WGS84",
    "get_intersection_locations",
    "LAT_LON",
    "LAT_LON_ALT",
    "CrossingCondition",
    "INTERSECTION_LOCATION_CALLABLE",
]
