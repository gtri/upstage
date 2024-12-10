# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""0A 3-D intersection model for cartesian motion in UPSTAGE along straight-line paths."""

from typing import TypeVar

from upstage_des.base import MotionAndDetectionError
from upstage_des.data_types import CartesianLocation
from upstage_des.math_utils import (
    _col_mat_mul,
    _roots,
    _vector_add,
    _vector_dot,
    _vector_norm,
    _vector_subtract,
)

XY = tuple[float, float]
XYZ = tuple[float, float, float]

L = TypeVar("L", XY, XYZ)


def ray_intersection(
    start: L,
    toward: L,
    center: L,
    radii: float | L,
    speed: float,
) -> tuple[list[L], list[float]]:
    """Ray intersection with ellispoid.

    Args:
        start (XY | XYZ): Start position
        toward (XY | XYZ): Point being looked at
        center (XY | XYZ): Center of the ellipsoid
        radii (float | XY | XYZ): Radii of each dimension of ellipsoid
        speed (float): Speed of the particle moving from start to toward

    Returns:
        tuple[list[XY] | list[XYZ], list[float]]: Intersecting positions and times.
    """
    n_dim = len(start)
    for compare in [toward, center]:
        assert len(compare) == n_dim, "Mismatched dimensions in ray intersection."

    M = [[0.0 for _ in range(n_dim)] for _ in range(n_dim)]
    _radii: tuple[float, ...]
    if isinstance(radii, float | int):
        _radii = tuple([float(radii)] * n_dim)
    elif len(radii) == 1:
        _radii = tuple([radii[0]] * n_dim)
    else:
        _radii = radii
        if len(start) != len(radii):
            raise MotionAndDetectionError(
                "Radius for a sensor must be a single float or the same dimensionality as the "
                "locations."
            )
    for i in range(n_dim):
        M[i][i] = 1 / _radii[i]

    v = _vector_subtract(toward, start)
    v1 = _col_mat_mul(v, M)
    vec1 = _col_mat_mul(start, M)
    vec2 = _col_mat_mul(center, M)
    P1 = _vector_subtract(vec1, vec2)
    c = _vector_norm(P1) ** 2 - 1
    b = 2 * _vector_dot(P1, v1)
    a = _vector_norm(v1) ** 2
    roots = _roots(a, b, c)
    possible = [r for r in roots if r >= 0]

    intersections: list[L] = []
    times: list[float] = []
    for t in sorted(possible):
        loc = _vector_add(start, [t * x for x in v])
        dist = float(_vector_norm(_vector_subtract(loc, start)))
        times.append(dist / speed)
        intersections.append(tuple(loc))  # type: ignore [arg-type]
    return intersections, times


def cartesian_linear_intersection(
    start: CartesianLocation,
    finish: CartesianLocation,
    speed: float,
    sensor_location: CartesianLocation,
    sensor_radius: float,
) -> tuple[list[CartesianLocation], list[float], list[str], float]:
    """Get the intersection of straight line motion and a sphere.

    Args:
        start (CartesianLocation): the start location of the mover
        finish (CartesianLocation): the finish location of the mover
        speed (float): the speed of the mover (in STAGE units)
        sensor_location (CartesianLocation): the location of the sensor
        sensor_radius (float): the radius of the sensor (in STAGE units)

    Returns:
        tuple[list[CartesianLocation], list[float], list[str], float]: _description_
    """
    path_dist = finish - start
    path_time = path_dist / speed
    dist_start = sensor_location - start
    dist_finish = sensor_location - finish
    start_tup = (start.x, start.y, start.z)
    finish_tup = (finish.x, finish.y, finish.z)

    # for start and finish inside, we can skip the intersection math
    start_inside = dist_start <= sensor_radius
    finish_inside = dist_finish <= sensor_radius
    if start_inside and finish_inside:
        inters = [start, finish]
        the_times = [0, path_time]
        return inters, the_times, ["START_INSIDE", "END_INSIDE"], path_time

    sensor_location_tup = (sensor_location.x, sensor_location.y, sensor_location.z)
    intersections, times = ray_intersection(
        start_tup,
        finish_tup,
        sensor_location_tup,
        sensor_radius,
        speed,
    )
    if not intersections or min(times) > path_time:
        return [], [], ["BAD", "BAD"], -1.0

    # filter out intersections beyond the path length
    idxs = sorted(range(len(times)), key=lambda i: times[i])
    inters = [CartesianLocation(*intersections[i]) for i in idxs if times[i] <= path_time]
    times = [times[i] for i in idxs if times[i] <= path_time]
    type_start = "START_INSIDE" if start_inside else "ENTER"
    type_end = "END_INSIDE" if finish_inside else "EXIT"
    if start_inside:
        inters = [start] + inters
        times = [0] + times
    if finish_inside:
        inters = inters + [finish]
        times = times + [path_time]
    if len(inters) != 2:
        raise MotionAndDetectionError(
            f"There should be two intersections, not {len(inters)} ({inters})"
        )
    if len(times) != 2:
        raise MotionAndDetectionError("There should be two time intersections")

    return inters, times, [type_start, type_end], path_time
