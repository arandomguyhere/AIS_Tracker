"""
Global Fishing Watch API Client

Behavioral enrichment data for vessel tracking.
https://globalfishingwatch.org/our-apis/

Features:
- Vessel event history (loitering, port visits, encounters)
- Fishing activity detection
- Track data for specific vessels
- AIS gap detection

This is an ENRICHMENT source - it supplements position data
with behavioral analysis, not real-time positions.

API Requirements:
- Free API key required (register at GFW portal)
- Rate limits apply (check current tier)
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from .base import (
    AISSource, AISPosition, AISVesselInfo, AISEvent,
    SourceType, SourceStatus
)


class GlobalFishingWatchSource(AISSource):
    """
    Global Fishing Watch API client.

    Enrichment source for behavioral events. Does NOT provide
    real-time positions - use for historical analysis and
    behavioral pattern detection.

    Configuration:
        api_key: GFW API key (required)
        rate_limit: Requests per minute (default: 10)

    Usage:
        source = GlobalFishingWatchSource(api_key="your-key")
        source.connect()

        # Get behavioral events for a vessel
        events = source.fetch_events("413000000", days=30)

        # Get fishing hours (for fishing vessels)
        fishing = source.fetch_fishing_activity("413000000")
    """

    BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"

    # Event types returned by GFW
    EVENT_TYPES = {
        "loitering": "loitering",
        "port_visit": "port_visit",
        "encounter": "encounter",
        "fishing": "fishing",
        "gap": "ais_gap"
    }

    def __init__(self, api_key: str, rate_limit: int = 10):
        super().__init__(name="gfw", source_type=SourceType.ENRICHMENT)

        self.api_key = api_key
        self.rate_limit = rate_limit

        # Rate limiting
        self._request_times: List[float] = []

        # Cache for events
        self._event_cache: Dict[str, List[AISEvent]] = {}
        self._cache_ttl: int = 3600  # 1 hour

        # Vessel ID mapping (MMSI -> GFW vessel ID)
        self._vessel_id_cache: Dict[str, str] = {}

    def connect(self) -> bool:
        """
        Verify API key and connection.

        GFW requires authentication for all endpoints.
        """
        if not self.api_key:
            self._set_status(SourceStatus.ERROR, "API key required")
            return False

        try:
            # Test API access with a simple request
            self._log("Verifying GFW API access...")

            # Try to access the vessels endpoint
            # This validates the API key
            url = f"{self.BASE_URL}/vessels?limit=1"
            result = self._make_request(url)

            if result is not None:
                self._set_status(SourceStatus.CONNECTED)
                return True
            else:
                self._set_status(SourceStatus.ERROR, "API verification failed")
                return False

        except Exception as e:
            self._set_status(SourceStatus.ERROR, str(e))
            return False

    def disconnect(self) -> None:
        """Close connection (no-op for REST)."""
        self._set_status(SourceStatus.DISCONNECTED)

    def fetch_positions(self, mmsi_list: List[str]) -> List[AISPosition]:
        """
        GFW does not provide real-time positions.

        This method returns empty list - use fetch_events() for behavioral data.
        For real-time positions, use AISStream or Marinesia.
        """
        self._log("GFW is enrichment-only, use fetch_events() for behavioral data", level="warning")
        return []

    def fetch_events(self, mmsi: str, days: int = 30) -> List[AISEvent]:
        """
        Fetch behavioral events for a vessel.

        Args:
            mmsi: Vessel MMSI number
            days: How many days of history to fetch (default: 30)

        Returns:
            List of AISEvent objects (loitering, port visits, encounters)
        """
        if not self.is_available():
            if not self.connect():
                return []

        # Check cache
        cache_key = f"{mmsi}_{days}"
        cached = self._get_cached_events(cache_key)
        if cached:
            return cached

        # Rate limit check
        if not self._check_rate_limit():
            self._log("Rate limit reached", level="warning")
            return []

        # First, we need to find the GFW vessel ID from MMSI
        vessel_id = self._get_vessel_id(mmsi)
        if not vessel_id:
            self._log(f"Could not find GFW vessel ID for MMSI {mmsi}", level="warning")
            return []

        # Fetch events
        events = self._fetch_vessel_events(vessel_id, mmsi, days)

        # Cache results
        if events:
            self._event_cache[cache_key] = (datetime.utcnow(), events)

        return events

    def fetch_vessel_info(self, mmsi: str) -> Optional[AISVesselInfo]:
        """Fetch vessel information from GFW."""
        if not self.is_available():
            if not self.connect():
                return None

        if not self._check_rate_limit():
            return None

        return self._fetch_vessel_details(mmsi)

    def fetch_fishing_activity(self, mmsi: str, days: int = 90) -> Dict[str, Any]:
        """
        Fetch fishing activity summary for a vessel.

        Returns fishing hours, apparent fishing events, and
        activity by region (for fishing vessels).
        """
        if not self.is_available():
            if not self.connect():
                return {}

        if not self._check_rate_limit():
            return {}

        vessel_id = self._get_vessel_id(mmsi)
        if not vessel_id:
            return {}

        return self._fetch_fishing_data(vessel_id, days)

    def _get_vessel_id(self, mmsi: str) -> Optional[str]:
        """
        Look up GFW vessel ID from MMSI.

        GFW uses internal vessel IDs, not MMSI directly.
        """
        # Check cache
        if mmsi in self._vessel_id_cache:
            return self._vessel_id_cache[mmsi]

        try:
            # Search for vessel by MMSI
            url = f"{self.BASE_URL}/vessels/search?query={mmsi}&datasets=public-global-vessel-identity:latest"
            data = self._make_request(url)

            if not data or "entries" not in data:
                return None

            entries = data.get("entries", [])
            if not entries:
                return None

            # Find matching vessel
            for entry in entries:
                # Check if MMSI matches in any of the vessel's identities
                ssvid = entry.get("ssvid", "")
                if ssvid == mmsi:
                    vessel_id = entry.get("id")
                    if vessel_id:
                        self._vessel_id_cache[mmsi] = vessel_id
                        return vessel_id

            return None

        except Exception as e:
            self._log(f"Error looking up vessel ID: {e}", level="warning")
            return None

    def _fetch_vessel_events(self, vessel_id: str, mmsi: str, days: int) -> List[AISEvent]:
        """Fetch events for a specific vessel from GFW."""
        events = []

        try:
            # Calculate date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Format dates for API
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")

            # Fetch events endpoint
            url = (
                f"{self.BASE_URL}/events?"
                f"vessels[]={vessel_id}&"
                f"start-date={start_str}&"
                f"end-date={end_str}&"
                f"datasets[]=public-global-loitering-events:latest&"
                f"datasets[]=public-global-port-visits-c2-events:latest&"
                f"datasets[]=public-global-encounters-events:latest"
            )

            data = self._make_request(url)

            if not data or "entries" not in data:
                return events

            # Parse each event
            for entry in data.get("entries", []):
                event = self._parse_event(entry, mmsi)
                if event:
                    events.append(event)

            self._log(f"Fetched {len(events)} events for vessel {mmsi}")
            return events

        except Exception as e:
            self._log(f"Error fetching events: {e}", level="error")
            return events

    def _parse_event(self, data: Dict[str, Any], mmsi: str) -> Optional[AISEvent]:
        """Parse GFW event into AISEvent."""
        try:
            event_type = data.get("type", "unknown")

            # Map GFW event type to our internal type
            normalized_type = self.EVENT_TYPES.get(event_type, event_type)

            # Parse timestamps
            start_str = data.get("start")
            end_str = data.get("end")

            start_time = self._parse_timestamp(start_str)
            end_time = self._parse_timestamp(end_str) if end_str else None

            if not start_time:
                return None

            # Extract position (may be in different formats)
            position = data.get("position", {})
            lat = position.get("lat") or data.get("lat")
            lon = position.get("lon") or data.get("lon")

            # Build details dict
            details = {
                "gfw_event_id": data.get("id"),
                "duration_hours": data.get("durationHours"),
                "vessel_id": data.get("vessel", {}).get("id")
            }

            # Add event-specific details
            if event_type == "loitering":
                details["total_distance_km"] = data.get("loitering", {}).get("totalDistanceKm")
                details["average_speed_knots"] = data.get("loitering", {}).get("averageSpeedKnots")

            elif event_type == "port_visit":
                port_info = data.get("portVisit", {})
                details["port_name"] = port_info.get("visit", {}).get("anchorage", {}).get("name")
                details["port_flag"] = port_info.get("visit", {}).get("anchorage", {}).get("flag")
                details["confidence"] = port_info.get("confidence")

            elif event_type == "encounter":
                encounter_info = data.get("encounter", {})
                details["encountered_vessel_id"] = encounter_info.get("vessel", {}).get("id")
                details["encountered_vessel_name"] = encounter_info.get("vessel", {}).get("name")
                details["median_distance_km"] = encounter_info.get("medianDistanceKilometers")

            # Calculate confidence (GFW provides confidence for some events)
            confidence = data.get("confidence") or details.get("confidence") or 0.7

            return AISEvent(
                mmsi=mmsi,
                event_type=normalized_type,
                start_time=start_time,
                end_time=end_time,
                latitude=lat,
                longitude=lon,
                confidence=float(confidence) if confidence else 0.7,
                details=details,
                source="gfw"
            )

        except Exception as e:
            self._log(f"Error parsing event: {e}", level="warning")
            return None

    def _fetch_vessel_details(self, mmsi: str) -> Optional[AISVesselInfo]:
        """Fetch vessel details from GFW."""
        try:
            # Search for vessel
            url = f"{self.BASE_URL}/vessels/search?query={mmsi}&datasets=public-global-vessel-identity:latest"
            data = self._make_request(url)

            if not data or "entries" not in data:
                return None

            entries = data.get("entries", [])
            if not entries:
                return None

            # Find matching vessel
            for entry in entries:
                if entry.get("ssvid") == mmsi:
                    return self._parse_vessel_info(entry, mmsi)

            return None

        except Exception as e:
            self._log(f"Error fetching vessel details: {e}", level="warning")
            return None

    def _parse_vessel_info(self, data: Dict[str, Any], mmsi: str) -> AISVesselInfo:
        """Parse GFW vessel data into AISVesselInfo."""
        # GFW has rich vessel registry data
        registry = data.get("registryInfo", [{}])[0] if data.get("registryInfo") else {}

        return AISVesselInfo(
            mmsi=mmsi,
            imo=registry.get("imoNumber") or data.get("imo"),
            name=data.get("shipname") or registry.get("shipname", "").strip(),
            callsign=registry.get("callsign", "").strip(),
            ship_type=None,  # GFW uses text types
            ship_type_text=data.get("vesselType") or registry.get("vesselType"),
            length=registry.get("lengthM"),
            width=None,  # GFW doesn't typically provide width
            flag_state=data.get("flag") or registry.get("flag"),
            source="gfw"
        )

    def _fetch_fishing_data(self, vessel_id: str, days: int) -> Dict[str, Any]:
        """Fetch fishing activity data for a vessel."""
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # This endpoint may require additional permissions
            url = (
                f"{self.BASE_URL}/vessels/{vessel_id}/activity?"
                f"start-date={start_date.strftime('%Y-%m-%d')}&"
                f"end-date={end_date.strftime('%Y-%m-%d')}"
            )

            data = self._make_request(url)

            if not data:
                return {}

            return {
                "fishing_hours": data.get("fishingHours", 0),
                "presence_hours": data.get("presenceHours", 0),
                "activity_by_date": data.get("activityByDate", []),
                "source": "gfw"
            }

        except Exception as e:
            self._log(f"Error fetching fishing data: {e}", level="warning")
            return {}

    def _make_request(self, url: str) -> Optional[Dict[str, Any]]:
        """Make authenticated HTTP request to GFW API."""
        try:
            self._record_request()

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "ArsenalTracker/1.0",
                "Accept": "application/json"
            }

            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
                else:
                    self._log(f"API returned status {response.status}", level="warning")
                    return None

        except urllib.error.HTTPError as e:
            if e.code == 401:
                self._set_status(SourceStatus.ERROR, "Invalid API key")
                self._log("Authentication failed - check API key", level="error")
            elif e.code == 429:
                self._set_status(SourceStatus.RATE_LIMITED)
                self._log("Rate limited by GFW API", level="warning")
            elif e.code == 403:
                self._log("Access forbidden - may need additional API permissions", level="warning")
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

    def _parse_timestamp(self, ts_str: str) -> Optional[datetime]:
        """Parse ISO timestamp string."""
        if not ts_str:
            return None

        try:
            # Handle various ISO formats
            ts_str = ts_str.replace("Z", "+00:00")
            return datetime.fromisoformat(ts_str)
        except:
            try:
                # Try parsing as Unix timestamp
                return datetime.utcfromtimestamp(float(ts_str))
            except:
                return None

    def _check_rate_limit(self) -> bool:
        """Check if we can make another request."""
        now = time.time()
        self._request_times = [t for t in self._request_times if now - t < 60]
        return len(self._request_times) < self.rate_limit

    def _record_request(self) -> None:
        """Record a request for rate limiting."""
        self._request_times.append(time.time())

    def _get_cached_events(self, cache_key: str) -> Optional[List[AISEvent]]:
        """Get cached events if still valid."""
        if cache_key not in self._event_cache:
            return None

        cached_time, events = self._event_cache[cache_key]
        age = (datetime.utcnow() - cached_time).total_seconds()

        if age < self._cache_ttl:
            return events

        return None


# Example response formats for documentation
GFW_LOITERING_EVENT_EXAMPLE = {
    "id": "abc123",
    "type": "loitering",
    "start": "2025-12-20T10:00:00Z",
    "end": "2025-12-20T18:30:00Z",
    "position": {
        "lat": 31.2456,
        "lon": 121.489
    },
    "vessel": {
        "id": "vessel-id-123",
        "ssvid": "413000000",
        "name": "ZHONG DA 79"
    },
    "loitering": {
        "totalDistanceKm": 15.2,
        "averageSpeedKnots": 0.8
    },
    "durationHours": 8.5
}

GFW_NORMALIZED_EVENT = {
    "mmsi": "413000000",
    "event_type": "loitering",
    "start_time": "2025-12-20T10:00:00+00:00",
    "end_time": "2025-12-20T18:30:00+00:00",
    "latitude": 31.2456,
    "longitude": 121.489,
    "confidence": 0.7,
    "details": {
        "gfw_event_id": "abc123",
        "duration_hours": 8.5,
        "total_distance_km": 15.2,
        "average_speed_knots": 0.8
    },
    "source": "gfw"
}
