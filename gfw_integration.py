#!/usr/bin/env python3
"""
Global Fishing Watch API Integration

Provides access to GFW's free vessel tracking data:
- Vessel events (loitering, encounters, port visits, AIS gaps)
- SAR vessel detections
- Vessel identity search
- Fishing activity data

Registration: https://globalfishingwatch.org/our-apis/
API Docs: https://globalfishingwatch.org/our-apis/documentation

Free for non-commercial use.
"""

import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


# GFW API Configuration
GFW_API_BASE = "https://gateway.api.globalfishingwatch.org/v3"
GFW_TOKEN = os.environ.get("GFW_API_TOKEN", "")

# Check for token in config file if not in env
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'gfw_config.json')
if not GFW_TOKEN and os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
            GFW_TOKEN = config.get('api_token', '')
    except:
        pass


class EventType(Enum):
    """GFW event types."""
    ENCOUNTER = "encounter"      # Ship-to-ship meeting
    LOITERING = "loitering"      # Extended time in area
    PORT_VISIT = "port_visit"    # Port call
    GAP = "gap"                  # AIS signal gap
    FISHING = "fishing"          # Fishing activity


@dataclass
class GFWEvent:
    """Event from Global Fishing Watch API."""
    id: str
    event_type: str
    start: datetime
    end: Optional[datetime]
    lat: float
    lon: float
    vessel_id: str
    vessel_name: Optional[str] = None
    vessel_mmsi: Optional[str] = None
    vessel_flag: Optional[str] = None
    # Event-specific fields
    duration_hours: Optional[float] = None
    distance_km: Optional[float] = None
    # For encounters
    encountered_vessel_id: Optional[str] = None
    encountered_vessel_name: Optional[str] = None
    encountered_vessel_mmsi: Optional[str] = None
    # For port visits
    port_name: Optional[str] = None
    port_country: Optional[str] = None
    # Raw data
    raw: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'event_type': self.event_type,
            'start': self.start.isoformat() if self.start else None,
            'end': self.end.isoformat() if self.end else None,
            'lat': self.lat,
            'lon': self.lon,
            'vessel_id': self.vessel_id,
            'vessel_name': self.vessel_name,
            'vessel_mmsi': self.vessel_mmsi,
            'vessel_flag': self.vessel_flag,
            'duration_hours': self.duration_hours,
            'distance_km': self.distance_km,
            'encountered_vessel_id': self.encountered_vessel_id,
            'encountered_vessel_name': self.encountered_vessel_name,
            'encountered_vessel_mmsi': self.encountered_vessel_mmsi,
            'port_name': self.port_name,
            'port_country': self.port_country
        }


@dataclass
class GFWVessel:
    """Vessel identity from Global Fishing Watch."""
    id: str
    mmsi: Optional[str] = None
    imo: Optional[str] = None
    name: Optional[str] = None
    flag: Optional[str] = None
    vessel_type: Optional[str] = None
    length_m: Optional[float] = None
    tonnage_gt: Optional[float] = None
    owner: Optional[str] = None
    operator: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    raw: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'mmsi': self.mmsi,
            'imo': self.imo,
            'name': self.name,
            'flag': self.flag,
            'vessel_type': self.vessel_type,
            'length_m': self.length_m,
            'tonnage_gt': self.tonnage_gt,
            'owner': self.owner,
            'operator': self.operator,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None
        }


@dataclass
class SARDetection:
    """SAR vessel detection from Global Fishing Watch."""
    id: str
    timestamp: datetime
    lat: float
    lon: float
    length_m: Optional[float] = None
    matched_mmsi: Optional[str] = None
    matched_vessel_name: Optional[str] = None
    is_dark: bool = False  # No AIS match
    confidence: float = 0.0
    source: str = "sentinel-1"

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'lat': self.lat,
            'lon': self.lon,
            'length_m': self.length_m,
            'matched_mmsi': self.matched_mmsi,
            'matched_vessel_name': self.matched_vessel_name,
            'is_dark': self.is_dark,
            'confidence': self.confidence,
            'source': self.source
        }


