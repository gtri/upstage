# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""A model of the geodetic earth and intersecting paths/spheres."""

from math import sqrt

from upstage_des.data_types import GeodeticLocation
from upstage_des.geography import (
    INTERSECTION_LOCATION_CALLABLE,
    CrossingCondition,
    Spherical,
)
from upstage_des.motion.great_circle_calcs import get_dist_rad, get_great_circle_points
from upstage_des.units import unit_convert


def _to_tuple(loc: GeodeticLocation) -> tuple[float, float, float]:
    """Convert a Geodetic location to a tuple.

    Properly corrects for meters being expected.

    Args:
        loc (GeodeticLocation): Lat/Lon/Alt location

    Returns:
        tuple[float, float, float]: Data as tuple
    """
    _l = loc.to_degrees()
    units: str = loc.stage.altitude_units
    alt = unit_convert(_l.alt, units, "m")
    return (_l.lat, _l.lon, alt)


def subdivide_intersection(
    start: GeodeticLocation,
    finish: GeodeticLocation,
    speed: float,
    sensor_location: GeodeticLocation,
    sensor_radius: float,
) -> tuple[list[GeodeticLocation], list[float], list[str], float]:
    """Numerical intersection calculation.

    Requires:
        UP.add_stage_variable("intersection_model", INTERSECTION_LOCATION_CALLABLE)
        UP.add_stage_variable("distance_units", ...)

    Args:
        start (GeodeticLocation): Path start
        finish (GeodeticLocation): Path end
        speed (float): Speed on path
        sensor_location (GeodeticLocation): Location of a sensor
        sensor_radius (float): Radius of sensor line of sight.

    Returns:
        tuple[list[GeodeticLocation], list[float], list[str], float]: intersections,
        times, types, path_time
    """
    STAGE = start.stage
    alt_units: str = STAGE.altitude_units
    dist_units: str = STAGE.distance_units
    intersection: INTERSECTION_LOCATION_CALLABLE = STAGE.intersection_model
    path_dist = finish - start
    path_time = path_dist / speed
    intersect_locs = intersection(
        _to_tuple(start),
        _to_tuple(finish),
        _to_tuple(sensor_location),
        sensor_radius,
        dist_units,
        STAGE.stage_model,
        9260,
        [10, 20],
    )

    if not intersect_locs:
        return [], [], ["Bad", "Bad"], 0.0

    # convert the data to a more useful format
    intersections: list[GeodeticLocation] = []
    times: list[float] = []
    types: list[str] = []
    condition: CrossingCondition
    for condition in intersect_locs:
        lat, lon, alt = condition.begin
        alt = unit_convert(alt, "m", alt_units)
        the_loc = GeodeticLocation(lat, lon, alt)
        dist_from_start = the_loc - start
        time_from_start = dist_from_start / speed
        intersections.append(the_loc)
        times.append(time_from_start)
        types.append(condition.kind)

    return intersections, times, types, path_time


def analytical_intersection(
    start: GeodeticLocation,
    finish: GeodeticLocation,
    speed: float,
    sensor_location: GeodeticLocation,
    sensor_radius: float,
) -> tuple[list[GeodeticLocation], list[float], list[str], float]:
    """Calculate the intersection of a great circle.

    The circle is defined by start & finish and the sphere defined by
    sensor_location and sensor_radius.

    This function mimics the above `subdivide_intersection`, but uses analytical
    equations that run much faster.

    Requires:
        UP.add_stage_variable("distance_units", ...)
        UP.add_stage_variable("altitude_units", ...)

    Args:
        start (GeodeticLocation): the start location of the mover
        finish (GeodeticLocation): the finish location of the mover
        speed (float): the speed of the mover (in STAGE units)
        sensor_location (GeodeticLocation): the location of the sensor
        sensor_radius (float): the radius of the sensor (in STAGE units)

    Returns:
        tuple[list[GeodeticLocation], list[float], list[str], float]:
        intersections, times, types, path_time
    """
    STAGE = start.stage
    dist_units: str = STAGE.distance_units
    altitude_units: str = STAGE.altitude_units
    # convert some units
    earth_rad = unit_convert(Spherical.EARTH_RADIUS, "m", dist_units)
    start_rad = start.to_radians()
    finish_rad = finish.to_radians()
    sensor_location_rad = sensor_location.to_radians()

    # modify the sensor's radius to account for the altitude of the mover
    average_path_height = (start.alt + finish.alt) / 2.0
    average_path_height_dist_units = unit_convert(average_path_height, altitude_units, dist_units)
    adjusted_sensor_radius = sqrt(sensor_radius**2 - average_path_height_dist_units**2)
    sensor_radius_rad = adjusted_sensor_radius / earth_rad

    # Note: some calcs may be doubled here, further speed up potentially by optimizing this
    point_results = get_great_circle_points(
        start_rad, finish_rad, sensor_location_rad, sensor_radius_rad
    )
    dist_start = get_dist_rad(sensor_location_rad, start_rad)
    dist_finish = get_dist_rad(sensor_location_rad, finish_rad)
    path_dist = get_dist_rad(start_rad, finish_rad)
    path_time = (path_dist * earth_rad) / speed

    # no intersection
    if point_results is None:
        # return matches subdivide_intersection results
        return [], [], ["Bad", "Bad"], -1.0

    points, distances = point_results
    # get points, times, and types
    intersections = []
    times = []
    types = []
    alt_change_per_dist = (finish.alt - start.alt) / path_dist  # altitude change per radian

    # check for start in the sensor range
    if dist_start < sensor_radius_rad:
        types.append("START_INSIDE")
        intersections.append(start)
        times.append(0.0)
    else:
        types.append("ENTER")

        # estimate intersection altitude assuming linear change
        alt_1 = start.alt + (distances[0] / path_dist) * alt_change_per_dist
        # adjust distance to account for average altitude from start to first intersection
        d1_m = distances[0] * (
            earth_rad + unit_convert(0.5 * (start.alt + alt_1), altitude_units, dist_units)
        )

        intersections.append(
            GeodeticLocation(
                *points[0],
                alt=alt_1,
                in_radians=True,
            ).to_degrees()
        )
        times.append(d1_m / speed)

    # check for end in the sensor range
    if dist_finish < sensor_radius_rad:
        types.append("END_INSIDE")
        intersections.append(finish)
        d_end = path_dist * earth_rad
        times.append(d_end / speed)
    else:
        types.append("EXIT")

        # estimate intersection altitude assuming linear change
        alt_2 = start.alt + (distances[1] / path_dist) * alt_change_per_dist
        # adjust distance to account for average altitude from start to first intersection
        d2_m = distances[1] * (
            earth_rad + unit_convert(0.5 * (start.alt + alt_2), altitude_units, dist_units)
        )

        intersections.append(GeodeticLocation(*points[1], alt=alt_2, in_radians=True).to_degrees())
        times.append(d2_m / speed)

    return intersections, times, types, path_time
