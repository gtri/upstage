# Copyright (C) 2026 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.

"""Unit conversion help."""

_distance_to_m = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "km": 1000.0,
    "inch": 0.0254,
    "inches": 0.0254,
    "in": 0.0254,
    "ft": 0.3048,
    "feet": 0.3048,
    "foot": 0.3048,
    "yd": 0.9144,
    "yard": 0.9144,
    "yards": 0.9144,
    "mile": 1609.344,
    "miles": 1609.344,
    "mi": 1609.344,
    "nmi": 1852.0,
}

_time_to_s = {
    "ns": 1e-9,
    "us": 1e-6,
    "μs": 1e-6,
    "ms": 0.001,
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "min": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "day": 86400.0,
    "days": 86400.0,
}


def unit_convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between distance and time units.

    Supported distance units:
        mm, cm, m, meter, meters, km, inch, inches, in,
        ft, feet, foot, yd, yard, yards, mile, miles, mi, nmi

    Supported time units:
        ns, us, μs, ms, s, sec, seconds, min, minute, minutes,
        h, hr, hour, hours, day, days

    Example:
        unit_convert(100, 'km', 'mile')   # -> 62.1371...
        unit_convert(3600, 's', 'h')      # -> 1.0
    """
    # Normalize input (handle case and common variations)
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    if from_unit in _distance_to_m and to_unit in _distance_to_m:
        meters = value * _distance_to_m[from_unit]
        return meters / _distance_to_m[to_unit]
    elif from_unit in _time_to_s and to_unit in _time_to_s:
        seconds = value * _time_to_s[from_unit]
        return seconds / _time_to_s[to_unit]
    else:
        raise ValueError(
            f"Cannot convert from '{from_unit}' to '{to_unit}'. "
            f"Both units must be either distance or time."
        )


def speed_convert(value: float, dist1: str, time1: str, dist2: str, time2: str) -> float:
    """Convert between speeds.

    Example:
      speed_convert(60, "miles", "hour", "km", "sec") # -> 0.0268224
      speed_convert(1, "meters", "second", "nmi", "hr") # -> 1.98
    """
    d = unit_convert(1, dist1, dist2)
    t = unit_convert(1, time1, time2)
    return value * d / t
