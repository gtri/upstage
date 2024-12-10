# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Functions for finding intersections in geodetics."""

from upstage_des.math_utils import _vector_norm, _vector_subtract
from upstage_des.units import unit_convert

from .geo_types import LAT_LON_ALT, POSITION, POSITIONS, CrossingCondition
from .spherical import Spherical
from .wgs84 import WGS84


class IntersectionError(Exception):
    """An exception when intersection code fails."""

    ...


def _preprocess(
    start_lla: LAT_LON_ALT,
    finish_lla: LAT_LON_ALT,
    point_lla: LAT_LON_ALT,
    earth: Spherical | WGS84,
    dist_between: float,
) -> tuple[POSITIONS, POSITIONS, POSITION]:
    """Preprocess points for intersection calculations.

    Args:
        start_lla (LAT_LON_ALT): Starting point (degrees/meters)
        finish_lla (LAT_LON_ALT): Ending point (degrees/meters)
        point_lla (LAT_LON_ALT): Point to convert to ecef (degrees/meters)
        earth (Spherical | WGS84): Earth model
        dist_between (float): Distance to use for segment length (m)

    Returns:
        tuple[POSITIONS, POSITIONS, POSITION]: Preprocessed locations
    """
    start_alt = start_lla[2]
    finish_alt = finish_lla[2]
    dist = earth.distance(start_lla[:2], finish_lla[:2], units="m")
    points = int(dist / dist_between) + 1
    while points <= 2:
        dist_between = dist_between / 2.0
        if dist_between < 100:
            raise IntersectionError(
                f"Intersetion Segment {start_lla} -> {finish_lla} is too small!"
            )
        points = int(dist / dist_between) + 1
    ecef_point = earth.lla2ecef([point_lla])[0]
    assert len(ecef_point) == 3
    ecef_test, geo_test = earth.ecef_and_geo_linspace(
        start_lla[:2],
        finish_lla[:2],
        start_alt,
        finish_alt,
        points,
    )
    return ecef_test, geo_test, ecef_point


def find_crossing_points(
    start_lla: LAT_LON_ALT,
    finish_lla: LAT_LON_ALT,
    point_lla: LAT_LON_ALT,
    earth: Spherical | WGS84,
    radius: float,
    dist_between: float = 9260.0,
) -> list[CrossingCondition]:
    """Finds the points along a great circle path and a sphere.

    The output data provides booleans to state If the start or end are within
    range/visibility.

    Args:
        start_lla (LAT_LON_ALT): Starting point (degrees/meters)
        finish_lla (LAT_LON_ALT): Ending point (degrees/meters)
        point_lla (LAT_LON_ALT): Point of sensing (degrees/meters)
        earth (Spherical | WGS84): Earth model
        radius (float): Radius that the sensor can see (meters)
        dist_between (float, optional): Distance to use for segment length (meters).
            Defaults to 5 nmi (or 9260 meters).

    Returns:
        list[CrossingCondition]:
            A list of data describing the crossover points on the great circle path.
            It will start with: ["START_INSIDE" or "START_OUT", start LLA].
            Then there will be one or two: ["ENTER" or "EXIT", LLA, LLA] where the
            two LLA values are the OUT and IN points as described.
            It will end with: ["END_INSIDE" or "END_OUT", end LLA].
    """
    ecef_test, lla_test, ecef_point = _preprocess(
        start_lla,
        finish_lla,
        point_lla,
        earth,
        dist_between=dist_between,
    )

    last_out: int | None = None
    last_in: int | None = None
    cross_points: list[CrossingCondition] = []

    for i, test_loc in enumerate(ecef_test):
        diff = _vector_subtract(test_loc, ecef_point)
        dist = _vector_norm(diff)
        is_in = dist <= radius

        if i == 0:
            use = "START_INSIDE" if is_in else "START_OUT"
            cond = CrossingCondition(kind=use, begin=lla_test[i])
            cross_points.append(cond)
        elif is_in and last_in != i - 1:
            assert last_out is not None
            cond = CrossingCondition(
                kind="ENTER",
                begin=lla_test[last_out],
                end=lla_test[i],
            )
            cross_points.append(cond)
            assert last_out == i - 1
        elif not is_in and last_out != i - 1:
            assert last_in is not None
            cond = CrossingCondition(
                kind="EXIT",
                begin=lla_test[last_in],
                end=lla_test[i],
            )
            cross_points.append(cond)
            assert last_in == i - 1

        if is_in:
            last_in = i
        else:
            last_out = i

    use = "END_INSIDE" if is_in else "END_OUT"
    cond = CrossingCondition(kind=use, begin=lla_test[-1])
    cross_points.append(cond)

    return cross_points


