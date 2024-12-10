# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""WGS84 Earth model."""

from math import atan, atan2, cos, degrees, radians, sin, sqrt, tan

from upstage_des.units import unit_convert

from .conversions import WGS84_A, WGS84_B, WGS84_F, WGS84Conversions
from .geo_types import GEO_POINT, LAT_LON, POSITIONS, _convert_geo


class WGS84(WGS84Conversions):
    """Geographical math using elliptical coordinates for Earth.

    Based on Vincenty's methods and WGS84 parameters.
    """

    @classmethod
    def distance(
        cls,
        loc1: LAT_LON | GEO_POINT,
        loc2: LAT_LON | GEO_POINT,
        units: str = "nmi",
        tol: float = 1e-12,
        max_iter: int = 200,
    ) -> float:
        """Find distance between two points.

        Return the great circle distance from the loc1 to another loc2.

        Args:
            loc1 (LAT_LON): Starting point (degrees)
            loc2 (LAT_LON): Ending point (degrees)
            units (str, optional): Units requested for distance. Defaults to 'nmi'.
            tol (float, optional): Calculation convergence tolerance. Defaults to 1e-12
            max_iter (int, optional): Max iterations. Defaults to 200

        Returns:
            float: Distances in the defined units
        """
        dist, _ = cls.distance_and_bearing(loc1, loc2, units, tol, max_iter)
        return dist

    @classmethod
    def bearing(
        cls,
        loc1: LAT_LON | GEO_POINT,
        loc2: LAT_LON | GEO_POINT,
        tol: float = 1e-12,
        max_iter: int = 200,
    ) -> float:
        """Calculate the forward bearing (in degrees) from loc1 to loc2.

        Args:
            loc1 (LAT_LON): Starting point (degrees)
            loc2 (LAT_LON): Ending point (degrees)
            units (str, optional): Units requested for distance. Defaults to 'nmi'.
            tol (float, optional): Calculation convergence tolerance. Defaults to 1e-12
            max_iter (int, optional): Max iterations. Defaults to 200

        Returns:
            float: Bearing
        """
        _, angle = cls.distance_and_bearing(loc1, loc2, tol=tol, max_iter=max_iter)
        return angle

    @classmethod
    def distance_and_bearing(
        cls,
        loc1: LAT_LON | GEO_POINT,
        loc2: LAT_LON | GEO_POINT,
        units: str = "nmi",
        tol: float = 1e-12,
        max_iter: int = 200,
    ) -> tuple[float, float]:
        """Find great circle distance and forward bearing between two points.

        Args:
            loc1 (LAT_LON): Starting point
            loc2 (LAT_LON): Ending point
            units (str, optional): Distance units requested. Defaults to 'nmi'.
            tol (float, optional): Calculation convergence tolerance. Defaults to 1e-12
            max_iter (int, optional): Max iterations. Defaults to 200

        Returns:
            tuple[float, float]: Distance and Bearing
        """
        loc1 = _convert_geo(loc1)
        loc2 = _convert_geo(loc2)
        if loc1[0] == loc2[0] and loc1[1] == loc2[1]:
            return 0.0, 0.0
        # reduced latitudes
        u1 = atan((1 - WGS84_F) * tan(radians(loc1[0])))
        u2 = atan((1 - WGS84_F) * tan(radians(loc2[0])))
        delta_lon = radians(loc2[1] - loc1[1])
        lambda_lon = delta_lon

        sin_u1 = sin(u1)
        cos_u1 = cos(u1)
        sin_u2 = sin(u2)
        cos_u2 = cos(u2)

        for _ in range(max_iter):
            sin_lambda = sin(lambda_lon)
            cos_lambda = cos(lambda_lon)
            sin_sigma = sqrt(
                (cos_u2 * sin_lambda) ** 2 + (cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lambda) ** 2
            )

            cos_sigma = sin_u1 * sin_u2 + cos_u1 * cos_u2 * cos_lambda
            sigma = atan2(sin_sigma, cos_sigma)
            sin_alpha = cos_u1 * cos_u2 * sin_lambda / sin_sigma
            cos_sq_alpha = 1 - sin_alpha**2
            try:
                cos2_sigma_m = cos_sigma - 2 * sin_u1 * sin_u2 / cos_sq_alpha
            except ZeroDivisionError:
                cos2_sigma_m = 0
            c = WGS84_F / 16 * cos_sq_alpha * (4 + WGS84_F * (4 - 3 * cos_sq_alpha))
            _lambda_prev = lambda_lon
            lambda_lon = delta_lon + (1 - c) * WGS84_F * sin_alpha * (
                sigma + c * sin_sigma * (cos2_sigma_m + c * cos_sigma * (-1 + 2 * cos2_sigma_m**2))
            )
            if abs(lambda_lon - _lambda_prev) < tol:
                break  # successful convergence
        else:
            raise ValueError("Could not converge distance/bearing calculation.")

        u_sq = cos_sq_alpha * (WGS84_A**2 - WGS84_B**2) / (WGS84_B**2)
        a = 1 + u_sq / 16384 * (4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq)))
        b = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))
        delta_sigma = (
            b
            * sin_sigma
            * (
                cos2_sigma_m
                + b
                / 4
                * (
                    cos_sigma * (-1 + 2 * cos2_sigma_m**2)
                    - b / 6 * cos2_sigma_m * (-3 + 4 * sin_sigma**2) * (-3 + 4 * cos2_sigma_m**2)
                )
            )
        )

        dist_m = round(WGS84_B * a * (sigma - delta_sigma), 6)

        azimuth = atan2(
            cos_u2 * sin_lambda,
            cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lambda,
        )
        return unit_convert(dist_m, "m", units), degrees(azimuth) % 360

    @classmethod
    def point_from_bearing_dist(
        cls,
        point: LAT_LON | GEO_POINT,
        bearing: float,
        distance: float,
        distance_units: str = "nmi",
        tol: float = 1e-12,
        max_iter: int = 200,
    ) -> LAT_LON:
        """Get a Location from a starting point, a bearing, and a distance.

        Args:
            point (LAT_LON): Starting point (degrees)
            bearing (float): Bearing to travel along (degrees)
            distance (float): Distance to travel
            distance_units (str, optional): Units of the distance. Defaults to 'nmi'.
            tol (float, optional): Calculation convergence tolerance. Defaults to 1e-12
            max_iter (int, optional): Max iterations. Defaults to 200

        Returns:
            LAT_LON: The point in degrees
        """
        point = _convert_geo(point)
        s = unit_convert(distance, distance_units, "km") * 1000
        phi_1 = radians(point[0])
        lambda_1 = radians(point[1])
        a, b, f = WGS84_A, WGS84_B, WGS84_F
        alpha_1 = radians(bearing)

        sin_alpha_1 = sin(alpha_1)
        cos_alpha_1 = cos(alpha_1)

        tan_u1 = (1 - f) * tan(phi_1)
        cos_u1 = 1 / sqrt(1 + tan_u1**2)
        sin_u1 = tan_u1 * cos_u1

        sigma_1 = atan2(tan_u1, cos_alpha_1)
        sin_alpha = cos_u1 * sin_alpha_1
        cos_sq_alpha = 1 - sin_alpha**2
        u_sq = cos_sq_alpha * (a**2 - b**2) / (b**2)
        A = 1 + u_sq / 16384 * (4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq)))
        B = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))

        sigma = s / (b * A)
        for _ in range(max_iter):
            cos2_sigma_m = cos(2 * sigma_1 + sigma)
            sin_sigma = sin(sigma)
            cos_sigma = cos(sigma)
            delta_sigma = (
                B
                * sin_sigma
                * (
                    cos2_sigma_m
                    + B
                    / 4
                    * (
                        cos_sigma * (-1 + 2 * cos2_sigma_m**2)
                        - B
                        / 6
                        * cos2_sigma_m
                        * (-3 + 4 * sin_sigma**2)
                        * (-3 + 4 * cos2_sigma_m**2)
                    )
                )
            )
            sigma_prime = sigma
            sigma = s / (b * A) + delta_sigma
            if abs(sigma_prime - sigma) < tol:
                break
        else:
            raise ValueError("Failed to converge on point from bearing and distance.")

        x = sin_u1 * sin_sigma - cos_u1 * cos_sigma * cos_alpha_1
        phi_2 = atan2(
            sin_u1 * cos_sigma + cos_u1 * sin_sigma * cos_alpha_1,
            (1 - f) * sqrt(sin_alpha**2 + x**2),
        )
        lam = atan2(
            sin_sigma * sin_alpha_1,
            cos_u1 * cos_sigma - sin_u1 * sin_sigma * cos_alpha_1,
        )
        C = f / 16 * cos_sq_alpha * (4 + f * (4 - 3 * cos_sq_alpha))
        L = lam - (1 - C) * f * sin_alpha * (
            sigma + C * sin_alpha * (cos2_sigma_m + C * cos_sigma * (-1 + 2 * cos2_sigma_m**2))
        )
        lambda_2 = lambda_1 + L

        lat, lon = degrees(phi_2), degrees(lambda_2)
        return lat, lon

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
        if num_segments < 2:
            raise ValueError("Not enough points for interpolation")

        # total distance in km
        dist, bearing = cls.distance_and_bearing(start, end, units="km")

        lats = []
        lons = []
        for fraction in range(0, num_segments + 1):
            f = fraction / num_segments
            if fraction == 0:
                loc = start
            elif fraction == num_segments:
                loc = end
            else:
                loc = cls.point_from_bearing_dist(
                    start,
                    bearing,
                    dist * f,
                    distance_units="km",
                )
            lats.append(loc[0])
            lons.append(loc[1])

        return [(la, lo) for la, lo in zip(lats, lons)]

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
        lats = []
        lons = []
        for fraction in range(0, num_points + 1):
            f = fraction / num_points
            bearing = f * 360
            loc = cls.point_from_bearing_dist(
                center,
                bearing,
                radius,
                distance_units=radius_units,
            )
            lats.append(loc[0])
            lons.append(loc[1])

        return [(la, lo) for la, lo in zip(lats, lons)]

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
            list[tuple[float, float, float]]: Lat/Lon/Alt (degrees)
        """
        start = _convert_geo(start)
        finish = _convert_geo(finish)
        latlons = cls.geo_linspace(start, finish, num_segments=segments)
        delta_alt = finish_alt - start_alt
        alts = [start_alt + delta_alt * i / segments for i in range(segments + 1)]
        lla: POSITIONS = [(latlon[0], latlon[1], alt) for latlon, alt in zip(latlons, alts)]
        return cls.lla2ecef(lla), lla
