"""
Base interface and data models for AIS sources.

All AIS source implementations must conform to this interface.
This ensures consistent behavior and allows transparent fallback.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Callable, Any
import json


class SourceStatus(Enum):
    """Connection status for AIS sources."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


class SourceType(Enum):
    """Type of AIS source for priority ordering."""
    REALTIME = "realtime"      # WebSocket, streaming (highest priority)
    REST = "rest"              # REST API polling
    ENRICHMENT = "enrichment"  # Supplementary data only
    HISTORICAL = "historical"  # Bulk/historical data


@dataclass
class AISPosition:
    """
    Normalized AIS position report.

    All sources must convert their data to this format.
    Fields map to AIS message types 1, 2, 3, 18, 19.
    """
    mmsi: str
    latitude: float
    longitude: float
    timestamp: datetime

    # Navigation data (optional)
    speed_knots: Optional[float] = None
    course: Optional[float] = None        # Course over ground (degrees)
    heading: Optional[float] = None       # True heading (degrees)
    nav_status: Optional[int] = None      # Navigation status code

    # Metadata
    source: str = "unknown"               # Source identifier
    source_timestamp: Optional[datetime] = None  # When source received it
    raw_message: Optional[str] = None     # Original message for audit

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "mmsi": self.mmsi,
            "lat": self.latitude,
            "lon": self.longitude,
            "speed": self.speed_knots,
            "course": self.course,
            "heading": self.heading,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def is_valid(self) -> bool:
        """Check if position is valid (basic sanity checks)."""
        if not self.mmsi or len(self.mmsi) != 9:
            return False
        if not (-90 <= self.latitude <= 90):
            return False
        if not (-180 <= self.longitude <= 180):
            return False
        # Check for null island / invalid coords
        if self.latitude == 0 and self.longitude == 0:
            return False
        # AIS uses 91 for unavailable latitude, 181 for longitude
        if abs(self.latitude) > 90 or abs(self.longitude) > 180:
            return False
        return True


@dataclass
class AISVesselInfo:
    """
    Static vessel information from AIS message type 5 or database lookup.
    """
    mmsi: str
    imo: Optional[str] = None
    name: Optional[str] = None
    callsign: Optional[str] = None
    ship_type: Optional[int] = None
    ship_type_text: Optional[str] = None

    # Dimensions
    length: Optional[float] = None
    width: Optional[float] = None
    draught: Optional[float] = None

    # Voyage data
    destination: Optional[str] = None
    eta: Optional[datetime] = None

    # Metadata
    flag_state: Optional[str] = None
    source: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "imo": self.imo,
            "name": self.name,
            "callsign": self.callsign,
            "ship_type": self.ship_type,
            "ship_type_text": self.ship_type_text,
            "length": self.length,
            "width": self.width,
            "flag_state": self.flag_state,
            "destination": self.destination,
            "source": self.source
        }


@dataclass
class AISEvent:
    """
    Behavioral event derived from AIS data (e.g., loitering, port visit).
    Used for enrichment sources like Global Fishing Watch.
    """
    mmsi: str
    event_type: str           # loitering, port_visit, encounter, etc.
    start_time: datetime
    end_time: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: float = 0.0   # 0.0 to 1.0
    details: Dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "event_type": self.event_type,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "confidence": self.confidence,
            "details": self.details,
            "source": self.source
        }