def _split_down(
    begin: LAT_LON_ALT,
    end: LAT_LON_ALT,
    sphere_center: LAT_LON_ALT,
    radius: float,
    earth: Spherical | WGS84,
    distance_between: float,
    subdivide_levels: list[int] | None = None,
) -> CrossingCondition:
    """Find an intersection point from a sphere to a great circle.

    Default subdivision is [10, 20]

    We assume this is being called only on one clear crossing point, because it
    expects to find START_(IN|OUT) -> (IN_OUT | OUT_IN)  -> (END_(OUT|IN)) from the
    calls to find_crossing_points

    Args:
        begin (LAT_LON_ALT): Starting point (degrees/meters)
        end (LAT_LON_ALT): Ending point (degrees/meters)
        sphere_center (LAT_LON_ALT): Center of the sensing sphere (not earth, degrees/meters)
        radius (float): Sensor radius (meters)
        earth (Spherical | WGS84): Geodetic description
        distance_between (float): Splitting distance for search
        subdivide_levels (list[int], optional): Levels for searching smaller sections.
            Defaults to None.

    Returns:
        tuple[str, LAT_LON_ALT]: The intersection type, if any (degrees/meters)
    """
    subdivide_levels = [10, 20] if subdivide_levels is None else subdivide_levels

    for divide in subdivide_levels:
        distance_between = distance_between / divide
        split_data = find_crossing_points(
            begin,
            end,
            sphere_center,
            earth,
            radius,
            distance_between,
        )
        if len(split_data) != 3:
            raise IntersectionError(
                "A subdivide split shouldn't have 2 crossovers in intersections with a sphere"
            )
        if split_data[1].kind not in ["EXIT", "ENTER"]:
            raise IntersectionError("Subdividing an intersection check gave an invalid Direction")
        assert split_data[1].end is not None
        begin, end = split_data[1].begin, split_data[1].end

    cond = CrossingCondition(
        split_data[1].kind,
        begin=split_data[1].begin,
        end=split_data[1].end,
    )
    return cond


def get_intersection_locations(
    start: LAT_LON_ALT,
    finish: LAT_LON_ALT,
    sphere_center: LAT_LON_ALT,
    radius: float,
    radius_units: str,
    earth: WGS84 | Spherical,
    dist_between: float | None = None,
    subdivide_levels: list[int] | None = None,
) -> list[CrossingCondition]:
    """Get the locations and kinds of intersections of a path to a sphere.

    Args:
        start (LAT_LON_ALT): Starting point (degrees)
        finish (LAT_LON_ALT): Ending point (degrees)
        sphere_center (LAT_LON_ALT): Center of the sensing sphere (not earth, degrees/meters)
        radius (float): Sensor radius
        radius_units (str): Units of the sensor radius
        earth (Spherical | WGS84): Geodetic description
        dist_between (float, optional): Splitting distance for search.
            Defaults to 9260.0 meters (5 nmi)
        subdivide_levels (list[int], optional): Levels for searching smaller sections.
            Defaults to None.

    Returns:
        list[CrossingCondition]: The intersection type, if any
            It will start with:
                ["START_INSIDE" or "START_OUT"]
            Then there will be one or two:
                ["ENTER" or "EXIT"]
                where the two LLA values are the OUT and IN points as described
            It will end with:
                ["END_INSIDE" or "END_OUT"]
    """
    dist_between = 9260.0 if dist_between is None else dist_between
    radius = unit_convert(radius, radius_units, "m")
    subdivide_levels = [10, 20] if subdivide_levels is None else subdivide_levels
    rough_split_data = find_crossing_points(
        start,
        finish,
        sphere_center,
        earth,
        radius,
        dist_between,
    )

    # subdivide the splits for precision
    intersections: list[CrossingCondition] = []
    for condition in rough_split_data[1:-1]:
        assert condition.end is not None
        new_condition = _split_down(
            condition.begin,
            condition.end,
            sphere_center,
            radius,
            earth,
            dist_between,
            subdivide_levels=subdivide_levels,
        )
        if new_condition.kind != condition.kind:
            raise IntersectionError("Subdividing the intersection switched directions")
        use_lla = new_condition.begin if condition.kind == "EXIT" else new_condition.end
        assert use_lla is not None
        intersections.append(CrossingCondition(kind=condition.kind, begin=use_lla))

    # for START_IN and END_IN, append that data, too
    if rough_split_data[0].kind == "START_INSIDE":
        intersections = [rough_split_data[0]] + intersections
    if rough_split_data[-1].kind == "END_INSIDE":
        intersections = intersections + [rough_split_data[-1]]
    return intersections
