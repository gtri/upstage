# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Geodetic frame conversions."""

from math import atan2, cos, degrees, radians, sin, sqrt

from .geo_types import POSITION, POSITIONS

# Constants for the earth
spherical_radius: float = 6378137.0
WGS84_A: float = 6378137.0  # meters - semimajor axis
WGS84_F: float = 1 / 298.257223563  # flattening factor
WGS84_B: float = WGS84_A * (1 - WGS84_F)  # meters - semiminor axis

# build the constant values
sR_e = spherical_radius
sR_p = spherical_radius
se_2 = (sR_e**2 - sR_p**2) / sR_e**2
sep_2 = (sR_e**2 - sR_p**2) / sR_p**2
se = sqrt(se_2)
sep = sqrt(se)

wR_e = WGS84_A
wR_p = WGS84_B
# first eccentricity squared
we_2 = WGS84_F * (2 - WGS84_F)
# second eccentricity squared
wep_2 = we_2 / (1 - WGS84_F) ** 2
we = sqrt(we_2)
wep = sqrt(we)
wF = WGS84_F


class BaseConversions:
    """Base class for converting in geodetic frames."""

    radius_e = 0.0
    radius_p = 0.0
    e_2 = 0.0
    ep_2 = 0.0
    e = 0.0
    ep = 0.0
    f = 0.0

    @classmethod
    def _lla2ecef(cls, lla: POSITION, input_in_radians: bool = False) -> POSITION:
        """Convert Lat-Lon-Altitude into ECEF.

        Args:
            lla (POSITION): lat/lon/alt data in 3 columns and 1 row.
            input_in_radians (bool, optional): If the lat/lon are in radians. Defaults to False.

        Returns:
            POSITION: XYZ ECEF value for the position.
        """
        rad_lat, rad_lon, ht = lla
        if not input_in_radians:
            rad_lat = radians(rad_lat)  # sometimes denoted as lambda
            rad_lon = radians(rad_lon)  # sometimes denoted as phi

        N = cls.radius_e / sqrt(1 - (cls.e_2 * sin(rad_lat) ** 2))
        temp1 = (N + ht) * cos(rad_lat)
        temp2 = N * (1 - cls.f) ** 2 + ht
        x = temp1 * cos(rad_lon)
        y = temp1 * sin(rad_lon)
        z = temp2 * sin(rad_lat)
        return (x, y, z)

    @classmethod
    def lla2ecef(cls, lla: POSITIONS, input_in_radians: bool = False) -> POSITIONS:
        """Convert Lat-Lon-Altitude into ECEF.

        Args:
            lla (POSITIONS): lat/lon/alt data in 3 columns and N rows.
            input_in_radians (bool, optional): If the lat/lon are in radians. Defaults to False.

        Returns:
            POSITIONS: Array of XYZ ECEF values.
        """
        return [cls._lla2ecef(row, input_in_radians) for row in lla]

    @classmethod
    def _ecef2lla(cls, ecef: POSITION, radians_out: bool = False) -> POSITION:
        """Convert ECEF to Lat/Lon/Altitude.

        Args:
            ecef (POSITION): ECEF point
            radians_out (bool, optional): If lat/lon out should be in radians. Defaults to False.

        Returns:
            POSITION: Lat/Lon/Altitude
        """
        X, Y, Z = ecef
        # Longitude (rad; 1xN)
        lon = atan2(Y, X)

        # Calculations
        e2 = cls.e_2
        r2 = X**2 + Y**2
        r = sqrt(r2)
        a = cls.radius_e
        b = cls.radius_p
        a2 = a**2
        b2 = b**2
        E2 = a2 - b2
        Z2 = Z**2
        F = 54 * b2 * Z2
        G = r2 + (1 - e2) * Z2 - e2 * E2
        c = (e2 * e2 * F * r2) / (G * G * G)

        s = (1 + c + sqrt(c * c + 2 * c)) ** (1 / 3)
        P = F / (3 * (s + 1 / s + 1) ** 2 * G * G)
        Q = sqrt(1 + 2 * e2 * e2 * P)
        ro = -(e2 * P * r) / (1 + Q) + sqrt(
            (a * a / 2) * (1 + 1 / Q) - ((1 - e2) * P * Z2) / (Q * (1 + Q)) - P * r2 / 2
        )
        tmp = (r - e2 * ro) ** 2
        U = sqrt(tmp + Z2)
        V = sqrt(tmp + (1 - e2) * Z2)
        zo = (b2 * Z) / (a * V)

        h = U * (1 - b2 / (a * V))
        lat = atan2((Z + cls.ep_2 * zo), r)

        if not radians_out:
            lon = degrees(lon)
            lat = degrees(lat)

        lla = (lat, lon, h)
        return lla

    @classmethod
    def ecef2lla(cls, ecef: POSITIONS, radians_out: bool = False) -> POSITIONS:
        """Convert ECEF to Lat/Lon/Altitude.

        Args:
            ecef (POSITIONS): ECEF points
            radians_out (bool, optional): If lat/lon out should be in radians. Defaults to False.

        Returns:
            POSITIONS: Lat/Lon/Altitude
        """
        return [cls._ecef2lla(row, radians_out) for row in ecef]