class AISSource(ABC):
    """
    Abstract base class for all AIS data sources.

    Implementations must:
    - Handle connection lifecycle
    - Normalize data to AISPosition format
    - Report status accurately
    - Log significant events

    Design principles:
    - Fail gracefully (return empty, don't crash)
    - Be explicit about capabilities
    - Preserve raw data for audit
    """

    def __init__(self, name: str, source_type: SourceType):
        self.name = name
        self.source_type = source_type
        self.status = SourceStatus.DISCONNECTED
        self.last_update: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.positions_received: int = 0
        self._callbacks: List[Callable[[AISPosition], None]] = []

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the data source.

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection and cleanup resources."""
        pass

    @abstractmethod
    def fetch_positions(self, mmsi_list: List[str]) -> List[AISPosition]:
        """
        Fetch current positions for specified vessels.

        Args:
            mmsi_list: List of MMSI numbers to query.

        Returns:
            List of AISPosition objects (may be empty).

        Note:
            For streaming sources, this may return cached positions.
            For REST sources, this triggers an API call.
        """
        pass

    def fetch_vessel_info(self, mmsi: str) -> Optional[AISVesselInfo]:
        """
        Fetch static vessel information.

        Default implementation returns None.
        Override in sources that support vessel lookup.
        """
        return None

    def fetch_events(self, mmsi: str, days: int = 30) -> List[AISEvent]:
        """
        Fetch behavioral events for a vessel.

        Default implementation returns empty list.
        Override in enrichment sources.
        """
        return []

    def subscribe(self, mmsi_list: List[str]) -> bool:
        """
        Subscribe to updates for specific vessels.

        For streaming sources, this sets up the subscription.
        For REST sources, this may be a no-op.

        Returns:
            True if subscription updated, False on error.
        """
        return True

    def add_callback(self, callback: Callable[[AISPosition], None]) -> None:
        """Register callback for real-time position updates."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[AISPosition], None]) -> None:
        """Remove a registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self, position: AISPosition) -> None:
        """Notify all registered callbacks of a new position."""
        for callback in self._callbacks:
            try:
                callback(position)
            except Exception as e:
                self._log(f"Callback error: {e}", level="error")

    def _log(self, message: str, level: str = "info") -> None:
        """Log a message with source context."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{timestamp}] [{self.name}]"

        if level == "error":
            print(f"{prefix} ERROR: {message}")
        elif level == "warning":
            print(f"{prefix} WARNING: {message}")
        else:
            print(f"{prefix} {message}")

    def _set_status(self, status: SourceStatus, error: str = None) -> None:
        """Update source status with logging."""
        old_status = self.status
        self.status = status
        self.error_message = error

        if status != old_status:
            if status == SourceStatus.CONNECTED:
                self._log("Connected")
            elif status == SourceStatus.DISCONNECTED:
                self._log("Disconnected")
            elif status == SourceStatus.ERROR:
                self._log(f"Error: {error}", level="error")
            elif status == SourceStatus.RATE_LIMITED:
                self._log("Rate limited", level="warning")

    def get_status(self) -> Dict[str, Any]:
        """Get current source status as dict."""
        return {
            "name": self.name,
            "type": self.source_type.value,
            "status": self.status.value,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "positions_received": self.positions_received,
            "error": self.error_message
        }

    def is_available(self) -> bool:
        """Check if source is available for queries."""
        return self.status == SourceStatus.CONNECTED

    def is_realtime(self) -> bool:
        """Check if source provides real-time data."""
        return self.source_type == SourceType.REALTIME


# Ship type code to text mapping (ITU-R M.1371)
SHIP_TYPE_MAP = {
    0: "Not available",
    20: "Wing in ground",
    30: "Fishing",
    31: "Towing",
    32: "Towing (large)",
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
    71: "Cargo - Hazard A",
    72: "Cargo - Hazard B",
    73: "Cargo - Hazard C",
    74: "Cargo - Hazard D",
    80: "Tanker",
    81: "Tanker - Hazard A",
    82: "Tanker - Hazard B",
    83: "Tanker - Hazard C",
    84: "Tanker - Hazard D",
    90: "Other",
}


def get_ship_type_text(code: int) -> str:
    """Convert ship type code to human-readable text."""
    if code in SHIP_TYPE_MAP:
        return SHIP_TYPE_MAP[code]
    # Check ranges
    if 21 <= code <= 29:
        return "Wing in ground"
    if 40 <= code <= 49:
        return "High speed craft"
    if 60 <= code <= 69:
        return "Passenger"
    if 70 <= code <= 79:
        return "Cargo"
    if 80 <= code <= 89:
        return "Tanker"
    return f"Unknown ({code})"
