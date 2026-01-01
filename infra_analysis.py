#!/usr/bin/env python3
"""
Infrastructure Threat Analysis Module

Analyzes vessel behavior in proximity to critical undersea infrastructure
(cables, pipelines) to support situational awareness and incident investigation.

This module demonstrates how open-source AIS data can be correlated with
reported events to establish timelines, identify anomalies, and assess
whether vessel behavior warrants closer scrutiny.

IMPORTANT DISCLAIMER:
AIS analysis alone does not establish intent or responsibility. Correlation
is not attribution. AIS data can be incomplete, delayed, or deliberately
manipulated. Any findings must be evaluated alongside official investigations,
sensor data, and legal evidence.

Features:
- Anchor drag detection (speed/course anomalies in infrastructure zones)
- Loitering pattern analysis near cable routes
- AIS gap correlation with incident timelines
- Proximity alerts for critical infrastructure
- Behavioral anomaly scoring
- Timeline reconstruction for incident reporting

References:
- Finland cable incident (Dec 31, 2025)
- Eagle S / Estlink-2 incident (Dec 25, 2025)
- Balticconnector pipeline incident (Oct 2023)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
import math

from utils import haversine
from behavior import (
    detect_loitering, detect_ais_gaps, detect_spoofing,
    analyze_vessel_behavior, BehaviorEvent
)


class InfrastructureType(Enum):
    """Types of undersea infrastructure."""
    TELECOM_CABLE = "telecom_cable"
    POWER_CABLE = "power_cable"
    GAS_PIPELINE = "gas_pipeline"
    OIL_PIPELINE = "oil_pipeline"
    FIBER_OPTIC = "fiber_optic"


class ThreatIndicator(Enum):
    """Behavioral threat indicators for infrastructure proximity."""
    ANCHOR_DRAG = "anchor_drag"           # Slow movement with heading changes
    PROLONGED_STOP = "prolonged_stop"     # Extended stationary period
    COURSE_DEVIATION = "course_deviation" # Unexpected route change toward infra
    AIS_SUPPRESSION = "ais_suppression"   # Signal gaps near infrastructure
    SPEED_ANOMALY = "speed_anomaly"       # Unusual speed in shipping lane
    LOITERING = "loitering"               # Circling or drifting pattern
    APPROACH_PATTERN = "approach_pattern" # Direct approach to cable route


@dataclass
class InfrastructureAsset:
    """Represents a piece of critical undersea infrastructure."""
    name: str
    infra_type: InfrastructureType
    # For cables/pipelines: list of waypoints defining the route
    waypoints: List[Tuple[float, float]] = field(default_factory=list)
    # For point assets: single location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Protection zone radius in nautical miles
    protection_radius_nm: float = 5.0
    # Metadata
    operator: Optional[str] = None
    capacity: Optional[str] = None  # e.g., "1.2 Tbps" or "650 MW"
    notes: str = ""

    def get_nearest_point(self, lat: float, lon: float) -> Tuple[float, float, float]:
        """
        Get the nearest point on this infrastructure to a given position.

        Returns: (nearest_lat, nearest_lon, distance_nm)
        """
        if self.waypoints:
            min_dist = float('inf')
            nearest = self.waypoints[0]

            for i, wp in enumerate(self.waypoints):
                dist = haversine(lat, lon, wp[0], wp[1]) / 1.852  # km to nm
                if dist < min_dist:
                    min_dist = dist
                    nearest = wp

                # Also check segments between waypoints
                if i > 0:
                    prev = self.waypoints[i-1]
                    seg_point, seg_dist = _nearest_point_on_segment(
                        lat, lon, prev[0], prev[1], wp[0], wp[1]
                    )
                    if seg_dist < min_dist:
                        min_dist = seg_dist
                        nearest = seg_point

            return (nearest[0], nearest[1], min_dist)
        elif self.latitude and self.longitude:
            dist = haversine(lat, lon, self.latitude, self.longitude) / 1.852
            return (self.latitude, self.longitude, dist)
        else:
            return (0, 0, float('inf'))


@dataclass
class InfrastructureProximityEvent:
    """Records when a vessel enters an infrastructure protection zone."""
    vessel_mmsi: str
    vessel_name: Optional[str]
    infrastructure: str
    infra_type: InfrastructureType
    entry_time: datetime
    exit_time: Optional[datetime] = None
    min_distance_nm: float = 0.0
    duration_minutes: float = 0.0
    indicators: List[ThreatIndicator] = field(default_factory=list)
    positions: List[dict] = field(default_factory=list)
    risk_score: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "vessel_mmsi": self.vessel_mmsi,
            "vessel_name": self.vessel_name,
            "infrastructure": self.infrastructure,
            "infra_type": self.infra_type.value,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "min_distance_nm": self.min_distance_nm,
            "duration_minutes": self.duration_minutes,
            "indicators": [i.value for i in self.indicators],
            "risk_score": self.risk_score,
            "notes": self.notes
        }


@dataclass
class IncidentAnalysis:
    """Complete analysis of a vessel's behavior during an infrastructure incident."""
    vessel_mmsi: str
    vessel_name: Optional[str]
    vessel_flag: Optional[str]
    analysis_period_start: datetime
    analysis_period_end: datetime

    # Timeline reconstruction
    positions_analyzed: int = 0
    track_gaps: List[dict] = field(default_factory=list)

    # Infrastructure proximity
    proximity_events: List[InfrastructureProximityEvent] = field(default_factory=list)
    min_distance_to_infra_nm: float = float('inf')
    time_in_protection_zone_minutes: float = 0.0

    # Behavioral indicators
    indicators_detected: List[ThreatIndicator] = field(default_factory=list)
    loitering_events: List[dict] = field(default_factory=list)
    speed_anomalies: List[dict] = field(default_factory=list)
    anchor_drag_detected: bool = False

    # Scoring
    overall_risk_score: float = 0.0
    confidence_level: str = "low"  # low, medium, high

    # Context
    departure_port: Optional[str] = None
    destination_port: Optional[str] = None

    # Disclaimer
    disclaimer: str = (
        "This analysis is based on open-source AIS data and does not establish "
        "intent or responsibility. Correlation is not attribution. AIS data may "
        "be incomplete, delayed, or manipulated. Findings must be evaluated "
        "alongside official investigations and legal evidence."
    )

    def to_dict(self) -> dict:
        return {
            "vessel": {
                "mmsi": self.vessel_mmsi,
                "name": self.vessel_name,
                "flag": self.vessel_flag,
                "departure_port": self.departure_port,
                "destination_port": self.destination_port
            },
            "analysis_period": {
                "start": self.analysis_period_start.isoformat(),
                "end": self.analysis_period_end.isoformat()
            },
            "track_summary": {
                "positions_analyzed": self.positions_analyzed,
                "ais_gaps": len(self.track_gaps),
                "gaps": self.track_gaps[:5]  # First 5 gaps
            },
            "infrastructure_proximity": {
                "events": [e.to_dict() for e in self.proximity_events],
                "min_distance_nm": self.min_distance_to_infra_nm,
                "time_in_zone_minutes": self.time_in_protection_zone_minutes
            },
            "behavioral_indicators": {
                "detected": [i.value for i in self.indicators_detected],
                "loitering_events": len(self.loitering_events),
                "speed_anomalies": len(self.speed_anomalies),
                "anchor_drag_detected": self.anchor_drag_detected
            },
            "assessment": {
                "risk_score": self.overall_risk_score,
                "confidence": self.confidence_level
            },
            "disclaimer": self.disclaimer
        }

    def generate_report(self) -> str:
        """Generate a human-readable incident analysis report."""
        lines = [
            "=" * 70,
            "INFRASTRUCTURE INCIDENT ANALYSIS REPORT",
            "=" * 70,
            "",
            "DISCLAIMER:",
            self.disclaimer,
            "",
            "-" * 70,
            "VESSEL INFORMATION",
            "-" * 70,
            f"  Name:        {self.vessel_name or 'Unknown'}",
            f"  MMSI:        {self.vessel_mmsi}",
            f"  Flag:        {self.vessel_flag or 'Unknown'}",
            f"  Departure:   {self.departure_port or 'Unknown'}",
            f"  Destination: {self.destination_port or 'Unknown'}",
            "",
            "-" * 70,
            "ANALYSIS PERIOD",
            "-" * 70,
            f"  Start:       {self.analysis_period_start.strftime('%Y-%m-%d %H:%M UTC')}",
            f"  End:         {self.analysis_period_end.strftime('%Y-%m-%d %H:%M UTC')}",
            f"  Positions:   {self.positions_analyzed} AIS reports analyzed",
            f"  AIS Gaps:    {len(self.track_gaps)} periods of signal loss",
            "",
            "-" * 70,
            "INFRASTRUCTURE PROXIMITY",
            "-" * 70,
            f"  Closest approach:     {self.min_distance_to_infra_nm:.2f} nautical miles",
            f"  Time in zone:         {self.time_in_protection_zone_minutes:.1f} minutes",
            f"  Proximity events:     {len(self.proximity_events)}",
        ]

        for event in self.proximity_events:
            lines.append(f"\n  [{event.infrastructure}]")
            lines.append(f"    Entry:     {event.entry_time.strftime('%Y-%m-%d %H:%M UTC')}")
            if event.exit_time:
                lines.append(f"    Exit:      {event.exit_time.strftime('%Y-%m-%d %H:%M UTC')}")
            lines.append(f"    Duration:  {event.duration_minutes:.1f} minutes")
            lines.append(f"    Min dist:  {event.min_distance_nm:.2f} nm")
            if event.indicators:
                lines.append(f"    Indicators: {', '.join(i.value for i in event.indicators)}")

        lines.extend([
            "",
            "-" * 70,
            "BEHAVIORAL INDICATORS",
            "-" * 70,
        ])

        if self.anchor_drag_detected:
            lines.append("  [!] ANCHOR DRAG PATTERN DETECTED")

        if self.indicators_detected:
            lines.append(f"  Indicators detected: {len(self.indicators_detected)}")
            for ind in self.indicators_detected:
                lines.append(f"    - {ind.value}")
        else:
            lines.append("  No significant behavioral indicators detected")

        lines.extend([
            "",
            "-" * 70,
            "RISK ASSESSMENT",
            "-" * 70,
            f"  Overall Score:   {self.overall_risk_score:.0f}/100",
            f"  Confidence:      {self.confidence_level.upper()}",
            "",
        ])

        # Risk interpretation
        if self.overall_risk_score >= 70:
            lines.append("  INTERPRETATION: High concern - behavior warrants close scrutiny")
        elif self.overall_risk_score >= 40:
            lines.append("  INTERPRETATION: Moderate concern - anomalies detected")
        else:
            lines.append("  INTERPRETATION: Low concern - behavior appears normal")

        lines.extend([
            "",
            "=" * 70,
            "END OF REPORT",
            "=" * 70,
        ])

        return "\n".join(lines)


