# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Conversions for common distance and time units."""

CONVERSIONS: dict[str, dict[str, float]] = {
    "m": {
        "km": 1 / 1000.0,
        "mi": 1 / 1000.0 * 0.62137119223,
        "nmi": 1 / 1000.0 * 0.539957,
        "m": 1.0,
    },
    "km": {"km": 1.0, "mi": 0.62137119223, "nmi": 0.539957, "m": 1000.0},
    "mi": {
        "km": 1 / 0.62137119223,
        "mi": 1.0,
        "nmi": 0.868976,
        "m": 1 / 0.62137119223 * 1000,
    },
    "nmi": {
        "km": 1 / 0.539957,
        "mi": 1 / 0.868976,
        "nmi": 1.0,
        "m": 1 / 0.539957 * 1000,
    },
    "s": {"hr": 1.0 / (60.0 * 60.0), "min": 1.0 / 60.0, "s": 1.0},
    "min": {"hr": 1.0 / 60.0, "min": 1.0, "s": 60.0},
    "hr": {"hr": 1.0, "min": 60.0, "s": (60.0 * 60.0)},
    "day": {"hr": 24.0, "week": 1 / 7.0, "min": 24 * 60.0, "s": 24 * 3600},
    "week": {"day": 7.0, "hr": 7.0 * 24, "min": 7.0 * 24 * 60.0, "s": 7.0 * 24 * 3600},
}

DISTANCE_UNITS = ["m", "km", "mi", "nmi", "ft"]
TIME_UNITS = ["s", "min", "hr", "day", "week"]
TIME_ALTERNATES = {
    "seconds": "s",
    "second": "s",
    "minute": "min",
    "minutes": "min",
    "hour": "hr",
    "hours": "hr",
    "days": "day",
    "weeks": "week",
}
STANDARD_TIMES = ["s", "min", "hr"]

# add feet to conversions
CONVERSIONS["ft"] = {"ft": 1.0, "mi": 1 / 5280.0}
for unit in DISTANCE_UNITS:
    if unit == "ft":
        continue
    CONVERSIONS["ft"][unit] = CONVERSIONS["mi"][unit] / 5280.0
    CONVERSIONS[unit]["ft"] = 1 / CONVERSIONS["ft"][unit]


def unit_convert(value: int | float, units_from: str, units_to: str) -> float:
    """Convert between units of distance and time.

    Units must be one of:
        distance: km, m, mi, nmi, ft

        time:

        * s, second, or seconds
        * min, minute, or minutes
        * hr, hour, or hours
        * day or days
        * week or weeks

    All units are lower-cased on input.

    Args:
        value (int | float): Value of "from" unit
        units_from (str): Unit to convert from
        units_to (str): Unit to convert to

    Raises:
        ValueError: _description_

    Returns:
        float: _description_
    """
    units_fr = units_from.lower()
    units_t = units_to.lower()
    units_fr = TIME_ALTERNATES.get(units_fr, units_fr)
    units_t = TIME_ALTERNATES.get(units_t, units_t)
    try:
        return value * CONVERSIONS[units_fr][units_t]
    except KeyError:
        raise ValueError(f"Cannot convert from {units_from} to {units_to}.")
