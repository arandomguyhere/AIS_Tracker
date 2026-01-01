"""
Dark Fleet Detection Module

Multi-region sanctions evasion detection for:
- Russia: Shadow fleet evading oil price cap (3,300+ vessels)
- Iran: Sanctions evasion via Malaysia STS hub (1.6M bpd exports)
- Venezuela: Caribbean dark fleet operations (40% of sanctioned tankers)
- China: Destination ports and teapot refineries receiving sanctioned oil

Based on methodologies from:
- Kpler maritime intelligence
- Windward AI analytics
- UANI (United Against Nuclear Iran)
- KSE (Kyiv School of Economics) Russian Oil Tracker
- TankerTrackers.com

Key Detection Methods:
- AIS spoofing and "going dark" detection
- Ship-to-ship (STS) transfer monitoring
- Flag hopping and false flag identification
- Identity laundering / "zombie vessel" detection
- Port call analysis at known sanctioned facilities

References:
- Kpler 2025: 3,300 shadow fleet vessels, 6-7% of global crude
- Windward 2025: 1,900+ dark fleet vessels, 1,000+ sanctioned
- UANI 2025: Iran exports 1.6M bpd via shadow fleet
- KSE 2025: 610 sanctioned tankers for Russian oil
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
# Region Definitions
# =============================================================================

class Region(Enum):
    """Sanctioned regions for dark fleet monitoring."""
    RUSSIA = "russia"
    IRAN = "iran"
    VENEZUELA = "venezuela"
    CHINA = "china"  # Destination/receiver


# =============================================================================
# Monitoring Zones by Region
# =============================================================================

REGION_BOUNDS = {
    Region.RUSSIA: [
        {
            "name": "Baltic/Primorsk",
            "north": 60.5,
            "south": 59.0,
            "east": 30.0,
            "west": 27.0,
            "description": "Baltic Sea export zone - Primorsk, Ust-Luga"
        },
        {
            "name": "Black Sea",
            "north": 46.0,
            "south": 41.0,
            "east": 42.0,
            "west": 27.0,
            "description": "Black Sea - Novorossiysk, Tuapse"
        },
        {
            "name": "Pacific/Kozmino",
            "north": 43.5,
            "south": 42.0,
            "east": 134.0,
            "west": 131.0,
            "description": "Pacific ESPO terminal - Kozmino"
        },
        {
            "name": "Murmansk Arctic",
            "north": 70.0,
            "south": 68.0,
            "east": 35.0,
            "west": 30.0,
            "description": "Arctic oil exports - Murmansk"
        }
    ],
    Region.IRAN: [
        {
            "name": "Persian Gulf/Kharg",
            "north": 30.0,
            "south": 25.0,
            "east": 55.0,
            "west": 48.0,
            "description": "Persian Gulf - Kharg Island (90% of Iran exports)"
        },
        {
            "name": "Malaysia STS Zone",
            "north": 6.0,
            "south": 1.0,
            "east": 108.0,
            "west": 103.0,
            "description": "Eastern Johor STS hub - 500+ transfers in 2025"
        },
        {
            "name": "Strait of Hormuz",
            "north": 27.0,
            "south": 25.5,
            "east": 57.0,
            "west": 54.0,
            "description": "Critical chokepoint for Iranian exports"
        }
    ],
    Region.VENEZUELA: [
        {
            "name": "Venezuela Caribbean",
            "north": 15.0,
            "south": 8.0,
            "east": -58.0,
            "west": -72.0,
            "description": "Primary Venezuela monitoring zone"
        }
    ],
    Region.CHINA: [
        {
            "name": "Shandong/Qingdao",
            "north": 38.0,
            "south": 35.0,
            "east": 122.0,
            "west": 118.0,
            "description": "Teapot refinery hub - 90% of Iran oil imports"
        },
        {
            "name": "Dalian/Liaoning",
            "north": 40.0,
            "south": 38.5,
            "east": 123.0,
            "west": 120.0,
            "description": "Northern China import terminal"
        },
        {
            "name": "Zhoushan/Ningbo",
            "north": 31.0,
            "south": 29.0,
            "east": 123.0,
            "west": 121.0,
            "description": "Major STS and import zone"
        },
        {
            "name": "Huizhou/Guangdong",
            "north": 23.5,
            "south": 22.0,
            "east": 115.5,
            "west": 113.5,
            "description": "Southern China import terminal"
        }
    ]
}


# =============================================================================
# Key Points by Region
# =============================================================================

KEY_POINTS = {
    Region.RUSSIA: [
        # Baltic
        {"name": "Primorsk Terminal", "lat": 60.35, "lon": 28.67, "type": "terminal",
         "description": "Russia's largest Baltic oil export terminal (+360K BPD)", "risk_level": "critical"},
        {"name": "Ust-Luga Terminal", "lat": 59.68, "lon": 28.40, "type": "terminal",
         "description": "Major Baltic oil products terminal (+160K BPD)", "risk_level": "critical"},
        # Black Sea
        {"name": "Novorossiysk Terminal", "lat": 44.72, "lon": 37.79, "type": "terminal",
         "description": "Black Sea oil export hub (+250K BPD crude)", "risk_level": "critical"},
        {"name": "CPC Terminal", "lat": 44.77, "lon": 37.85, "type": "terminal",
         "description": "Caspian Pipeline Consortium terminal", "risk_level": "high"},
        {"name": "Tuapse Refinery", "lat": 44.10, "lon": 39.08, "type": "refinery",
         "description": "Black Sea refinery and export point", "risk_level": "high"},
        {"name": "Kavkaz STS Zone", "lat": 45.35, "lon": 36.70, "type": "sts_zone",
         "description": "Kerch Strait STS transfer area", "risk_level": "critical"},
        # Pacific
        {"name": "Kozmino Terminal", "lat": 42.73, "lon": 133.02, "type": "terminal",
         "description": "ESPO pipeline terminus, Pacific exports ($62.8/bbl)", "risk_level": "critical"},
        # Arctic
        {"name": "Murmansk Terminal", "lat": 68.97, "lon": 33.05, "type": "terminal",
         "description": "Arctic oil export facility", "risk_level": "high"},
        # Mediterranean STS
        {"name": "Kalamata STS Zone", "lat": 36.80, "lon": 22.10, "type": "sts_zone",
         "description": "Greek waters STS transfer zone", "risk_level": "high"},
        {"name": "Ceuta STS Zone", "lat": 35.90, "lon": -5.30, "type": "sts_zone",
         "description": "Gibraltar Strait STS transfers", "risk_level": "high"},
    ],
    Region.IRAN: [
        # Persian Gulf
        {"name": "Kharg Island", "lat": 29.23, "lon": 50.32, "type": "terminal",
         "description": "Iran's largest export facility (90% of crude)", "risk_level": "critical"},
        {"name": "Bandar Abbas", "lat": 27.18, "lon": 56.27, "type": "terminal",
         "description": "Major port and naval base", "risk_level": "high"},
        {"name": "Lavan Island", "lat": 26.80, "lon": 53.35, "type": "terminal",
         "description": "Offshore oil export terminal", "risk_level": "high"},
        {"name": "Sirri Island", "lat": 25.88, "lon": 54.53, "type": "terminal",
         "description": "Offshore storage and export", "risk_level": "high"},
        # Malaysia STS Hub
        {"name": "Johor STS Zone", "lat": 1.50, "lon": 104.50, "type": "sts_zone",
         "description": "Primary Iran-China STS hub (500+ transfers 2025)", "risk_level": "critical"},
        {"name": "Linggi STS Zone", "lat": 2.40, "lon": 101.95, "type": "sts_zone",
         "description": "Malacca Strait STS area", "risk_level": "high"},
        {"name": "Tanjung Pelepas Anchorage", "lat": 1.35, "lon": 103.55, "type": "anchorage",
         "description": "Staging area for STS operations", "risk_level": "medium"},
    ],
    Region.VENEZUELA: [
        {"name": "Jose Terminal", "lat": 10.15, "lon": -64.68, "type": "terminal",
         "description": "Venezuela's primary oil export facility", "risk_level": "critical"},
        {"name": "La Borracha STS Zone", "lat": 10.08, "lon": -64.89, "type": "sts_zone",
         "description": "Known ship-to-ship transfer area", "risk_level": "critical"},
        {"name": "Barcelona STS Zone", "lat": 10.12, "lon": -64.72, "type": "sts_zone",
         "description": "STS transfer zone near Barcelona, Venezuela", "risk_level": "high"},
        {"name": "Amuay Refinery", "lat": 11.74, "lon": -70.21, "type": "refinery",
         "description": "Major Venezuelan refinery complex", "risk_level": "high"},
        {"name": "Paraguana Peninsula", "lat": 11.95, "lon": -70.00, "type": "anchorage",
         "description": "Staging area for dark fleet vessels", "risk_level": "medium"},
        {"name": "Curacao Anchorage", "lat": 12.10, "lon": -68.95, "type": "anchorage",
         "description": "Offshore anchorage used for STS transfers", "risk_level": "medium"},
    ],
    Region.CHINA: [
        # Shandong Teapot Zone
        {"name": "Qingdao Port", "lat": 36.07, "lon": 120.38, "type": "terminal",
         "description": "Major crude import terminal for teapot refineries", "risk_level": "high"},
        {"name": "Rizhao Port", "lat": 35.38, "lon": 119.53, "type": "terminal",
         "description": "Shandong crude import terminal", "risk_level": "high"},
        {"name": "Dongying/Shengli", "lat": 37.45, "lon": 118.50, "type": "refinery",
         "description": "Shandong teapot refinery cluster", "risk_level": "high"},
        {"name": "Yantai Port", "lat": 37.55, "lon": 121.40, "type": "terminal",
         "description": "Shandong Province import terminal", "risk_level": "medium"},
        # Other Import Hubs
        {"name": "Dalian Port", "lat": 38.92, "lon": 121.64, "type": "terminal",
         "description": "Northern China crude import hub", "risk_level": "medium"},
        {"name": "Zhoushan STS Zone", "lat": 30.00, "lon": 122.20, "type": "sts_zone",
         "description": "Major STS and storage zone", "risk_level": "high"},
        {"name": "Ningbo-Zhoushan Port", "lat": 29.87, "lon": 121.85, "type": "terminal",
         "description": "World's largest port by cargo tonnage", "risk_level": "medium"},
    ]
}


# =============================================================================
# Flags Associated with Dark Fleet by Region
# =============================================================================

DARK_FLEET_FLAGS = {
    Region.RUSSIA: [
        "Cameroon", "Gabon", "Palau", "Togo", "Tanzania",
        "Sao Tome and Principe", "Comoros", "Djibouti",
        "Equatorial Guinea", "Marshall Islands", "Liberia",
        "Panama", "Cook Islands", "Niue", "Nauru"
    ],
    Region.IRAN: [
        "Cameroon", "Tanzania", "Palau", "Togo", "Comoros",
        "Sao Tome and Principe", "Gabon", "Djibouti",
        "Equatorial Guinea", "Honduras", "Mongolia",
        "Zanzibar", "Central African Republic"
    ],
    Region.VENEZUELA: [
        "Tanzania", "Palau", "Comoros", "Djibouti",
        "Equatorial Guinea", "Togo", "Sao Tome and Principe",
        "Marshall Islands", "Gabon", "Cameroon"
    ],
    Region.CHINA: [
        # Flags commonly seen on vessels delivering to China
        "Panama", "Liberia", "Marshall Islands", "Hong Kong",
        "Singapore", "Malta", "Bahamas", "Cyprus"
    ]
}

# Newly emerged fraudulent registries (2024-2025)
FRAUDULENT_REGISTRIES = [
    "Tonga", "Maldives", "Mozambique", "Angola",
    "Botswana", "Zambia", "Gambia", "Zanzibar",
    "Central African Republic"
]


# =============================================================================
# Detection Radii
# =============================================================================

DETECTION_RADII_KM = {
    "terminal": 10.0,
    "sts_zone": 25.0,
    "refinery": 15.0,
    "anchorage": 15.0,
    "spoofing_target": 50.0
}


# =============================================================================
# Vessel Status and Data Classes
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
    region: Region
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
            "region": self.region.value,
            "mmsi": self.mmsi,
            "imo": self.imo,
            "former_names": self.former_names,
            "flag": self.flag,
            "status": self.status.value,
            "sanctioned_by": self.sanctioned_by,
            "notes": self.notes,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None
        }


# =============================================================================
# Known Dark Fleet Vessels Database
# =============================================================================

KNOWN_DARK_FLEET_VESSELS = [
    # Venezuela
    DarkFleetVessel(
        name="Skipper",
        region=Region.VENEZUELA,
        imo="9179834",
        former_names=["Adisa"],
        flag="Cameroon",
        status=VesselStatus.SEIZED,
        sanctioned_by=["US", "UK"],
        notes="Seized December 2025. 80+ days AIS spoofing. Iran-Venezuela-China route.",
        last_updated=datetime(2025, 12, 20)
    ),
    DarkFleetVessel(
        name="Centuries",
        region=Region.VENEZUELA,
        status=VesselStatus.SEIZED,
        sanctioned_by=["US"],
        notes="Seized December 2025 alongside Skipper.",
        last_updated=datetime(2025, 12, 20)
    ),
    DarkFleetVessel(
        name="Bella 1",
        region=Region.VENEZUELA,
        status=VesselStatus.PURSUED,
        notes="Pursued by U.S. Navy December 2025.",
        last_updated=datetime(2025, 12, 28)
    ),
    # Russia - Black Sea
    DarkFleetVessel(
        name="Virat",
        region=Region.RUSSIA,
        status=VesselStatus.FLAGGED,
        notes="Struck by Ukraine SBU drone November 2025, Black Sea.",
        last_updated=datetime(2025, 11, 25)
    ),
    DarkFleetVessel(
        name="Kairos",
        region=Region.RUSSIA,
        status=VesselStatus.FLAGGED,
        notes="Struck by Ukraine SBU drone November 2025, Turkish waters.",
        last_updated=datetime(2025, 11, 25)
    ),
    DarkFleetVessel(
        name="Dashan",
        region=Region.RUSSIA,
        status=VesselStatus.SANCTIONED,
        sanctioned_by=["EU"],
        notes="EU-sanctioned tanker struck by Ukraine drone, Black Sea.",
        last_updated=datetime(2025, 11, 28)
    ),
    # Iran - Malaysia STS
    DarkFleetVessel(
        name="Vani",
        region=Region.IRAN,
        status=VesselStatus.ACTIVE,
        notes="Disappeared May 2025 off Malaysia, reappeared with full load. Delivered to Qingdao.",
        last_updated=datetime(2025, 5, 20)
    ),
    DarkFleetVessel(
        name="Nora",
        region=Region.IRAN,
        status=VesselStatus.SANCTIONED,
        sanctioned_by=["US"],
        notes="Loaded crude at Kharg Island, transferred to Vani via STS.",
        last_updated=datetime(2025, 5, 20)
    ),
    DarkFleetVessel(
        name="Reston",
        region=Region.IRAN,
        status=VesselStatus.SANCTIONED,
        sanctioned_by=["US"],
        notes="Received 1M+ barrels Iranian oil via STS early 2025.",
        last_updated=datetime(2025, 3, 1)
    ),
]


# =============================================================================
# Alert Types
# =============================================================================

class AlertType(Enum):
    """Types of dark fleet alerts."""
    TERMINAL_ARRIVAL = "terminal_arrival"
    STS_ZONE_ENTRY = "sts_zone_entry"
    DARK_VOYAGE = "dark_voyage"
    SPOOFING_DETECTED = "spoofing_detected"
    SANCTIONED_VESSEL = "sanctioned_vessel"
    FLAG_CHANGE = "flag_change"
    POSITION_DISCREPANCY = "position_discrepancy"
    KNOWN_DARK_FLEET = "known_dark_fleet"
    FRAUDULENT_FLAG = "fraudulent_flag"
    DESTINATION_MISMATCH = "destination_mismatch"


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class DarkFleetAlert:
    """Dark fleet detection alert."""
    alert_type: AlertType
    region: Region
    severity: AlertSeverity
    vessel_mmsi: str
    vessel_name: Optional[str]
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "alert_type": self.alert_type.value,
            "region": self.region.value,
            "severity": self.severity.value,
            "vessel_mmsi": self.vessel_mmsi,
            "vessel_name": self.vessel_name,
            "description": self.description,
            "evidence": self.evidence,
            "timestamp": self.timestamp.isoformat()
        }


# =============================================================================
# Zone Detection Functions
# =============================================================================

def is_in_region_zone(lat: float, lon: float, region: Region) -> bool:
    """Check if position is within any monitoring zone for the region."""
    bounds_list = REGION_BOUNDS.get(region, [])
    for bounds in bounds_list:
        if (bounds["south"] <= lat <= bounds["north"] and
            bounds["west"] <= lon <= bounds["east"]):
            return True
    return False


def is_in_any_monitored_zone(lat: float, lon: float) -> List[Region]:
    """Check which monitored regions a position falls within."""
    regions = []
    for region in Region:
        if is_in_region_zone(lat, lon, region):
            regions.append(region)
    return regions


def get_nearby_key_points(lat: float, lon: float, region: Optional[Region] = None,
                          max_distance_km: float = 50.0) -> List[Dict[str, Any]]:
    """Find key points within specified distance of position."""
    nearby = []

    regions_to_check = [region] if region else list(Region)

    for r in regions_to_check:
        points = KEY_POINTS.get(r, [])
        for point in points:
            distance = haversine(lat, lon, point["lat"], point["lon"])
            if distance <= max_distance_km:
                nearby.append({
                    **point,
                    "region": r.value,
                    "distance_km": round(distance, 2)
                })

    return sorted(nearby, key=lambda x: x["distance_km"])


# =============================================================================
# Risk Scoring
# =============================================================================

def calculate_dark_fleet_risk_score(
    mmsi: str,
    vessel_info: Optional[dict] = None,
    track_history: Optional[List[dict]] = None,
    satellite_positions: Optional[List[dict]] = None,
    target_region: Optional[Region] = None
) -> Dict[str, Any]:
    """
    Calculate dark fleet risk score across all monitored regions.

    Args:
        mmsi: Vessel MMSI
        vessel_info: Vessel details (flag, type, owner, etc.)
        track_history: Historical AIS positions
        satellite_positions: SAR/optical satellite detections
        target_region: Optional specific region to score for

    Returns:
        Risk assessment with score, breakdown by region, and factors
    """
    score = 0
    factors = []
    region_scores = {}

    vessel_info = vessel_info or {}
    track_history = track_history or []
    satellite_positions = satellite_positions or []

    regions_to_check = [target_region] if target_region else list(Region)

    # Factor 1: Flag Risk (0-35 points)
    flag = vessel_info.get("flag_state") or vessel_info.get("flag")
    if flag:
        # Check fraudulent registries first
        if flag in FRAUDULENT_REGISTRIES:
            score += 35
            factors.append({
                "factor": "fraudulent_registry",
                "points": 35,
                "detail": f"{flag} is a known fraudulent/emerging dark fleet registry"
            })
        else:
            # Check region-specific dark fleet flags
            for region in regions_to_check:
                if flag in DARK_FLEET_FLAGS.get(region, []):
                    score += 25
                    factors.append({
                        "factor": "dark_fleet_flag",
                        "points": 25,
                        "detail": f"{flag} is associated with {region.value} dark fleet operations"
                    })
                    break
            else:
                if is_shadow_fleet_flag(flag):
                    score += 15
                    factors.append({
                        "factor": "shadow_fleet_flag",
                        "points": 15,
                        "detail": f"{flag} is a known shadow fleet registry"
                    })
                elif is_flag_of_convenience(flag):
                    score += 8
                    factors.append({
                        "factor": "flag_of_convenience",
                        "points": 8,
                        "detail": f"{flag} is a flag of convenience"
                    })

    # Factor 2: Known Dark Fleet Vessel (0-45 points)
    vessel_name = vessel_info.get("name", "").upper()
    vessel_imo = vessel_info.get("imo", "")

    for known in KNOWN_DARK_FLEET_VESSELS:
        name_match = known.name.upper() == vessel_name
        imo_match = known.imo and known.imo == vessel_imo
        former_match = vessel_name in [n.upper() for n in known.former_names]

        if name_match or imo_match or former_match:
            score += 45
            factors.append({
                "factor": "known_dark_fleet_vessel",
                "points": 45,
                "detail": f"Matches known dark fleet vessel: {known.name} ({known.region.value})",
                "status": known.status.value,
                "sanctioned_by": known.sanctioned_by
            })
            break

    # Factor 3: AIS Gaps (0-20 points)
    if track_history and mmsi:
        gaps = detect_ais_gaps(track_history, mmsi, min_gap_minutes=120)
        if gaps:
            total_gap_hours = sum(g.get("details", {}).get("gap_hours", 0) for g in gaps)
            if total_gap_hours > 48:
                score += 20
                factors.append({
                    "factor": "significant_ais_gaps",
                    "points": 20,
                    "detail": f"{len(gaps)} AIS gaps totaling {total_gap_hours:.0f} hours"
                })
            elif total_gap_hours > 12:
                score += 12
                factors.append({
                    "factor": "ais_gaps",
                    "points": 12,
                    "detail": f"{len(gaps)} AIS gaps totaling {total_gap_hours:.0f} hours"
                })

    # Factor 4: Regional Presence (0-15 points per region)
    if track_history:
        for region in regions_to_check:
            positions_in_region = 0
            for pos in track_history[-200:]:
                lat = pos.get("lat", pos.get("latitude"))
                lon = pos.get("lon", pos.get("longitude"))
                if lat and lon and is_in_region_zone(lat, lon, region):
                    positions_in_region += 1

            if positions_in_region > 20:
                region_points = min(15, positions_in_region // 10)
                score += region_points
                region_scores[region.value] = region_points
                factors.append({
                    "factor": f"{region.value}_zone_presence",
                    "points": region_points,
                    "detail": f"{positions_in_region} positions in {region.value} monitoring zone"
                })

    # Factor 5: AIS Spoofing Detection (0-30 points)
    if satellite_positions and track_history:
        max_discrepancy = 0
        for sat_pos in satellite_positions:
            sat_time = sat_pos.get("timestamp")
            sat_lat = sat_pos.get("lat")
            sat_lon = sat_pos.get("lon")

            if not all([sat_time, sat_lat, sat_lon]):
                continue

            # Find closest AIS position by time
            for ais_pos in track_history:
                ais_time = ais_pos.get("timestamp")
                if not ais_time:
                    continue

                # Within 1 hour
                if isinstance(sat_time, str):
                    sat_time = datetime.fromisoformat(sat_time.replace("Z", "+00:00"))
                if isinstance(ais_time, str):
                    ais_time = datetime.fromisoformat(ais_time.replace("Z", "+00:00"))

                time_diff = abs((sat_time - ais_time).total_seconds())
                if time_diff < 3600:
                    ais_lat = ais_pos.get("lat", ais_pos.get("latitude"))
                    ais_lon = ais_pos.get("lon", ais_pos.get("longitude"))
                    discrepancy = haversine(sat_lat, sat_lon, ais_lat, ais_lon)
                    max_discrepancy = max(max_discrepancy, discrepancy)

        if max_discrepancy > 100:
            score += 30
            factors.append({
                "factor": "ais_spoofing_critical",
                "points": 30,
                "detail": f"AIS-satellite discrepancy of {max_discrepancy:.0f}km (likely spoofing)"
            })
        elif max_discrepancy > 20:
            score += 15
            factors.append({
                "factor": "ais_spoofing_possible",
                "points": 15,
                "detail": f"AIS-satellite discrepancy of {max_discrepancy:.0f}km detected"
            })

    # Factor 6: Vessel Age (0-10 points)
    year_built = vessel_info.get("year_built")
    if year_built:
        age = datetime.now().year - int(year_built)
        if age > 20:
            score += 10
            factors.append({
                "factor": "vessel_age",
                "points": 10,
                "detail": f"Vessel is {age} years old (shadow fleet typically >15 years)"
            })
        elif age > 15:
            score += 5
            factors.append({
                "factor": "vessel_age",
                "points": 5,
                "detail": f"Vessel is {age} years old"
            })

    # Cap score at 100
    score = min(100, score)

    # Determine risk level
    if score >= 70:
        risk_level = "critical"
        assessment = "High probability of dark fleet / sanctions evasion activity"
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
        assessment = "No significant dark fleet indicators"

    return {
        "score": score,
        "risk_level": risk_level,
        "assessment": assessment,
        "factors": factors,
        "region_scores": region_scores,
        "regions_checked": [r.value for r in regions_to_check],
        "methodology": "Based on Kpler/Windward/UANI/KSE detection criteria"
    }


# =============================================================================
# Alert Detection
# =============================================================================

def check_dark_fleet_alerts(
    mmsi: str,
    vessel_name: Optional[str],
    current_position: dict,
    track_history: List[dict],
    vessel_info: Optional[dict] = None
) -> List[DarkFleetAlert]:
    """
    Check for dark fleet alerts across all monitored regions.

    Args:
        mmsi: Vessel MMSI
        vessel_name: Vessel name if known
        current_position: Current position dict with lat/lon
        track_history: Historical positions
        vessel_info: Additional vessel information

    Returns:
        List of triggered alerts
    """
    alerts = []
    vessel_info = vessel_info or {}

    lat = current_position.get("lat", current_position.get("latitude"))
    lon = current_position.get("lon", current_position.get("longitude"))

    if lat is None or lon is None:
        return alerts

    # Check which regions the vessel is in
    active_regions = is_in_any_monitored_zone(lat, lon)

    if not active_regions:
        return alerts

    for region in active_regions:
        # Alert 1: Key Point Proximity
        nearby_points = get_nearby_key_points(lat, lon, region, max_distance_km=25)
        for point in nearby_points:
            radius = DETECTION_RADII_KM.get(point["type"], 15.0)
            if point["distance_km"] <= radius:
                if point["type"] == "terminal":
                    alerts.append(DarkFleetAlert(
                        alert_type=AlertType.TERMINAL_ARRIVAL,
                        region=region,
                        severity=AlertSeverity.HIGH,
                        vessel_mmsi=mmsi,
                        vessel_name=vessel_name,
                        description=f"Vessel within {point['distance_km']:.1f}km of {point['name']}",
                        evidence={"point": point}
                    ))
                elif point["type"] == "sts_zone":
                    alerts.append(DarkFleetAlert(
                        alert_type=AlertType.STS_ZONE_ENTRY,
                        region=region,
                        severity=AlertSeverity.CRITICAL,
                        vessel_mmsi=mmsi,
                        vessel_name=vessel_name,
                        description=f"Vessel in STS transfer zone: {point['name']}",
                        evidence={"point": point}
                    ))

        # Alert 2: Fraudulent Flag
        flag = vessel_info.get("flag_state") or vessel_info.get("flag")
        if flag and flag in FRAUDULENT_REGISTRIES:
            alerts.append(DarkFleetAlert(
                alert_type=AlertType.FRAUDULENT_FLAG,
                region=region,
                severity=AlertSeverity.CRITICAL,
                vessel_mmsi=mmsi,
                vessel_name=vessel_name,
                description=f"Vessel flying fraudulent registry flag: {flag}",
                evidence={"flag": flag, "registry_type": "fraudulent"}
            ))

        # Alert 3: Known Dark Fleet Vessel
        vessel_name_upper = (vessel_name or "").upper()
        vessel_imo = vessel_info.get("imo", "")

        for known in KNOWN_DARK_FLEET_VESSELS:
            if (known.name.upper() == vessel_name_upper or
                (known.imo and known.imo == vessel_imo) or
                vessel_name_upper in [n.upper() for n in known.former_names]):
                alerts.append(DarkFleetAlert(
                    alert_type=AlertType.KNOWN_DARK_FLEET,
                    region=region,
                    severity=AlertSeverity.CRITICAL,
                    vessel_mmsi=mmsi,
                    vessel_name=vessel_name,
                    description=f"Known dark fleet vessel: {known.name}",
                    evidence=known.to_dict()
                ))
                break

    return alerts


# =============================================================================
# Configuration Export
# =============================================================================

def get_dark_fleet_config(region: Optional[Region] = None) -> Dict[str, Any]:
    """
    Get dark fleet monitoring configuration.

    Args:
        region: Optional specific region, or all if None

    Returns:
        Configuration for the monitoring system
    """
    if region:
        regions = [region]
    else:
        regions = list(Region)

    config = {
        "regions": [],
        "total_key_points": 0,
        "total_known_vessels": len(KNOWN_DARK_FLEET_VESSELS),
        "fraudulent_registries": FRAUDULENT_REGISTRIES,
        "detection_radii": DETECTION_RADII_KM,
        "alert_types": [t.value for t in AlertType],
        "methodology": "Based on Kpler, Windward, UANI, KSE detection criteria"
    }

    for r in regions:
        region_config = {
            "name": r.value,
            "bounds": REGION_BOUNDS.get(r, []),
            "key_points": KEY_POINTS.get(r, []),
            "dark_fleet_flags": DARK_FLEET_FLAGS.get(r, []),
            "known_vessels": [
                v.to_dict() for v in KNOWN_DARK_FLEET_VESSELS
                if v.region == r
            ]
        }
        config["regions"].append(region_config)
        config["total_key_points"] += len(region_config["key_points"])

    return config


def get_known_vessels_by_region(region: Optional[Region] = None) -> List[Dict]:
    """Get known dark fleet vessels, optionally filtered by region."""
    vessels = KNOWN_DARK_FLEET_VESSELS
    if region:
        vessels = [v for v in vessels if v.region == region]
    return [v.to_dict() for v in vessels]


# =============================================================================
# Statistics
# =============================================================================

def get_dark_fleet_statistics() -> Dict[str, Any]:
    """Get dark fleet statistics based on 2025 intelligence."""
    return {
        "global_statistics": {
            "total_shadow_fleet": 3300,
            "total_sanctioned_vessels": 1000,
            "global_crude_percentage": 6.7,
            "source": "Kpler 2025"
        },
        "by_region": {
            "russia": {
                "shadow_tankers": 610,
                "sanctioned_by": ["EU", "US", "UK", "CA", "NZ"],
                "exports_above_price_cap": True,
                "key_ports": ["Primorsk", "Kozmino", "Novorossiysk"],
                "source": "KSE October 2025"
            },
            "iran": {
                "exports_bpd": 1600000,
                "sts_transfers_2025": 500,
                "primary_sts_zone": "Eastern Johor, Malaysia",
                "primary_destination": "Shandong teapot refineries",
                "source": "UANI 2025"
            },
            "venezuela": {
                "share_of_sanctioned_tankers": 0.40,
                "caribbean_yoy_increase": 0.95,
                "recent_seizures": ["Skipper", "Centuries"],
                "source": "Windward 2025"
            },
            "china": {
                "teapot_refineries_share": 0.90,
                "sanctioned_refineries": ["Shandong Shengxing", "Hebei Xinhai"],
                "key_ports": ["Qingdao", "Rizhao", "Dalian", "Zhoushan"],
                "source": "US Treasury 2025"
            }
        },
        "trends_2025": {
            "dark_sts_transfers": "surging",
            "ais_spoofing": "persistently high",
            "fraudulent_flags": "1000+ vessels",
            "gambia_flag_growth": "626% Q4 2024",
            "source": "Kpler/Windward 2025"
        }
    }