# =============================================================================
# Baltic Sea Infrastructure Database
# =============================================================================

BALTIC_INFRASTRUCTURE = [
    InfrastructureAsset(
        name="C-Lion1",
        infra_type=InfrastructureType.TELECOM_CABLE,
        waypoints=[
            (60.17, 24.94),   # Helsinki
            (59.45, 24.75),   # Gulf of Finland
            (58.50, 20.00),   # Baltic Sea
            (55.00, 14.00),   # Southern Baltic
            (54.18, 12.09),   # Rostock
        ],
        protection_radius_nm=5.0,
        operator="Cinia",
        capacity="144 Tbps design capacity",
        notes="Finland-Germany submarine telecom cable, ~1,200km. Damaged Dec 31, 2025."
    ),
    InfrastructureAsset(
        name="Estlink-2",
        infra_type=InfrastructureType.POWER_CABLE,
        waypoints=[
            (59.47, 24.76),   # Purtse, Estonia
            (59.55, 25.00),   # Gulf of Finland
            (60.22, 25.20),   # Porvoo, Finland
        ],
        protection_radius_nm=3.0,
        operator="Elering/Fingrid",
        capacity="650 MW HVDC",
        notes="Estonia-Finland power interconnector. Damaged Dec 25, 2025 by Eagle S."
    ),
    InfrastructureAsset(
        name="Estlink-1",
        infra_type=InfrastructureType.POWER_CABLE,
        waypoints=[
            (59.45, 24.70),   # Harku, Estonia
            (59.50, 25.10),   # Gulf of Finland
            (60.10, 25.50),   # Espoo, Finland
        ],
        protection_radius_nm=3.0,
        operator="Elering/Fingrid",
        capacity="350 MW HVDC",
        notes="First Estonia-Finland power cable (2006)."
    ),
    InfrastructureAsset(
        name="Balticconnector",
        infra_type=InfrastructureType.GAS_PIPELINE,
        waypoints=[
            (59.47, 24.76),   # Paldiski, Estonia
            (59.60, 24.80),   # Gulf of Finland
            (60.10, 25.20),   # Inkoo, Finland
        ],
        protection_radius_nm=5.0,
        operator="Gasgrid Finland/Elering",
        capacity="7.2 bcm/year",
        notes="Finland-Estonia gas pipeline. Damaged Oct 2023 by anchor drag."
    ),
]


