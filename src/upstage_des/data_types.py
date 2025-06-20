# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Data types for common operations. Currently just locations."""

from dataclasses import FrozenInstanceError
from math import degrees, radians, sqrt
from typing import Any

from upstage_des.base import UpstageBase
from upstage_des.math_utils import _vector_norm, _vector_subtract
from upstage_des.units import unit_convert

__all__ = (
    "CartesianLocation",
    "GeodeticLocation",
    "Location",
    "CartesianLocationData",
    "GeodeticLocationData",
)


class Location(UpstageBase):
    """An abstract class for representing a location in a space."""

    def copy(self) -> "Location":
        """Copy the location."""
        raise NotImplementedError("Subclass must implement copy.")

    @property
    def _repred_attrs(self) -> dict[str, Any]:
        """A way to customize how attributes are represented by __repr__.

        Returns:
            dict[str, Any]: Relevant attributes with name:value pairs.
        """
        return {
            k: v
            for k, v in self.__dict__.items()
            if not k.startswith("_") and k not in ["env", "stage"]
        }

    def _key(self) -> tuple[float, ...]:
        """A key used for hashing."""
        raise NotImplementedError("Location is intended to be subclassed.")

    def _to_tuple(self) -> tuple[float, ...]:
        """Return a tuple of the location.

        To be implemented in a subclass.

        Returns:
            tuple[float, ...]: Tuple of numbers describing a location.
        """
        raise NotImplementedError("Subclass must implement tuple.")

    def straight_line_distance(self, other: object) -> float:
        """Straight line distances b/w locations.

        Args:
            other (Location): Another location
        """
        raise NotImplementedError(
            "Subclass must implement a subtraction operator to calculate distance between Locations"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        """Locations should be frozen, so this setattr restricts changing the values.

        Args:
            name (str): Attribute name
            value (Any): Attribute value
        """
        if hasattr(self, "_no_override") and name in self._no_override:
            raise FrozenInstanceError(f"Locations are disallowed from setting {name}")
        return super().__setattr__(name, value)

    def __sub__(self, other: object) -> float:
        """Subtract location.

        Args:
            other (Location): Another location
        """
        raise NotImplementedError(
            "Subclass must implement a subtraction operator to calculate distance between Locations"
        )

    def __eq__(self, other: object) -> bool:
        """Test for equality with another location.

        Args:
            other (object): The other location object

        Returns:
            bool: If it is equal.
        """
        raise NotImplementedError("Subclass must implement a equality comparison")

    def __hash__(self) -> int:
        raise NotImplementedError("Location is not intended for solo use.")

    def __repr__(self) -> str:
        """Customized the printable representation of the object.

        Does this by:
        1. Using all the dataclass fields that have `repr` set to True
        2. Representation for attributes can be customized by defining a
           `_get_repred_attrs` method that returns a dictionary of attributes
           keys and repr'ed values.
        """
        clean_attrs = [f"{key}={value}" for key, value in self._repred_attrs.items()]
        return f"{self.__class__.__name__}({', '.join(clean_attrs)})"


class CartesianLocation(Location):
    """A location that can be mapped to a 3-dimensional cartesian space."""

    def __init__(
        self,
        x: float,
        y: float,
        z: float = 0.0,
        *,
        use_altitude_units: bool = False,
    ) -> None:
        """A Cartesian (3D space) location.

        use_altitude_units, when false, means Z distance uses the "distance_units" unit.

        When true, it uses "altitude_units".

        Use UP.add_stage_variable("altitude_units", "ft"), e.g.

        Args:
            x (float): X dimension location
            y (float): Y dimension location
            z (float, optional): Z location. Defaults to 0.0.
            use_altitude_units (bool, optional): Use the sim's altitude units. Defaults to False.
        """
        super().__init__()
        self.x = x
        self.y = y
        self.z = z
        self.use_altitude_units = use_altitude_units
        self._no_override = ["x", "y", "z", "use_altitude_units"]

    @property
    def _repred_attrs(self) -> dict[str, str]:
        """Allows for attributes to be repr'ed based on the state of the units.

        Returns:
            dict[str, str]: Strings of attributes.
        """
        attrs = {}
        try:
            hor_units = self.stage.distance_units
        except AttributeError:
            hor_units = ""
        try:
            alt_units = (
                self.stage.altitude_units if self.use_altitude_units else self.stage.distance_units
            )
        except AttributeError:
            alt_units = ""
        for coordinate in ("x", "y"):
            attrs[coordinate] = f"{getattr(self, coordinate):,}{hor_units}"
        attrs["z"] = f"{self.z:,}{alt_units}"
        return attrs

    def _as_array(self) -> tuple[float, float, float]:
        """Make an array of consistent units for all dimensions.

        Returns:
            tuple[float, float, float]: A 1-D array of (x, y, z)
        """
        if self.use_altitude_units:
            height = unit_convert(self.z, self.stage.altitude_units, self.stage.distance_units)
        else:
            height = self.z
        return (self.x, self.y, height)

    def _to_tuple(self) -> tuple[float, float, float]:
        """Return a tuple of the location.

        Returns:
            tuple[float, float, float]: Latitude, longitude, altitude.
        """
        return self._as_array()

    def copy(self) -> "CartesianLocation":
        """Return a copy of the location.

        Returns:
            CartesianLocation
        """
        return self.__class__(
            x=self.x, y=self.y, z=self.z, use_altitude_units=self.use_altitude_units
        )

    def _key(self) -> tuple[float, float, float, bool]:
        """Key for hashing.

        Returns:
            tuple[float, float, float, bool]
        """
        return (self.x, self.y, self.z, self.use_altitude_units)

    def straight_line_distance(self, other: object) -> float:
        """Get the straight line distance between this and another location.

        Args:
            other (object): The other CartesianLocation point.
        """
        return self - other

    def __getitem__(self, idx: int) -> float:
        """Convenience way to get an xyz position by index.

        Args:
            idx (int): Index (xyz)

        Returns:
            float: Value at index
        """
        if not 0 <= idx <= 2:
            raise ValueError(f"CartesianLocation only has 3 indices (x, y, z), not a {idx}th index")
        return [self.x, self.y, self.z][idx]

    def __sub__(self, other: object) -> float:
        """Subtract one cartesian location from another.

        Distance is straight lint.

        Args:
            other (CartesianLocation): Another location

        Returns:
            float: Distance between this and another location.
        """
        if isinstance(other, CartesianLocation):
            sum_sq = sum((a - b) ** 2 for a, b in zip(self._as_array(), other._as_array()))
            return sqrt(sum_sq)
        else:
            raise ValueError(f"Cannot subtract {other.__class__.__name__} from a CartesianLocation")

    def __eq__(self, other: object) -> bool:
        """Test if two positions are the same.

        Uses a tolerance so this will be True for very close positions.

        Args:
            other (CartesianLocation): Another location

        Returns:
            bool: Is equal or not
        """
        if not isinstance(other, CartesianLocation):
            raise ValueError(f"Cannot compare {other.__class__.__name__} to a CartesianLocation")
        dist = self - other
        return bool(abs(dist) <= 0.00001)

    def __hash__(self) -> int:
        """Hash based on the key.

        Returns:
            int: The hash.
        """
        return hash(self._key())


class GeodeticLocation(Location):
    """A Location that can be mapped to the surface of a spheroid (a.k.a. ellipsoid).

    More specifically, a Location representing somewhere on an ellipsoid, with Latitude,
    Longitude, and Altitude that uses the geodetic datum (or geodetic system).  Can be
    used to define a location on Earth or other planetary bodies.

    Units for the horizontal datum (i.e., `lat` and `lon`) can be Decimal Degrees or
    Radians, depending on the value of `units`, the vertical datum (i.e., `alt`) is
    assumed to be in meters.

    Subtraction represents a great circle distance, NOT a true 3D straight-line distance.

    Speeds used for this location type will represent ground speed, which allows
    the class to ignore solving the exact altitude change in the path.

    Units are an input to the location type.

    The ellipsoid model must have a `.distance(Location1, Location2)` method
    that looks for .lat and .lon.

    `altitude` is 0.0 by default.

    `lat` (latitude) and `lon` (longitude) are in degrees by default.
        if using radians, set `in_radians` to `True`.

    """

    def __init__(
        self,
        lat: float,
        lon: float,
        alt: float = 0.0,
        *,
        in_radians: bool = False,
    ) -> None:
        """A location on a geodetic (Earth).

        Altitude uses the "altitude_units" stage variable.

        Args:
            lat (float): Latitude (North/South)
            lon (float): Longitude (East/West)
            alt (float, optional): Altitude. Defaults to 0.0.
            in_radians (bool, optional): If the lat/lon are in radians or degrees.
                Defaults to False.

        Returns:
            GeodeticLocation
        """
        super().__init__()
        self.lat = lat
        self.lon = lon
        self.alt = alt
        self.in_radians = in_radians
        self._no_override = ["lat", "lon", "alt", "in_radians"]

    @property
    def _repred_attrs(self) -> dict[str, str]:
        """Allows for attributes to be repr'ed based on the state of the units.

        Returns:
            dict[str, str]: Strings of attributes.
        """
        attrs = {}
        units = "rad" if self.in_radians else "°"
        try:
            alt_units = self.stage.altitude_units
        except AttributeError:
            alt_units = ""
        for coordinate in ("lat", "lon"):
            attrs[coordinate] = f"{getattr(self, coordinate)}{units}"
        attrs["alt"] = f"{self.alt:,}{alt_units}"
        return attrs

    def _to_tuple(self) -> tuple[float, float, float]:
        """Return a tuple of the location.

        Returns:
            tuple[float, float, float]: Latitude, longitude, altitude.
        """
        return (self.lat, self.lon, self.alt)

    def latlon(self) -> tuple[float, float]:
        """Return a tuple of just lat/lon as degrees.

        Returns:
            tuple[float, float]: Latitude and longitude in degrees.
        """
        s = self.to_degrees()
        return (s.lat, s.lon)

    def to_radians(self) -> "GeodeticLocation":
        """Convert to radians, if already in radians, return self.

        Returns:
            GeodeticLocation
        """
        if self.in_radians:
            return self
        kwargs: dict[str, float | bool] = {"alt": self.alt}
        for coordinate in ("lat", "lon"):
            kwargs[coordinate] = radians(getattr(self, coordinate))
        kwargs["in_radians"] = True
        return self.__class__(**kwargs)  # type: ignore [arg-type]

    def to_degrees(self) -> "GeodeticLocation":
        """Convert to degrees, if already in degrees, return self.

        Returns:
            GeodeticLocation
        """
        if not self.in_radians:
            return self
        kwargs: dict[str, float | bool] = {"alt": self.alt}
        for coordinate in ("lat", "lon"):
            kwargs[coordinate] = degrees(getattr(self, coordinate))
        kwargs["in_radians"] = False
        return self.__class__(**kwargs)  # type: ignore [arg-type]

    def _key(self) -> tuple[float, float, float, bool]:
        """A key for hashing.

        Returns:
            tuple[float, float, float, bool]: All values.
        """
        return (self.lat, self.lon, self.alt, self.in_radians)

    def copy(self) -> "GeodeticLocation":
        """Copy the location.

        Returns:
            GeodeticLocation
        """
        return self.__class__(
            lat=self.lat,
            lon=self.lon,
            alt=self.alt,
            in_radians=self.in_radians,
        )

    def dist_with_altitude(self, other: "GeodeticLocation") -> float:
        """Get the distance between two points with an altitude component.

        Args:
            other (GeodeticLocation): The other point

        Returns:
            float: Distance - pythagorean of great-circle and altitude
        """
        dist = self - other
        alt = abs(self.alt - other.alt)
        alt = unit_convert(alt, self.stage.altitude_units, self.stage.distance_units)
        full_dist: float = sqrt(alt**2 + dist**2)
        return full_dist

    def straight_line_distance(self, other: object) -> float:
        """Straight-line distance, using ECEF.

        This won't account for horizon.

        Args:
            other (GeodeticLocation): The other point

        Returns:
            float: Distance
        """
        if not isinstance(other, GeodeticLocation):
            raise TypeError(f"Cannot subtract a {other.__class__.__name__} from a GeodeticLocation")
        lat, lon, alt = self.to_degrees()._to_tuple()
        alt = unit_convert(alt, self.stage.altitude_units, "m")
        ecef_self = self.stage.stage_model.lla2ecef([(lat, lon, alt)])[0]

        lat, lon, alt = other.to_degrees()._to_tuple()
        alt = unit_convert(alt, self.stage.altitude_units, "m")
        ecef_other = self.stage.stage_model.lla2ecef([(lat, lon, alt)])[0]

        dist_meters = float(_vector_norm(_vector_subtract(ecef_other, ecef_self)))
        dist_units = unit_convert(dist_meters, "m", self.stage.distance_units)
        return dist_units

    def __getitem__(self, idx: int) -> float:
        """Convenience way to get an xyz position by index.

        Args:
            idx (int): Index (lat/lon/alt)

        Returns:
            float: Value at index
        """
        if not 0 <= idx <= 2:
            raise IndexError(
                f"GeodeticLocation only has 3 indices (lat, lon, alt), not a {idx}th index"
            )
        return [self.lat, self.lon, self.alt][idx]

    def __sub__(self, other: object) -> float:
        """Find the great circle distance between Geodetic points.

        Args:
            other (GeodeticLocation): Another location

        Returns:
            float: distance in stage "distance_units" units.
        """
        if not isinstance(other, GeodeticLocation):
            raise ValueError(
                f"Cannot subtract a {other.__class__.__name__} from a GeodeticLocation"
            )
        # distances presume positions are in degrees
        dlat, dlon = self.to_degrees()._key()[:2]
        olat, olon = other.to_degrees()._key()[:2]
        dist = self.stage.stage_model.distance(
            (dlat, dlon),
            (olat, olon),
            units=self.stage.distance_units,
        )
        return dist

    def __eq__(self, other: object) -> bool:
        """Test if two locations are the same.

        No tolerance is applied here.

        Args:
            other (GeodeticLocation): Another location

        Returns:
            bool: Close enough or not.
        """
        if not isinstance(other, GeodeticLocation):
            raise ValueError(f"Cannot compare a {other.__class__.__name__} to a GeodeticLocation")
        if other.in_radians != self.in_radians:
            if self.in_radians:
                other = other.to_radians()
            else:
                other = other.to_degrees()
        return all(
            getattr(self, dimension) == getattr(other, dimension)
            for dimension in ["lat", "lon", "alt"]
        )

    def __hash__(self) -> int:
        """Hash based on the key.

        Returns:
            int: The hash.
        """
        return hash(self._key())


class CartesianLocationData:
    """Object for storing caretesian data without an environment."""

    def __init__(
        self,
        x: float,
        y: float,
        z: float = 0.0,
        *,
        use_altitude_units: bool = True,
    ) -> None:
        """Cartesian data storage.

        Args:
            x (float): _description_
            y (float): _description_
            z (float, optional): _description_. Defaults to 0.0.
            use_altitude_units (bool, optional): _description_. Defaults to True.
        """
        self.x = x
        self.y = y
        self.z = z
        self.use_altitude_unts = use_altitude_units

    def make_location(self) -> CartesianLocation:
        """Create a location from the data.

        Do this inside an environment contex.t

        Returns:
            CartesianLocation: The location object.
        """
        return CartesianLocation(
            x=self.x, y=self.y, z=self.z, use_altitude_units=self.use_altitude_unts
        )

    def __eq__(self, value: Any) -> bool:
        """Test for equality of two cartesian locations data objects."""
        if not isinstance(value, CartesianLocationData):
            raise ValueError(
                f"Cannot compare a {value.__class__.__name__} to a CartesianLocationData"
            )
        check = ["x", "y", "z"]
        return all(getattr(self, c) == getattr(value, c) for c in check)


class GeodeticLocationData:
    """Object for storing geodetic data without an environment."""

    def __init__(
        self,
        lat: float,
        lon: float,
        alt: float = 0.0,
        *,
        in_radians: bool = False,
    ) -> None:
        """Geodetic data storage.

        Args:
            lat (float): _description_
            lon (float): _description_
            alt (float, optional): _description_. Defaults to 0.0.
            in_radians (bool, optional): _description_. Defaults to False.
        """
        self.lat = lat
        self.lon = lon
        self.alt = alt
        self.in_radians = in_radians

    def latlon(self) -> tuple[float, float]:
        """Return a tuple of just lat/lon as degrees.

        Returns:
            tuple[float, float]: Latitude and longitude in degrees.
        """
        lat = degrees(self.lat) if self.in_radians else self.lat
        lon = degrees(self.lon) if self.in_radians else self.lon
        return (lat, lon)

    def make_location(self) -> GeodeticLocation:
        """Create a location from the data.

        Do this inside an environment contex.t

        Returns:
            GeodeticLocation: The location object.
        """
        return GeodeticLocation(
            lat=self.lat,
            lon=self.lon,
            alt=self.alt,
            in_radians=self.in_radians,
        )

    def __eq__(self, value: Any) -> bool:
        """Test for equality of two cartesian locations data objects."""
        if not isinstance(value, GeodeticLocationData):
            raise ValueError(
                f"Cannot compare a {value.__class__.__name__} to a GeodeticLocationData"
            )
        other = [value.lat, value.lon]
        if value.in_radians != self.in_radians:
            if self.in_radians:
                other = list(map(radians, other))
            else:
                other = list(map(degrees, other))
        angles = [self.lat, self.lon] == other
        return angles and self.alt == value.alt
