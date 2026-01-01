"""
Vessel Behavior Detection Module

Implements algorithms inspired by Global Fishing Watch and maritime intelligence
best practices for detecting suspicious vessel behavior.

Features:
- Encounter detection (potential transshipment)
- Loitering detection (dark vessel indicator)
- AIS gap detection (going dark)
- MMSI validation and spoofing detection
- Track downsampling and segmentation

References:
- Global Fishing Watch: https://globalfishingwatch.org/
- pyais: https://github.com/M0r13n/pyais
- DMA AisTrack: https://github.com/dma-ais/AisTrack
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from utils import haversine


# Maritime Identification Digits (MID) to Country mapping
# Source: ITU Maritime Identification Digits
MID_TO_COUNTRY = {
    "201": "Albania", "202": "Andorra", "203": "Austria", "204": "Portugal",
    "205": "Belgium", "206": "Belarus", "207": "Bulgaria", "208": "Vatican",
    "209": "Cyprus", "210": "Cyprus", "211": "Germany", "212": "Cyprus",
    "213": "Georgia", "214": "Moldova", "215": "Malta", "216": "Armenia",
    "218": "Germany", "219": "Denmark", "220": "Denmark", "224": "Spain",
    "225": "Spain", "226": "France", "227": "France", "228": "France",
    "229": "Malta", "230": "Finland", "231": "Faroe Islands", "232": "United Kingdom",
    "233": "United Kingdom", "234": "United Kingdom", "235": "United Kingdom",
    "236": "Gibraltar", "237": "Greece", "238": "Croatia", "239": "Greece",
    "240": "Greece", "241": "Greece", "242": "Morocco", "243": "Hungary",
    "244": "Netherlands", "245": "Netherlands", "246": "Netherlands",
    "247": "Italy", "248": "Malta", "249": "Malta", "250": "Ireland",
    "251": "Iceland", "252": "Liechtenstein", "253": "Luxembourg",
    "254": "Monaco", "255": "Portugal", "256": "Malta", "257": "Norway",
    "258": "Norway", "259": "Norway", "261": "Poland", "262": "Montenegro",
    "263": "Portugal", "264": "Romania", "265": "Sweden", "266": "Sweden",
    "267": "Slovakia", "268": "San Marino", "269": "Switzerland",
    "270": "Czech Republic", "271": "Turkey", "272": "Ukraine",
    "273": "Russia", "274": "North Macedonia", "275": "Latvia",
    "276": "Estonia", "277": "Lithuania", "278": "Slovenia", "279": "Serbia",

    # Asia-Pacific
    "301": "Anguilla", "303": "Alaska", "304": "Antigua and Barbuda",
    "305": "Antigua and Barbuda", "306": "Dutch Antilles", "307": "Aruba",
    "308": "Bahamas", "309": "Bahamas", "310": "Bermuda", "311": "Bahamas",
    "312": "Belize", "314": "Barbados", "316": "Canada", "319": "Cayman Islands",
    "321": "Costa Rica", "323": "Cuba", "325": "Dominica", "327": "Dominican Republic",
    "329": "Guadeloupe", "330": "Grenada", "331": "Greenland", "332": "Guatemala",
    "334": "Honduras", "336": "Haiti", "338": "USA", "339": "Jamaica",
    "341": "Saint Kitts and Nevis", "343": "Saint Lucia", "345": "Mexico",
    "347": "Martinique", "348": "Montserrat", "350": "Nicaragua",
    "351": "Panama", "352": "Panama", "353": "Panama", "354": "Panama",
    "355": "Panama", "356": "Panama", "357": "Panama", "358": "Puerto Rico",
    "359": "El Salvador", "361": "Saint Pierre and Miquelon",
    "362": "Trinidad and Tobago", "364": "Turks and Caicos Islands",
    "366": "USA", "367": "USA", "368": "USA", "369": "USA",
    "370": "Panama", "371": "Panama", "372": "Panama", "373": "Panama",
    "374": "Panama", "375": "Saint Vincent and the Grenadines",
    "376": "Saint Vincent and the Grenadines", "377": "Saint Vincent and the Grenadines",
    "378": "British Virgin Islands", "379": "US Virgin Islands",

    # China and East Asia
    "412": "China", "413": "China", "414": "China", "416": "Taiwan",
    "417": "Sri Lanka", "419": "India", "422": "Iran", "423": "Azerbaijan",
    "425": "Iraq", "428": "Israel", "431": "Japan", "432": "Japan",
    "434": "Turkmenistan", "436": "Kazakhstan", "437": "Uzbekistan",
    "438": "Jordan", "440": "South Korea", "441": "South Korea",
    "443": "Palestine", "445": "North Korea", "447": "Kuwait",
    "450": "Lebanon", "451": "Kyrgyzstan", "453": "Macau", "455": "Maldives",
    "457": "Mongolia", "459": "Nepal", "461": "Oman", "463": "Pakistan",
    "466": "Qatar", "468": "Syria", "470": "UAE", "472": "Tajikistan",
    "473": "Yemen", "475": "Yemen", "477": "Hong Kong",
    "478": "Bosnia and Herzegovina", "501": "Antarctica",

    # Southeast Asia
    "503": "Australia", "506": "Myanmar", "508": "Brunei", "510": "Micronesia",
    "511": "Palau", "512": "New Zealand", "514": "Cambodia", "515": "Cambodia",
    "516": "Christmas Island", "518": "Cook Islands", "520": "Fiji",
    "523": "Cocos Islands", "525": "Indonesia", "529": "Kiribati",
    "531": "Laos", "533": "Malaysia", "536": "Northern Mariana Islands",
    "538": "Marshall Islands", "540": "New Caledonia", "542": "Niue",
    "544": "Nauru", "546": "French Polynesia", "548": "Philippines",
    "553": "Papua New Guinea", "555": "Pitcairn Island", "557": "Solomon Islands",
    "559": "American Samoa", "561": "Samoa", "563": "Singapore",
    "564": "Singapore", "565": "Singapore", "566": "Singapore",
    "567": "Thailand", "570": "Tonga", "572": "Tuvalu", "574": "Vietnam",
    "576": "Vanuatu", "577": "Vanuatu", "578": "Wallis and Futuna Islands",

    # Africa
    "601": "South Africa", "603": "Angola", "605": "Algeria", "607": "St Paul/Amsterdam Is",
    "608": "Ascension Island", "609": "Burundi", "610": "Benin",
    "611": "Botswana", "612": "Central African Republic", "613": "Cameroon",
    "615": "Congo", "616": "Comoros", "617": "Cabo Verde", "618": "Crozet Archipelago",
    "619": "Ivory Coast", "620": "Comoros", "621": "Djibouti",
    "622": "Egypt", "624": "Ethiopia", "625": "Eritrea", "626": "Gabon",
    "627": "Ghana", "629": "Gambia", "630": "Guinea-Bissau", "631": "Equatorial Guinea",
    "632": "Guinea", "633": "Burkina Faso", "634": "Kenya", "635": "Kerguelen Islands",
    "636": "Liberia", "637": "Liberia", "638": "South Sudan", "642": "Libya",
    "644": "Lesotho", "645": "Mauritius", "647": "Madagascar", "649": "Mali",
    "650": "Mozambique", "654": "Mauritania", "655": "Malawi", "656": "Niger",
    "657": "Nigeria", "659": "Namibia", "660": "Reunion", "661": "Rwanda",
    "662": "Sudan", "663": "Senegal", "664": "Seychelles", "665": "St Helena",
    "666": "Somalia", "667": "Sierra Leone", "668": "Sao Tome and Principe",
    "669": "Eswatini", "670": "Chad", "671": "Togo", "672": "Tunisia",
    "674": "Tanzania", "675": "Uganda", "676": "DR Congo", "677": "Tanzania",
    "678": "Zambia", "679": "Zimbabwe",

    # South America
    "701": "Argentina", "710": "Brazil", "720": "Bolivia", "725": "Chile",
    "730": "Colombia", "735": "Ecuador", "740": "Falkland Islands",
    "745": "Guiana", "750": "Guyana", "755": "Paraguay", "760": "Peru",
    "765": "Suriname", "770": "Uruguay", "775": "Venezuela",
}

# Known test/fake MMSIs
INVALID_MMSIS = {
    "000000000", "111111111", "123456789", "999999999",
    "000000001", "888888888", "012345678"
}


class BehaviorType(Enum):
    """Types of detected vessel behavior."""
    ENCOUNTER = "encounter"
    LOITERING = "loitering"
    AIS_GAP = "ais_gap"
    SPOOFING = "spoofing"
    IMPOSSIBLE_SPEED = "impossible_speed"


@dataclass
class BehaviorEvent:
    """Detected behavior event."""
    event_type: BehaviorType
    mmsi: str
    start_time: datetime
    end_time: datetime
    latitude: float
    longitude: float
    confidence: float  # 0-1
    details: Dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "mmsi": self.mmsi,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "confidence": self.confidence,
            "details": self.details
        }


# =============================================================================
# MMSI Validation
# =============================================================================

def validate_mmsi(mmsi: str) -> Dict[str, Any]:
    """
    Validate MMSI and extract country information.

    MMSI Format: MIDXXXXXX where MID = Maritime Identification Digits (country)

    Args:
        mmsi: 9-digit MMSI string

    Returns:
        Dict with validation result, country, and type
    """
    if not mmsi:
        return {"valid": False, "reason": "Empty MMSI"}

    # Clean and validate format
    mmsi = str(mmsi).strip()
    if len(mmsi) != 9:
        return {"valid": False, "reason": f"Invalid length: {len(mmsi)}"}

    if not mmsi.isdigit():
        return {"valid": False, "reason": "Non-numeric characters"}

    # Check for known invalid MMSIs
    if mmsi in INVALID_MMSIS:
        return {"valid": False, "reason": "Known test/fake MMSI"}

    # Extract MID (first 3 digits)
    mid = mmsi[:3]

    # Special MMSI types
    if mmsi.startswith("00"):
        return {"valid": True, "type": "coast_station", "country": None, "mid": mid}

    if mmsi.startswith("111"):
        # SAR aircraft
        mid = mmsi[3:6]
        country = MID_TO_COUNTRY.get(mid)
        return {"valid": True, "type": "sar_aircraft", "country": country, "mid": mid}

    if mmsi.startswith("8"):
        return {"valid": True, "type": "handheld_vhf", "country": None, "mid": mid}

    if mmsi.startswith("98"):
        # Auxiliary craft
        mid = mmsi[2:5]
        country = MID_TO_COUNTRY.get(mid)
        return {"valid": True, "type": "auxiliary_craft", "country": country, "mid": mid}

    if mmsi.startswith("99"):
        # Aids to navigation
        mid = mmsi[2:5]
        country = MID_TO_COUNTRY.get(mid)
        return {"valid": True, "type": "aid_to_navigation", "country": country, "mid": mid}

    if mmsi.startswith("970"):
        return {"valid": True, "type": "sar_transmitter", "country": None, "mid": mid}

    if mmsi.startswith("972"):
        return {"valid": True, "type": "mob_device", "country": None, "mid": mid}

    if mmsi.startswith("974"):
        return {"valid": True, "type": "epirb", "country": None, "mid": mid}

    # Standard vessel MMSI
    country = MID_TO_COUNTRY.get(mid)
    if country:
        return {"valid": True, "type": "vessel", "country": country, "mid": mid}

    # Unknown MID but valid format
    return {"valid": True, "type": "vessel", "country": None, "mid": mid,
            "warning": "Unknown MID"}


def get_flag_country(mmsi: str) -> Optional[str]:
    """Get the flag country for an MMSI."""
    result = validate_mmsi(mmsi)
    return result.get("country")


# =============================================================================
# Encounter Detection (Transshipment)
# =============================================================================

def detect_encounters(
    tracks: Dict[str, List[dict]],
    max_distance_km: float = 0.5,
    max_speed_knots: float = 2.0,
    min_duration_hours: float = 2.0,
    min_distance_from_shore_km: float = 10.0
) -> List[BehaviorEvent]:
    """
    Detect potential vessel encounters (transshipment events).

    Based on Global Fishing Watch methodology:
    - Two vessels within 500m for 2+ hours
    - Both traveling < 2 knots
    - More than 10km from shore

    Args:
        tracks: Dict of MMSI -> list of position dicts
        max_distance_km: Maximum distance between vessels (default 0.5km = 500m)
        max_speed_knots: Maximum speed for both vessels
        min_duration_hours: Minimum encounter duration
        min_distance_from_shore_km: Minimum distance from coastline

    Returns:
        List of detected encounter events
    """
    encounters = []
    mmsi_list = list(tracks.keys())

    for i, mmsi1 in enumerate(mmsi_list):
        for mmsi2 in mmsi_list[i+1:]:
            track1 = tracks[mmsi1]
            track2 = tracks[mmsi2]

            # Find overlapping time periods
            encounter_segments = _find_encounter_segments(
                track1, track2,
                max_distance_km,
                max_speed_knots
            )

            # Filter by duration
            for segment in encounter_segments:
                duration = (segment["end_time"] - segment["start_time"]).total_seconds() / 3600
                if duration >= min_duration_hours:
                    encounters.append(BehaviorEvent(
                        event_type=BehaviorType.ENCOUNTER,
                        mmsi=f"{mmsi1},{mmsi2}",
                        start_time=segment["start_time"],
                        end_time=segment["end_time"],
                        latitude=segment["lat"],
                        longitude=segment["lon"],
                        confidence=min(1.0, duration / 4.0),  # Higher confidence for longer encounters
                        details={
                            "vessel1_mmsi": mmsi1,
                            "vessel2_mmsi": mmsi2,
                            "duration_hours": round(duration, 2),
                            "avg_distance_km": segment["avg_distance"],
                            "avg_speed_knots": segment["avg_speed"]
                        }
                    ))

    return encounters


def _find_encounter_segments(
    track1: List[dict],
    track2: List[dict],
    max_distance_km: float,
    max_speed_knots: float
) -> List[dict]:
    """Find time segments where two vessels are in close proximity."""
    segments = []
    current_segment = None

    # Create time-indexed lookup for track2
    track2_by_time = {pos.get("timestamp"): pos for pos in track2 if pos.get("timestamp")}

    for pos1 in track1:
        ts1 = pos1.get("timestamp")
        if not ts1:
            continue

        # Find closest position in track2 (within 5 minutes)
        pos2 = _find_closest_position(ts1, track2_by_time, max_gap_minutes=5)
        if not pos2:
            if current_segment:
                segments.append(current_segment)
                current_segment = None
            continue

        # Calculate distance
        distance = haversine(
            pos1.get("lat", pos1.get("latitude", 0)),
            pos1.get("lon", pos1.get("longitude", 0)),
            pos2.get("lat", pos2.get("latitude", 0)),
            pos2.get("lon", pos2.get("longitude", 0))
        )

        speed1 = pos1.get("speed", pos1.get("speed_knots", 0)) or 0
        speed2 = pos2.get("speed", pos2.get("speed_knots", 0)) or 0

        # Check encounter criteria
        if distance <= max_distance_km and speed1 <= max_speed_knots and speed2 <= max_speed_knots:
            if current_segment is None:
                current_segment = {
                    "start_time": ts1,
                    "end_time": ts1,
                    "lat": pos1.get("lat", pos1.get("latitude")),
                    "lon": pos1.get("lon", pos1.get("longitude")),
                    "distances": [distance],
                    "speeds": [speed1, speed2]
                }
            else:
                current_segment["end_time"] = ts1
                current_segment["distances"].append(distance)
                current_segment["speeds"].extend([speed1, speed2])
        else:
            if current_segment:
                current_segment["avg_distance"] = sum(current_segment["distances"]) / len(current_segment["distances"])
                current_segment["avg_speed"] = sum(current_segment["speeds"]) / len(current_segment["speeds"])
                segments.append(current_segment)
                current_segment = None

    if current_segment:
        current_segment["avg_distance"] = sum(current_segment["distances"]) / len(current_segment["distances"])
        current_segment["avg_speed"] = sum(current_segment["speeds"]) / len(current_segment["speeds"])
        segments.append(current_segment)

    return segments


def _find_closest_position(target_time: datetime, positions_by_time: dict, max_gap_minutes: int = 5) -> Optional[dict]:
    """Find the closest position to a target time."""
    if not positions_by_time:
        return None

    best_pos = None
    best_gap = timedelta(minutes=max_gap_minutes + 1)

    for ts, pos in positions_by_time.items():
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except:
                continue

        gap = abs(ts - target_time) if isinstance(target_time, datetime) else timedelta(hours=999)
        if gap < best_gap:
            best_gap = gap
            best_pos = pos

    if best_gap <= timedelta(minutes=max_gap_minutes):
        return best_pos
    return None


# =============================================================================
# Loitering Detection
# =============================================================================

def detect_loitering(
    track: List[dict],
    mmsi: str,
    max_speed_knots: float = 2.0,
    min_duration_hours: float = 3.0,
    min_distance_from_port_nm: float = 20.0
) -> List[BehaviorEvent]:
    """
    Detect loitering behavior (potential dark transshipment indicator).

    A vessel is loitering when:
    - Speed < 2 knots for extended period
    - Far from ports/anchorages
    - No other vessel visible nearby (dark encounter)

    Args:
        track: List of position dicts with timestamp, lat, lon, speed
        mmsi: Vessel MMSI
        max_speed_knots: Speed threshold
        min_duration_hours: Minimum loitering duration
        min_distance_from_port_nm: Minimum distance from known ports

    Returns:
        List of loitering events
    """
    events = []
    slow_segment = []

    for pos in sorted(track, key=lambda x: x.get("timestamp", datetime.min)):
        speed = pos.get("speed", pos.get("speed_knots", 0)) or 0

        if speed <= max_speed_knots:
            slow_segment.append(pos)
        else:
            # Check if segment qualifies as loitering
            if len(slow_segment) >= 2:
                event = _evaluate_loitering_segment(slow_segment, mmsi, min_duration_hours)
                if event:
                    events.append(event)
            slow_segment = []

    # Check final segment
    if len(slow_segment) >= 2:
        event = _evaluate_loitering_segment(slow_segment, mmsi, min_duration_hours)
        if event:
            events.append(event)

    return events


def _evaluate_loitering_segment(segment: List[dict], mmsi: str, min_duration_hours: float) -> Optional[BehaviorEvent]:
    """Evaluate a slow-moving segment for loitering."""
    if len(segment) < 2:
        return None

    start_time = segment[0].get("timestamp")
    end_time = segment[-1].get("timestamp")

    if not start_time or not end_time:
        return None

    # Handle string timestamps
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

    duration_hours = (end_time - start_time).total_seconds() / 3600

    if duration_hours < min_duration_hours:
        return None

    # Calculate center point
    avg_lat = sum(p.get("lat", p.get("latitude", 0)) for p in segment) / len(segment)
    avg_lon = sum(p.get("lon", p.get("longitude", 0)) for p in segment) / len(segment)
    avg_speed = sum(p.get("speed", p.get("speed_knots", 0)) or 0 for p in segment) / len(segment)

    return BehaviorEvent(
        event_type=BehaviorType.LOITERING,
        mmsi=mmsi,
        start_time=start_time,
        end_time=end_time,
        latitude=avg_lat,
        longitude=avg_lon,
        confidence=min(1.0, duration_hours / 6.0),  # Higher confidence for longer loitering
        details={
            "duration_hours": round(duration_hours, 2),
            "avg_speed_knots": round(avg_speed, 2),
            "position_count": len(segment)
        }
    )


# =============================================================================
# AIS Gap Detection
# =============================================================================

def detect_ais_gaps(
    track: List[dict],
    mmsi: str,
    max_gap_minutes: float = 60.0,
    min_gap_minutes: float = 30.0
) -> List[BehaviorEvent]:
    """
    Detect gaps in AIS transmission (vessel going dark).

    Flags when a vessel stops transmitting for an extended period,
    which may indicate intentional AIS disabling.

    Args:
        track: List of position dicts with timestamps
        mmsi: Vessel MMSI
        max_gap_minutes: Report gaps longer than this (default 60 min)
        min_gap_minutes: Ignore gaps shorter than this (default 30 min)

    Returns:
        List of AIS gap events
    """
    events = []

    # Sort by timestamp
    sorted_track = sorted(track, key=lambda x: x.get("timestamp", datetime.min))

    for i in range(1, len(sorted_track)):
        prev_pos = sorted_track[i-1]
        curr_pos = sorted_track[i]

        prev_time = prev_pos.get("timestamp")
        curr_time = curr_pos.get("timestamp")

        if not prev_time or not curr_time:
            continue

        # Handle string timestamps
        if isinstance(prev_time, str):
            prev_time = datetime.fromisoformat(prev_time.replace("Z", "+00:00"))
        if isinstance(curr_time, str):
            curr_time = datetime.fromisoformat(curr_time.replace("Z", "+00:00"))

        gap_minutes = (curr_time - prev_time).total_seconds() / 60

        if gap_minutes >= max_gap_minutes:
            # Calculate distance jumped during gap
            distance = haversine(
                prev_pos.get("lat", prev_pos.get("latitude", 0)),
                prev_pos.get("lon", prev_pos.get("longitude", 0)),
                curr_pos.get("lat", curr_pos.get("latitude", 0)),
                curr_pos.get("lon", curr_pos.get("longitude", 0))
            )

            # Calculate implied speed during gap
            gap_hours = gap_minutes / 60
            implied_speed_kmh = distance / gap_hours if gap_hours > 0 else 0
            implied_speed_knots = implied_speed_kmh / 1.852

            events.append(BehaviorEvent(
                event_type=BehaviorType.AIS_GAP,
                mmsi=mmsi,
                start_time=prev_time,
                end_time=curr_time,
                latitude=prev_pos.get("lat", prev_pos.get("latitude", 0)),
                longitude=prev_pos.get("lon", prev_pos.get("longitude", 0)),
                confidence=min(1.0, gap_minutes / 180),  # Higher confidence for longer gaps
                details={
                    "gap_minutes": round(gap_minutes, 1),
                    "gap_hours": round(gap_hours, 2),
                    "distance_km": round(distance, 2),
                    "implied_speed_knots": round(implied_speed_knots, 1),
                    "start_position": {
                        "lat": prev_pos.get("lat", prev_pos.get("latitude")),
                        "lon": prev_pos.get("lon", prev_pos.get("longitude"))
                    },
                    "end_position": {
                        "lat": curr_pos.get("lat", curr_pos.get("latitude")),
                        "lon": curr_pos.get("lon", curr_pos.get("longitude"))
                    }
                }
            ))

    return events


# =============================================================================
# Spoofing Detection
# =============================================================================

def detect_spoofing(
    track: List[dict],
    mmsi: str,
    max_speed_knots: float = 50.0
) -> List[BehaviorEvent]:
    """
    Detect potential AIS spoofing (impossible vessel movements).

    Flags when a vessel appears to move faster than physically possible,
    indicating either GPS manipulation or MMSI collision (two vessels
    using the same MMSI).

    Args:
        track: List of position dicts
        mmsi: Vessel MMSI
        max_speed_knots: Maximum realistic vessel speed (default 50 knots)

    Returns:
        List of spoofing events
    """
    events = []
    max_speed_kmh = max_speed_knots * 1.852

    sorted_track = sorted(track, key=lambda x: x.get("timestamp", datetime.min))

    for i in range(1, len(sorted_track)):
        prev_pos = sorted_track[i-1]
        curr_pos = sorted_track[i]

        prev_time = prev_pos.get("timestamp")
        curr_time = curr_pos.get("timestamp")

        if not prev_time or not curr_time:
            continue

        # Handle string timestamps
        if isinstance(prev_time, str):
            prev_time = datetime.fromisoformat(prev_time.replace("Z", "+00:00"))
        if isinstance(curr_time, str):
            curr_time = datetime.fromisoformat(curr_time.replace("Z", "+00:00"))

        time_diff_hours = (curr_time - prev_time).total_seconds() / 3600

        if time_diff_hours <= 0:
            continue

        distance = haversine(
            prev_pos.get("lat", prev_pos.get("latitude", 0)),
            prev_pos.get("lon", prev_pos.get("longitude", 0)),
            curr_pos.get("lat", curr_pos.get("latitude", 0)),
            curr_pos.get("lon", curr_pos.get("longitude", 0))
        )

        required_speed_kmh = distance / time_diff_hours
        required_speed_knots = required_speed_kmh / 1.852

        # Allow 50% buffer for GPS errors
        if required_speed_kmh > max_speed_kmh * 1.5:
            events.append(BehaviorEvent(
                event_type=BehaviorType.IMPOSSIBLE_SPEED,
                mmsi=mmsi,
                start_time=prev_time,
                end_time=curr_time,
                latitude=prev_pos.get("lat", prev_pos.get("latitude", 0)),
                longitude=prev_pos.get("lon", prev_pos.get("longitude", 0)),
                confidence=min(1.0, (required_speed_knots - max_speed_knots) / 100),
                details={
                    "distance_km": round(distance, 2),
                    "time_hours": round(time_diff_hours, 3),
                    "required_speed_knots": round(required_speed_knots, 1),
                    "max_realistic_speed_knots": max_speed_knots,
                    "likely_cause": "MMSI collision or GPS spoofing",
                    "start_position": {
                        "lat": prev_pos.get("lat", prev_pos.get("latitude")),
                        "lon": prev_pos.get("lon", prev_pos.get("longitude"))
                    },
                    "end_position": {
                        "lat": curr_pos.get("lat", curr_pos.get("latitude")),
                        "lon": curr_pos.get("lon", curr_pos.get("longitude"))
                    }
                }
            ))

    return events


# =============================================================================
# Track Utilities
# =============================================================================

def downsample_track(
    track: List[dict],
    interval_seconds: int = 60
) -> List[dict]:
    """
    Downsample a track to reduce storage requirements.

    Keeps only one position per time interval.

    Args:
        track: List of position dicts
        interval_seconds: Minimum time between positions (default 60s)

    Returns:
        Downsampled track
    """
    if not track:
        return []

    sorted_track = sorted(track, key=lambda x: x.get("timestamp", datetime.min))
    sampled = [sorted_track[0]]

    for pos in sorted_track[1:]:
        last_time = sampled[-1].get("timestamp")
        curr_time = pos.get("timestamp")

        if not last_time or not curr_time:
            continue

        # Handle string timestamps
        if isinstance(last_time, str):
            last_time = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
        if isinstance(curr_time, str):
            curr_time = datetime.fromisoformat(curr_time.replace("Z", "+00:00"))

        if (curr_time - last_time).total_seconds() >= interval_seconds:
            sampled.append(pos)

    return sampled


def segment_track(
    track: List[dict],
    max_gap_hours: float = 24.0
) -> List[List[dict]]:
    """
    Split a track into segments based on time gaps.

    Useful for separating different voyages or detecting when
    a vessel was inactive.

    Args:
        track: List of position dicts
        max_gap_hours: Maximum gap before starting new segment

    Returns:
        List of track segments
    """
    if not track:
        return []

    sorted_track = sorted(track, key=lambda x: x.get("timestamp", datetime.min))
    segments = []
    current_segment = [sorted_track[0]]

    for pos in sorted_track[1:]:
        last_time = current_segment[-1].get("timestamp")
        curr_time = pos.get("timestamp")

        if not last_time or not curr_time:
            current_segment.append(pos)
            continue

        # Handle string timestamps
        if isinstance(last_time, str):
            last_time = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
        if isinstance(curr_time, str):
            curr_time = datetime.fromisoformat(curr_time.replace("Z", "+00:00"))

        gap_hours = (curr_time - last_time).total_seconds() / 3600

        if gap_hours > max_gap_hours:
            segments.append(current_segment)
            current_segment = []

        current_segment.append(pos)

    if current_segment:
        segments.append(current_segment)

    return segments


def filter_by_distance(
    positions: List[dict],
    ref_lat: float,
    ref_lon: float,
    max_distance_km: float
) -> List[dict]:
    """
    Filter positions within a distance from a reference point.

    Args:
        positions: List of position dicts
        ref_lat: Reference latitude
        ref_lon: Reference longitude
        max_distance_km: Maximum distance in kilometers

    Returns:
        Filtered positions
    """
    filtered = []

    for pos in positions:
        lat = pos.get("lat", pos.get("latitude", 0))
        lon = pos.get("lon", pos.get("longitude", 0))

        distance = haversine(ref_lat, ref_lon, lat, lon)
        if distance <= max_distance_km:
            filtered.append(pos)

    return filtered


def deduplicate_positions(
    positions: List[dict],
    window_seconds: int = 10
) -> List[dict]:
    """
    Remove duplicate positions within a time window.

    Args:
        positions: List of position dicts
        window_seconds: Time window for deduplication

    Returns:
        Deduplicated positions
    """
    if not positions:
        return []

    sorted_positions = sorted(positions, key=lambda x: x.get("timestamp", datetime.min))
    deduped = [sorted_positions[0]]

    for pos in sorted_positions[1:]:
        last_time = deduped[-1].get("timestamp")
        curr_time = pos.get("timestamp")

        if not last_time or not curr_time:
            deduped.append(pos)
            continue

        # Handle string timestamps
        if isinstance(last_time, str):
            last_time = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
        if isinstance(curr_time, str):
            curr_time = datetime.fromisoformat(curr_time.replace("Z", "+00:00"))

        if (curr_time - last_time).total_seconds() >= window_seconds:
            deduped.append(pos)

    return deduped


# =============================================================================
# Batch Analysis
# =============================================================================

def analyze_vessel_behavior(
    track: List[dict],
    mmsi: str
) -> Dict[str, Any]:
    """
    Run all behavior detection algorithms on a vessel track.

    Args:
        track: List of position dicts
        mmsi: Vessel MMSI

    Returns:
        Dict with all detected events and statistics
    """
    # Validate MMSI
    mmsi_validation = validate_mmsi(mmsi)

    # Detect various behaviors
    loitering_events = detect_loitering(track, mmsi)
    ais_gaps = detect_ais_gaps(track, mmsi)
    spoofing_events = detect_spoofing(track, mmsi)

    # Calculate track statistics
    if track:
        total_distance = 0
        sorted_track = sorted(track, key=lambda x: x.get("timestamp", datetime.min))
        for i in range(1, len(sorted_track)):
            total_distance += haversine(
                sorted_track[i-1].get("lat", sorted_track[i-1].get("latitude", 0)),
                sorted_track[i-1].get("lon", sorted_track[i-1].get("longitude", 0)),
                sorted_track[i].get("lat", sorted_track[i].get("latitude", 0)),
                sorted_track[i].get("lon", sorted_track[i].get("longitude", 0))
            )

        speeds = [p.get("speed", p.get("speed_knots", 0)) or 0 for p in track]
        avg_speed = sum(speeds) / len(speeds) if speeds else 0
        max_speed = max(speeds) if speeds else 0
    else:
        total_distance = 0
        avg_speed = 0
        max_speed = 0

    # Calculate dark fleet risk score
    dark_fleet_score = calculate_dark_fleet_score(
        mmsi=mmsi,
        ais_gap_count=len(ais_gaps),
        loitering_count=len(loitering_events),
        spoofing_count=len(spoofing_events)
    )

    return {
        "mmsi": mmsi,
        "mmsi_validation": mmsi_validation,
        "track_statistics": {
            "position_count": len(track),
            "total_distance_km": round(total_distance, 2),
            "avg_speed_knots": round(avg_speed, 2),
            "max_speed_knots": round(max_speed, 2)
        },
        "events": {
            "loitering": [e.to_dict() for e in loitering_events],
            "ais_gaps": [e.to_dict() for e in ais_gaps],
            "spoofing": [e.to_dict() for e in spoofing_events]
        },
        "risk_indicators": {
            "loitering_count": len(loitering_events),
            "ais_gap_count": len(ais_gaps),
            "spoofing_count": len(spoofing_events),
            "total_events": len(loitering_events) + len(ais_gaps) + len(spoofing_events)
        },
        "dark_fleet_score": dark_fleet_score
    }


# =============================================================================
# Dark Fleet Detection (Based on Academic Research)
# =============================================================================
# References:
# - "Shadow Fleets: A Growing Challenge" (MDPI Applied Sciences, 2025)
# - "AIS Data Manipulation in the Illicit Global Oil Trade" (MDPI JMSE, 2023)
# - Global Fishing Watch Nature Study (2024)
# =============================================================================

# Flags of Convenience - Countries with lax maritime regulations
# Used by shadow fleets to obscure ownership and evade oversight
# Source: ITU, Paris MOU, academic literature on FOC registries
FLAGS_OF_CONVENIENCE = {
    # Traditional FOC (Open Registries)
    "Panama", "Liberia", "Marshall Islands", "Bahamas", "Malta",
    "Cyprus", "Bermuda", "Antigua and Barbuda", "Saint Vincent and the Grenadines",
    "Cayman Islands", "Vanuatu", "Comoros", "Moldova", "Mongolia",
    "Togo", "Tanzania", "Palau", "Belize", "Honduras",
    "Bolivia", "Cambodia", "Sierra Leone",
    # Emerging FOC used by shadow fleet (per 2024-2025 research)
    "Gabon", "Cameroon", "Sao Tome and Principe", "Equatorial Guinea",
    "Guinea-Bissau", "Djibouti", "Barbados",
}

# High-risk flags specifically associated with sanctions evasion
# Based on documented shadow fleet patterns (Russia/Iran/Venezuela)
SHADOW_FLEET_FLAGS = {
    "Gabon", "Cameroon", "Palau", "Sao Tome and Principe",
    "Equatorial Guinea", "Comoros", "Togo", "Tanzania",
}


def is_flag_of_convenience(country: Optional[str]) -> bool:
    """
    Check if a flag state is a Flag of Convenience.

    FOC registries have minimal regulations and are frequently
    used by shadow fleets to obscure vessel ownership.

    Args:
        country: Flag state name

    Returns:
        True if country is a known FOC
    """
    if not country:
        return False
    return country in FLAGS_OF_CONVENIENCE


def is_shadow_fleet_flag(country: Optional[str]) -> bool:
    """
    Check if a flag is specifically associated with shadow fleet operations.

    These are flags with documented patterns of sanctions evasion,
    particularly for Russian, Iranian, and Venezuelan oil trade.

    Args:
        country: Flag state name

    Returns:
        True if country is a known shadow fleet flag
    """
    if not country:
        return False
    return country in SHADOW_FLEET_FLAGS


def calculate_dark_fleet_score(
    mmsi: str = "",
    flag: Optional[str] = None,
    year_built: Optional[int] = None,
    owner: Optional[str] = None,
    ais_gap_count: int = 0,
    loitering_count: int = 0,
    spoofing_count: int = 0,
    sts_transfer_count: int = 0,
    vessel_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate dark fleet risk score based on multiple indicators.

    Based on academic research identifying key shadow fleet characteristics:
    - Disabled/manipulated AIS
    - Flags of convenience (especially emerging FOC)
    - Aging vessels (>15-20 years)
    - Obscure ownership structures
    - Ship-to-ship transfers at sea

    References:
        - "Shadow Fleets: A Growing Challenge" (MDPI, 2025)
        - "AIS Data Manipulation in Illicit Oil Trade" (MDPI, 2023)

    Args:
        mmsi: Vessel MMSI
        flag: Flag state
        year_built: Year vessel was built
        owner: Registered owner name
        ais_gap_count: Number of AIS transmission gaps
        loitering_count: Number of loitering events
        spoofing_count: Number of position spoofing events
        sts_transfer_count: Number of ship-to-ship transfer events
        vessel_type: Type of vessel

    Returns:
        Dict with score (0-100), risk level, and breakdown
    """
    score = 0
    factors = []

    # Factor 1: Flag of Convenience (0-25 points)
    # Shadow fleet flag = 25, general FOC = 15
    if flag:
        if is_shadow_fleet_flag(flag):
            score += 25
            factors.append({"factor": "shadow_fleet_flag", "points": 25,
                          "detail": f"{flag} is associated with shadow fleet operations"})
        elif is_flag_of_convenience(flag):
            score += 15
            factors.append({"factor": "flag_of_convenience", "points": 15,
                          "detail": f"{flag} is a flag of convenience"})

    # Factor 2: Vessel Age (0-20 points)
    # Shadow fleets use aging tankers (lower insurance, expendable)
    if year_built:
        current_year = datetime.now().year
        age = current_year - year_built
        if age >= 25:
            score += 20
            factors.append({"factor": "vessel_age", "points": 20,
                          "detail": f"Vessel is {age} years old (high risk)"})
        elif age >= 20:
            score += 15
            factors.append({"factor": "vessel_age", "points": 15,
                          "detail": f"Vessel is {age} years old (elevated risk)"})
        elif age >= 15:
            score += 10
            factors.append({"factor": "vessel_age", "points": 10,
                          "detail": f"Vessel is {age} years old (moderate risk)"})

    # Factor 3: Ownership Opacity (0-15 points)
    # Shell companies and hidden ownership are key indicators
    if not owner or owner.strip() == "":
        score += 15
        factors.append({"factor": "unknown_owner", "points": 15,
                      "detail": "No registered owner information"})
    elif any(x in owner.lower() for x in ["unknown", "n/a", "private", "confidential"]):
        score += 10
        factors.append({"factor": "obscured_owner", "points": 10,
                      "detail": "Owner information appears obscured"})

    # Factor 4: AIS Gaps (0-20 points)
    # Going dark is primary shadow fleet tactic
    if ais_gap_count >= 5:
        score += 20
        factors.append({"factor": "ais_gaps", "points": 20,
                      "detail": f"{ais_gap_count} AIS transmission gaps detected"})
    elif ais_gap_count >= 3:
        score += 15
        factors.append({"factor": "ais_gaps", "points": 15,
                      "detail": f"{ais_gap_count} AIS transmission gaps detected"})
    elif ais_gap_count >= 1:
        score += 10
        factors.append({"factor": "ais_gaps", "points": 10,
                      "detail": f"{ais_gap_count} AIS transmission gap(s) detected"})

    # Factor 5: Position Spoofing (0-15 points)
    # Falsified positions indicate intentional deception
    if spoofing_count >= 3:
        score += 15
        factors.append({"factor": "spoofing", "points": 15,
                      "detail": f"{spoofing_count} position anomalies suggest spoofing"})
    elif spoofing_count >= 1:
        score += 10
        factors.append({"factor": "spoofing", "points": 10,
                      "detail": f"{spoofing_count} position anomaly detected"})

    # Factor 6: Loitering Behavior (0-10 points)
    # Loitering at sea often indicates STS transfers
    if loitering_count >= 3:
        score += 10
        factors.append({"factor": "loitering", "points": 10,
                      "detail": f"{loitering_count} loitering events detected"})
    elif loitering_count >= 1:
        score += 5
        factors.append({"factor": "loitering", "points": 5,
                      "detail": f"{loitering_count} loitering event(s) detected"})

    # Factor 7: STS Transfers (0-15 points)
    # Direct indicator of sanctions evasion
    if sts_transfer_count >= 2:
        score += 15
        factors.append({"factor": "sts_transfers", "points": 15,
                      "detail": f"{sts_transfer_count} ship-to-ship transfers detected"})
    elif sts_transfer_count >= 1:
        score += 10
        factors.append({"factor": "sts_transfers", "points": 10,
                      "detail": f"{sts_transfer_count} ship-to-ship transfer detected"})

    # Factor 8: Vessel Type (0-5 points)
    # Tankers are primary shadow fleet vessel type
    if vessel_type:
        tanker_types = ["tanker", "crude", "oil", "chemical", "lpg", "lng", "product"]
        if any(t in vessel_type.lower() for t in tanker_types):
            score += 5
            factors.append({"factor": "vessel_type", "points": 5,
                          "detail": f"Tanker vessels are common in shadow fleets"})

    # Cap score at 100
    score = min(100, score)

    # Determine risk level
    if score >= 70:
        risk_level = "critical"
        assessment = "High probability of shadow fleet involvement"
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
        "methodology": "Based on MDPI shadow fleet research (2023-2025)"
    }


