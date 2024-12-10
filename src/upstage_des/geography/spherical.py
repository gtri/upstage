# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Geographical math using spherical coordinates for Earth."""

from math import acos, asin, atan, atan2, cos, degrees, radians, sin, sqrt

from upstage_des.math_utils import _vector_dot
from upstage_des.units import unit_convert

from .conversions import SphericalConversions, spherical_radius
from .geo_types import GEO_POINT, LAT_LON, POSITION, POSITIONS, _convert_geo


class Spherical(SphericalConversions):
    """Geographical math using spherical coordinates for Earth."""

    EARTH_RADIUS = spherical_radius  # m

    @staticmethod
    def _bearing(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        ans = degrees(
            atan2(
                sin(lon2 - lon1) * cos(lat2),
                cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2 - lon1),
            )
        )
        ans = ans % 360
        return float(ans)

    @classmethod
    def bearing(
        cls,
        origin: LAT_LON | GEO_POINT,
        destination: LAT_LON | GEO_POINT,
    ) -> float:
        """Calculate the forward bearing from origin to destination.

        Args:
            origin (LAT_LON): Start lat/lon
            destination (LAT_LON): End lat/lon

        Returns:
            float: The forward bearing (0 is north)
        """
        origin = _convert_geo(origin)
        destination = _convert_geo(destination)
        positions = [origin[1], origin[0], destination[1], destination[0]]
        lon1, lat1, lon2, lat2 = map(radians, positions)

        return cls._bearing(lat1, lon1, lat2, lon2)

    @staticmethod
    def _point_along(
        d: float,
        f: float,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> LAT_LON:
        """Get a point a fraction between two points on a great circle.

        Args:
            d (float): Distance between the points (meters)
            f (float): Fraction of the distance for the new point
            lat1 (float): Latitude of the first point (radians)
            lon1 (float): Longitude of the second point (radians)
            lat2 (float): Latitude of the second point (radians)
            lon2 (float): Longitude of the second point (radians)

        Returns:
            LAT_LON: Lat and Lon (degrees)
        """
        a = sin((1 - f) * d) / sin(d)
        b = sin(f * d) / sin(d)
        x = a * cos(lat1) * cos(lon1) + b * cos(lat2) * cos(lon2)
        y = a * cos(lat1) * sin(lon1) + b * cos(lat2) * sin(lon2)
        z = a * sin(lat1) + b * sin(lat2)
        lat = degrees(atan2(z, sqrt(x**2 + y**2)))
        lon = degrees(atan2(y, x))

        return lat, lon

    @classmethod
    def point_along(
        cls,
        origin: LAT_LON | GEO_POINT,
        destination: LAT_LON | GEO_POINT,
        f: float,
    ) -> LAT_LON:
        """Find the location fractionally along a great circle path.

        Args:
            origin (LAT_LON): Lat / Lon (degrees)
            destination (LAT_LON): Lat / Lon (degrees)
            f (float): Fraction along the great circle path to get the point at

        Returns:
            LAT_LON: Point between origin and destination (degrees)
        """
        origin = _convert_geo(origin)
        destination = _convert_geo(destination)
        positions = [origin[1], origin[0], destination[1], destination[0]]
        lon1, lat1, lon2, lat2 = map(radians, positions)
        d = cls.distance(origin, destination, units="m") / spherical_radius
        lat, lon = cls._point_along(d, f, lat1, lon1, lat2, lon2)
        return (lat, lon)

    @classmethod
    def _ll2cart(cls, lat: float, lon: float, radius: float = 1.0) -> POSITION:
        """Latitude and longitude to cartesian on a spherical earth.

        Args:
            lat (float | list[float]): Latitude
            lon (float | list[float]): Longitude
            radius (float, optional): Sphere radius. Defaults to 1.

        Returns:
            POSITION: XYZ coordinates
        """
        theta, lam = radians(lon), radians(lat)
        cl = cos(lam)
        v = (radius * cos(theta) * cl, radius * sin(theta) * cl, radius * sin(lam))
        return v

    @classmethod
    def _cart2lla(cls, cart: POSITION, radius: float = 1.0) -> POSITION:
        """Convert XYZ to lat/lon.

        Args:
            cart (POSITION): Cartesian (XYZ) point.
            radius (float, optional): Radius of the sphere. Defaults to 1.0.

        Returns:
            POSITION: Latitude and longitude (degrees), and altitude (meters)
        """
        a, b, c = cart
        lam = asin(c)
        theta = atan2(b, a)
        alt = sum(x**2 for x in cart) - radius
        return degrees(lam), degrees(theta), alt

    @classmethod
    def geo_linspace(
        cls,
        start: LAT_LON | GEO_POINT,
        end: LAT_LON | GEO_POINT,
        num_segments: int = 10,
    ) -> list[LAT_LON]:
        """Make a discrete great circle path between two points.

        Altitudes are not considered since they do not affect angular coordinates.

        The number of points is the number

        Args:
            start (LAT_LON): Start point
            end (LAT_LON): End point
            num_segments (int, optional): Number of segments on the path. Defaults to 10.

        Returns:
           list[LAT_LON]: Lattiude and Longitude (degrees)
        """
        start = _convert_geo(start)
        end = _convert_geo(end)
        lats, lons, _ = cls.geo_linspace_with_ecef(start, end, num_segments)
        latlon: list[LAT_LON] = [(la, lo) for la, lo in zip(lats, lons)]
        return latlon

    @classmethod
    def geo_linspace_with_ecef(
        cls,
        start: LAT_LON | GEO_POINT,
        end: LAT_LON | GEO_POINT,
        num_segments: int = 10,
    ) -> tuple[list[float], list[float], POSITIONS]:
        """Make a discrete great circle path between two points.

        Altitudes are not considered since they do not affect angular coordinates.

        Latitude and Longitude are all in degrees

        Args:
            start (LAT_LON): Starting lat/lon (degrees)
            end (LAT_LON): Ending lat/lon (degrees)
            num_segments (int, optional): Number of segments to make. Defaults to 10.

        Returns:
            tuple[list[float], list[float], POSITIONS]: Latitude, Longitude, and ECEF points.
        """
        start = _convert_geo(start)
        end = _convert_geo(end)
        if num_segments < 2:
            raise ValueError("Not enough segments for interpolation")
        # We keep the earth radius to be 1 since we're interpolating along radians only
        v1 = cls._ll2cart(start[0], start[1])
        v2 = cls._ll2cart(end[0], end[1])
        # solve for the parameter value that equals the end point
        d = _vector_dot(v1, v2)
        common = sqrt(-1 / ((d - 1) * (d + 1)))
        alpha, beta = -d * common, common
        a, _, _ = v1
        d, _, _ = v2
        lead = a * alpha + beta * d
        sqrt_inner = a**2 * alpha**2 + a**2 + 2 * a * alpha * beta * d + beta**2 * d**2 - d**2
        if sqrt_inner < 0:
            raise ValueError("geo_linspace fails due to negative sqrt")
        t = 2 * atan((lead + sqrt(sqrt_inner)) / (a + d))
        W = tuple([alpha * x + beta * y for x, y in zip(v1, v2)])
        assert len(W) == 3
        W = (W[0], W[1], W[2])
        # test that the t is right
        ct, st = cos(t), sin(t)
        end_pt = tuple([ct * x + st * w for x, w in zip(v1, W)])
        assert len(end_pt) == 3
        end_pt = (end_pt[0], end_pt[1], end_pt[2])
        is_close = all(abs(a - b) <= 1e-8 for a, b in zip(end_pt, v2))
        if not is_close:
            t = 2 * atan((lead - sqrt(sqrt_inner)) / (a + d))

        ts = [(t / num_segments) * i for i in range(0, num_segments + 1)]
        v_cos = [tuple(cos(t) * v for v in v1) for t in ts]
        w_sin = [tuple(sin(t) * w for w in W) for t in ts]
        end_points: list[POSITION] = []
        for v, w in zip(v_cos, w_sin):
            pt = (v[0] + w[0], v[1] + w[1], v[2] + w[2])
            end_points.append(pt)

        lla = cls.ecef2lla(end_points)

        return [lat for lat, *_ in lla], [lon for _, lon, _ in lla], end_points

    @classmethod
    def geo_circle(
        cls,
        center: LAT_LON | GEO_POINT,
        radius: float,
        radius_units: str = "nmi",
        num_points: int = 10,
    ) -> list[LAT_LON]:
        """Make an approximate circle by sweeping bearing from a central location.

        Altitudes are not considered since they do not affect angular coordinates.

        Args:
            center (LAT_LON): Center point (degrees)
            radius (float): Radius of the circle
            radius_units (str, optional): Units of the radius. Defaults to 'nmi'.
            num_points (int, optional): Number of points on the circle. Defaults to 10.

        Returns:
            list[LAT_LON]: Latitude and Longitude (degrees) of the circle
        """
        center = _convert_geo(center)
        lats: list[float] = []
        lons: list[float] = []
        for fraction in range(0, num_points + 1):
            f = fraction / num_points
            bearing = f * 360
            lat, lon = cls.point_from_bearing_dist(
                center,
                bearing,
                radius,
                distance_units=radius_units,
            )
            lats.append(lat)
            lons.append(lon)

        latlon: list[LAT_LON] = [(la, lo) for la, lo in zip(lats, lons)]
        return latlon

    @classmethod
    def distance(
        cls,
        loc1: LAT_LON | GEO_POINT,
        loc2: LAT_LON | GEO_POINT,
        units: str = "nmi",
    ) -> float:
        """Find distance between two points.

        Return the great circle distance from the loc1 to another loc2.

        Args:
            loc1 (LAT_LON): Starting point (degrees)
            loc2 (LAT_LON): Ending point (degrees)
            units (str, optional): Units requested for distance. Defaults to 'nmi'.

        Returns:
            float: Distances in the defined units
        """
        loc1 = _convert_geo(loc1)
        loc2 = _convert_geo(loc2)
        positions = [loc1[1], loc1[0], loc2[1], loc2[0]]
        lon1, lat1, lon2, lat2 = map(radians, positions)
        a = sin(0.5 * (lat2 - lat1)) ** 2 + cos(lat1) * cos(lat2) * sin(0.5 * (lon2 - lon1)) ** 2

        dist_m = spherical_radius * 2 * atan2(sqrt(a), sqrt(1.0 - a))
        return unit_convert(dist_m, "m", units)

    @classmethod
    def distance_and_bearing(
        cls,
        loc1: LAT_LON | GEO_POINT,
        loc2: LAT_LON | GEO_POINT,
        units: str = "nmi",
    ) -> tuple[float, float]:
        """Find great circle distance and forward bearing between two points.

        Args:
            loc1 (LAT_LON): Starting point
            loc2 (LAT_LON): Ending point
            units (str, optional): Distance units requested. Defaults to 'nmi'.

        Returns:
            tuple[float, float]: Distance and Bearing
        """
        dist = cls.distance(loc1, loc2, units=units)
        bearing = cls.bearing(loc1, loc2)
        return dist, bearing

    @classmethod
    def point_from_bearing_dist(
        cls,
        point: LAT_LON | GEO_POINT,
        bearing: float,
        distance: float,
        distance_units: str = "nmi",
    ) -> LAT_LON:
        """Get a Location from a starting point, a bearing, and a distance.

        Args:
            point (LAT_LON): Starting point (degrees)
            bearing (float): Bearing to travel along (degrees)
            distance (float): Distance to travel
            distance_units (str, optional): Units of the distance. Defaults to 'nmi'.

        Returns:
            LAT_LON: The point
        """
        point = _convert_geo(point)
        bearing = radians(bearing)
        dist = unit_convert(distance, distance_units, "m")

        lat, lon = point
        lat1 = radians(lat)
        lon1 = radians(lon)

        lat2 = asin(
            sin(lat1) * cos(dist / spherical_radius)
            + cos(lat1) * sin(dist / spherical_radius) * cos(bearing)
        )

        lon2 = lon1 + atan2(
            sin(bearing) * sin(dist / spherical_radius) * cos(lat1),
            cos(dist / spherical_radius) - sin(lat1) * sin(lat2),
        )

        return degrees(lat2), degrees(lon2)

    @classmethod
    def cross_track_distance(
        cls,
        origin: LAT_LON | GEO_POINT,
        destination: LAT_LON | GEO_POINT,
        point: LAT_LON | GEO_POINT,
        units: str = "nmi",
    ) -> float:
        """Find the minimum distance from a point to a great circle path.

        Args:
            origin (LAT_LON): Great circle start
            destination (LAT_LON): Great circle end
            point (LAT_LON): Point to start distance measurement
            units (str, optional): Units for the distance output. Defaults to 'nmi'.

        Returns:
            float: Distance from point to origin->destination great circle
        """
        origin = _convert_geo(origin)
        destination = _convert_geo(destination)
        point = _convert_geo(point)
        delta_1_3 = cls.distance(origin, point, units="m") / spherical_radius
        theta_1_3 = radians(cls.bearing(origin, point))
        theta_1_2 = radians(cls.bearing(origin, destination))

        dist = asin(sin(delta_1_3) * sin(theta_1_3 - theta_1_2)) * spherical_radius
        return unit_convert(abs(dist), "m", units)

    @classmethod
    def cross_track_point(
        cls,
        origin: LAT_LON | GEO_POINT,
        destination: LAT_LON | GEO_POINT,
        point: LAT_LON | GEO_POINT,
    ) -> LAT_LON:
        """Find the point on a great circle that minimizes the distance to another point.

        Args:
            origin (LAT_LON): Great circle start
            destination (LAT_LON): Great circle end
            point (LAT_LON): Point to start distance measurement

        Returns:
            LAT_LON: Location on great circle closest to a point
        """
        origin = _convert_geo(origin)
        destination = _convert_geo(destination)
        point = _convert_geo(point)
        delta_1_3 = cls.distance(origin, point, units="m") / spherical_radius
        theta_1_3 = radians(cls.bearing(origin, point))
        theta_1_2 = radians(cls.bearing(origin, destination))
        d = asin(sin(delta_1_3) * sin(theta_1_3 - theta_1_2))

        dist_from_origin = acos(cos(delta_1_3) / cos(d)) * spherical_radius
        cross_track_point = cls.point_from_bearing_dist(
            origin,
            degrees(theta_1_2),
            dist_from_origin,
            "m",
        )
        return cross_track_point

    @classmethod
    def ecef_linspace(
        cls,
        start: LAT_LON | GEO_POINT,
        finish: LAT_LON | GEO_POINT,
        start_alt: float,
        finish_alt: float,
        segments: int,
    ) -> POSITIONS:
        """Get an array of spaced points along a greate circle path in ECEF.

        Args:
            start (LAT_LON): Start point (lat/lon degrees)
            finish (LAT_LON): End point (lat/lon degrees)
            start_alt (float): Starting altitude (meters)
            finish_alt (float): Ending altitude (meters)
            segments (int): Number of segments to create

        Returns:
            POSITIONS: ECEF coordinates
        """
        start = _convert_geo(start)
        finish = _convert_geo(finish)
        lats, lons = cls.geo_linspace(start, finish, num_segments=segments)
        delta_alt = finish_alt - start_alt
        alts = [start_alt + delta_alt * i / segments for i in range(segments + 1)]
        lla = [(lat, lon, alt) for lat, lon, alt in zip(lats, lons, alts)]
        return cls.lla2ecef(lla)

    @classmethod
    def ecef_and_geo_linspace(
        cls,
        start: LAT_LON | GEO_POINT,
        finish: LAT_LON | GEO_POINT,
        start_alt: float,
        finish_alt: float,
        segments: int,
    ) -> tuple[POSITIONS, POSITIONS]:
        """Get an array of spaced points along a greate circle path in ECEF and LLA.

        Args:
            start (LAT_LON): Start point (lat/lon degrees)
            finish (LAT_LON): End point (lat/lon degrees)
            start_alt (float): Starting altitude (meters)
            finish_alt (float): Ending altitude (meters)
            segments (int): Number of segments to create

        Returns:
            POSITIONS: ECEF coordinates
            POSITIONS: Lat/Lon/Alt (degrees)
        """
        start = _convert_geo(start)
        finish = _convert_geo(finish)
        lats, lons, _ = cls.geo_linspace_with_ecef(start, finish, num_segments=segments)
        delta_alt = finish_alt - start_alt
        alts = [start_alt + delta_alt * i / segments for i in range(segments + 1)]
        lla = [(lat, lon, alt) for lat, lon, alt in zip(lats, lons, alts)]
        return cls.lla2ecef(lla), lla
