"""
AISHub API Client

Free community-based AIS data sharing service.
https://www.aishub.net/

Features:
- Free access (requires registration and data contribution)
- Vessel position data via REST API
- Bounding box queries supported
- JSON/XML output formats

Registration:
1. Register at https://www.aishub.net/register
2. Set up data sharing (contribute AIS data to receive access)
3. Get your username for API access

Used as:
- Additional data source for broader coverage
- Fallback when other sources unavailable
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple

from .base import (
    AISSource, AISPosition, AISVesselInfo, SourceType, SourceStatus,
    get_ship_type_text
)


class AISHubSource(AISSource):
    """
    AISHub REST API client.

    Community-based AIS data exchange. Requires registration and
    data contribution to access.

    Configuration:
        username: AISHub registered username
        bounding_box: Optional tuple (lat_min, lon_min, lat_max, lon_max)

    Usage:
        source = AISHubSource(username="your_username")
        source.connect()

        # Fetch by MMSI list
        positions = source.fetch_positions(["413000000"])

        # Fetch by area (uses bounding box)
        source.set_bounding_box(20, 110, 40, 130)
        all_positions = source.fetch_area_positions()
    """

    BASE_URL = "https://data.aishub.net/ws.php"

    # AIS ship type mapping (type code to description)
    SHIP_TYPES = {
        0: "Not available",
        20: "Wing in ground",
        30: "Fishing",
        31: "Towing",
        32: "Towing large",
        33: "Dredging",
        34: "Diving ops",
        35: "Military ops",
        36: "Sailing",
        37: "Pleasure craft",
        40: "High speed craft",
        50: "Pilot vessel",
        51: "Search and rescue",
        52: "Tug",
        53: "Port tender",
        54: "Anti-pollution",
        55: "Law enforcement",
        60: "Passenger",
        70: "Cargo",
        71: "Cargo - hazardous A",
        72: "Cargo - hazardous B",
        73: "Cargo - hazardous C",
        74: "Cargo - hazardous D",
        80: "Tanker",
        81: "Tanker - hazardous A",
        82: "Tanker - hazardous B",
        83: "Tanker - hazardous C",
        84: "Tanker - hazardous D",
        90: "Other"
    }

    def __init__(self, username: str, bounding_box: Optional[Tuple[float, float, float, float]] = None):
        super().__init__(name="aishub", source_type=SourceType.REST)

        self.username = username
        self.bounding_box = bounding_box  # (lat_min, lon_min, lat_max, lon_max)

        # Rate limiting (AISHub: max once per minute!)
        self._last_request_time: float = 0
        self._min_request_interval: float = 60.0  # AISHub requires 60 seconds between requests

        # Cache
        self._position_cache: Dict[str, AISPosition] = {}
        self._vessel_cache: Dict[str, AISVesselInfo] = {}
        self._cache_ttl: int = 300  # 5 minutes
        self._cache_timestamps: Dict[str, float] = {}

    def set_bounding_box(self, lat_min: float, lon_min: float, lat_max: float, lon_max: float) -> None:
        """Set geographic bounding box for area queries."""
        self.bounding_box = (lat_min, lon_min, lat_max, lon_max)
        self._log(f"Bounding box set: {lat_min},{lon_min} to {lat_max},{lon_max}")

    def connect(self) -> bool:
        """
        Verify API is reachable and credentials work.
        """
        if not self.username:
            self._set_status(SourceStatus.ERROR, "Username required")
            return False

        try:
            self._log("Verifying AISHub API access...")

            # Make a minimal test request
            params = {
                "username": self.username,
                "format": "1",  # JSON
                "output": "json",
                "compress": "0",
                "latmin": "0",
                "latmax": "1",
                "lonmin": "0",
                "lonmax": "1"
            }

            url = self._build_url(params)
            response = self._make_request(url)

            if response is not None:
                self._set_status(SourceStatus.CONNECTED)
                self._log("Connected to AISHub")
                return True
            else:
                self._set_status(SourceStatus.ERROR, "API request failed")
                return False

        except Exception as e:
            self._set_status(SourceStatus.ERROR, str(e))
            return False

    def disconnect(self) -> None:
        """Close connection (no-op for REST)."""
        self._set_status(SourceStatus.DISCONNECTED)

    def fetch_positions(self, mmsi_list: List[str]) -> List[AISPosition]:
        """
        Fetch current positions for specified vessels.

        Note: AISHub doesn't support direct MMSI queries efficiently.
        For specific vessels, we fetch area data and filter.
        """
        if not self.is_available():
            if not self.connect():
                return []

        positions = []

        # Check cache first
        uncached_mmsi = []
        for mmsi in mmsi_list:
            cached = self._get_cached_position(mmsi)
            if cached:
                positions.append(cached)
            else:
                uncached_mmsi.append(mmsi)

        if not uncached_mmsi:
            return positions

        # Fetch all area data and filter
        if self.bounding_box:
            area_positions = self.fetch_area_positions()
            for pos in area_positions:
                if pos.mmsi in uncached_mmsi:
                    positions.append(pos)
                    uncached_mmsi.remove(pos.mmsi)

        return positions

    def fetch_area_positions(self) -> List[AISPosition]:
        """
        Fetch all vessel positions within the configured bounding box.

        Returns list of AISPosition objects for all vessels in the area.
        """
        if not self.is_available():
            if not self.connect():
                return []

        if not self.bounding_box:
            self._log("No bounding box set for area query", level="warning")
            return []

        # Rate limit check
        if not self._check_rate_limit():
            self._log("Rate limited, returning cached data", level="warning")
            return list(self._position_cache.values())

        lat_min, lon_min, lat_max, lon_max = self.bounding_box

        params = {
            "username": self.username,
            "format": "1",  # JSON
            "output": "json",
            "compress": "0",
            "latmin": str(lat_min),
            "latmax": str(lat_max),
            "lonmin": str(lon_min),
            "lonmax": str(lon_max)
        }

        url = self._build_url(params)
        data = self._make_request(url)

        if not data:
            return []

        positions = self._parse_response(data)

        # Cache all positions
        for pos in positions:
            self._cache_position(pos)

        self._log(f"Fetched {len(positions)} positions from AISHub")
        return positions

    def fetch_vessel_info(self, mmsi: str) -> Optional[AISVesselInfo]:
        """
        Fetch vessel static information.

        AISHub includes some static data in position responses.
        """
        if mmsi in self._vessel_cache:
            return self._vessel_cache[mmsi]

        # Try to get from a position fetch
        positions = self.fetch_positions([mmsi])
        if positions and mmsi in self._vessel_cache:
            return self._vessel_cache[mmsi]

        return None

    def _build_url(self, params: Dict[str, str]) -> str:
        """Build API URL with parameters."""
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}?{query}"

    def _make_request(self, url: str) -> Optional[Any]:
        """Make HTTP request to AISHub API."""
        try:
            self._last_request_time = time.time()

            request = urllib.request.Request(url)
            request.add_header("User-Agent", "ArsenalShipTracker/1.0")

            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read().decode("utf-8")

                # AISHub returns JSON array
                if content.strip().startswith("["):
                    return json.loads(content)
                elif content.strip().startswith("{"):
                    # Error response
                    error_data = json.loads(content)
                    if "ERROR" in error_data:
                        self._log(f"API error: {error_data['ERROR']}", level="error")
                        return None
                    return error_data
                else:
                    self._log(f"Unexpected response format", level="warning")
                    return None

        except urllib.error.HTTPError as e:
            self._log(f"HTTP error {e.code}: {e.reason}", level="error")
            if e.code == 429:
                self._set_status(SourceStatus.RATE_LIMITED)
            return None
        except urllib.error.URLError as e:
            self._log(f"URL error: {e.reason}", level="error")
            return None
        except json.JSONDecodeError as e:
            self._log(f"JSON decode error: {e}", level="error")
            return None
        except Exception as e:
            self._log(f"Request error: {e}", level="error")
            return None

    def _parse_response(self, data: Any) -> List[AISPosition]:
        """
        Parse AISHub API response into AISPosition objects.

        AISHub returns array of vessel objects with format:
        [
            {
                "MMSI": "123456789",
                "TIME": "2024-01-01 12:00:00",
                "LONGITUDE": 121.5,
                "LATITUDE": 31.2,
                "COG": 180.0,
                "SOG": 10.5,
                "HEADING": 175,
                "NAVSTAT": 0,
                "IMO": "1234567",
                "NAME": "VESSEL NAME",
                "CALLSIGN": "ABCD",
                "TYPE": 70,
                ...
            },
            ...
        ]
        """
        positions = []

        if not isinstance(data, list):
            return positions

        for vessel in data:
            try:
                mmsi = str(vessel.get("MMSI", ""))
                if not mmsi or len(mmsi) != 9:
                    continue

                lat = vessel.get("LATITUDE")
                lon = vessel.get("LONGITUDE")

                if lat is None or lon is None:
                    continue

                # Parse timestamp (format: "2021-07-09 08:06:53 GMT")
                time_str = vessel.get("TIME", "")
                try:
                    # Remove " GMT" suffix if present
                    time_str = time_str.replace(" GMT", "")
                    timestamp = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                except:
                    timestamp = datetime.utcnow()

                position = AISPosition(
                    mmsi=mmsi,
                    latitude=float(lat),
                    longitude=float(lon),
                    timestamp=timestamp,
                    speed_knots=vessel.get("SOG"),
                    course=vessel.get("COG"),
                    heading=vessel.get("HEADING"),
                    nav_status=vessel.get("NAVSTAT"),
                    source="aishub",
                    source_timestamp=datetime.utcnow()
                )

                if position.is_valid():
                    positions.append(position)

                    # Also cache vessel info if available
                    if vessel.get("NAME") or vessel.get("IMO"):
                        ship_type = vessel.get("TYPE")
                        vessel_info = AISVesselInfo(
                            mmsi=mmsi,
                            imo=str(vessel.get("IMO", "")) or None,
                            name=vessel.get("NAME"),
                            callsign=vessel.get("CALLSIGN"),
                            ship_type=ship_type,
                            ship_type_text=self._get_ship_type_text(ship_type),
                            length=vessel.get("A", 0) + vessel.get("B", 0) if vessel.get("A") else None,
                            width=vessel.get("C", 0) + vessel.get("D", 0) if vessel.get("C") else None,
                            destination=vessel.get("DEST"),
                            source="aishub"
                        )
                        self._vessel_cache[mmsi] = vessel_info

            except Exception as e:
                self._log(f"Error parsing vessel data: {e}", level="warning")
                continue

        return positions

    def _get_ship_type_text(self, type_code: Optional[int]) -> Optional[str]:
        """Convert AIS ship type code to text description."""
        if type_code is None:
            return None

        # Check exact match
        if type_code in self.SHIP_TYPES:
            return self.SHIP_TYPES[type_code]

        # Check type ranges
        if 20 <= type_code <= 29:
            return "Wing in ground"
        if 30 <= type_code <= 39:
            return "Fishing/Towing"
        if 40 <= type_code <= 49:
            return "High speed craft"
        if 50 <= type_code <= 59:
            return "Special craft"
        if 60 <= type_code <= 69:
            return "Passenger"
        if 70 <= type_code <= 79:
            return "Cargo"
        if 80 <= type_code <= 89:
            return "Tanker"

        return "Other"

    def _check_rate_limit(self) -> bool:
        """Check if we can make a request (rate limiting)."""
        now = time.time()
        if now - self._last_request_time < self._min_request_interval:
            return False
        return True

    def _get_cached_position(self, mmsi: str) -> Optional[AISPosition]:
        """Get cached position if still valid."""
        if mmsi not in self._position_cache:
            return None

        cache_time = self._cache_timestamps.get(mmsi, 0)
        if time.time() - cache_time > self._cache_ttl:
            del self._position_cache[mmsi]
            del self._cache_timestamps[mmsi]
            return None

        return self._position_cache[mmsi]

    def _cache_position(self, position: AISPosition) -> None:
        """Cache a position."""
        self._position_cache[position.mmsi] = position
        self._cache_timestamps[position.mmsi] = time.time()
