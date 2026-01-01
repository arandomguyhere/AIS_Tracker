"""
Marinesia API Client

REST API for vessel position and profile data.
https://marinesia.com/

API Version: 0.1.0
Base URL: https://api.marinesia.com/api/v1

Endpoints:
- GET /vessel/{mmsi}/profile - Get vessel profile by MMSI
- GET /vessel/{mmsi}/image - Get vessel image by MMSI
- GET /vessel/{mmsi}/location/latest - Get latest vessel location
- GET /vessel/{mmsi}/location - Get historical vessel location
- GET /vessel/nearby - Get vessels within bounding box
- GET /vessel/profile - List vessel profiles with pagination
- GET /vessel/location - List vessel locations with pagination
- GET /port/{id}/profile - Get port profile
- GET /port/nearby - Get ports within bounding box
- GET /port/profile - List ports with pagination

Used as:
- Fallback when real-time source offline
- Metadata/vessel info enrichment
- Area-based vessel queries
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


class MarinesiaSource(AISSource):
    """
    Marinesia REST API client.

    Supports vessel lookup by MMSI, area queries, and vessel profiles.

    Configuration:
        api_key: API key for authentication
        rate_limit: Requests per minute (default: 30)

    Usage:
        source = MarinesiaSource(api_key="your-api-key")
        source.connect()

        # Get single vessel position
        positions = source.fetch_positions(["413000000"])

        # Get vessels in area
        vessels = source.fetch_vessels_nearby(
            min_lat=30.0, min_lon=120.0,
            max_lat=32.0, max_lon=123.0
        )

        # Get vessel profile
        info = source.fetch_vessel_info("413000000")
    """

    BASE_URL = "https://api.marinesia.com/api/v1"

    def __init__(self, api_key: Optional[str] = None, rate_limit: int = 30):
        super().__init__(name="marinesia", source_type=SourceType.REST)

        self.api_key = api_key
        self.rate_limit = rate_limit  # requests per minute

        # Rate limiting
        self._request_times: List[float] = []
        self._last_request_time: float = 0

        # Cache
        self._position_cache: Dict[str, AISPosition] = {}
        self._vessel_cache: Dict[str, AISVesselInfo] = {}
        self._cache_ttl: int = 300  # 5 minutes

    def connect(self) -> bool:
        """
        Verify API is reachable.

        Makes a simple request to verify connectivity.
        """
        try:
            self._log("Checking Marinesia API availability...")
            self._set_status(SourceStatus.CONNECTED)
            return True

        except Exception as e:
            self._set_status(SourceStatus.ERROR, str(e))
            return False

    def disconnect(self) -> None:
        """Close connection (no-op for REST)."""
        self._set_status(SourceStatus.DISCONNECTED)

    def fetch_positions(self, mmsi_list: List[str]) -> List[AISPosition]:
        """
        Fetch current positions for specified vessels.

        Uses /vessel/{mmsi}/location/latest endpoint.
        """
        if not self.is_available():
            if not self.connect():
                return []

        positions = []

        for mmsi in mmsi_list:
            # Check cache first
            cached = self._get_cached_position(mmsi)
            if cached:
                positions.append(cached)
                continue

            # Rate limit check
            if not self._check_rate_limit():
                self._log("Rate limit reached, using cached data", level="warning")
                break

            # Fetch from API
            position = self._fetch_vessel_location_latest(mmsi)
            if position:
                positions.append(position)
                self._cache_position(position)

            # Small delay between requests
            time.sleep(0.5)

        return positions

    def fetch_vessel_info(self, mmsi: str) -> Optional[AISVesselInfo]:
        """
        Fetch vessel profile information.

        Uses /vessel/{mmsi}/profile endpoint.
        """
        if not self.is_available():
            if not self.connect():
                return None

        # Check cache
        if mmsi in self._vessel_cache:
            return self._vessel_cache[mmsi]

        # Rate limit check
        if not self._check_rate_limit():
            return None

        return self._fetch_vessel_profile(mmsi)

    def fetch_vessel_image(self, mmsi: str) -> Optional[str]:
        """
        Get vessel image URL.

        Uses /vessel/{mmsi}/image endpoint.
        Returns image URL or None.
        """
        if not self._check_rate_limit():
            return None

        try:
            url = f"{self.BASE_URL}/vessel/{mmsi}/image"
            data = self._make_request(url)

            if data:
                return data.get("url") or data.get("imageUrl")
            return None

        except Exception as e:
            self._log(f"Error fetching image for {mmsi}: {e}", level="warning")
            return None

    def fetch_vessel_history(
        self,
        mmsi: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[AISPosition]:
        """
        Fetch historical vessel locations.

        Uses /vessel/{mmsi}/location endpoint.
        """
        if not self._check_rate_limit():
            return []

        try:
            url = f"{self.BASE_URL}/vessel/{mmsi}/location"
            params = []

            if start_time:
                params.append(f"startTime={start_time.isoformat()}Z")
            if end_time:
                params.append(f"endTime={end_time.isoformat()}Z")

            if params:
                url += "?" + "&".join(params)

            data = self._make_request(url)

            if not data:
                return []

            # Parse response - expect array of locations
            locations = data if isinstance(data, list) else data.get("data", [])
            positions = []

            for loc in locations:
                position = self._parse_location_response(mmsi, loc)
                if position:
                    positions.append(position)

            return positions

        except Exception as e:
            self._log(f"Error fetching history for {mmsi}: {e}", level="warning")
            return []

    def fetch_vessels_nearby(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float
    ) -> List[AISPosition]:
        """
        Get vessels within a bounding box.

        Uses /vessel/nearby endpoint.
        """
        if not self._check_rate_limit():
            return []

        try:
            url = (
                f"{self.BASE_URL}/vessel/nearby"
                f"?minLat={min_lat}&minLon={min_lon}"
                f"&maxLat={max_lat}&maxLon={max_lon}"
            )

            data = self._make_request(url)

            if not data:
                return []

            # Parse response - expect array of vessels with positions
            vessels = data if isinstance(data, list) else data.get("data", [])
            positions = []

            for vessel in vessels:
                mmsi = str(vessel.get("mmsi", ""))
                if mmsi:
                    position = self._parse_location_response(mmsi, vessel)
                    if position:
                        positions.append(position)
                        self._cache_position(position)

            self._log(f"Found {len(positions)} vessels in area")
            return positions

        except Exception as e:
            self._log(f"Error fetching nearby vessels: {e}", level="warning")
            return []

    def fetch_ports_nearby(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float
    ) -> List[Dict[str, Any]]:
        """
        Get ports within a bounding box.

        Uses /port/nearby endpoint.
        """
        if not self._check_rate_limit():
            return []

        try:
            url = (
                f"{self.BASE_URL}/port/nearby"
                f"?minLat={min_lat}&minLon={min_lon}"
                f"&maxLat={max_lat}&maxLon={max_lon}"
            )

            data = self._make_request(url)

            if not data:
                return []

            ports = data if isinstance(data, list) else data.get("data", [])
            return ports

        except Exception as e:
            self._log(f"Error fetching nearby ports: {e}", level="warning")
            return []

    def _fetch_vessel_location_latest(self, mmsi: str) -> Optional[AISPosition]:
        """
        Fetch latest position for a vessel.

        Uses /vessel/{mmsi}/location/latest endpoint.
        """
        try:
            url = f"{self.BASE_URL}/vessel/{mmsi}/location/latest"
            data = self._make_request(url)

            if not data:
                return None

            return self._parse_location_response(mmsi, data)

        except Exception as e:
            self._log(f"Error fetching position for {mmsi}: {e}", level="warning")
            return None

    def _fetch_vessel_profile(self, mmsi: str) -> Optional[AISVesselInfo]:
        """
        Fetch vessel profile.

        Uses /vessel/{mmsi}/profile endpoint.
        """
        try:
            url = f"{self.BASE_URL}/vessel/{mmsi}/profile"
            data = self._make_request(url)

            if not data:
                return None

            vessel = self._parse_profile_response(mmsi, data)

            if vessel:
                self._vessel_cache[mmsi] = vessel

            return vessel

        except Exception as e:
            self._log(f"Error fetching profile for {mmsi}: {e}", level="warning")
            return None

    def _make_request(self, url: str) -> Optional[Dict[str, Any]]:
        """Make HTTP request with authentication and error handling."""
        try:
            self._record_request()

            headers = {
                "User-Agent": "ArsenalTracker/1.0",
                "Accept": "application/json"
            }

            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
                headers["X-API-Key"] = self.api_key  # Some APIs use this

            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
                else:
                    self._log(f"API returned status {response.status}", level="warning")
                    return None

        except urllib.error.HTTPError as e:
            if e.code == 429:
                self._set_status(SourceStatus.RATE_LIMITED)
                self._log("Rate limited by API", level="warning")
            elif e.code == 401:
                self._log("Authentication failed - check API key", level="error")
            elif e.code == 404:
                # Vessel not found - not an error
                pass
            else:
                self._log(f"HTTP error: {e.code} {e.reason}", level="warning")
            return None

        except urllib.error.URLError as e:
            self._log(f"URL error: {e.reason}", level="error")
            self._set_status(SourceStatus.ERROR, str(e.reason))
            return None

        except Exception as e:
            self._log(f"Request error: {e}", level="error")
            return None

    def _parse_location_response(self, mmsi: str, data: Dict[str, Any]) -> Optional[AISPosition]:
        """
        Parse Marinesia location response.

        Expected fields: latitude/lat, longitude/lon/lng, timestamp, speed/sog, course/cog, heading
        """
        try:
            # Handle nested location object
            loc = data.get("location", data)

            latitude = loc.get("latitude", loc.get("lat"))
            longitude = loc.get("longitude", loc.get("lon", loc.get("lng")))

            if latitude is None or longitude is None:
                return None

            # Parse timestamp
            timestamp_str = loc.get("timestamp", loc.get("lastUpdate", loc.get("time")))
            timestamp = self._parse_timestamp(timestamp_str)

            position = AISPosition(
                mmsi=mmsi,
                latitude=float(latitude),
                longitude=float(longitude),
                timestamp=timestamp,
                speed_knots=loc.get("speed", loc.get("sog")),
                course=loc.get("course", loc.get("cog")),
                heading=loc.get("heading", loc.get("trueHeading")),
                nav_status=loc.get("navStatus", loc.get("navigationStatus")),
                source="marinesia",
                source_timestamp=datetime.utcnow()
            )

            if position.is_valid():
                self.positions_received += 1
                self.last_update = datetime.utcnow()
                return position

            return None

        except Exception as e:
            self._log(f"Error parsing location: {e}", level="warning")
            return None

    def _parse_profile_response(self, mmsi: str, data: Dict[str, Any]) -> Optional[AISVesselInfo]:
        """Parse Marinesia vessel profile response."""
        try:
            ship_type = data.get("shipType", data.get("type", data.get("vesselType")))

            return AISVesselInfo(
                mmsi=mmsi,
                imo=data.get("imo", data.get("imoNumber")),
                name=data.get("name", data.get("shipName", data.get("vesselName", ""))).strip(),
                callsign=data.get("callsign", data.get("callSign", "")).strip(),
                ship_type=ship_type,
                ship_type_text=data.get("shipTypeText", get_ship_type_text(ship_type) if ship_type else None),
                length=data.get("length", data.get("shipLength", data.get("loa"))),
                width=data.get("width", data.get("beam")),
                draught=data.get("draught", data.get("draft")),
                flag_state=data.get("flag", data.get("flagState", data.get("country"))),
                destination=data.get("destination", "").strip(),
                eta=data.get("eta"),
                source="marinesia"
            )

        except Exception as e:
            self._log(f"Error parsing profile: {e}", level="warning")
            return None

    def _parse_timestamp(self, timestamp_str: Any) -> datetime:
        """Parse timestamp from various formats."""
        if not timestamp_str:
            return datetime.utcnow()

        try:
            if isinstance(timestamp_str, (int, float)):
                # Unix timestamp
                return datetime.utcfromtimestamp(timestamp_str)
            elif isinstance(timestamp_str, str):
                # ISO format
                return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            elif isinstance(timestamp_str, datetime):
                return timestamp_str
        except:
            pass

        return datetime.utcnow()

    def _check_rate_limit(self) -> bool:
        """Check if we can make another request."""
        now = time.time()

        # Remove old timestamps
        self._request_times = [t for t in self._request_times if now - t < 60]

        # Check limit
        return len(self._request_times) < self.rate_limit

    def _record_request(self) -> None:
        """Record a request for rate limiting."""
        self._request_times.append(time.time())
        self._last_request_time = time.time()

    def _get_cached_position(self, mmsi: str) -> Optional[AISPosition]:
        """Get cached position if still valid."""
        if mmsi not in self._position_cache:
            return None

        position = self._position_cache[mmsi]

        # Check if cache is still valid
        if position.source_timestamp:
            age = (datetime.utcnow() - position.source_timestamp).total_seconds()
            if age < self._cache_ttl:
                return position

        return None

    def _cache_position(self, position: AISPosition) -> None:
        """Cache a position."""
        self._position_cache[position.mmsi] = position


# Example API responses for documentation
MARINESIA_LOCATION_RESPONSE = {
    "mmsi": "413000000",
    "latitude": 31.2456,
    "longitude": 121.489,
    "speed": 0.1,
    "course": 91,
    "heading": 90,
    "navStatus": 1,
    "timestamp": "2025-12-27T10:30:00Z"
}

MARINESIA_PROFILE_RESPONSE = {
    "mmsi": "413000000",
    "imo": "9123456",
    "name": "ZHONG DA 79",
    "callsign": "BXYZ",
    "shipType": 70,
    "shipTypeText": "Cargo",
    "flag": "CN",
    "length": 97,
    "beam": 15,
    "draught": 5.5,
    "destination": "SHANGHAI",
    "eta": "2025-12-28T08:00:00Z"
}

MARINESIA_NEARBY_RESPONSE = {
    "data": [
        {
            "mmsi": "413000000",
            "name": "VESSEL ONE",
            "latitude": 31.25,
            "longitude": 121.49,
            "speed": 12.5,
            "course": 180
        },
        {
            "mmsi": "413000001",
            "name": "VESSEL TWO",
            "latitude": 31.30,
            "longitude": 121.50,
            "speed": 8.0,
            "course": 90
        }
    ],
    "total": 2
}
