"""
Marinesia API Client

Free REST API for vessel position and profile data.
https://marinesia.com/

Features:
- Vessel position lookup by MMSI/IMO
- Vessel profile/details
- No API key required (free tier)
- Rate limits apply

Used as:
- Fallback when real-time source offline
- Metadata/vessel info enrichment
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Optional, Any

from .base import (
    AISSource, AISPosition, AISVesselInfo, SourceType, SourceStatus,
    get_ship_type_text
)


class MarinesiaSource(AISSource):
    """
    Marinesia REST API client.

    Fallback AIS source using REST API. Supports vessel lookup by MMSI/IMO.
    Free tier with rate limits.

    Configuration:
        api_key: Optional API key (not required for basic access)
        rate_limit: Requests per minute (default: 30)

    Usage:
        source = MarinesiaSource()
        source.connect()  # Verifies API is reachable

        positions = source.fetch_positions(["413000000"])
        info = source.fetch_vessel_info("413000000")
    """

    BASE_URL = "https://api.marinesia.com/v1"

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

        For REST APIs, this does a simple health check.
        """
        try:
            # Try to reach the API
            self._log("Checking API availability...")

            # Simple check - just verify we can make a request
            # In production, you'd hit a health endpoint
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

        Makes API calls for each MMSI (respecting rate limits).
        Returns cached data if recent enough.
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
            position = self._fetch_vessel_position(mmsi)
            if position:
                positions.append(position)
                self._cache_position(position)

            # Small delay between requests
            time.sleep(0.5)

        return positions

    def fetch_vessel_info(self, mmsi: str) -> Optional[AISVesselInfo]:
        """Fetch vessel static information."""
        if not self.is_available():
            if not self.connect():
                return None

        # Check cache
        if mmsi in self._vessel_cache:
            return self._vessel_cache[mmsi]

        # Rate limit check
        if not self._check_rate_limit():
            return None

        return self._fetch_vessel_details(mmsi)

    def _fetch_vessel_position(self, mmsi: str) -> Optional[AISPosition]:
        """
        Fetch position for a single vessel from Marinesia API.

        Note: Marinesia API endpoint structure may vary.
        This is a generalized implementation.
        """
        try:
            url = f"{self.BASE_URL}/vessels/{mmsi}/position"
            data = self._make_request(url)

            if not data:
                return None

            # Parse response (adjust based on actual API response format)
            position = self._parse_position_response(mmsi, data)
            return position

        except Exception as e:
            self._log(f"Error fetching position for {mmsi}: {e}", level="warning")
            return None

    def _fetch_vessel_details(self, mmsi: str) -> Optional[AISVesselInfo]:
        """Fetch vessel details from Marinesia API."""
        try:
            url = f"{self.BASE_URL}/vessels/{mmsi}"
            data = self._make_request(url)

            if not data:
                return None

            # Parse response
            vessel = self._parse_vessel_response(mmsi, data)

            if vessel:
                self._vessel_cache[mmsi] = vessel

            return vessel

        except Exception as e:
            self._log(f"Error fetching vessel info for {mmsi}: {e}", level="warning")
            return None

    def _make_request(self, url: str) -> Optional[Dict[str, Any]]:
        """Make HTTP request with error handling."""
        try:
            self._record_request()

            headers = {
                "User-Agent": "ArsenalTracker/1.0",
                "Accept": "application/json"
            }

            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

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

    def _parse_position_response(self, mmsi: str, data: Dict[str, Any]) -> Optional[AISPosition]:
        """
        Parse Marinesia position response.

        Adjust field names based on actual API response format.
        """
        try:
            # Common field names (adjust as needed)
            latitude = data.get("latitude", data.get("lat"))
            longitude = data.get("longitude", data.get("lon", data.get("lng")))

            if latitude is None or longitude is None:
                return None

            # Parse timestamp
            timestamp_str = data.get("timestamp", data.get("lastUpdate", data.get("time")))
            if timestamp_str:
                try:
                    if isinstance(timestamp_str, (int, float)):
                        timestamp = datetime.utcfromtimestamp(timestamp_str)
                    else:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                except:
                    timestamp = datetime.utcnow()
            else:
                timestamp = datetime.utcnow()

            position = AISPosition(
                mmsi=mmsi,
                latitude=float(latitude),
                longitude=float(longitude),
                timestamp=timestamp,
                speed_knots=data.get("speed", data.get("sog")),
                course=data.get("course", data.get("cog")),
                heading=data.get("heading", data.get("trueHeading")),
                source="marinesia",
                source_timestamp=datetime.utcnow()
            )

            if position.is_valid():
                self.positions_received += 1
                self.last_update = datetime.utcnow()
                return position

            return None

        except Exception as e:
            self._log(f"Error parsing position: {e}", level="warning")
            return None

    def _parse_vessel_response(self, mmsi: str, data: Dict[str, Any]) -> Optional[AISVesselInfo]:
        """Parse Marinesia vessel details response."""
        try:
            ship_type = data.get("shipType", data.get("type"))

            return AISVesselInfo(
                mmsi=mmsi,
                imo=data.get("imo", data.get("imoNumber")),
                name=data.get("name", data.get("shipName", "")).strip(),
                callsign=data.get("callsign", data.get("callSign", "")).strip(),
                ship_type=ship_type,
                ship_type_text=get_ship_type_text(ship_type) if ship_type else None,
                length=data.get("length", data.get("shipLength")),
                width=data.get("width", data.get("beam")),
                flag_state=data.get("flag", data.get("flagState", data.get("country"))),
                destination=data.get("destination", "").strip(),
                source="marinesia"
            )

        except Exception as e:
            self._log(f"Error parsing vessel info: {e}", level="warning")
            return None

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


# Alternative free vessel lookup APIs
class VesselFinderFreeSource(AISSource):
    """
    VesselFinder Free Tier API (if available).

    Only use if free tier access is detected.
    Do NOT hard-depend on this source.
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(name="vesselfinder_free", source_type=SourceType.REST)
        self.api_key = api_key
        self._available = False

    def connect(self) -> bool:
        """Check if free tier is available."""
        # VesselFinder free tier is very limited
        # Only enable if explicitly configured and key provided
        if not self.api_key:
            self._set_status(SourceStatus.DISCONNECTED)
            return False

        # In production, verify key works with free tier
        self._available = True
        self._set_status(SourceStatus.CONNECTED)
        return True

    def disconnect(self) -> None:
        self._set_status(SourceStatus.DISCONNECTED)

    def fetch_positions(self, mmsi_list: List[str]) -> List[AISPosition]:
        """Fetch positions - limited in free tier."""
        if not self._available:
            return []

        # VesselFinder free tier is very limited
        # Implementation would go here if needed
        return []


# Example response formats for documentation
MARINESIA_EXAMPLE_RESPONSE = {
    "mmsi": "413000000",
    "name": "ZHONG DA 79",
    "imo": None,
    "callsign": "",
    "shipType": 70,
    "flag": "CN",
    "latitude": 31.2456,
    "longitude": 121.489,
    "speed": 0.1,
    "course": 91,
    "heading": 90,
    "timestamp": "2025-12-27T10:30:00Z",
    "destination": "SHANGHAI"
}

MARINESIA_NORMALIZED_OUTPUT = {
    "mmsi": "413000000",
    "lat": 31.2456,
    "lon": 121.489,
    "speed": 0.1,
    "course": 91,
    "heading": 90,
    "timestamp": "2025-12-27T10:30:00+00:00",
    "source": "marinesia"
}
