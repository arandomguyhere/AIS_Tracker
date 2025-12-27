"""
AISStream.io WebSocket Client

Real-time global AIS data via WebSocket.
https://aisstream.io/

Features:
- Real-time position updates
- MMSI filtering (subscribe to specific vessels)
- Global coverage
- Free tier available (API key required)

Message Types Supported:
- PositionReport (types 1, 2, 3)
- StandardClassBPositionReport (type 18)
- ExtendedClassBPositionReport (type 19)
- StaticDataReport (type 5, 24)
"""

import json
import threading
import time
from datetime import datetime
from typing import List, Dict, Optional, Any
from queue import Queue, Empty

from .base import (
    AISSource, AISPosition, AISVesselInfo, SourceType, SourceStatus,
    get_ship_type_text
)

# WebSocket support - use built-in or fall back gracefully
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False


class AISStreamSource(AISSource):
    """
    AISStream.io WebSocket client.

    Primary real-time AIS source. Connects via WebSocket and receives
    continuous position updates for subscribed vessels or geographic areas.

    Configuration:
        api_key: AISStream.io API key (required)
        bounding_boxes: List of [[lat_min, lon_min], [lat_max, lon_max]] areas

    Usage - Specific Vessels:
        source = AISStreamSource(api_key="your-key")
        source.subscribe(["413000000", "123456789"])
        source.connect()

    Usage - Geographic Area (all traffic):
        source = AISStreamSource(api_key="your-key")
        source.set_bounding_box(lat_min=20, lon_min=110, lat_max=35, lon_max=130)
        source.connect()

        # Get all vessels in the area
        positions = source.get_all_cached_positions()
    """

    WEBSOCKET_URL = "wss://stream.aisstream.io/v0/stream"

    def __init__(self, api_key: str, bounding_boxes: Optional[List[List[List[float]]]] = None):
        super().__init__(name="aisstream", source_type=SourceType.REALTIME)

        if not WEBSOCKET_AVAILABLE:
            self._log("websocket-client not installed. Install with: pip install websocket-client", level="warning")

        self.api_key = api_key
        self.subscribed_mmsi: List[str] = []

        # Bounding boxes for geographic filtering
        # Format: [[[lat_min, lon_min], [lat_max, lon_max]], ...]
        self.bounding_boxes: List[List[List[float]]] = bounding_boxes or []

        # WebSocket connection
        self._ws: Optional[Any] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._running = False

        # Position cache (MMSI -> latest position)
        self._position_cache: Dict[str, AISPosition] = {}
        self._vessel_info_cache: Dict[str, AISVesselInfo] = {}
        self._cache_lock = threading.Lock()

        # Message queue for processing
        self._message_queue: Queue = Queue(maxsize=1000)

    def connect(self) -> bool:
        """Establish WebSocket connection to AISStream."""
        if not WEBSOCKET_AVAILABLE:
            self._set_status(SourceStatus.ERROR, "websocket-client not installed")
            return False

        if not self.api_key:
            self._set_status(SourceStatus.ERROR, "API key required")
            return False

        if self._running:
            return True

        self._set_status(SourceStatus.CONNECTING)

        try:
            self._running = True
            self._ws_thread = threading.Thread(target=self._websocket_loop, daemon=True)
            self._ws_thread.start()

            # Wait for connection (up to 10 seconds)
            for _ in range(100):
                if self.status == SourceStatus.CONNECTED:
                    return True
                if self.status == SourceStatus.ERROR:
                    return False
                time.sleep(0.1)

            self._set_status(SourceStatus.ERROR, "Connection timeout")
            return False

        except Exception as e:
            self._set_status(SourceStatus.ERROR, str(e))
            self._running = False
            return False

    def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False

        if self._ws:
            try:
                self._ws.close()
            except:
                pass
            self._ws = None

        self._set_status(SourceStatus.DISCONNECTED)

    def subscribe(self, mmsi_list: List[str]) -> bool:
        """
        Subscribe to position updates for specific vessels.

        This updates the subscription filter. If already connected,
        sends an updated subscription message.
        """
        self.subscribed_mmsi = list(set(mmsi_list))
        self._log(f"Subscribed to {len(self.subscribed_mmsi)} MMSI(s)")

        # If connected, update subscription
        if self.is_available() and self._ws:
            try:
                self._send_subscription()
                return True
            except Exception as e:
                self._log(f"Failed to update subscription: {e}", level="error")
                return False

        return True

    def set_bounding_box(self, lat_min: float, lon_min: float,
                         lat_max: float, lon_max: float) -> None:
        """
        Set geographic bounding box for area-based tracking.

        This subscribes to ALL vessels in the specified area.
        Clear subscribed_mmsi to avoid MMSI filtering.

        Args:
            lat_min: Southern latitude boundary
            lon_min: Western longitude boundary
            lat_max: Northern latitude boundary
            lon_max: Eastern longitude boundary

        Example - East China Sea area:
            source.set_bounding_box(20, 110, 35, 130)
        """
        self.bounding_boxes = [[[lat_min, lon_min], [lat_max, lon_max]]]
        self.subscribed_mmsi = []  # Clear MMSI filter for area mode
        self._log(f"Set bounding box: ({lat_min},{lon_min}) to ({lat_max},{lon_max})")

        # If connected, update subscription
        if self.is_available() and self._ws:
            self._send_subscription()

    def add_bounding_box(self, lat_min: float, lon_min: float,
                         lat_max: float, lon_max: float) -> None:
        """Add an additional bounding box (supports multiple areas)."""
        self.bounding_boxes.append([[lat_min, lon_min], [lat_max, lon_max]])
        self._log(f"Added bounding box: ({lat_min},{lon_min}) to ({lat_max},{lon_max})")

        if self.is_available() and self._ws:
            self._send_subscription()

    def clear_bounding_boxes(self) -> None:
        """Clear all bounding boxes."""
        self.bounding_boxes = []
        self._log("Cleared all bounding boxes")

    def fetch_positions(self, mmsi_list: List[str]) -> List[AISPosition]:
        """
        Fetch latest cached positions for specified vessels.

        For real-time sources, this returns cached data from the stream.
        Does not trigger new API calls.
        """
        positions = []

        with self._cache_lock:
            for mmsi in mmsi_list:
                if mmsi in self._position_cache:
                    positions.append(self._position_cache[mmsi])

        return positions

    def fetch_vessel_info(self, mmsi: str) -> Optional[AISVesselInfo]:
        """Get cached vessel info from static data reports."""
        with self._cache_lock:
            return self._vessel_info_cache.get(mmsi)

    def get_all_cached_positions(self) -> List[AISPosition]:
        """Get all positions currently in cache."""
        with self._cache_lock:
            return list(self._position_cache.values())

    def _websocket_loop(self) -> None:
        """Main WebSocket event loop (runs in background thread)."""
        while self._running:
            try:
                self._log("Connecting to WebSocket...")

                self._ws = websocket.WebSocketApp(
                    self.WEBSOCKET_URL,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )

                # Run with ping interval for keepalive
                self._ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10
                )

            except Exception as e:
                self._log(f"WebSocket error: {e}", level="error")

            if self._running:
                self._log("Reconnecting in 5 seconds...")
                time.sleep(5)

    def _on_open(self, ws) -> None:
        """Handle WebSocket connection opened."""
        self._set_status(SourceStatus.CONNECTED)
        self._send_subscription()

    def _on_message(self, ws, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            self._process_message(data)
        except json.JSONDecodeError as e:
            self._log(f"Invalid JSON: {e}", level="warning")
        except Exception as e:
            self._log(f"Message processing error: {e}", level="error")

    def _on_error(self, ws, error) -> None:
        """Handle WebSocket error."""
        error_str = str(error)
        self._log(f"WebSocket error: {error_str}", level="error")

        if "401" in error_str or "unauthorized" in error_str.lower():
            self._set_status(SourceStatus.ERROR, "Invalid API key")
        elif "429" in error_str or "rate" in error_str.lower():
            self._set_status(SourceStatus.RATE_LIMITED)
        else:
            self._set_status(SourceStatus.ERROR, error_str[:100])

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """Handle WebSocket connection closed."""
        if self._running:
            self._log(f"Connection closed: {close_status_code} {close_msg}", level="warning")
            self._set_status(SourceStatus.DISCONNECTED)
        else:
            self._set_status(SourceStatus.DISCONNECTED)

    def _send_subscription(self) -> None:
        """Send subscription message to AISStream."""
        if not self._ws:
            return

        # Build subscription message
        subscribe_msg = {
            "APIKey": self.api_key,
        }

        # Use configured bounding boxes or default to global
        if self.bounding_boxes:
            subscribe_msg["BoundingBoxes"] = self.bounding_boxes
            box_count = len(self.bounding_boxes)
            self._log(f"Using {box_count} bounding box(es) for geographic filtering")
        else:
            # Global coverage
            subscribe_msg["BoundingBoxes"] = [[[-90, -180], [90, 180]]]

        # Only add MMSI filter if we have specific vessels to track
        # (not in area mode)
        if self.subscribed_mmsi:
            subscribe_msg["FiltersShipMMSI"] = self.subscribed_mmsi
            self._log(f"Subscription sent: {len(self.subscribed_mmsi)} vessels")
        else:
            self._log(f"Subscription sent: ALL vessels in bounding box")

        try:
            self._ws.send(json.dumps(subscribe_msg))
        except Exception as e:
            self._log(f"Failed to send subscription: {e}", level="error")

    def _process_message(self, data: Dict[str, Any]) -> None:
        """Process incoming AISStream message."""
        msg_type = data.get("MessageType")

        if msg_type == "PositionReport":
            self._process_position_report(data)
        elif msg_type == "StandardClassBPositionReport":
            self._process_position_report(data)
        elif msg_type == "ExtendedClassBPositionReport":
            self._process_position_report(data)
        elif msg_type == "StaticDataReport":
            self._process_static_data(data)
        elif msg_type == "ShipStaticData":
            self._process_static_data(data)
        # Ignore other message types (BaseStationReport, etc.)

    def _process_position_report(self, data: Dict[str, Any]) -> None:
        """Process position report message (types 1, 2, 3, 18, 19)."""
        try:
            # Extract metadata
            meta = data.get("MetaData", {})
            mmsi = str(meta.get("MMSI", ""))

            if not mmsi or len(mmsi) != 9:
                return

            # Extract message content
            message = data.get("Message", {})
            pos_report = message.get("PositionReport", message.get("StandardClassBPositionReport", message.get("ExtendedClassBPositionReport", {})))

            if not pos_report:
                return

            # Parse coordinates
            latitude = pos_report.get("Latitude")
            longitude = pos_report.get("Longitude")

            if latitude is None or longitude is None:
                return

            # Parse timestamp
            timestamp_str = meta.get("time_utc", meta.get("TimeReceived"))
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                except:
                    timestamp = datetime.utcnow()
            else:
                timestamp = datetime.utcnow()

            # Create position object
            position = AISPosition(
                mmsi=mmsi,
                latitude=latitude,
                longitude=longitude,
                timestamp=timestamp,
                speed_knots=pos_report.get("Sog"),
                course=pos_report.get("Cog"),
                heading=pos_report.get("TrueHeading"),
                nav_status=pos_report.get("NavigationalStatus"),
                source="aisstream",
                source_timestamp=datetime.utcnow(),
                raw_message=json.dumps(data)[:500]  # Truncate for storage
            )

            # Validate position
            if not position.is_valid():
                return

            # Update cache
            with self._cache_lock:
                self._position_cache[mmsi] = position

            # Update stats
            self.positions_received += 1
            self.last_update = datetime.utcnow()

            # Notify callbacks
            self._notify_callbacks(position)

            # Log periodically
            if self.positions_received % 100 == 0:
                self._log(f"Received {self.positions_received} positions, {len(self._position_cache)} vessels cached")

        except Exception as e:
            self._log(f"Error processing position: {e}", level="warning")

    def _process_static_data(self, data: Dict[str, Any]) -> None:
        """Process static data report (type 5, 24)."""
        try:
            meta = data.get("MetaData", {})
            mmsi = str(meta.get("MMSI", ""))

            if not mmsi:
                return

            message = data.get("Message", {})
            static = message.get("ShipStaticData", message.get("StaticDataReport", {}))

            if not static:
                return

            # Create vessel info
            vessel_info = AISVesselInfo(
                mmsi=mmsi,
                imo=static.get("ImoNumber"),
                name=static.get("Name", "").strip(),
                callsign=static.get("CallSign", "").strip(),
                ship_type=static.get("Type"),
                ship_type_text=get_ship_type_text(static.get("Type", 0)),
                length=static.get("Dimension", {}).get("A", 0) + static.get("Dimension", {}).get("B", 0),
                width=static.get("Dimension", {}).get("C", 0) + static.get("Dimension", {}).get("D", 0),
                draught=static.get("MaximumStaticDraught"),
                destination=static.get("Destination", "").strip(),
                source="aisstream"
            )

            with self._cache_lock:
                self._vessel_info_cache[mmsi] = vessel_info

        except Exception as e:
            self._log(f"Error processing static data: {e}", level="warning")


# Example message for documentation/testing
EXAMPLE_POSITION_MESSAGE = {
    "MessageType": "PositionReport",
    "MetaData": {
        "MMSI": 413000000,
        "MMSI_String": "413000000",
        "ShipName": "ZHONG DA 79",
        "time_utc": "2025-12-27T10:30:00Z"
    },
    "Message": {
        "PositionReport": {
            "MessageID": 1,
            "RepeatIndicator": 0,
            "UserID": 413000000,
            "NavigationalStatus": 0,
            "Sog": 0.1,
            "Longitude": 121.489,
            "Latitude": 31.2456,
            "Cog": 91.0,
            "TrueHeading": 90,
            "Timestamp": 30
        }
    }
}

EXAMPLE_NORMALIZED_OUTPUT = {
    "mmsi": "413000000",
    "lat": 31.2456,
    "lon": 121.489,
    "speed": 0.1,
    "course": 91.0,
    "heading": 90,
    "timestamp": "2025-12-27T10:30:00+00:00",
    "source": "aisstream"
}