class GFWClient:
    """Global Fishing Watch API client."""

    def __init__(self, token: str = None):
        self.token = token or GFW_TOKEN
        self.base_url = GFW_API_BASE

    def _request(self, endpoint: str, params: dict = None) -> dict:
        """Make authenticated API request."""
        if not self.token:
            return {'error': 'No GFW API token configured. Get one at https://globalfishingwatch.org/our-apis/'}

        url = f"{self.base_url}{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            return {'error': f'API error {e.code}: {error_body}'}
        except urllib.error.URLError as e:
            return {'error': f'Network error: {str(e)}'}
        except Exception as e:
            return {'error': f'Request failed: {str(e)}'}

    def _post(self, endpoint: str, data: dict) -> dict:
        """Make authenticated POST request."""
        if not self.token:
            return {'error': 'No GFW API token configured'}

        url = f"{self.base_url}{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers=headers,
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            return {'error': f'API error {e.code}: {error_body}'}
        except Exception as e:
            return {'error': f'Request failed: {str(e)}'}

    def search_vessel(self, query: str = None, mmsi: str = None,
                     imo: str = None, name: str = None) -> List[GFWVessel]:
        """
        Search for vessels by MMSI, IMO, or name.

        Returns list of matching vessels with identity info.
        """
        # Build search query
        search_query = query
        if mmsi:
            search_query = f"mmsi:{mmsi}"
        elif imo:
            search_query = f"imo:{imo}"
        elif name:
            search_query = name

        if not search_query:
            return []

        params = {
            'query': search_query,
            'datasets': 'public-global-vessel-identity:latest',
            'limit': 10
        }

        result = self._request('/vessels/search', params)

        if 'error' in result:
            print(f"GFW search error: {result['error']}")
            return []

        vessels = []
        for entry in result.get('entries', []):
            # Parse vessel data
            registry = entry.get('registryInfo', [{}])[0] if entry.get('registryInfo') else {}
            combined = entry.get('combinedSourcesInfo', [{}])[0] if entry.get('combinedSourcesInfo') else {}

            vessels.append(GFWVessel(
                id=entry.get('id', ''),
                mmsi=entry.get('ssvid'),
                imo=registry.get('imoNumber') or combined.get('imoNumber'),
                name=registry.get('shipname') or combined.get('shipname'),
                flag=registry.get('flag') or combined.get('flag'),
                vessel_type=combined.get('shiptypes', [None])[0] if combined.get('shiptypes') else None,
                length_m=combined.get('lengthM'),
                tonnage_gt=combined.get('tonnageGt'),
                owner=registry.get('owner'),
                raw=entry
            ))

        return vessels

    def get_vessel_events(self, vessel_id: str = None, mmsi: str = None,
                         event_types: List[str] = None,
                         start_date: datetime = None,
                         end_date: datetime = None,
                         limit: int = 100) -> List[GFWEvent]:
        """
        Get events for a vessel.

        Event types: encounter, loitering, port_visit, gap, fishing
        """
        # Default to last 90 days
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=90)

        # If MMSI provided, search for vessel ID first
        if mmsi and not vessel_id:
            vessels = self.search_vessel(mmsi=mmsi)
            if vessels:
                vessel_id = vessels[0].id
            else:
                return []

        if not vessel_id:
            return []

        # Default event types
        if not event_types:
            event_types = ['encounter', 'loitering', 'port_visit', 'gap']

        params = {
            'vessels': vessel_id,
            'datasets': ','.join([f'public-global-{et}-events:latest' for et in event_types]),
            'start-date': start_date.strftime('%Y-%m-%d'),
            'end-date': end_date.strftime('%Y-%m-%d'),
            'limit': limit
        }

        result = self._request('/events', params)

        if 'error' in result:
            print(f"GFW events error: {result['error']}")
            return []

        events = []
        for entry in result.get('entries', []):
            # Parse event
            start_str = entry.get('start')
            end_str = entry.get('end')

            start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00')) if start_str else None
            end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00')) if end_str else None

            position = entry.get('position', {})

            # Get encounter info if present
            encounter = entry.get('encounter', {})
            encountered_vessel = encounter.get('vessel', {})

            # Get port info if present
            port = entry.get('port', {})

            events.append(GFWEvent(
                id=entry.get('id', ''),
                event_type=entry.get('type', 'unknown'),
                start=start_dt,
                end=end_dt,
                lat=position.get('lat', 0),
                lon=position.get('lon', 0),
                vessel_id=vessel_id,
                vessel_mmsi=mmsi,
                duration_hours=entry.get('durationHours'),
                distance_km=entry.get('distanceKm'),
                encountered_vessel_id=encountered_vessel.get('id'),
                encountered_vessel_name=encountered_vessel.get('name'),
                encountered_vessel_mmsi=encountered_vessel.get('ssvid'),
                port_name=port.get('name'),
                port_country=port.get('flag'),
                raw=entry
            ))

        return events

    def get_ais_gaps(self, mmsi: str = None, vessel_id: str = None,
                    start_date: datetime = None, end_date: datetime = None) -> List[GFWEvent]:
        """Get AIS gap events for a vessel."""
        return self.get_vessel_events(
            vessel_id=vessel_id,
            mmsi=mmsi,
            event_types=['gap'],
            start_date=start_date,
            end_date=end_date
        )

    def get_encounters(self, mmsi: str = None, vessel_id: str = None,
                      start_date: datetime = None, end_date: datetime = None) -> List[GFWEvent]:
        """Get encounter (STS) events for a vessel."""
        return self.get_vessel_events(
            vessel_id=vessel_id,
            mmsi=mmsi,
            event_types=['encounter'],
            start_date=start_date,
            end_date=end_date
        )

    def get_loitering(self, mmsi: str = None, vessel_id: str = None,
                     start_date: datetime = None, end_date: datetime = None) -> List[GFWEvent]:
        """Get loitering events for a vessel."""
        return self.get_vessel_events(
            vessel_id=vessel_id,
            mmsi=mmsi,
            event_types=['loitering'],
            start_date=start_date,
            end_date=end_date
        )

    def get_port_visits(self, mmsi: str = None, vessel_id: str = None,
                       start_date: datetime = None, end_date: datetime = None) -> List[GFWEvent]:
        """Get port visit events for a vessel."""
        return self.get_vessel_events(
            vessel_id=vessel_id,
            mmsi=mmsi,
            event_types=['port_visit'],
            start_date=start_date,
            end_date=end_date
        )

    def get_area_activity(self, min_lat: float, min_lon: float,
                         max_lat: float, max_lon: float,
                         start_date: datetime = None,
                         end_date: datetime = None,
                         event_types: List[str] = None) -> List[GFWEvent]:
        """
        Get all events in a geographic area.

        Useful for monitoring zones like STS hotspots.
        """
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        if not event_types:
            event_types = ['encounter', 'loitering']

        # Use geometry filter
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat]
            ]]
        }

        params = {
            'datasets': ','.join([f'public-global-{et}-events:latest' for et in event_types]),
            'start-date': start_date.strftime('%Y-%m-%d'),
            'end-date': end_date.strftime('%Y-%m-%d'),
            'limit': 100
        }

        # Add geometry as query param
        params['geometry'] = json.dumps(geometry)

        result = self._request('/events', params)

        if 'error' in result:
            return []

        events = []
        for entry in result.get('entries', []):
            start_str = entry.get('start')
            end_str = entry.get('end')
            position = entry.get('position', {})

            events.append(GFWEvent(
                id=entry.get('id', ''),
                event_type=entry.get('type', 'unknown'),
                start=datetime.fromisoformat(start_str.replace('Z', '+00:00')) if start_str else None,
                end=datetime.fromisoformat(end_str.replace('Z', '+00:00')) if end_str else None,
                lat=position.get('lat', 0),
                lon=position.get('lon', 0),
                vessel_id=entry.get('vessel', {}).get('id', ''),
                vessel_name=entry.get('vessel', {}).get('name'),
                vessel_mmsi=entry.get('vessel', {}).get('ssvid'),
                duration_hours=entry.get('durationHours'),
                raw=entry
            ))

        return events

    def get_sar_detections(self, min_lat: float, min_lon: float,
                           max_lat: float, max_lon: float,
                           start_date: datetime = None,
                           end_date: datetime = None,
                           matched_only: bool = False) -> List[SARDetection]:
        """
        Get SAR vessel detections from Sentinel-1 in an area.

        Uses GFW 4Wings API to query pre-processed SAR detections.
        Can filter for AIS-matched or unmatched (dark) vessels.

        Args:
            min_lat, min_lon, max_lat, max_lon: Bounding box
            start_date: Start of time range (default: 30 days ago)
            end_date: End of time range (default: now)
            matched_only: If False, returns unmatched (dark) vessels

        Returns:
            List of SARDetection objects
        """
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Build 4Wings report request
        # Dataset for SAR detections
        dataset = "public-global-sar-presence:latest"

        # Create spatial filter
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat]
            ]]
        }

        # 4Wings report endpoint
        report_data = {
            "datasets": [dataset],
            "date-range": [
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            ],
            "spatial-resolution": "high",  # 0.01 degree resolution
            "temporal-resolution": "daily",
            "region": geometry,
            "group-by": ["flag", "matched"]  # Group by AIS match status
        }

        result = self._post('/4wings/report', report_data)

        if 'error' in result:
            # Try alternative endpoint format
            params = {
                'datasets': dataset,
                'date-range': f"{start_date.strftime('%Y-%m-%d')},{end_date.strftime('%Y-%m-%d')}",
                'format': 'json'
            }
            params['geometry'] = json.dumps(geometry)
            result = self._request('/4wings/report', params)

            if 'error' in result:
                print(f"SAR detection query error: {result.get('error')}")
                return []

        detections = []

        # Parse response - format varies based on API version
        entries = result.get('entries', result.get('data', []))

        for entry in entries:
            # Check if matched/unmatched based on filter
            is_matched = entry.get('matched', entry.get('ais_matched', False))

            if matched_only and not is_matched:
                continue
            if not matched_only and is_matched:
                continue  # We want dark vessels

            # Parse detection
            timestamp_str = entry.get('timestamp', entry.get('date'))
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')) if timestamp_str else datetime.now()
            except:
                timestamp = datetime.now()

            detection = SARDetection(
                id=entry.get('id', f"sar_{timestamp.timestamp()}"),
                timestamp=timestamp,
                lat=float(entry.get('lat', entry.get('latitude', 0))),
                lon=float(entry.get('lon', entry.get('longitude', 0))),
                length_m=entry.get('length_m', entry.get('vessel_length')),
                matched_mmsi=entry.get('mmsi', entry.get('ssvid')) if is_matched else None,
                matched_vessel_name=entry.get('vessel_name', entry.get('shipname')) if is_matched else None,
                is_dark=not is_matched,
                confidence=float(entry.get('confidence', entry.get('score', 0.8))),
                source="sentinel-1"
            )

            if detection.lat != 0 and detection.lon != 0:
                detections.append(detection)

        return detections

    def find_dark_vessels(self, min_lat: float, min_lon: float,
                          max_lat: float, max_lon: float,
                          ais_positions: List[dict] = None,
                          days: int = 7) -> dict:
        """
        Find vessels detected by SAR but not broadcasting AIS.

        Cross-references SAR detections with AIS data to identify
        potentially illicit "dark" vessels.

        Args:
            min_lat, min_lon, max_lat, max_lon: Area to search
            ais_positions: List of known AIS positions [{lat, lon, mmsi, timestamp}]
            days: Days of history to check

        Returns:
            Dict with dark_vessels, matched_vessels, and statistics
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Get all SAR detections (both matched and unmatched)
        unmatched = self.get_sar_detections(
            min_lat, min_lon, max_lat, max_lon,
            start_date, end_date, matched_only=False
        )

        matched = self.get_sar_detections(
            min_lat, min_lon, max_lat, max_lon,
            start_date, end_date, matched_only=True
        )

        # If caller provided AIS positions, do additional matching
        extra_matches = []
        still_dark = []

        if ais_positions and unmatched:
            from math import radians, sin, cos, sqrt, atan2

            def haversine_km(lat1, lon1, lat2, lon2):
                R = 6371  # Earth radius km
                dlat = radians(lat2 - lat1)
                dlon = radians(lon2 - lon1)
                a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
                return 2 * R * atan2(sqrt(a), sqrt(1-a))

            for det in unmatched:
                found_match = False
                for ais in ais_positions:
                    dist = haversine_km(det.lat, det.lon, ais.get('lat', 0), ais.get('lon', 0))
                    if dist < 2.0:  # Within 2km - likely same vessel
                        det.matched_mmsi = ais.get('mmsi')
                        det.matched_vessel_name = ais.get('name')
                        det.is_dark = False
                        extra_matches.append(det)
                        found_match = True
                        break

                if not found_match:
                    still_dark.append(det)
        else:
            still_dark = unmatched

        return {
            'dark_vessels': [d.to_dict() for d in still_dark],
            'matched_vessels': [d.to_dict() for d in matched + extra_matches],
            'statistics': {
                'total_sar_detections': len(unmatched) + len(matched),
                'dark_count': len(still_dark),
                'matched_count': len(matched) + len(extra_matches),
                'dark_percentage': round(len(still_dark) / max(1, len(unmatched) + len(matched)) * 100, 1),
                'area': {
                    'min_lat': min_lat, 'min_lon': min_lon,
                    'max_lat': max_lat, 'max_lon': max_lon
                },
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
            },
            'source': 'Global Fishing Watch Sentinel-1 SAR'
        }


# Convenience functions
_client = None


def get_gfw_client() -> GFWClient:
    """Get or create GFW client singleton."""
    global _client
    if _client is None:
        _client = GFWClient()
    return _client


def is_configured() -> bool:
    """Check if GFW API token is configured."""
    return bool(GFW_TOKEN)


def search_vessel(query: str = None, mmsi: str = None,
                 imo: str = None, name: str = None) -> dict:
    """Search for vessel identity."""
    client = get_gfw_client()
    vessels = client.search_vessel(query=query, mmsi=mmsi, imo=imo, name=name)
    return {
        'vessels': [v.to_dict() for v in vessels],
        'count': len(vessels),
        'source': 'Global Fishing Watch'
    }


def get_vessel_events(mmsi: str, days: int = 90) -> dict:
    """Get all events for a vessel."""
    client = get_gfw_client()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    events = client.get_vessel_events(
        mmsi=mmsi,
        start_date=start_date,
        end_date=end_date
    )

    # Group by type
    by_type = {}
    for e in events:
        t = e.event_type
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(e.to_dict())

    return {
        'mmsi': mmsi,
        'period_days': days,
        'total_events': len(events),
        'events_by_type': by_type,
        'all_events': [e.to_dict() for e in events],
        'source': 'Global Fishing Watch'
    }


def get_dark_fleet_indicators(mmsi: str, days: int = 90) -> dict:
    """
    Get dark fleet risk indicators from GFW data.

    Combines:
    - AIS gaps (signal suppression)
    - Encounters (STS transfers)
    - Loitering (suspicious behavior)
    """
    client = get_gfw_client()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    gaps = client.get_ais_gaps(mmsi=mmsi, start_date=start_date, end_date=end_date)
    encounters = client.get_encounters(mmsi=mmsi, start_date=start_date, end_date=end_date)
    loitering = client.get_loitering(mmsi=mmsi, start_date=start_date, end_date=end_date)

    # Calculate risk score
    gap_hours = sum(g.duration_hours or 0 for g in gaps)
    encounter_count = len(encounters)
    loitering_hours = sum(l.duration_hours or 0 for l in loitering)

    risk_score = 0
    risk_factors = []

    # AIS gaps are highly suspicious
    if gap_hours > 48:
        risk_score += 30
        risk_factors.append(f"Extended AIS gaps: {gap_hours:.0f} hours")
    elif gap_hours > 12:
        risk_score += 15
        risk_factors.append(f"AIS gaps: {gap_hours:.0f} hours")

    # Encounters suggest STS
    if encounter_count > 3:
        risk_score += 25
        risk_factors.append(f"Multiple encounters: {encounter_count}")
    elif encounter_count > 0:
        risk_score += 10
        risk_factors.append(f"Encounters: {encounter_count}")

    # Excessive loitering
    if loitering_hours > 72:
        risk_score += 20
        risk_factors.append(f"Extended loitering: {loitering_hours:.0f} hours")
    elif loitering_hours > 24:
        risk_score += 10
        risk_factors.append(f"Loitering: {loitering_hours:.0f} hours")

    # Standardized risk levels matching behavior.py and dark_fleet.py
    if risk_score >= 70:
        risk_level = 'critical'
    elif risk_score >= 50:
        risk_level = 'high'
    elif risk_score >= 30:
        risk_level = 'medium'
    elif risk_score >= 15:
        risk_level = 'low'
    else:
        risk_level = 'minimal'

    return {
        'mmsi': mmsi,
        'period_days': days,
        'risk_score': min(risk_score, 100),
        'risk_level': risk_level,
        'risk_factors': risk_factors,
        'ais_gaps': {
            'count': len(gaps),
            'total_hours': gap_hours,
            'events': [g.to_dict() for g in gaps[:5]]
        },
        'encounters': {
            'count': encounter_count,
            'events': [e.to_dict() for e in encounters[:5]]
        },
        'loitering': {
            'count': len(loitering),
            'total_hours': loitering_hours,
            'events': [l.to_dict() for l in loitering[:5]]
        },
        'source': 'Global Fishing Watch'
    }


def check_sts_zone(min_lat: float, min_lon: float,
                  max_lat: float, max_lon: float,
                  days: int = 30) -> dict:
    """
    Check for STS activity in a geographic zone.

    Useful for monitoring known STS hotspots like:
    - Tanjung Pelepas (Malaysia) - Iran oil
    - Kalamata (Greece) - Russia oil
    - La Borracha (Venezuela) - sanctioned oil
    """
    client = get_gfw_client()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    encounters = client.get_area_activity(
        min_lat=min_lat, min_lon=min_lon,
        max_lat=max_lat, max_lon=max_lon,
        start_date=start_date, end_date=end_date,
        event_types=['encounter']
    )

    loitering = client.get_area_activity(
        min_lat=min_lat, min_lon=min_lon,
        max_lat=max_lat, max_lon=max_lon,
        start_date=start_date, end_date=end_date,
        event_types=['loitering']
    )

    return {
        'zone': {
            'min_lat': min_lat, 'min_lon': min_lon,
            'max_lat': max_lat, 'max_lon': max_lon
        },
        'period_days': days,
        'encounters': {
            'count': len(encounters),
            'events': [e.to_dict() for e in encounters]
        },
        'loitering': {
            'count': len(loitering),
            'events': [l.to_dict() for l in loitering]
        },
        'source': 'Global Fishing Watch'
    }


def get_sar_detections(min_lat: float, min_lon: float,
                       max_lat: float, max_lon: float,
                       days: int = 30, dark_only: bool = True) -> dict:
    """
    Get SAR vessel detections in an area.

    Args:
        min_lat, min_lon, max_lat, max_lon: Bounding box
        days: Days of history
        dark_only: If True, only return AIS-unmatched vessels

    Returns:
        Dict with detections and statistics
    """
    client = get_gfw_client()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    detections = client.get_sar_detections(
        min_lat, min_lon, max_lat, max_lon,
        start_date, end_date,
        matched_only=not dark_only
    )

    return {
        'detections': [d.to_dict() for d in detections],
        'count': len(detections),
        'dark_only': dark_only,
        'area': {
            'min_lat': min_lat, 'min_lon': min_lon,
            'max_lat': max_lat, 'max_lon': max_lon
        },
        'period_days': days,
        'source': 'Global Fishing Watch Sentinel-1 SAR'
    }


def find_dark_vessels(min_lat: float, min_lon: float,
                      max_lat: float, max_lon: float,
                      ais_positions: list = None,
                      days: int = 7) -> dict:
    """
    Find vessels detected by SAR but not broadcasting AIS.

    Args:
        min_lat, min_lon, max_lat, max_lon: Area to search
        ais_positions: Optional list of known AIS positions for cross-reference
        days: Days of history

    Returns:
        Dict with dark_vessels, matched_vessels, and statistics
    """
    client = get_gfw_client()
    return client.find_dark_vessels(
        min_lat, min_lon, max_lat, max_lon,
        ais_positions, days
    )


# Configuration helper
def save_token(token: str) -> bool:
    """Save GFW API token to config file."""
    global GFW_TOKEN, _client
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump({'api_token': token}, f)
        GFW_TOKEN = token
        _client = None  # Reset client
        return True
    except Exception as e:
        print(f"Failed to save token: {e}")
        return False


if __name__ == '__main__':
    # Test the integration
    if not is_configured():
        print("GFW API not configured. Set GFW_API_TOKEN environment variable")
        print("or run: python -c \"from gfw_integration import save_token; save_token('YOUR_TOKEN')\"")
        print("\nGet free token at: https://globalfishingwatch.org/our-apis/")
    else:
        print("GFW API configured. Testing search...")
        result = search_vessel(name="EAGLE S")
        print(json.dumps(result, indent=2, default=str))