# =============================================================================
# Analysis Functions
# =============================================================================

def analyze_infrastructure_incident(
    track_history: List[dict],
    mmsi: str,
    vessel_name: Optional[str] = None,
    vessel_flag: Optional[str] = None,
    infrastructure: Optional[List[InfrastructureAsset]] = None,
    incident_time: Optional[datetime] = None,
    analysis_window_hours: int = 48
) -> IncidentAnalysis:
    """
    Perform comprehensive infrastructure incident analysis on a vessel's track.

    Args:
        track_history: List of position dicts with lat, lon, timestamp, speed, heading
        mmsi: Vessel MMSI
        vessel_name: Optional vessel name
        vessel_flag: Optional flag state
        infrastructure: List of infrastructure assets to check (defaults to Baltic)
        incident_time: Time of reported incident (for focused analysis)
        analysis_window_hours: Hours before/after incident to analyze

    Returns:
        IncidentAnalysis with full assessment
    """
    if infrastructure is None:
        infrastructure = BALTIC_INFRASTRUCTURE

    if not track_history:
        return IncidentAnalysis(
            vessel_mmsi=mmsi,
            vessel_name=vessel_name,
            vessel_flag=vessel_flag,
            analysis_period_start=datetime.utcnow(),
            analysis_period_end=datetime.utcnow(),
            confidence_level="low"
        )

    # Sort positions by timestamp
    positions = sorted(track_history, key=lambda p: _parse_timestamp(p.get('timestamp')))

    # Determine analysis period
    if incident_time:
        window = timedelta(hours=analysis_window_hours / 2)
        start_time = incident_time - window
        end_time = incident_time + window
        positions = [p for p in positions
                     if start_time <= _parse_timestamp(p.get('timestamp')) <= end_time]

    if not positions:
        return IncidentAnalysis(
            vessel_mmsi=mmsi,
            vessel_name=vessel_name,
            vessel_flag=vessel_flag,
            analysis_period_start=incident_time or datetime.utcnow(),
            analysis_period_end=incident_time or datetime.utcnow(),
            confidence_level="low"
        )

    analysis = IncidentAnalysis(
        vessel_mmsi=mmsi,
        vessel_name=vessel_name,
        vessel_flag=vessel_flag,
        analysis_period_start=_parse_timestamp(positions[0].get('timestamp')),
        analysis_period_end=_parse_timestamp(positions[-1].get('timestamp')),
        positions_analyzed=len(positions)
    )

    # 1. Detect AIS gaps
    analysis.track_gaps = _detect_track_gaps(positions, min_gap_minutes=30)

    # 2. Analyze infrastructure proximity
    for asset in infrastructure:
        proximity = _analyze_asset_proximity(positions, asset, mmsi, vessel_name)
        if proximity:
            analysis.proximity_events.append(proximity)
            if proximity.min_distance_nm < analysis.min_distance_to_infra_nm:
                analysis.min_distance_to_infra_nm = proximity.min_distance_nm
            analysis.time_in_protection_zone_minutes += proximity.duration_minutes
            analysis.indicators_detected.extend(proximity.indicators)

    # 3. Detect anchor drag pattern
    anchor_drag = _detect_anchor_drag(positions)
    if anchor_drag:
        analysis.anchor_drag_detected = True
        if ThreatIndicator.ANCHOR_DRAG not in analysis.indicators_detected:
            analysis.indicators_detected.append(ThreatIndicator.ANCHOR_DRAG)

    # 4. Detect loitering
    loitering = detect_loitering(positions, mmsi, min_duration_hours=0.5)
    analysis.loitering_events = [
        {"start": e.start_time.isoformat(), "duration_hours": e.duration_hours,
         "lat": e.latitude, "lon": e.longitude}
        for e in loitering
    ]
    if loitering:
        if ThreatIndicator.LOITERING not in analysis.indicators_detected:
            analysis.indicators_detected.append(ThreatIndicator.LOITERING)

    # 5. Detect speed anomalies
    analysis.speed_anomalies = _detect_speed_anomalies(positions)
    if analysis.speed_anomalies:
        if ThreatIndicator.SPEED_ANOMALY not in analysis.indicators_detected:
            analysis.indicators_detected.append(ThreatIndicator.SPEED_ANOMALY)

    # 6. Check for AIS suppression near infrastructure
    if analysis.track_gaps and analysis.proximity_events:
        for gap in analysis.track_gaps:
            gap_time = _parse_timestamp(gap.get('start'))
            for prox in analysis.proximity_events:
                if prox.entry_time <= gap_time <= (prox.exit_time or prox.entry_time):
                    if ThreatIndicator.AIS_SUPPRESSION not in analysis.indicators_detected:
                        analysis.indicators_detected.append(ThreatIndicator.AIS_SUPPRESSION)
                    break

    # 7. Calculate overall risk score
    analysis.overall_risk_score = _calculate_infrastructure_risk_score(analysis)

    # 8. Set confidence level
    if analysis.positions_analyzed >= 50 and len(analysis.track_gaps) < 3:
        analysis.confidence_level = "high"
    elif analysis.positions_analyzed >= 20:
        analysis.confidence_level = "medium"
    else:
        analysis.confidence_level = "low"

    # Deduplicate indicators
    analysis.indicators_detected = list(set(analysis.indicators_detected))

    return analysis