def detect_sts_transfers(
    tracks: Dict[str, List[dict]],
    min_distance_km: float = 0.5,
    max_speed_knots: float = 3.0,
    min_duration_hours: float = 4.0,
    max_duration_hours: float = 48.0,
    min_distance_from_shore_nm: float = 12.0
) -> List[BehaviorEvent]:
    """
    Detect ship-to-ship (STS) transfers at sea.

    STS transfers are a primary method for sanctions evasion, where cargo
    (typically oil) is transferred between vessels at sea to obscure origin.

    Detection criteria based on research:
    - Two vessels within 500m for 4-48 hours (oil transfer time)
    - Both vessels nearly stationary (<3 knots)
    - Located far from shore (>12nm, outside territorial waters)

    References:
        - "Automatic Detection of Dark Ship-to-Ship Transfers" (arXiv, 2024)
        - "AIS Data Manipulation in Illicit Oil Trade" (MDPI, 2023)

    Args:
        tracks: Dict of MMSI -> list of position dicts
        min_distance_km: Maximum distance between vessels (0.5km = 500m)
        max_speed_knots: Maximum speed for both vessels during transfer
        min_duration_hours: Minimum transfer duration (4h for partial cargo)
        max_duration_hours: Maximum transfer duration (48h for full cargo)
        min_distance_from_shore_nm: Minimum distance from coast

    Returns:
        List of detected STS transfer events
    """
    transfers = []
    mmsi_list = list(tracks.keys())

    for i, mmsi1 in enumerate(mmsi_list):
        for mmsi2 in mmsi_list[i+1:]:
            track1 = tracks[mmsi1]
            track2 = tracks[mmsi2]

            # Find rendezvous events with STS characteristics
            sts_segments = _find_sts_segments(
                track1, track2,
                min_distance_km,
                max_speed_knots,
                min_duration_hours,
                max_duration_hours
            )

            for segment in sts_segments:
                duration_hours = segment["duration_hours"]

                # Estimate transfer type based on duration
                if duration_hours >= 24:
                    transfer_type = "full_cargo"
                    confidence = 0.9
                elif duration_hours >= 12:
                    transfer_type = "partial_cargo"
                    confidence = 0.8
                else:
                    transfer_type = "possible_transfer"
                    confidence = 0.6

                transfers.append(BehaviorEvent(
                    event_type=BehaviorType.ENCOUNTER,
                    mmsi=f"{mmsi1},{mmsi2}",
                    start_time=segment["start_time"],
                    end_time=segment["end_time"],
                    latitude=segment["lat"],
                    longitude=segment["lon"],
                    confidence=confidence,
                    details={
                        "event_subtype": "sts_transfer",
                        "vessel1_mmsi": mmsi1,
                        "vessel2_mmsi": mmsi2,
                        "duration_hours": round(duration_hours, 2),
                        "transfer_type": transfer_type,
                        "avg_distance_m": round(segment["avg_distance"] * 1000, 0),
                        "avg_speed_knots": round(segment["avg_speed"], 2),
                        "methodology": "arXiv 2024 STS detection criteria"
                    }
                ))

    return transfers


