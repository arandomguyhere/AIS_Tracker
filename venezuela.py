"""
Venezuela Dark Fleet Detection Module

Implements detection algorithms for sanctioned vessel activity in Venezuelan waters,
based on commercial intelligence methodologies (Kpler, Windward, TankerTrackers).

The Venezuela crisis represents an active case study for dark fleet monitoring:
- 920+ sanctioned tankers globally, ~40% serving Venezuela under U.S. sanctions
- 95% YoY increase in high-risk tanker presence in Caribbean (2025)
- Detection-to-interdiction transition: U.S. now physically seizing vessels

Key Detection Methods:
- AIS spoofing detection via satellite imagery comparison
- STS transfer monitoring in known zones
- "Zombie vessel" identity laundering detection
- Flag hopping and false flag identification

References:
- Kpler maritime intelligence
- Windward AI satellite analytics
- TankerTrackers.com vessel monitoring
- UANI (United Against Nuclear Iran) dark fleet tracking
- The Skipper seizure case study (December 2025)
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from utils import haversine
from behavior import (
    validate_mmsi, get_flag_country, is_flag_of_convenience,
    is_shadow_fleet_flag, detect_ais_gaps, detect_loitering,
    detect_spoofing, BehaviorEvent, BehaviorType
)


# =============================================================================
# Venezuela Monitoring Zones
# =============================================================================

# Primary bounding box for Caribbean/Venezuela monitoring
VENEZUELA_BOUNDS = {
    "name": "Venezuela Caribbean",
    "north": 15.0,
    "south": 8.0,
    "east": -58.0,
    "west": -72.0
}

# Key locations for monitoring
VENEZUELA_KEY_POINTS = [
    {
        "name": "Jose Terminal",
        "lat": 10.15,
        "lon": -64.68,
        "type": "terminal",
        "description": "Venezuela's primary oil export facility",
        "risk_level": "critical"
    },
    {
        "name": "La Borracha STS Zone",
        "lat": 10.08,
        "lon": -64.89,
        "type": "sts_zone",
        "description": "Known ship-to-ship transfer area",
        "risk_level": "critical"
    },
    {
        "name": "Barcelona STS Zone",
        "lat": 10.12,
        "lon": -64.72,
        "type": "sts_zone",
        "description": "STS transfer zone near Barcelona, Venezuela",
        "risk_level": "high"
    },
    {
        "name": "Amuay Refinery",
        "lat": 11.74,
        "lon": -70.21,
        "type": "refinery",
        "description": "Major Venezuelan refinery complex",
        "risk_level": "high"
    },
    {
        "name": "Paraguana Peninsula",
        "lat": 11.95,
        "lon": -70.00,
        "type": "anchorage",
        "description": "Staging area for dark fleet vessels",
        "risk_level": "medium"
    },
    {
        "name": "Curacao Anchorage",
        "lat": 12.10,
        "lon": -68.95,
        "type": "anchorage",
        "description": "Offshore anchorage used for STS transfers",
        "risk_level": "medium"
    },
    {
        "name": "Guyana Offshore",
        "lat": 7.5,
        "lon": -57.5,
        "type": "spoofing_target",
        "description": "Common false AIS destination for spoofing",
        "risk_level": "low"
    }
]

# Detection radius for key points (in km)
TERMINAL_DETECTION_RADIUS_KM = 10.0
STS_ZONE_RADIUS_KM = 20.0
ANCHORAGE_RADIUS_KM = 15.0


# =============================================================================
# Known Dark Fleet Vessels (Venezuela Focus)
# =============================================================================

class VesselStatus(Enum):
    """Status of known dark fleet vessels."""
    ACTIVE = "active"
    SEIZED = "seized"
    PURSUED = "pursued"
    SANCTIONED = "sanctioned"
    FLAGGED = "flagged"


@dataclass
class DarkFleetVessel:
    """Known dark fleet vessel record."""
    name: str
    mmsi: Optional[str] = None
    imo: Optional[str] = None
    former_names: List[str] = field(default_factory=list)
    flag: Optional[str] = None
    status: VesselStatus = VesselStatus.ACTIVE
    sanctioned_by: List[str] = field(default_factory=list)
    notes: str = ""
    last_updated: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mmsi": self.mmsi,
            "imo": self.imo,
            "former_names": self.former_names,
            "flag": self.flag,
            "status": self.status.value,
            "sanctioned_by": self.sanctioned_by,
            "notes": self.notes,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None
        }


# Known dark fleet vessels from current reporting (December 2025)
KNOWN_DARK_FLEET_VESSELS = [
    DarkFleetVessel(
        name="Skipper",
        imo="9179834",
        former_names=["Adisa"],
        flag="Cameroon",
        status=VesselStatus.SEIZED,
        sanctioned_by=["US", "UK"],
        notes="Seized December 2025. 80+ days of AIS spoofing. Iran-Venezuela-China route.",
        last_updated=datetime(2025, 12, 20)
    ),
    DarkFleetVessel(
        name="Centuries",
        status=VesselStatus.SEIZED,
        sanctioned_by=["US"],
        notes="Seized December 2025 alongside Skipper.",
        last_updated=datetime(2025, 12, 20)
    ),
    DarkFleetVessel(
        name="Bella 1",
        status=VesselStatus.PURSUED,
        notes="Currently being pursued by U.S. Navy (December 2025).",
        last_updated=datetime(2025, 12, 28)
    ),
]

# High-risk flags for Venezuela dark fleet (based on UANI/Windward data)
VENEZUELA_DARK_FLEET_FLAGS = {
    "Cameroon",      # Skipper's flag
    "Gabon",
    "Palau",
    "Marshall Islands",  # Often used for shell company registration
    "Sao Tome and Principe",
    "Equatorial Guinea",
    "Comoros",
    "Togo",
    "Tanzania",
    "Djibouti",
}

# Shell company jurisdictions commonly used in Venezuela trade
SHELL_COMPANY_JURISDICTIONS = {
    "Marshall Islands",
    "Panama",
    "Liberia",
    "Nigeria",  # Thomarose Global Ventures Ltd (Skipper operator)
    "UAE",
    "Hong Kong",
}


# =============================================================================
# Deceptive Shipping Practices Detection
# =============================================================================

class DeceptionType(Enum):
    """Types of deceptive shipping practices."""
    AIS_SPOOFING = "ais_spoofing"
    GOING_DARK = "going_dark"
    FLAG_HOPPING = "flag_hopping"
    FALSE_FLAG = "false_flag"
    IDENTITY_LAUNDERING = "identity_laundering"  # "Zombie vessel"
    CIRCLE_SPOOFING = "circle_spoofing"
    GNSS_MANIPULATION = "gnss_manipulation"
    STS_CONCEALMENT = "sts_concealment"


@dataclass
class DeceptionEvent:
    """Detected deceptive shipping practice."""
    deception_type: DeceptionType
    mmsi: str
    detected_at: datetime
    location: Optional[Tuple[float, float]] = None  # (lat, lon)
    confidence: float = 0.5
    evidence: Dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"  # low, medium, high, critical

    def to_dict(self) -> dict:
        return {
            "deception_type": self.deception_type.value,
            "mmsi": self.mmsi,
            "detected_at": self.detected_at.isoformat(),
            "location": {"lat": self.location[0], "lon": self.location[1]} if self.location else None,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "severity": self.severity
        }


def detect_ais_spoofing(
    ais_positions: List[dict],
    satellite_positions: List[dict],
    mmsi: str,
    max_discrepancy_km: float = 10.0
) -> List[DeceptionEvent]:
    """
    Detect AIS spoofing by comparing AIS positions with satellite imagery.

    The Skipper case study: AIS showed vessel near Guyana while satellite
    images confirmed it was at Venezuela's Jose Terminal, 550 miles away.

    Args:
        ais_positions: AIS-reported positions with timestamps
        satellite_positions: Satellite-verified positions with timestamps
        mmsi: Vessel MMSI
        max_discrepancy_km: Maximum allowed discrepancy before flagging

    Returns:
        List of detected spoofing events
    """
    events = []

    for sat_pos in satellite_positions:
        sat_time = sat_pos.get("timestamp")
        sat_lat = sat_pos.get("lat", sat_pos.get("latitude"))
        sat_lon = sat_pos.get("lon", sat_pos.get("longitude"))

        if not sat_time or sat_lat is None or sat_lon is None:
            continue

        # Find closest AIS position in time
        closest_ais = _find_closest_ais_position(sat_time, ais_positions)

        if not closest_ais:
            continue

        ais_lat = closest_ais.get("lat", closest_ais.get("latitude"))
        ais_lon = closest_ais.get("lon", closest_ais.get("longitude"))

        if ais_lat is None or ais_lon is None:
            continue

        # Calculate discrepancy
        discrepancy_km = haversine(sat_lat, sat_lon, ais_lat, ais_lon)

        if discrepancy_km > max_discrepancy_km:
            # Determine severity based on discrepancy
            if discrepancy_km > 500:
                severity = "critical"
                confidence = 0.95
            elif discrepancy_km > 100:
                severity = "high"
                confidence = 0.85
            elif discrepancy_km > 50:
                severity = "medium"
                confidence = 0.70
            else:
                severity = "low"
                confidence = 0.50

            events.append(DeceptionEvent(
                deception_type=DeceptionType.AIS_SPOOFING,
                mmsi=mmsi,
                detected_at=sat_time if isinstance(sat_time, datetime) else datetime.fromisoformat(str(sat_time).replace("Z", "+00:00")),
                location=(sat_lat, sat_lon),
                confidence=confidence,
                severity=severity,
                evidence={
                    "ais_position": {"lat": ais_lat, "lon": ais_lon},
                    "satellite_position": {"lat": sat_lat, "lon": sat_lon},
                    "discrepancy_km": round(discrepancy_km, 2),
                    "discrepancy_nm": round(discrepancy_km / 1.852, 2),
                    "source": sat_pos.get("source", "satellite"),
                    "methodology": "Kpler/Windward satellite-AIS comparison"
                }
            ))

    return events


def detect_circle_spoofing(
    positions: List[dict],
    mmsi: str,
    min_points: int = 10,
    circularity_threshold: float = 0.85
) -> List[DeceptionEvent]:
    """
    Detect circle spoofing where AIS broadcasts geometric patterns.

    Circle spoofing is a common anomaly where a vessel's AIS signal
    broadcasts a perfect geometric circle or holding pattern, indicating
    the use of automated spoofing devices.

    Args:
        positions: List of position dicts with lat/lon
        mmsi: Vessel MMSI
        min_points: Minimum positions to analyze
        circularity_threshold: How circular the pattern must be (0-1)

    Returns:
        List of detected circle spoofing events
    """
    events = []

    if len(positions) < min_points:
        return events

    # Sort by timestamp
    sorted_positions = sorted(
        positions,
        key=lambda x: x.get("timestamp", datetime.min)
    )

    # Analyze in sliding windows
    window_size = min_points

    for i in range(len(sorted_positions) - window_size + 1):
        window = sorted_positions[i:i + window_size]

        # Calculate centroid
        lats = [p.get("lat", p.get("latitude", 0)) for p in window]
        lons = [p.get("lon", p.get("longitude", 0)) for p in window]

        centroid_lat = sum(lats) / len(lats)
        centroid_lon = sum(lons) / len(lons)

        # Calculate distances from centroid
        distances = []
        for p in window:
            lat = p.get("lat", p.get("latitude", 0))
            lon = p.get("lon", p.get("longitude", 0))
            dist = haversine(centroid_lat, centroid_lon, lat, lon)
            distances.append(dist)

        if not distances:
            continue

        # Check circularity: low variance in distances = circular pattern
        mean_dist = sum(distances) / len(distances)
        if mean_dist < 0.1:  # Too small to analyze
            continue

        variance = sum((d - mean_dist) ** 2 for d in distances) / len(distances)
        std_dev = variance ** 0.5
        coefficient_of_variation = std_dev / mean_dist if mean_dist > 0 else 1

        circularity = 1 - min(1, coefficient_of_variation)

        if circularity >= circularity_threshold:
            start_time = window[0].get("timestamp")
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))

            events.append(DeceptionEvent(
                deception_type=DeceptionType.CIRCLE_SPOOFING,
                mmsi=mmsi,
                detected_at=start_time or datetime.utcnow(),
                location=(centroid_lat, centroid_lon),
                confidence=circularity,
                severity="high",
                evidence={
                    "circularity_score": round(circularity, 3),
                    "radius_km": round(mean_dist, 3),
                    "point_count": len(window),
                    "pattern": "circular",
                    "methodology": "Geometric pattern analysis"
                }
            ))

    return events


def detect_identity_laundering(
    mmsi: str,
    vessel_name: str,
    imo: Optional[str] = None,
    scrapped_vessels_db: Optional[List[dict]] = None
) -> Optional[DeceptionEvent]:
    """
    Detect "zombie vessel" identity laundering.

    Operators purchase scrapped vessels' MMSI numbers and program them
    into active tankers. This allows a ship carrying sanctioned oil to
    masquerade digitally as a ship that was broken up years ago.

    Args:
        mmsi: Current vessel MMSI
        vessel_name: Current vessel name
        imo: IMO number if known
        scrapped_vessels_db: Database of known scrapped vessel identities

    Returns:
        DeceptionEvent if identity laundering detected
    """
    if scrapped_vessels_db is None:
        # Use built-in known zombie vessels
        scrapped_vessels_db = KNOWN_ZOMBIE_VESSELS

    for scrapped in scrapped_vessels_db:
        if mmsi == scrapped.get("mmsi") or imo == scrapped.get("imo"):
            return DeceptionEvent(
                deception_type=DeceptionType.IDENTITY_LAUNDERING,
                mmsi=mmsi,
                detected_at=datetime.utcnow(),
                confidence=0.9,
                severity="critical",
                evidence={
                    "scrapped_vessel_name": scrapped.get("name"),
                    "scrapped_date": scrapped.get("scrapped_date"),
                    "original_flag": scrapped.get("flag"),
                    "current_name": vessel_name,
                    "methodology": "Zombie vessel database cross-reference"
                }
            )

    return None


# Known scrapped vessels whose identities may be used for laundering
KNOWN_ZOMBIE_VESSELS = [
    # Add known scrapped vessel identities here
    # Format: {"name": "...", "mmsi": "...", "imo": "...", "scrapped_date": "..."}
]


def _find_closest_ais_position(
    target_time: datetime,
    positions: List[dict],
    max_gap_minutes: int = 30
) -> Optional[dict]:
    """Find the closest AIS position to a target time."""
    if not positions:
        return None

    best_pos = None
    best_gap = timedelta(minutes=max_gap_minutes + 1)

    for pos in positions:
        ts = pos.get("timestamp")
        if not ts:
            continue

        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except:
                continue

        if isinstance(target_time, str):
            try:
                target_time = datetime.fromisoformat(target_time.replace("Z", "+00:00"))
            except:
                continue

        gap = abs(ts - target_time)
        if gap < best_gap:
            best_gap = gap
            best_pos = pos

    if best_gap <= timedelta(minutes=max_gap_minutes):
        return best_pos
    return None


# =============================================================================
# Venezuela-Specific Alert System
# =============================================================================

class AlertType(Enum):
    """Types of Venezuela monitoring alerts."""
    TERMINAL_ARRIVAL = "terminal_arrival"
    STS_ZONE_ENTRY = "sts_zone_entry"
    DARK_VOYAGE = "dark_voyage"
    SPOOFING_DETECTED = "spoofing_detected"
    SANCTIONED_VESSEL = "sanctioned_vessel"
    FLAG_CHANGE = "flag_change"
    POSITION_DISCREPANCY = "position_discrepancy"


@dataclass
class VenezuelaAlert:
    """Alert for suspicious Venezuela-related activity."""
    alert_type: AlertType
    mmsi: str
    vessel_name: Optional[str]
    timestamp: datetime
    location: Optional[Tuple[float, float]]
    severity: str  # low, medium, high, critical
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "alert_type": self.alert_type.value,
            "mmsi": self.mmsi,
            "vessel_name": self.vessel_name,
            "timestamp": self.timestamp.isoformat(),
            "location": {"lat": self.location[0], "lon": self.location[1]} if self.location else None,
            "severity": self.severity,
            "description": self.description,
            "evidence": self.evidence
        }


def check_venezuela_alerts(
    mmsi: str,
    vessel_name: Optional[str],
    current_position: dict,
    track_history: List[dict],
    vessel_info: Optional[dict] = None
) -> List[VenezuelaAlert]:
    """
    Check for Venezuela-specific alert conditions.

    Alert triggers based on commercial intelligence methodologies:
    1. Vessel appears at Jose Terminal without prior AIS track
    2. AIS position differs from SAR detection by >5nm
    3. STS transfer detected in known transfer zones
    4. Vessel switches flag or name while in region
    5. Previously sanctioned vessel enters bounding box

    Args:
        mmsi: Vessel MMSI
        vessel_name: Vessel name if known
        current_position: Current position dict
        track_history: Historical positions
        vessel_info: Additional vessel information

    Returns:
        List of triggered alerts
    """
    alerts = []

    lat = current_position.get("lat", current_position.get("latitude"))
    lon = current_position.get("lon", current_position.get("longitude"))
    timestamp = current_position.get("timestamp", datetime.utcnow())

    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    if lat is None or lon is None:
        return alerts

    # Check if in Venezuela monitoring zone
    if not is_in_venezuela_zone(lat, lon):
        return alerts

    # Alert 1: Check proximity to key points
    for point in VENEZUELA_KEY_POINTS:
        point_lat = point["lat"]
        point_lon = point["lon"]
        point_type = point["type"]

        # Determine radius based on point type
        if point_type == "terminal":
            radius = TERMINAL_DETECTION_RADIUS_KM
        elif point_type == "sts_zone":
            radius = STS_ZONE_RADIUS_KM
        else:
            radius = ANCHORAGE_RADIUS_KM

        distance = haversine(lat, lon, point_lat, point_lon)

        if distance <= radius:
            if point_type == "terminal":
                # Check for dark arrival (no prior track)
                has_prior_track = _has_approaching_track(
                    track_history, point_lat, point_lon, hours=24
                )

                if not has_prior_track:
                    alerts.append(VenezuelaAlert(
                        alert_type=AlertType.TERMINAL_ARRIVAL,
                        mmsi=mmsi,
                        vessel_name=vessel_name,
                        timestamp=timestamp,
                        location=(lat, lon),
                        severity="critical",
                        description=f"Vessel appeared at {point['name']} without prior AIS track",
                        evidence={
                            "terminal": point["name"],
                            "distance_km": round(distance, 2),
                            "track_history_hours": 24,
                            "prior_positions": len(track_history)
                        }
                    ))
                else:
                    alerts.append(VenezuelaAlert(
                        alert_type=AlertType.TERMINAL_ARRIVAL,
                        mmsi=mmsi,
                        vessel_name=vessel_name,
                        timestamp=timestamp,
                        location=(lat, lon),
                        severity="high",
                        description=f"Vessel arrived at {point['name']}",
                        evidence={
                            "terminal": point["name"],
                            "distance_km": round(distance, 2)
                        }
                    ))

            elif point_type == "sts_zone":
                alerts.append(VenezuelaAlert(
                    alert_type=AlertType.STS_ZONE_ENTRY,
                    mmsi=mmsi,
                    vessel_name=vessel_name,
                    timestamp=timestamp,
                    location=(lat, lon),
                    severity="high",
                    description=f"Vessel entered STS transfer zone: {point['name']}",
                    evidence={
                        "zone": point["name"],
                        "distance_km": round(distance, 2),
                        "zone_description": point["description"]
                    }
                ))

    # Alert 2: Check if known sanctioned vessel
    for known_vessel in KNOWN_DARK_FLEET_VESSELS:
        if known_vessel.mmsi == mmsi or known_vessel.name == vessel_name:
            alerts.append(VenezuelaAlert(
                alert_type=AlertType.SANCTIONED_VESSEL,
                mmsi=mmsi,
                vessel_name=vessel_name,
                timestamp=timestamp,
                location=(lat, lon),
                severity="critical",
                description=f"Known dark fleet vessel detected: {known_vessel.name}",
                evidence={
                    "vessel_status": known_vessel.status.value,
                    "sanctioned_by": known_vessel.sanctioned_by,
                    "former_names": known_vessel.former_names,
                    "notes": known_vessel.notes
                }
            ))
            break

    # Alert 3: Check for high-risk flag
    if vessel_info:
        flag = vessel_info.get("flag_state") or vessel_info.get("flag")
        if flag and flag in VENEZUELA_DARK_FLEET_FLAGS:
            alerts.append(VenezuelaAlert(
                alert_type=AlertType.SANCTIONED_VESSEL,
                mmsi=mmsi,
                vessel_name=vessel_name,
                timestamp=timestamp,
                location=(lat, lon),
                severity="medium",
                description=f"Vessel with high-risk flag ({flag}) in Venezuela zone",
                evidence={
                    "flag": flag,
                    "risk_category": "venezuela_dark_fleet_flag"
                }
            ))

    # Alert 4: Check for AIS gaps (going dark)
    ais_gaps = detect_ais_gaps(track_history, mmsi, max_gap_minutes=120, min_gap_minutes=60)
    for gap in ais_gaps:
        # Check if gap occurred in Venezuela zone
        gap_lat = gap.latitude
        gap_lon = gap.longitude
        if is_in_venezuela_zone(gap_lat, gap_lon):
            alerts.append(VenezuelaAlert(
                alert_type=AlertType.DARK_VOYAGE,
                mmsi=mmsi,
                vessel_name=vessel_name,
                timestamp=gap.start_time,
                location=(gap_lat, gap_lon),
                severity="high",
                description=f"Vessel went dark for {gap.details.get('gap_hours', 0):.1f} hours in Venezuela zone",
                evidence=gap.details
            ))

    return alerts


def is_in_venezuela_zone(lat: float, lon: float) -> bool:
    """Check if coordinates are within Venezuela monitoring zone."""
    return (
        VENEZUELA_BOUNDS["south"] <= lat <= VENEZUELA_BOUNDS["north"] and
        VENEZUELA_BOUNDS["west"] <= lon <= VENEZUELA_BOUNDS["east"]
    )


def _has_approaching_track(
    track_history: List[dict],
    terminal_lat: float,
    terminal_lon: float,
    hours: int = 24
) -> bool:
    """Check if vessel has a visible approach track to terminal."""
    if len(track_history) < 3:
        return False

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Filter recent positions
    recent_positions = []
    for pos in track_history:
        ts = pos.get("timestamp")
        if ts:
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if ts >= cutoff:
                recent_positions.append(pos)

    # Need at least 3 positions showing approach
    if len(recent_positions) < 3:
        return False

    # Check if distances are decreasing (approaching)
    distances = []
    for pos in sorted(recent_positions, key=lambda x: x.get("timestamp", datetime.min)):
        lat = pos.get("lat", pos.get("latitude", 0))
        lon = pos.get("lon", pos.get("longitude", 0))
        dist = haversine(lat, lon, terminal_lat, terminal_lon)
        distances.append(dist)

    if len(distances) < 2:
        return False

    # Check if generally approaching (not strict monotonic)
    approaching_count = sum(1 for i in range(1, len(distances)) if distances[i] < distances[i-1])
    return approaching_count >= len(distances) // 2


# =============================================================================
# Venezuela Risk Scoring
# =============================================================================

def calculate_venezuela_risk_score(
    mmsi: str,
    vessel_info: Optional[dict] = None,
    track_history: Optional[List[dict]] = None,
    satellite_positions: Optional[List[dict]] = None
) -> Dict[str, Any]:
    """
    Calculate Venezuela-specific dark fleet risk score.

    Combines multiple indicators based on Kpler/Windward methodology:
    - Flag risk (shadow fleet flags)
    - Behavioral indicators (AIS gaps, spoofing)
    - Geographic risk (presence in STS zones)
    - Network risk (known dark fleet associations)

    Args:
        mmsi: Vessel MMSI
        vessel_info: Vessel details (flag, type, owner, etc.)
        track_history: Historical AIS positions
        satellite_positions: SAR/optical satellite detections

    Returns:
        Risk assessment with score and breakdown
    """
    score = 0
    factors = []

    vessel_info = vessel_info or {}
    track_history = track_history or []
    satellite_positions = satellite_positions or []

    # Factor 1: Flag Risk (0-30 points)
    flag = vessel_info.get("flag_state") or vessel_info.get("flag")
    if flag:
        if flag in VENEZUELA_DARK_FLEET_FLAGS:
            score += 30
            factors.append({
                "factor": "venezuela_dark_fleet_flag",
                "points": 30,
                "detail": f"{flag} is associated with Venezuela dark fleet operations"
            })
        elif is_shadow_fleet_flag(flag):
            score += 20
            factors.append({
                "factor": "shadow_fleet_flag",
                "points": 20,
                "detail": f"{flag} is a known shadow fleet registry"
            })
        elif is_flag_of_convenience(flag):
            score += 10
            factors.append({
                "factor": "flag_of_convenience",
                "points": 10,
                "detail": f"{flag} is a flag of convenience"
            })

    # Factor 2: Known Vessel Match (0-40 points)
    vessel_name = vessel_info.get("name", "")
    for known_vessel in KNOWN_DARK_FLEET_VESSELS:
        if (known_vessel.mmsi == mmsi or
            known_vessel.name == vessel_name or
            vessel_name in known_vessel.former_names):
            score += 40
            factors.append({
                "factor": "known_dark_fleet_vessel",
                "points": 40,
                "detail": f"Matches known vessel: {known_vessel.name}",
                "status": known_vessel.status.value
            })
            break

    # Factor 3: AIS Behavior (0-20 points)
    if track_history:
        ais_gaps = detect_ais_gaps(track_history, mmsi)
        spoofing_events = detect_spoofing(track_history, mmsi)

        gap_count = len(ais_gaps)
        if gap_count >= 5:
            score += 20
            factors.append({
                "factor": "ais_gaps",
                "points": 20,
                "detail": f"{gap_count} AIS transmission gaps detected"
            })
        elif gap_count >= 2:
            score += 10
            factors.append({
                "factor": "ais_gaps",
                "points": 10,
                "detail": f"{gap_count} AIS transmission gaps detected"
            })

        if spoofing_events:
            score += 15
            factors.append({
                "factor": "position_anomalies",
                "points": 15,
                "detail": f"{len(spoofing_events)} position anomalies detected"
            })

    # Factor 4: Satellite Discrepancy (0-25 points)
    if satellite_positions and track_history:
        spoofing_detections = detect_ais_spoofing(
            track_history, satellite_positions, mmsi
        )
        if spoofing_detections:
            max_discrepancy = max(
                d.evidence.get("discrepancy_km", 0)
                for d in spoofing_detections
            )
            if max_discrepancy > 100:
                score += 25
                factors.append({
                    "factor": "satellite_discrepancy",
                    "points": 25,
                    "detail": f"AIS-satellite discrepancy of {max_discrepancy:.0f}km detected"
                })
            elif max_discrepancy > 20:
                score += 15
                factors.append({
                    "factor": "satellite_discrepancy",
                    "points": 15,
                    "detail": f"AIS-satellite discrepancy of {max_discrepancy:.0f}km detected"
                })

    # Factor 5: Venezuela Zone Presence (0-10 points)
    in_zone_count = 0
    for pos in track_history[-100:]:  # Check last 100 positions
        lat = pos.get("lat", pos.get("latitude"))
        lon = pos.get("lon", pos.get("longitude"))
        if lat and lon and is_in_venezuela_zone(lat, lon):
            in_zone_count += 1

    if in_zone_count > 50:
        score += 10
        factors.append({
            "factor": "venezuela_zone_presence",
            "points": 10,
            "detail": f"Extended presence in Venezuela monitoring zone ({in_zone_count} positions)"
        })
    elif in_zone_count > 20:
        score += 5
        factors.append({
            "factor": "venezuela_zone_presence",
            "points": 5,
            "detail": f"Presence in Venezuela monitoring zone ({in_zone_count} positions)"
        })

    # Cap score at 100
    score = min(100, score)

    # Determine risk level
    if score >= 70:
        risk_level = "critical"
        assessment = "High probability of Venezuela sanctions evasion"
    elif score >= 50:
        risk_level = "high"
        assessment = "Multiple dark fleet indicators present"
    elif score >= 30:
        risk_level = "medium"
        assessment = "Some concerning indicators detected"
    elif score >= 15:
        risk_level = "low"
        assessment = "Minor risk factors present"
    else:
        risk_level = "minimal"
        assessment = "No significant Venezuela dark fleet indicators"

    return {
        "score": score,
        "risk_level": risk_level,
        "assessment": assessment,
        "factors": factors,
        "region": "venezuela_caribbean",
        "methodology": "Based on Kpler/Windward/UANI detection criteria"
    }


# =============================================================================
# Export Configuration
# =============================================================================

def get_venezuela_monitoring_config() -> Dict[str, Any]:
    """
    Get complete Venezuela monitoring configuration.

    Returns configuration suitable for the Arsenal Ship Tracker's
    bounding box and watchlist systems.
    """
    return {
        "region": VENEZUELA_BOUNDS,
        "key_points": VENEZUELA_KEY_POINTS,
        "detection_radii": {
            "terminal": TERMINAL_DETECTION_RADIUS_KM,
            "sts_zone": STS_ZONE_RADIUS_KM,
            "anchorage": ANCHORAGE_RADIUS_KM
        },
        "dark_fleet_flags": list(VENEZUELA_DARK_FLEET_FLAGS),
        "known_vessels": [v.to_dict() for v in KNOWN_DARK_FLEET_VESSELS],
        "alert_types": [t.value for t in AlertType],
        "deception_types": [d.value for d in DeceptionType]
    }
