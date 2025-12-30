"""
AIS Source Manager

Orchestrates multiple AIS data sources with priority-based fallback.
Ensures consistent data flow even when primary sources are unavailable.

Priority Order:
1. AISStream.io (real-time WebSocket) - Primary
2. Marinesia (REST API) - Fallback
3. Global Fishing Watch (REST API) - Enrichment only

Design Principles:
- Fail gracefully (never crash on source failure)
- Prefer real-time data over cached
- Deduplicate positions across sources
- Log source health for monitoring
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Callable

from .base import (
    AISSource, AISPosition, AISVesselInfo, AISEvent,
    SourceType, SourceStatus
)
from .aisstream import AISStreamSource
from .aishub import AISHubSource
from .marinesia import MarinesiaSource
from .gfw import GlobalFishingWatchSource


class AISSourceManager:
    """
    Manages multiple AIS data sources with automatic fallback.

    Provides a unified interface for fetching vessel positions
    regardless of which underlying source is available.

    Configuration:
        Load from ais_config.json or configure programmatically.

    Usage:
        manager = AISSourceManager.from_config("ais_config.json")
        manager.start()

        # Subscribe to vessels
        manager.subscribe(["413000000", "123456789"])

        # Get latest positions
        positions = manager.get_positions(["413000000"])

        # Get vessel info (checks all sources)
        info = manager.get_vessel_info("413000000")

        # Get behavioral events (from GFW)
        events = manager.get_events("413000000", days=30)

        manager.stop()
    """

    def __init__(self):
        self.sources: Dict[str, AISSource] = {}
        self.source_priority: List[str] = []  # Ordered by priority

        # Subscribed vessels
        self.subscribed_mmsi: List[str] = []

        # Position cache (MMSI -> latest position)
        self._position_cache: Dict[str, AISPosition] = {}
        self._cache_lock = threading.Lock()

        # Callbacks for position updates
        self._callbacks: List[Callable[[AISPosition], None]] = []

        # Status
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_interval: int = 60  # seconds for REST fallback polling

        # Logging
        self._log_callback: Optional[Callable[[str, str], None]] = None

    @classmethod
    def from_config(cls, config_path: str) -> "AISSourceManager":
        """
        Create manager from configuration file.

        Config format:
        {
            "sources": {
                "aisstream": {
                    "enabled": true,
                    "api_key": "${AISSTREAM_API_KEY}"
                },
                "marinesia": {
                    "enabled": true,
                    "rate_limit": 30
                },
                "gfw": {
                    "enabled": false,
                    "api_key": "${GFW_API_KEY}"
                }
            },
            "priority": ["aisstream", "marinesia"],
            "poll_interval": 60
        }
        """
        manager = cls()

        if not os.path.exists(config_path):
            manager._log(f"Config file not found: {config_path}", level="warning")
            return manager

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)

            # Parse sources (pass full config for area tracking)
            sources_config = config.get("sources", {})
            manager._configure_sources(sources_config, config)

            # Set priority order
            manager.source_priority = config.get("priority", ["aisstream", "marinesia"])

            # Set poll interval
            manager._poll_interval = config.get("poll_interval", 60)

            manager._log(f"Loaded configuration from {config_path}")

        except Exception as e:
            manager._log(f"Error loading config: {e}", level="error")

        return manager

    def _configure_sources(self, sources_config: Dict[str, Any], config: Dict[str, Any] = None) -> None:
        """Configure sources from config dict."""
        # AISStream
        ais_config = sources_config.get("aisstream", {})
        if ais_config.get("enabled", False):
            api_key = self._resolve_env_var(ais_config.get("api_key", ""))
            if api_key:
                source = AISStreamSource(api_key=api_key)

                # Check for area tracking config
                if config:
                    area_config = config.get("area_tracking", {})
                    if area_config.get("enabled", False):
                        bbox = area_config.get("bounding_box", {})
                        if all(k in bbox for k in ["lat_min", "lon_min", "lat_max", "lon_max"]):
                            source.set_bounding_box(
                                bbox["lat_min"], bbox["lon_min"],
                                bbox["lat_max"], bbox["lon_max"]
                            )
                            self._log(f"Area tracking enabled: {bbox.get('description', 'custom area')}")

                self.add_source(source)
            else:
                self._log("AISStream enabled but no API key provided", level="warning")

        # AISHub
        aishub_config = sources_config.get("aishub", {})
        if aishub_config.get("enabled", False):
            username = self._resolve_env_var(aishub_config.get("username", ""))
            if username:
                source = AISHubSource(username=username)

                # Set bounding box if area tracking enabled
                if config:
                    area_config = config.get("area_tracking", {})
                    if area_config.get("enabled", False):
                        bbox = area_config.get("bounding_box", {})
                        if all(k in bbox for k in ["lat_min", "lon_min", "lat_max", "lon_max"]):
                            source.set_bounding_box(
                                bbox["lat_min"], bbox["lon_min"],
                                bbox["lat_max"], bbox["lon_max"]
                            )

                self.add_source(source)
            else:
                self._log("AISHub enabled but no username provided", level="warning")

        # Marinesia
        mar_config = sources_config.get("marinesia", {})
        if mar_config.get("enabled", True):  # Default enabled as fallback
            api_key = self._resolve_env_var(mar_config.get("api_key", ""))
            rate_limit = mar_config.get("rate_limit", 30)
            self.add_source(MarinesiaSource(api_key=api_key, rate_limit=rate_limit))

        # Global Fishing Watch
        gfw_config = sources_config.get("gfw", {})
        if gfw_config.get("enabled", False):
            api_key = self._resolve_env_var(gfw_config.get("api_key", ""))
            if api_key:
                rate_limit = gfw_config.get("rate_limit", 10)
                self.add_source(GlobalFishingWatchSource(api_key=api_key, rate_limit=rate_limit))
            else:
                self._log("GFW enabled but no API key provided", level="warning")

    def _resolve_env_var(self, value: str) -> str:
        """Resolve environment variable references like ${VAR_NAME}."""
        if not value:
            return ""

        if value.startswith("${") and value.endswith("}"):
            var_name = value[2:-1]
            return os.environ.get(var_name, "")

        return value

    def add_source(self, source: AISSource) -> None:
        """Add an AIS source to the manager."""
        self.sources[source.name] = source
        self._log(f"Added source: {source.name} ({source.source_type.value})")

        # Register callback for real-time sources
        if source.is_realtime():
            source.add_callback(self._on_position_update)

    def remove_source(self, name: str) -> None:
        """Remove an AIS source."""
        if name in self.sources:
            source = self.sources[name]
            source.disconnect()
            del self.sources[name]
            self._log(f"Removed source: {name}")

    def start(self) -> bool:
        """
        Start all enabled sources.

        Connects to real-time sources and starts background
        polling for REST sources.
        """
        if self._running:
            return True

        self._running = True
        connected_any = False

        # Connect sources in priority order
        for name in self.source_priority:
            if name not in self.sources:
                continue

            source = self.sources[name]
            try:
                if source.connect():
                    connected_any = True
                    self._log(f"Connected to {name}")

                    # Subscribe real-time sources
                    if source.is_realtime() and self.subscribed_mmsi:
                        source.subscribe(self.subscribed_mmsi)
            except Exception as e:
                self._log(f"Failed to connect {name}: {e}", level="error")

        # Start background polling thread for REST fallback
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        return connected_any

    def stop(self) -> None:
        """Stop all sources and background tasks."""
        self._running = False

        for name, source in self.sources.items():
            try:
                source.disconnect()
            except Exception as e:
                self._log(f"Error disconnecting {name}: {e}", level="warning")

        self._log("All sources stopped")

    def subscribe(self, mmsi_list: List[str]) -> bool:
        """
        Subscribe to position updates for specific vessels.

        Updates subscriptions on all real-time sources.
        """
        self.subscribed_mmsi = list(set(mmsi_list))
        self._log(f"Subscribed to {len(self.subscribed_mmsi)} vessel(s)")

        success = True
        for name, source in self.sources.items():
            if source.is_realtime() and source.is_available():
                try:
                    if not source.subscribe(self.subscribed_mmsi):
                        success = False
                except Exception as e:
                    self._log(f"Subscription failed for {name}: {e}", level="error")
                    success = False

        return success

    def get_positions(self, mmsi_list: Optional[List[str]] = None) -> List[AISPosition]:
        """
        Get latest positions for specified vessels.

        Uses priority-based source selection:
        1. Return cached positions from real-time sources
        2. Fall back to REST API if real-time unavailable
        """
        if mmsi_list is None:
            mmsi_list = self.subscribed_mmsi

        positions = []
        missing_mmsi = list(mmsi_list)

        # First, try to get from cache (populated by real-time sources)
        with self._cache_lock:
            for mmsi in mmsi_list:
                if mmsi in self._position_cache:
                    pos = self._position_cache[mmsi]
                    # Check if position is recent (within 5 minutes)
                    if self._is_position_recent(pos, max_age_seconds=300):
                        positions.append(pos)
                        missing_mmsi.remove(mmsi)

        # For missing positions, try REST sources in priority order
        if missing_mmsi:
            for name in self.source_priority:
                if name not in self.sources:
                    continue

                source = self.sources[name]
                if not source.is_available():
                    continue

                # Skip real-time sources (already checked cache)
                if source.is_realtime():
                    continue

                try:
                    rest_positions = source.fetch_positions(missing_mmsi)
                    for pos in rest_positions:
                        positions.append(pos)
                        if pos.mmsi in missing_mmsi:
                            missing_mmsi.remove(pos.mmsi)

                        # Update cache
                        with self._cache_lock:
                            self._update_cache(pos)

                    if not missing_mmsi:
                        break  # Got all positions

                except Exception as e:
                    self._log(f"Error fetching from {name}: {e}", level="error")

        return positions

    def get_vessel_info(self, mmsi: str) -> Optional[AISVesselInfo]:
        """
        Get vessel static information.

        Queries sources in priority order until info is found.
        """
        for name in self.source_priority:
            if name not in self.sources:
                continue

            source = self.sources[name]
            if not source.is_available():
                continue

            try:
                info = source.fetch_vessel_info(mmsi)
                if info:
                    return info
            except Exception as e:
                self._log(f"Error fetching vessel info from {name}: {e}", level="warning")

        return None

    def get_events(self, mmsi: str, days: int = 30) -> List[AISEvent]:
        """
        Get behavioral events for a vessel.

        Only available from enrichment sources (GFW).
        """
        events = []

        for name, source in self.sources.items():
            if source.source_type != SourceType.ENRICHMENT:
                continue

            if not source.is_available():
                continue

            try:
                source_events = source.fetch_events(mmsi, days)
                events.extend(source_events)
            except Exception as e:
                self._log(f"Error fetching events from {name}: {e}", level="error")

        return events

    def get_status(self) -> Dict[str, Any]:
        """Get status of all sources."""
        return {
            "running": self._running,
            "subscribed_vessels": len(self.subscribed_mmsi),
            "cached_positions": len(self._position_cache),
            "sources": {
                name: source.get_status()
                for name, source in self.sources.items()
            }
        }

    def get_primary_source(self) -> Optional[AISSource]:
        """Get the highest-priority available source."""
        for name in self.source_priority:
            if name in self.sources:
                source = self.sources[name]
                if source.is_available():
                    return source
        return None

    def add_callback(self, callback: Callable[[AISPosition], None]) -> None:
        """Register callback for position updates."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[AISPosition], None]) -> None:
        """Remove a registered callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def set_log_callback(self, callback: Callable[[str, str], None]) -> None:
        """Set callback for log messages (level, message)."""
        self._log_callback = callback

    def _on_position_update(self, position: AISPosition) -> None:
        """Handle position update from real-time source."""
        with self._cache_lock:
            self._update_cache(position)

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(position)
            except Exception as e:
                self._log(f"Callback error: {e}", level="error")

    def _update_cache(self, position: AISPosition) -> None:
        """
        Update position cache with deduplication logic.

        Only updates if:
        - Position is newer than cached
        - Position is from higher-priority source
        - No existing position in cache
        """
        mmsi = position.mmsi

        if mmsi not in self._position_cache:
            self._position_cache[mmsi] = position
            return

        existing = self._position_cache[mmsi]

        # Always prefer newer data
        if position.timestamp and existing.timestamp:
            if position.timestamp > existing.timestamp:
                self._position_cache[mmsi] = position
                return

        # If same timestamp, prefer higher priority source
        if position.source in self.source_priority and existing.source in self.source_priority:
            new_priority = self.source_priority.index(position.source)
            old_priority = self.source_priority.index(existing.source)
            if new_priority < old_priority:  # Lower index = higher priority
                self._position_cache[mmsi] = position

    def _is_position_recent(self, position: AISPosition, max_age_seconds: int = 300) -> bool:
        """Check if position is within acceptable age."""
        if not position.source_timestamp:
            return False

        age = (datetime.utcnow() - position.source_timestamp).total_seconds()
        return age < max_age_seconds

    def _poll_loop(self) -> None:
        """Background polling loop for REST sources."""
        while self._running:
            try:
                # Check if primary real-time source is healthy
                primary = self.get_primary_source()

                if primary and primary.is_realtime() and primary.is_available():
                    # Real-time source is working, minimal polling needed
                    time.sleep(self._poll_interval)
                    continue

                # Primary source unavailable, actively poll REST sources
                self._log("Primary source unavailable, polling fallback sources")

                if self.subscribed_mmsi:
                    for name in self.source_priority:
                        if name not in self.sources:
                            continue

                        source = self.sources[name]
                        if source.is_realtime():
                            continue  # Skip real-time sources

                        if not source.is_available():
                            # Try to reconnect
                            try:
                                source.connect()
                            except:
                                continue

                        if source.is_available():
                            try:
                                positions = source.fetch_positions(self.subscribed_mmsi)
                                for pos in positions:
                                    self._on_position_update(pos)
                                break  # Got data from one source
                            except Exception as e:
                                self._log(f"Polling error for {name}: {e}", level="error")

            except Exception as e:
                self._log(f"Poll loop error: {e}", level="error")

            time.sleep(self._poll_interval)

    def _log(self, message: str, level: str = "info") -> None:
        """Log a message."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[{timestamp}] [ais_manager]"

        formatted = f"{prefix} {message}"
        if level == "error":
            formatted = f"{prefix} ERROR: {message}"
        elif level == "warning":
            formatted = f"{prefix} WARNING: {message}"

        print(formatted)

        if self._log_callback:
            self._log_callback(level, message)