def _detect_track_gaps(positions: List[dict], min_gap_minutes: int = 30) -> List[dict]:
    """Detect gaps in AIS transmission."""
    gaps = []
    for i in range(1, len(positions)):
        t1 = _parse_timestamp(positions[i-1].get('timestamp'))
        t2 = _parse_timestamp(positions[i].get('timestamp'))
        gap_minutes = (t2 - t1).total_seconds() / 60

        if gap_minutes >= min_gap_minutes:
            gaps.append({
                "start": t1.isoformat(),
                "end": t2.isoformat(),
                "duration_minutes": gap_minutes,
                "start_position": {
                    "lat": positions[i-1].get('lat', positions[i-1].get('latitude')),
                    "lon": positions[i-1].get('lon', positions[i-1].get('longitude'))
                }
            })
    return gaps


def _analyze_asset_proximity(
    positions: List[dict],
    asset: InfrastructureAsset,
    mmsi: str,
    vessel_name: Optional[str]
) -> Optional[InfrastructureProximityEvent]:
    """Analyze vessel proximity to a specific infrastructure asset."""
    in_zone = False
    entry_time = None
    zone_positions = []
    min_dist = float('inf')
    indicators = []

    for pos in positions:
        lat = pos.get('lat', pos.get('latitude', 0))
        lon = pos.get('lon', pos.get('longitude', 0))
        timestamp = _parse_timestamp(pos.get('timestamp'))

        _, _, dist = asset.get_nearest_point(lat, lon)

        if dist < min_dist:
            min_dist = dist

        # Check if in protection zone
        if dist <= asset.protection_radius_nm:
            if not in_zone:
                in_zone = True
                entry_time = timestamp
            zone_positions.append(pos)
        else:
            if in_zone:
                # Exited zone - create event
                exit_time = timestamp
                duration = (exit_time - entry_time).total_seconds() / 60

                # Analyze behavior in zone
                indicators = _analyze_zone_behavior(zone_positions)

                return InfrastructureProximityEvent(
                    vessel_mmsi=mmsi,
                    vessel_name=vessel_name,
                    infrastructure=asset.name,
                    infra_type=asset.infra_type,
                    entry_time=entry_time,
                    exit_time=exit_time,
                    min_distance_nm=min_dist,
                    duration_minutes=duration,
                    indicators=indicators,
                    positions=zone_positions
                )

    # Still in zone at end of track
    if in_zone and entry_time:
        exit_time = _parse_timestamp(positions[-1].get('timestamp'))
        duration = (exit_time - entry_time).total_seconds() / 60
        indicators = _analyze_zone_behavior(zone_positions)

        return InfrastructureProximityEvent(
            vessel_mmsi=mmsi,
            vessel_name=vessel_name,
            infrastructure=asset.name,
            infra_type=asset.infra_type,
            entry_time=entry_time,
            exit_time=exit_time,
            min_distance_nm=min_dist,
            duration_minutes=duration,
            indicators=indicators,
            positions=zone_positions
        )

    # Passed close but not in zone
    if min_dist < asset.protection_radius_nm * 2:
        return InfrastructureProximityEvent(
            vessel_mmsi=mmsi,
            vessel_name=vessel_name,
            infrastructure=asset.name,
            infra_type=asset.infra_type,
            entry_time=_parse_timestamp(positions[0].get('timestamp')),
            min_distance_nm=min_dist,
            duration_minutes=0,
            indicators=[],
            notes="Close approach but did not enter protection zone"
        )

    return None


