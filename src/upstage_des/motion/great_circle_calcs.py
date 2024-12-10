# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Great circle calculations.

These equations were largely adapted from https://edwilliams.org/avform147.htm,
although most of them can be verified from a number of open resources around
the web. The overall algorithms have been slightly modified to support UPSTAGE.
"""

from functools import lru_cache
from math import acos, asin, atan2, cos, pi, sin, sqrt
from typing import cast

from upstage_des.data_types import GeodeticLocation


@lru_cache
def get_dist_rad(point1: GeodeticLocation, point2: GeodeticLocation) -> float:
    """Get the distance (in radians) between point1 and point2.

    :param point1: the starting point
    :param point2: the ending point
    """
    point1 = point1.to_radians()
    point2 = point2.to_radians()
    ans = 2.0 * asin(
        sqrt(
            (sin((point1.lat - point2.lat) / 2.0)) ** 2
            + cos(point1.lat) * cos(point2.lat) * (sin((point1.lon - point2.lon) / 2.0)) ** 2
        )
    )
    return cast(float, ans)


@lru_cache
def get_course_rad(point1: GeodeticLocation, point2: GeodeticLocation) -> float:
    """Get the course (in radians) between point1 and point2.

    :param point1: the starting point
    :param point2: the ending point
    """
    point1 = point1.to_radians()
    point2 = point2.to_radians()
    tcl: float

    d = get_dist_rad(point1, point2)

    if sin(point2.lon - point1.lon) < 0:
        tcl = acos((sin(point2.lat) - sin(point1.lat) * cos(d)) / (sin(d) * cos(point1.lat)))
    else:
        tcl = 2.0 * pi - acos(
            (sin(point2.lat) - sin(point1.lat) * cos(d)) / (sin(d) * cos(point1.lat))
        )

    return tcl


@lru_cache
def get_pos_from_points_and_distance(
    point1: GeodeticLocation, point2: GeodeticLocation, dist: float
) -> tuple[float, float]:
    """Get a position (lat, lon) given a starting position, ending position, and distance.

    :param point1: GeodeticLocation of start of great circle
    :param point2: GeodeticLocation of end of great circle
    :param dist: (float) distance along great circle to find third point

    returns [lat, lon]
    """
    point1 = point1.to_radians()
    point2 = point2.to_radians()
    tc = get_course_rad(point1, point2)  # course from point 1 to 2

    lat: float = asin(sin(point1.lat) * cos(dist) + cos(point1.lat) * sin(dist) * cos(tc))

    dlon = atan2(
        sin(tc) * sin(dist) * cos(point1.lat),
        cos(dist) - sin(point1.lat) * sin(lat),
    )

    lon: float = ((point1.lon - dlon + pi) % (2.0 * pi)) - pi

    return (lat, lon)


@lru_cache
def get_great_circle_points(
    point_a: GeodeticLocation,
    point_b: GeodeticLocation,
    point_d: GeodeticLocation,
    dist: float,
) -> tuple[list[tuple[float, float]], list[float]] | None:
    """Let points A and B define a great circle route and D be a third point.

    Find the points on the great circle through A and B that lie a distance d from D, if they exist.

    :param point_a: GeodeticLocation of start of great circle
    :param point_b: GeodeticLocation of end of great circle
    :param point_d: GeodeticLocation, third point of interest (the center of sphere)
    :param dist: (float) distance from third to point to find intersection on great circle (radians)
    """
    point_a = point_a.to_radians()
    point_b = point_b.to_radians()
    point_d = point_d.to_radians()
    course_ad = get_course_rad(point_a, point_d)
    course_ab = get_course_rad(point_a, point_b)

    a = course_ad - course_ab
    b = get_dist_rad(point_a, point_d)

    r = (cos(b) ** 2 + sin(b) ** 2 * cos(a) ** 2) ** (
        1 / 2
    )  # arccos(r) is the cross track distance

    atd = atan2(sin(b) * cos(a), cos(b))  # the along track distance

    dist_ab = get_dist_rad(point_a, point_b)

    if cos(dist) ** 2 > r**2:
        # no points exist
        dp = None
    else:
        # two points exist
        dp = acos(cos(dist) / r)

    if dp:
        d1 = atd - dp
        d2 = atd + dp

        # make sure we can get to first crossing
        # if second cross is negative, both points are outside the D/dist radius
        if dist_ab < d1 or d2 < 0:
            return None

        p1 = get_pos_from_points_and_distance(point_a, point_b, d1)
        p2 = get_pos_from_points_and_distance(point_a, point_b, d2)

    else:
        return None

    return [p1, p2], [d1, d2]
