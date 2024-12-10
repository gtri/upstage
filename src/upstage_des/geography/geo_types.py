# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Geographical types and protocols."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

POSITION = tuple[float, float, float]
POSITIONS = list[POSITION]
LAT_LON_ALT = POSITION
LAT_LON = tuple[float, float]


class GEO_POINT(Protocol):
    """Protocol for mimicking geographic data."""

    def latlon(self) -> LAT_LON:
        """Return a tuple of latitude and longitude in degrees."""


def _convert_geo(point: LAT_LON | GEO_POINT) -> LAT_LON:
    """Convert a geo point (or Lat/Lon) to Lat/Lon.

    Args:
        point (LAT_LON | GEO_POINT): The position on a globe

    Returns:
        LAT_LON: Position as correct type.
    """
    if isinstance(point, tuple):
        return point
    return point.latlon()


class EarthProtocol(Protocol):
    """Protocol for defining an earth model interface."""

    def distance(
        self,
        loc1: LAT_LON | GEO_POINT,
        loc2: LAT_LON | GEO_POINT,
        units: str,
    ) -> float:
        """Get the distance between two lat/lon (degrees) points."""

    def bearing(
        self,
        loc1: LAT_LON | GEO_POINT,
        loc2: LAT_LON | GEO_POINT,
    ) -> float:
        """Get the distance between two lat/lon (degrees) points."""

    def distance_and_bearing(
        self,
        loc1: LAT_LON | GEO_POINT,
        loc2: LAT_LON | GEO_POINT,
        units: str,
    ) -> tuple[float, float]:
        """Get the distance between two lat/lon (degrees) points."""

    def point_from_bearing_dist(
        self,
        point: LAT_LON | GEO_POINT,
        bearing: float,
        distance: float,
        distance_units: str = "nmi",
    ) -> tuple[float, float]:
        """Get a lat/lon in degrees from a point, bearing, and distance."""

    def lla2ecef(
        self,
        locs: list[LAT_LON_ALT],
    ) -> list[tuple[float, float, float]]:
        """Get ECEF coordinates from lat lon alt."""

    def ecef2lla(
        self,
        locs: list[LAT_LON_ALT],
    ) -> list[tuple[float, float, float]]:
        """Get ECEF coordinates from lat lon alt."""

    def geo_linspace(
        self,
        start: LAT_LON | GEO_POINT,
        end: LAT_LON | GEO_POINT,
        num_segments: int,
    ) -> list[LAT_LON]:
        """Get evenly spaced coordinates between lat/lon pairs."""

    def geo_circle(
        self,
        center: LAT_LON | GEO_POINT,
        radius: float,
        radius_units: str,
        num_points: int,
    ) -> list[LAT_LON]:
        """Create a circle on a globe."""


@dataclass
class CrossingCondition:
    """Data about an intersection."""

    kind: str
    begin: LAT_LON_ALT
    end: LAT_LON_ALT | None = None


INTERSECTION_LOCATION_CALLABLE = Callable[
    [
        LAT_LON_ALT,
        LAT_LON_ALT,
        LAT_LON_ALT,
        float,
        str,
        EarthProtocol,
        float | None,
        list[int] | None,
    ],
    list[CrossingCondition],
]