# Convenience function for quick setup
def create_manager(
    aisstream_key: Optional[str] = None,
    gfw_key: Optional[str] = None,
    enable_marinesia: bool = True
) -> AISSourceManager:
    """
    Create an AISSourceManager with specified sources.

    Args:
        aisstream_key: AISStream.io API key (primary source)
        gfw_key: Global Fishing Watch API key (enrichment)
        enable_marinesia: Enable Marinesia as fallback (no key required)

    Returns:
        Configured AISSourceManager instance
    """
    manager = AISSourceManager()

    # Add sources based on available keys
    if aisstream_key:
        manager.add_source(AISStreamSource(api_key=aisstream_key))
        manager.source_priority.append("aisstream")

    if enable_marinesia:
        manager.add_source(MarinesiaSource())
        manager.source_priority.append("marinesia")

    if gfw_key:
        manager.add_source(GlobalFishingWatchSource(api_key=gfw_key))
        # GFW is enrichment only, not in position priority

    return manager


# Example configuration
EXAMPLE_CONFIG = {
    "sources": {
        "aisstream": {
            "enabled": True,
            "api_key": "${AISSTREAM_API_KEY}"
        },
        "aishub": {
            "enabled": False,
            "username": "${AISHUB_USERNAME}"
        },
        "marinesia": {
            "enabled": True,
            "rate_limit": 30
        },
        "gfw": {
            "enabled": False,
            "api_key": "${GFW_API_KEY}",
            "rate_limit": 10
        }
    },
    "priority": ["aisstream", "aishub", "marinesia"],
    "poll_interval": 60
}