class SphericalConversions(BaseConversions):
    """Conversions on a spherical globe."""

    radius_e = sR_e
    radius_p = sR_p
    e_2 = se_2
    ep_2 = sep_2
    e = se
    ep = sep

    @classmethod
    def _lla2ecef(cls, lla: POSITION, input_in_radians: bool = False) -> POSITION:
        """Lat-Lon-Alt to ECEF.

        Args:
            lla (POSITION): Lat-Lon-Altitude points
            input_in_radians (bool, optional): If lat/lon are in radians. Defaults to False.

        Returns:
            POSITION: ECEF
        """
        rad_lat = lla[0]
        rad_lon = lla[1]
        if not input_in_radians:
            rad_lat = radians(rad_lat)  # sometimes denoted as lambda
            rad_lon = radians(rad_lon)  # sometimes denoted as phi

        ht = lla[2]
        rad = cls.radius_e + ht
        clat = cos(rad_lat)
        x = rad * cos(rad_lon) * clat
        y = rad * clat * sin(rad_lon)
        z = rad * sin(rad_lat)
        return (x, y, z)

    @classmethod
    def lla2ecef(cls, lla: POSITIONS, input_in_radians: bool = False) -> POSITIONS:
        """Lat-Lon-Alt to ECEF.

        Args:
            lla (POSITIONS): Lat-Lon-Altitude points
            input_in_radians (bool, optional): If lat/lon are in radians. Defaults to False.

        Returns:
            POSITIONS: ECEF
        """
        return [cls._lla2ecef(row, input_in_radians) for row in lla]

    @classmethod
    def _ecef2lla(cls, ecef: POSITION, radians_out: bool = False) -> POSITION:
        """Convert ECEF to Lat-Lon-Alt.

        Args:
            ecef (POSITION): Points in ECEF
            radians_out (bool, optional): If Lat/Lon out are in radians. Defaults to False.

        Returns:
            POSITION: Lat-Lon-Alt points
        """
        x, y, z = ecef
        # Longitude (rad)
        lon = atan2(y, x)

        p = sqrt(x**2 + y**2)
        # Latitude (rads)
        lat = atan2(z, p)
        h = p / cos(lat) - cls.radius_e

        # correct for numerical instability in altitude near exact poles:
        # (after this correction, error is about 2 millimeters, which is about
        # the same as the numerical precision of the overall function)
        k = (abs(x) < 1) & (abs(y) < 1)
        if k:
            h = abs(z) - cls.radius_p

        if not radians_out:
            lon = degrees(lon)
            lat = degrees(lat)

        lla = (lat, lon, h)
        return lla

    @classmethod
    def ecef2lla(cls, ecef: POSITIONS, radians_out: bool = False) -> POSITIONS:
        """Convert ECEF to Lat-Lon-Alt.

        Args:
            ecef (POSITIONS): Points in ECEF
            radians_out (bool, optional): If Lat/Lon out are in radians. Defaults to False.

        Returns:
            POSITIONS: Lat-Lon-Alt points
        """
        return [cls._ecef2lla(row, radians_out) for row in ecef]


class WGS84Conversions(BaseConversions):
    """WGS84 coordinate conversions."""

    radius_e = wR_e
    radius_p = wR_p
    e_2 = we_2
    ep_2 = wep_2
    e = we
    ep = wep
    f = wF
