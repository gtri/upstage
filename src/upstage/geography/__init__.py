# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Geographical methods for intersections, distances, and locations."""

from .intersections import (
    LAT_LON_ALT,
    CrossingCondition,
    get_intersection_locations,
)
from .spherical import Spherical
from .wgs84 import WGS84

__all__ = [
    "Spherical",
    "WGS84",
    "get_intersection_locations",
    "LAT_LON_ALT",
    "CrossingCondition",
]