def _analyze_zone_behavior(positions: List[dict]) -> List[ThreatIndicator]:
    """Analyze vessel behavior while in infrastructure zone."""
    indicators = []

    if len(positions) < 2:
        return indicators

    speeds = [p.get('speed', p.get('speed_knots', 0)) or 0 for p in positions]
    headings = [p.get('heading', p.get('course', 0)) or 0 for p in positions]

    avg_speed = sum(speeds) / len(speeds) if speeds else 0

    # Very slow speed suggests stopping/anchoring
    if avg_speed < 2.0:
        indicators.append(ThreatIndicator.PROLONGED_STOP)

    # Heading variance suggests drifting/dragging
    if len(headings) > 3:
        heading_changes = [
            abs(headings[i] - headings[i-1]) % 360
            for i in range(1, len(headings))
        ]
        # Normalize to 0-180
        heading_changes = [min(h, 360-h) for h in heading_changes]
        avg_change = sum(heading_changes) / len(heading_changes)

        if avg_change > 20 and avg_speed < 5:
            indicators.append(ThreatIndicator.ANCHOR_DRAG)

    return indicators


def _detect_anchor_drag(positions: List[dict]) -> bool:
    """
    Detect anchor dragging pattern.

    Indicators:
    - Speed between 0.5 and 3 knots (too slow for steaming, too fast for anchored)
    - Erratic heading changes
    - Small position changes over time
    """
    if len(positions) < 5:
        return False

    drag_segments = 0

    for i in range(4, len(positions)):
        segment = positions[i-4:i+1]

        speeds = [p.get('speed', p.get('speed_knots', 0)) or 0 for p in segment]
        headings = [p.get('heading', p.get('course', 0)) or 0 for p in segment]

        avg_speed = sum(speeds) / len(speeds)

        # Anchor drag speed range
        if 0.3 <= avg_speed <= 4.0:
            # Check heading variance
            heading_changes = []
            for j in range(1, len(headings)):
                change = abs(headings[j] - headings[j-1])
                change = min(change, 360 - change)
                heading_changes.append(change)

            if heading_changes:
                avg_heading_change = sum(heading_changes) / len(heading_changes)

                # Significant heading variation at low speed = likely dragging
                if avg_heading_change > 15:
                    drag_segments += 1

    # If multiple segments show drag pattern, consider it detected
    return drag_segments >= 2


