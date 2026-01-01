#!/usr/bin/env python3
"""
Laden Status Detection Module

Detects cargo loading/discharge operations by analyzing:
1. Draft changes - significant changes indicate loading or discharge
2. Speed patterns - slow movements near ports suggest operations
3. Time at anchorage - extended stays suggest STS or bunkering
4. Satellite imagery comparison (when available)

Key for dark fleet detection:
- AIS may show unchanged draft while satellite shows laden status change
- Indicates unreported STS transfer (sanctions evasion indicator)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Tuple
import json


class LadenState(Enum):
    """Vessel laden status."""
    LADEN = "laden"           # Fully loaded
    BALLAST = "ballast"       # Empty/light cargo
    PARTIAL = "partial"       # Partially loaded
    UNKNOWN = "unknown"


class CargoEventType(Enum):
    """Type of cargo operation detected."""
    LOADING = "loading"          # Taking on cargo
    DISCHARGING = "discharging"  # Offloading cargo
    STS_TRANSFER = "sts_transfer"  # Ship-to-ship transfer
    BUNKERING = "bunkering"      # Taking on fuel


@dataclass
class DraftReading:
    """Single draft reading from AIS or satellite."""
    timestamp: datetime
    draft_m: float
    source: str = "ais"  # ais, satellite, manual
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed_knots: Optional[float] = None


@dataclass
class CargoEvent:
    """Detected cargo operation event."""
    event_type: CargoEventType
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[Tuple[float, float]] = None
    draft_change_m: float = 0.0
    initial_draft_m: float = 0.0
    final_draft_m: float = 0.0
    estimated_cargo_tonnes: Optional[float] = None
    confidence: float = 0.5
    nearby_vessel: Optional[str] = None  # For STS detection
    port_name: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            'event_type': self.event_type.value,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'location': list(self.location) if self.location else None,
            'draft_change_m': self.draft_change_m,
            'initial_draft_m': self.initial_draft_m,
            'final_draft_m': self.final_draft_m,
            'estimated_cargo_tonnes': self.estimated_cargo_tonnes,
            'confidence': self.confidence,
            'nearby_vessel': self.nearby_vessel,
            'port_name': self.port_name,
            'notes': self.notes
        }


@dataclass
class LadenAnalysis:
    """Complete laden status analysis result."""
    vessel_id: int
    mmsi: str
    vessel_name: str
    current_state: LadenState
    current_draft_m: Optional[float] = None
    max_draft_m: Optional[float] = None  # From vessel specs
    draft_readings: List[DraftReading] = field(default_factory=list)
    cargo_events: List[CargoEvent] = field(default_factory=list)
    anomalies: List[Dict] = field(default_factory=list)
    analysis_period_days: int = 30

    def to_dict(self) -> dict:
        return {
            'vessel_id': self.vessel_id,
            'mmsi': self.mmsi,
            'vessel_name': self.vessel_name,
            'current_state': self.current_state.value,
            'current_draft_m': self.current_draft_m,
            'max_draft_m': self.max_draft_m,
            'draft_readings_count': len(self.draft_readings),
            'cargo_events': [e.to_dict() for e in self.cargo_events],
            'anomalies': self.anomalies,
            'analysis_period_days': self.analysis_period_days
        }


# Vessel-specific draft parameters (typical values by type)
DRAFT_PARAMS = {
    'tanker': {
        'laden_threshold': 0.85,  # % of max draft when considered laden
        'ballast_threshold': 0.55,  # % of max draft when in ballast
        'min_change_m': 2.0,  # Minimum draft change for cargo event
        'typical_loading_hours': 24,
        'cargo_factor': 1.025  # Tonnes per cubic meter for crude
    },
    'container': {
        'laden_threshold': 0.80,
        'ballast_threshold': 0.45,
        'min_change_m': 1.5,
        'typical_loading_hours': 18,
        'cargo_factor': 0.5  # Lower due to container weight distribution
    },
    'bulk_carrier': {
        'laden_threshold': 0.90,
        'ballast_threshold': 0.50,
        'min_change_m': 3.0,
        'typical_loading_hours': 48,
        'cargo_factor': 1.4  # For iron ore
    },
    'default': {
        'laden_threshold': 0.75,
        'ballast_threshold': 0.50,
        'min_change_m': 1.0,
        'typical_loading_hours': 24,
        'cargo_factor': 1.0
    }
}


def get_vessel_type_category(vessel_type: str) -> str:
    """Map vessel type to category for draft parameters."""
    if not vessel_type:
        return 'default'

    vessel_type_lower = vessel_type.lower()
    if 'tanker' in vessel_type_lower or 'oil' in vessel_type_lower:
        return 'tanker'
    elif 'container' in vessel_type_lower or 'feeder' in vessel_type_lower:
        return 'container'
    elif 'bulk' in vessel_type_lower or 'cargo' in vessel_type_lower:
        return 'bulk_carrier'
    return 'default'


def extract_draft_readings(track_history: List[dict]) -> List[DraftReading]:
    """Extract draft readings from position history."""
    readings = []

    for pos in track_history:
        # Get draft from position data (may be in different fields)
        draft = pos.get('draught') or pos.get('draft') or pos.get('draft_m')

        if draft and float(draft) > 0:
            try:
                timestamp = pos.get('timestamp')
                if isinstance(timestamp, str):
                    # Try parsing ISO format
                    try:
                        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        # Skip positions with unparseable timestamps
                        continue
                elif not isinstance(timestamp, datetime):
                    # Skip positions without valid timestamps
                    continue

                readings.append(DraftReading(
                    timestamp=timestamp,
                    draft_m=float(draft),
                    source=pos.get('source', 'ais'),
                    latitude=pos.get('latitude') or pos.get('lat'),
                    longitude=pos.get('longitude') or pos.get('lon'),
                    speed_knots=pos.get('speed_knots') or pos.get('speed')
                ))
            except (ValueError, TypeError):
                continue

    # Sort by timestamp
    readings.sort(key=lambda r: r.timestamp)
    return readings


def detect_draft_changes(readings: List[DraftReading],
                         min_change_m: float = 1.0,
                         min_hours: float = 4.0) -> List[Tuple[int, int, float]]:
    """
    Detect significant draft changes indicating cargo operations.

    Returns list of (start_idx, end_idx, change_m) tuples.
    """
    if len(readings) < 2:
        return []

    changes = []
    i = 0

    while i < len(readings) - 1:
        start_draft = readings[i].draft_m
        start_time = readings[i].timestamp

        # Look for significant change
        for j in range(i + 1, len(readings)):
            current_draft = readings[j].draft_m
            time_diff = (readings[j].timestamp - start_time).total_seconds() / 3600

            # Check if change is significant and happened over reasonable time
            draft_change = current_draft - start_draft

            if abs(draft_change) >= min_change_m and time_diff >= min_hours:
                changes.append((i, j, draft_change))
                i = j  # Move past this change
                break
        else:
            i += 1

    return changes


def determine_laden_state(current_draft: float, max_draft: float,
                          vessel_type: str = 'default') -> LadenState:
    """Determine laden state from current vs max draft."""
    if not max_draft or max_draft <= 0:
        return LadenState.UNKNOWN

    params = DRAFT_PARAMS.get(get_vessel_type_category(vessel_type), DRAFT_PARAMS['default'])
    draft_ratio = current_draft / max_draft

    if draft_ratio >= params['laden_threshold']:
        return LadenState.LADEN
    elif draft_ratio <= params['ballast_threshold']:
        return LadenState.BALLAST
    else:
        return LadenState.PARTIAL


def estimate_cargo_tonnage(draft_change_m: float, length_m: float,
                           beam_m: float, vessel_type: str = 'default') -> float:
    """
    Estimate cargo tonnage from draft change using TPC approximation.

    TPC (Tonnes Per Centimeter) = (LBP x Beam x Cb x density) / 100
    Simplified: TPC ~ length * beam * 0.007 (for typical tanker)
    """
    if not length_m or not beam_m:
        # Use typical values
        length_m = length_m or 200
        beam_m = beam_m or 32

    params = DRAFT_PARAMS.get(get_vessel_type_category(vessel_type), DRAFT_PARAMS['default'])

    # Approximate TPC calculation
    tpc = length_m * beam_m * 0.007 * params['cargo_factor']

    # Convert draft change to cm and calculate tonnage
    draft_change_cm = abs(draft_change_m) * 100
    return round(tpc * draft_change_cm, 0)


def detect_sts_indicators(readings: List[DraftReading],
                          nearby_vessels: List[dict] = None) -> List[Dict]:
    """
    Detect Ship-to-Ship transfer indicators.

    STS indicators:
    - Draft change while at low speed/stopped
    - At sea (not in port)
    - Another vessel in close proximity
    - Extended time at same location (>6 hours)
    """
    indicators = []

    for i, reading in enumerate(readings):
        # Check for stationary/slow speed
        if reading.speed_knots is not None and reading.speed_knots < 3:
            # Check if at sea (crude check - not near typical ports)
            if reading.latitude and reading.longitude:
                lat, lon = reading.latitude, reading.longitude

                # Check for draft changes while stationary
                if i > 0:
                    draft_change = reading.draft_m - readings[i-1].draft_m
                    time_diff = (reading.timestamp - readings[i-1].timestamp).total_seconds() / 3600

                    if abs(draft_change) > 0.5 and time_diff > 2:
                        indicators.append({
                            'timestamp': reading.timestamp.isoformat(),
                            'location': (lat, lon),
                            'draft_change_m': draft_change,
                            'duration_hours': time_diff,
                            'type': 'draft_change_while_stationary',
                            'severity': 'high' if abs(draft_change) > 2 else 'medium'
                        })

    return indicators


def analyze_laden_status(vessel_id: int,
                         mmsi: str,
                         vessel_name: str,
                         track_history: List[dict],
                         vessel_info: dict = None,
                         satellite_data: List[dict] = None) -> LadenAnalysis:
    """
    Perform complete laden status analysis on a vessel.

    Args:
        vessel_id: Database vessel ID
        mmsi: Vessel MMSI
        vessel_name: Vessel name
        track_history: List of position records
        vessel_info: Vessel static info (type, dimensions, max draft)
        satellite_data: Optional satellite imagery analysis results

    Returns:
        LadenAnalysis with cargo events and anomalies
    """
    vessel_info = vessel_info or {}
    vessel_type = vessel_info.get('vessel_type', 'unknown')
    max_draft = vessel_info.get('draught') or vessel_info.get('max_draft')
    length_m = vessel_info.get('length_m')
    beam_m = vessel_info.get('beam_m')

    # Extract draft readings
    readings = extract_draft_readings(track_history)

    # Get vessel type category for parameters
    type_category = get_vessel_type_category(vessel_type)
    params = DRAFT_PARAMS.get(type_category, DRAFT_PARAMS['default'])

    # Determine current state
    current_draft = readings[-1].draft_m if readings else None
    current_state = LadenState.UNKNOWN

    if current_draft and max_draft:
        current_state = determine_laden_state(current_draft, max_draft, vessel_type)
    elif current_draft:
        # Estimate based on typical vessel dimensions
        if current_draft > 12:  # Deep draft suggests laden tanker
            current_state = LadenState.LADEN
        elif current_draft < 7:  # Shallow draft suggests ballast
            current_state = LadenState.BALLAST

    # Detect cargo events from draft changes
    cargo_events = []
    changes = detect_draft_changes(readings, params['min_change_m'])

    for start_idx, end_idx, change_m in changes:
        start_reading = readings[start_idx]
        end_reading = readings[end_idx]

        event_type = CargoEventType.LOADING if change_m > 0 else CargoEventType.DISCHARGING

        # Check if this might be STS
        if start_reading.speed_knots is not None and start_reading.speed_knots < 5:
            # Low speed during operation suggests STS
            sts_indicators = detect_sts_indicators(readings[start_idx:end_idx+1])
            if sts_indicators:
                event_type = CargoEventType.STS_TRANSFER

        cargo_events.append(CargoEvent(
            event_type=event_type,
            start_time=start_reading.timestamp,
            end_time=end_reading.timestamp,
            location=(start_reading.latitude, start_reading.longitude) if start_reading.latitude else None,
            draft_change_m=abs(change_m),
            initial_draft_m=start_reading.draft_m,
            final_draft_m=end_reading.draft_m,
            estimated_cargo_tonnes=estimate_cargo_tonnage(change_m, length_m, beam_m, vessel_type),
            confidence=0.7 if len(readings) > 10 else 0.5,
            notes=f"Draft {'increased' if change_m > 0 else 'decreased'} by {abs(change_m):.1f}m over {(end_reading.timestamp - start_reading.timestamp).total_seconds()/3600:.1f} hours"
        ))

    # Detect anomalies
    anomalies = []

    # Check for AIS vs satellite discrepancies (if satellite data available)
    if satellite_data:
        for sat in satellite_data:
            sat_draft = sat.get('estimated_draft')
            sat_time = sat.get('timestamp')
            if sat_draft and sat_time:
                # Find nearest AIS reading
                for reading in readings:
                    time_diff = abs((reading.timestamp - datetime.fromisoformat(sat_time)).total_seconds())
                    if time_diff < 7200:  # Within 2 hours
                        discrepancy = abs(sat_draft - reading.draft_m)
                        if discrepancy > 2.0:
                            anomalies.append({
                                'type': 'ais_satellite_discrepancy',
                                'timestamp': sat_time,
                                'ais_draft_m': reading.draft_m,
                                'satellite_draft_m': sat_draft,
                                'discrepancy_m': discrepancy,
                                'severity': 'critical' if discrepancy > 5 else 'high',
                                'notes': 'AIS draft does not match satellite observation - possible unreported cargo operation'
                            })
                        break

    # Check for static draft (no changes during port calls)
    static_periods = []
    if len(readings) > 10:
        # Find periods where draft didn't change but should have (port visits)
        for i in range(1, len(readings)):
            if readings[i].speed_knots is not None and readings[i].speed_knots < 1:
                # Vessel is stopped
                start = i
                while i < len(readings) and readings[i].speed_knots is not None and readings[i].speed_knots < 1:
                    i += 1
                end = i - 1

                if end - start > 5:  # Extended stop (many readings)
                    duration = (readings[end].timestamp - readings[start].timestamp).total_seconds() / 3600
                    draft_change = abs(readings[end].draft_m - readings[start].draft_m)

                    if duration > 12 and draft_change < 0.5:
                        anomalies.append({
                            'type': 'static_draft_at_port',
                            'start_time': readings[start].timestamp.isoformat(),
                            'end_time': readings[end].timestamp.isoformat(),
                            'duration_hours': duration,
                            'draft_m': readings[start].draft_m,
                            'severity': 'medium',
                            'notes': f'No draft change during {duration:.1f}h stop - possible unreported operation or data issue'
                        })

    # Detect STS indicators
    sts_indicators = detect_sts_indicators(readings)
    for indicator in sts_indicators:
        anomalies.append({
            'type': 'sts_indicator',
            **indicator
        })

    return LadenAnalysis(
        vessel_id=vessel_id,
        mmsi=mmsi,
        vessel_name=vessel_name,
        current_state=current_state,
        current_draft_m=current_draft,
        max_draft_m=max_draft,
        draft_readings=readings,
        cargo_events=cargo_events,
        anomalies=anomalies
    )


def get_laden_status_summary(analysis: LadenAnalysis) -> dict:
    """Generate a summary for UI display."""
    recent_events = sorted(analysis.cargo_events, key=lambda e: e.start_time, reverse=True)[:5]

    # Calculate total cargo moved
    total_loaded = sum(e.estimated_cargo_tonnes or 0 for e in analysis.cargo_events
                       if e.event_type == CargoEventType.LOADING)
    total_discharged = sum(e.estimated_cargo_tonnes or 0 for e in analysis.cargo_events
                          if e.event_type == CargoEventType.DISCHARGING)
    sts_count = len([e for e in analysis.cargo_events if e.event_type == CargoEventType.STS_TRANSFER])

    # Determine risk level based on anomalies
    high_anomalies = len([a for a in analysis.anomalies if a.get('severity') in ['critical', 'high']])
    risk_level = 'high' if high_anomalies > 2 else 'medium' if high_anomalies > 0 else 'low'

    return {
        'vessel_id': analysis.vessel_id,
        'vessel_name': analysis.vessel_name,
        'current_state': analysis.current_state.value,
        'current_draft_m': analysis.current_draft_m,
        'max_draft_m': analysis.max_draft_m,
        'loading_ratio': round(analysis.current_draft_m / analysis.max_draft_m * 100, 1) if analysis.current_draft_m and analysis.max_draft_m else None,
        'total_events': len(analysis.cargo_events),
        'recent_events': [e.to_dict() for e in recent_events],
        'total_loaded_tonnes': total_loaded,
        'total_discharged_tonnes': total_discharged,
        'sts_transfer_count': sts_count,
        'anomaly_count': len(analysis.anomalies),
        'high_priority_anomalies': high_anomalies,
        'risk_level': risk_level,
        'anomalies': analysis.anomalies[:5]  # Top 5 anomalies
    }


# Test function
if __name__ == '__main__':
    # Simulate track with draft changes
    from datetime import datetime, timedelta

    base_time = datetime.now() - timedelta(days=7)
    test_track = [
        {'timestamp': (base_time + timedelta(hours=i)).isoformat(),
         'latitude': 10.0 + i*0.01, 'longitude': -65.0,
         'speed_knots': 12 if i < 20 else 2 if i < 40 else 12,
         'draught': 8.0 if i < 25 else 8.0 + (i-25)*0.2 if i < 40 else 14.0}  # Loading event
        for i in range(60)
    ]

    analysis = analyze_laden_status(
        vessel_id=1,
        mmsi="123456789",
        vessel_name="TEST TANKER",
        track_history=test_track,
        vessel_info={'vessel_type': 'Oil Tanker', 'length_m': 250, 'beam_m': 44, 'max_draft': 16}
    )

    print(json.dumps(get_laden_status_summary(analysis), indent=2, default=str))