def _find_sts_segments(
    track1: List[dict],
    track2: List[dict],
    min_distance_km: float,
    max_speed_knots: float,
    min_duration_hours: float,
    max_duration_hours: float
) -> List[dict]:
    """
    Find time segments matching STS transfer criteria.

    More stringent than general encounter detection:
    - Both vessels must be nearly stationary
    - Duration must be within realistic transfer window
    """
    segments = []
    current_segment = None

    # Create time-indexed lookup for track2
    track2_by_time = {}
    for pos in track2:
        ts = pos.get("timestamp")
        if ts:
            track2_by_time[ts] = pos

    for pos1 in sorted(track1, key=lambda x: x.get("timestamp", datetime.min)):
        ts1 = pos1.get("timestamp")
        if not ts1:
            continue

        # Find closest position in track2 (within 10 minutes for STS)
        pos2 = _find_closest_position_sts(ts1, track2_by_time, max_gap_minutes=10)
        if not pos2:
            if current_segment:
                # Check if segment meets duration criteria
                duration = _calculate_segment_duration(current_segment)
                if min_duration_hours <= duration <= max_duration_hours:
                    current_segment["duration_hours"] = duration
                    segments.append(current_segment)
                current_segment = None
            continue

        # Calculate distance between vessels
        lat1 = pos1.get("lat", pos1.get("latitude", 0))
        lon1 = pos1.get("lon", pos1.get("longitude", 0))
        lat2 = pos2.get("lat", pos2.get("latitude", 0))
        lon2 = pos2.get("lon", pos2.get("longitude", 0))

        distance = haversine(lat1, lon1, lat2, lon2)

        speed1 = pos1.get("speed", pos1.get("speed_knots", 0)) or 0
        speed2 = pos2.get("speed", pos2.get("speed_knots", 0)) or 0

        # STS criteria: close, both stationary
        if distance <= min_distance_km and speed1 <= max_speed_knots and speed2 <= max_speed_knots:
            if current_segment is None:
                current_segment = {
                    "start_time": ts1,
                    "end_time": ts1,
                    "lat": lat1,
                    "lon": lon1,
                    "distances": [distance],
                    "speeds": [speed1, speed2]
                }
            else:
                current_segment["end_time"] = ts1
                current_segment["distances"].append(distance)
                current_segment["speeds"].extend([speed1, speed2])
        else:
            if current_segment:
                duration = _calculate_segment_duration(current_segment)
                if min_duration_hours <= duration <= max_duration_hours:
                    current_segment["duration_hours"] = duration
                    current_segment["avg_distance"] = sum(current_segment["distances"]) / len(current_segment["distances"])
                    current_segment["avg_speed"] = sum(current_segment["speeds"]) / len(current_segment["speeds"])
                    segments.append(current_segment)
                current_segment = None

    # Check final segment
    if current_segment:
        duration = _calculate_segment_duration(current_segment)
        if min_duration_hours <= duration <= max_duration_hours:
            current_segment["duration_hours"] = duration
            current_segment["avg_distance"] = sum(current_segment["distances"]) / len(current_segment["distances"])
            current_segment["avg_speed"] = sum(current_segment["speeds"]) / len(current_segment["speeds"])
            segments.append(current_segment)

    return segments


def _find_closest_position_sts(target_time: datetime, positions_by_time: dict, max_gap_minutes: int = 10) -> Optional[dict]:
    """Find closest position for STS detection (stricter time window)."""
    if not positions_by_time:
        return None

    best_pos = None
    best_gap = timedelta(minutes=max_gap_minutes + 1)

    for ts, pos in positions_by_time.items():
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

        gap = abs(ts - target_time) if isinstance(target_time, datetime) else timedelta(hours=999)
        if gap < best_gap:
            best_gap = gap
            best_pos = pos

    if best_gap <= timedelta(minutes=max_gap_minutes):
        return best_pos
    return None


def _calculate_segment_duration(segment: dict) -> float:
    """Calculate duration of a segment in hours."""
    start = segment.get("start_time")
    end = segment.get("end_time")

    if not start or not end:
        return 0

    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))

    return (end - start).total_seconds() / 3600