def _detect_speed_anomalies(positions: List[dict]) -> List[dict]:
    """Detect unusual speed patterns."""
    anomalies = []

    if len(positions) < 3:
        return anomalies

    speeds = [p.get('speed', p.get('speed_knots', 0)) or 0 for p in positions]
    avg_speed = sum(speeds) / len(speeds)

    for i, pos in enumerate(positions):
        speed = pos.get('speed', pos.get('speed_knots', 0)) or 0

        # Sudden stop
        if i > 0:
            prev_speed = positions[i-1].get('speed', 0) or 0
            if prev_speed > 8 and speed < 1:
                anomalies.append({
                    "type": "sudden_stop",
                    "timestamp": pos.get('timestamp'),
                    "previous_speed": prev_speed,
                    "speed": speed,
                    "lat": pos.get('lat', pos.get('latitude')),
                    "lon": pos.get('lon', pos.get('longitude'))
                })

        # Very slow in shipping lane (potential obstruction)
        if 0.5 < speed < 3:
            anomalies.append({
                "type": "very_slow",
                "timestamp": pos.get('timestamp'),
                "speed": speed,
                "lat": pos.get('lat', pos.get('latitude')),
                "lon": pos.get('lon', pos.get('longitude'))
            })

    return anomalies


def _calculate_infrastructure_risk_score(analysis: IncidentAnalysis) -> float:
    """
    Calculate overall infrastructure threat risk score (0-100).

    Factors:
    - Proximity to infrastructure
    - Time spent in protection zone
    - Behavioral indicators
    - AIS gaps/suppression
    """
    score = 0.0

    # Proximity factor (0-30 points)
    if analysis.min_distance_to_infra_nm < 1:
        score += 30
    elif analysis.min_distance_to_infra_nm < 3:
        score += 20
    elif analysis.min_distance_to_infra_nm < 5:
        score += 10

    # Time in zone factor (0-20 points)
    if analysis.time_in_protection_zone_minutes > 60:
        score += 20
    elif analysis.time_in_protection_zone_minutes > 30:
        score += 15
    elif analysis.time_in_protection_zone_minutes > 10:
        score += 10
    elif analysis.time_in_protection_zone_minutes > 0:
        score += 5

    # Indicator factors (0-40 points)
    indicator_scores = {
        ThreatIndicator.ANCHOR_DRAG: 15,
        ThreatIndicator.AIS_SUPPRESSION: 12,
        ThreatIndicator.PROLONGED_STOP: 10,
        ThreatIndicator.LOITERING: 8,
        ThreatIndicator.SPEED_ANOMALY: 5,
        ThreatIndicator.COURSE_DEVIATION: 5,
        ThreatIndicator.APPROACH_PATTERN: 3,
    }

    for indicator in analysis.indicators_detected:
        score += indicator_scores.get(indicator, 0)

    # AIS gap factor (0-10 points)
    gap_count = len(analysis.track_gaps)
    if gap_count >= 3:
        score += 10
    elif gap_count >= 1:
        score += 5

    return min(100, score)


