"""
Shared utility functions for Arsenal Ship Tracker.

This module contains common functions used across multiple modules
to avoid code duplication.
"""

import math
from typing import Tuple


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

    Uses the Haversine formula to compute the shortest distance over
    the Earth's surface between two points specified by latitude and
    longitude coordinates.

    Args:
        lat1: Latitude of first point in degrees
        lon1: Longitude of first point in degrees
        lat2: Latitude of second point in degrees
        lon2: Longitude of second point in degrees

    Returns:
        Distance between the two points in kilometers

    Example:
        >>> haversine(31.2, 121.4, 31.3, 121.5)  # Shanghai area
        13.96...  # approximately 14 km
    """
    R = 6371  # Earth's radius in kilometers

    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c


def nautical_miles_to_km(nm: float) -> float:
    """Convert nautical miles to kilometers."""
    return nm * 1.852


def km_to_nautical_miles(km: float) -> float:
    """Convert kilometers to nautical miles."""
    return km / 1.852


def validate_coordinates(lat: float, lon: float) -> bool:
    """
    Validate that coordinates are within valid ranges.

    Args:
        lat: Latitude (-90 to 90)
        lon: Longitude (-180 to 180)

    Returns:
        True if coordinates are valid, False otherwise
    """
    return -90 <= lat <= 90 and -180 <= lon <= 180


def is_null_island(lat: float, lon: float, threshold: float = 0.1) -> bool:
    """
    Check if coordinates are at or near Null Island (0, 0).

    Null Island is often used as a placeholder for invalid coordinates.

    Args:
        lat: Latitude
        lon: Longitude
        threshold: Distance threshold in degrees (default 0.1)

    Returns:
        True if near Null Island, False otherwise
    """
    return abs(lat) < threshold and abs(lon) < threshold