def _nearest_point_on_segment(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float
) -> Tuple[Tuple[float, float], float]:
    """Find nearest point on line segment AB to point P."""
    # Vector AB
    abx = bx - ax
    aby = by - ay

    # Vector AP
    apx = px - ax
    apy = py - ay

    # Project AP onto AB
    ab_sq = abx * abx + aby * aby
    if ab_sq == 0:
        return ((ax, ay), haversine(px, py, ax, ay) / 1.852)

    t = (apx * abx + apy * aby) / ab_sq
    t = max(0, min(1, t))  # Clamp to segment

    # Nearest point
    nx = ax + t * abx
    ny = ay + t * aby

    dist = haversine(px, py, nx, ny) / 1.852  # km to nm

    return ((nx, ny), dist)


def _parse_timestamp(ts) -> datetime:
    """Parse various timestamp formats."""
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except:
            pass
        try:
            return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except:
            pass
    return datetime.utcnow()


# =============================================================================
# API Functions for Server Integration
# =============================================================================

def get_baltic_infrastructure() -> List[dict]:
    """Get list of Baltic infrastructure for map display."""
    return [
        {
            "name": asset.name,
            "type": asset.infra_type.value,
            "waypoints": asset.waypoints,
            "latitude": asset.latitude,
            "longitude": asset.longitude,
            "protection_radius_nm": asset.protection_radius_nm,
            "operator": asset.operator,
            "capacity": asset.capacity,
            "notes": asset.notes
        }
        for asset in BALTIC_INFRASTRUCTURE
    ]


def analyze_vessel_for_incident(
    vessel_id: int,
    track_history: List[dict],
    mmsi: str,
    vessel_name: Optional[str] = None,
    vessel_flag: Optional[str] = None,
    incident_time: Optional[str] = None
) -> dict:
    """
    API wrapper for incident analysis.

    Returns JSON-serializable analysis result.
    """
    inc_time = None
    if incident_time:
        inc_time = _parse_timestamp(incident_time)

    analysis = analyze_infrastructure_incident(
        track_history=track_history,
        mmsi=mmsi,
        vessel_name=vessel_name,
        vessel_flag=vessel_flag,
        incident_time=inc_time
    )

    result = analysis.to_dict()
    result["vessel_id"] = vessel_id
    result["report"] = analysis.generate_report()

    return result
