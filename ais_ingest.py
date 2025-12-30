#!/usr/bin/env python3
"""
AIS Data Ingestion Module for Arsenal Ship Tracker
Supports multiple AIS data sources with watchlist filtering and geofence detection.
Zero external dependencies - uses only Python standard library.

Data Sources (priority order):
1. AISStream.io - Real-time WebSocket (primary)
2. Marinesia - REST API (fallback)
3. Global Fishing Watch - REST API (enrichment only)
"""

import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2

# Import new AIS source manager
try:
    from ais_sources import AISSourceManager, AISPosition
    NEW_SOURCES_AVAILABLE = True
except ImportError:
    NEW_SOURCES_AVAILABLE = False

# Configuration
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'arsenal_tracker.db')
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ais_config.json')
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')

# Default config template
DEFAULT_CONFIG = {
    "sources": {
        "aishub": {
            "enabled": False,
            "username": "",
            "api_url": "https://data.aishub.net/ws.php",
            "format": "json"
        },
        "vesselfinder": {
            "enabled": False,
            "api_key": "",
            "api_url": "https://api.vesselfinder.com/vessels"
        },
        "spire": {
            "enabled": False,
            "api_key": "",
            "api_url": "https://ais.spire.com/vessels"
        },
        "marinetraffic": {
            "enabled": False,
            "api_key": "",
            "api_url": "https://services.marinetraffic.com/api/exportvessels"
        }
    },
    "poll_interval_seconds": 300,
    "dark_period_hours": 24,
    "alerts": {
        "on_position_update": True,
        "on_geofence_enter": True,
        "on_geofence_exit": True,
        "on_dark_period": True
    }
}


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_database():
    """Ensure database exists, initialize if not."""
    if not os.path.exists(DB_PATH):
        if not os.path.exists(SCHEMA_PATH):
            print(f"[Error] Schema file not found: {SCHEMA_PATH}")
            print("Run this script from the same directory as schema.sql")
            sys.exit(1)
        print("Database not found. Initializing...")
        conn = get_db()
        with open(SCHEMA_PATH, 'r') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
        print(f"Database initialized: {DB_PATH}")


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c


def load_config():
    """Load configuration from file."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return DEFAULT_CONFIG


def save_config(config):
    """Save configuration to file."""
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def get_watchlist():
    """Get list of MMSIs to track."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT v.id, v.mmsi, v.name, w.alert_on_position, w.alert_on_dark, w.alert_on_geofence
        FROM watchlist w
        JOIN vessels v ON w.vessel_id = v.id
        WHERE v.mmsi IS NOT NULL AND v.mmsi != ''
    ''')
    watchlist = {row['mmsi']: dict(row) for row in cursor.fetchall()}
    conn.close()
    return watchlist


def get_shipyards():
    """Get list of shipyards with geofence data."""
    conn = get_db()
    cursor = conn.execute('SELECT * FROM shipyards')
    shipyards = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return shipyards


def get_last_position(vessel_id):
    """Get last known position for a vessel."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT * FROM positions
        WHERE vessel_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    ''', (vessel_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def log_position(vessel_id, lat, lon, heading=None, speed=None, source='ais'):
    """Log a position update."""
    conn = get_db()
    conn.execute('''
        INSERT INTO positions (vessel_id, latitude, longitude, heading, speed_knots, source)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (vessel_id, lat, lon, heading, speed, source))
    conn.execute('UPDATE vessels SET last_updated = CURRENT_TIMESTAMP WHERE id = ?', (vessel_id,))
    conn.commit()
    conn.close()


def log_event(vessel_id, event_type, severity, title, description=None, lat=None, lon=None, source=None):
    """Log an event."""
    conn = get_db()
    conn.execute('''
        INSERT INTO events (vessel_id, event_type, severity, title, description, latitude, longitude, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (vessel_id, event_type, severity, title, description, lat, lon, source))
    conn.commit()
    conn.close()


def create_alert(vessel_id, alert_type, severity, title, message):
    """Create an alert."""
    conn = get_db()
    conn.execute('''
        INSERT INTO alerts (vessel_id, alert_type, severity, title, message)
        VALUES (?, ?, ?, ?, ?)
    ''', (vessel_id, alert_type, severity, title, message))
    conn.commit()
    conn.close()


def check_geofences(vessel_id, lat, lon, shipyards):
    """Check if position is within any shipyard geofence."""
    for shipyard in shipyards:
        distance = haversine(lat, lon, shipyard['latitude'], shipyard['longitude'])
        if distance <= shipyard['geofence_radius_km']:
            return shipyard
    return None


def check_dark_period(vessel_id, config):
    """Check if vessel has been dark for too long."""
    last_pos = get_last_position(vessel_id)
    if not last_pos:
        return False

    last_time = datetime.fromisoformat(last_pos['timestamp'].replace('Z', '+00:00'))
    threshold = timedelta(hours=config.get('dark_period_hours', 24))

    if datetime.utcnow() - last_time > threshold:
        return True
    return False


# =============================================================================
# AIS Data Source Implementations
# =============================================================================

class AISSource:
    """Base class for AIS data sources."""

    def __init__(self, config):
        self.config = config

    def fetch_positions(self, mmsi_list):
        """Fetch positions for given MMSIs. Override in subclass."""
        raise NotImplementedError


class AISHubSource(AISSource):
    """AISHub data source (community-based, free with data sharing)."""

    def fetch_positions(self, mmsi_list):
        config = self.config.get('aishub', {})
        if not config.get('enabled') or not config.get('username'):
            return []

        # AISHub requires data sharing agreement
        # This is a simplified example - actual implementation needs proper auth
        url = f"{config['api_url']}?username={config['username']}&format=1&output=json&compress=0"

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'ArsenalTracker/1.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())

            positions = []
            for record in data:
                mmsi = str(record.get('MMSI', ''))
                if mmsi in mmsi_list:
                    positions.append({
                        'mmsi': mmsi,
                        'latitude': float(record.get('LATITUDE', 0)),
                        'longitude': float(record.get('LONGITUDE', 0)),
                        'heading': record.get('HEADING'),
                        'speed': record.get('SPEED'),
                        'timestamp': record.get('TIME')
                    })
            return positions

        except Exception as e:
            print(f"[AISHub Error] {e}")
            return []


class VesselFinderSource(AISSource):
    """VesselFinder API (free tier available)."""

    def fetch_positions(self, mmsi_list):
        config = self.config.get('vesselfinder', {})
        if not config.get('enabled') or not config.get('api_key'):
            return []

        positions = []
        for mmsi in mmsi_list:
            try:
                url = f"{config['api_url']}?userkey={config['api_key']}&mmsi={mmsi}"
                req = urllib.request.Request(url, headers={'User-Agent': 'ArsenalTracker/1.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = json.loads(response.read().decode())

                if data and isinstance(data, list) and len(data) > 0:
                    record = data[0]
                    positions.append({
                        'mmsi': mmsi,
                        'latitude': float(record.get('LAT', 0)),
                        'longitude': float(record.get('LON', 0)),
                        'heading': record.get('HEADING'),
                        'speed': record.get('SPEED'),
                        'timestamp': record.get('TIMESTAMP')
                    })
                time.sleep(1)  # Rate limiting

            except Exception as e:
                print(f"[VesselFinder Error] MMSI {mmsi}: {e}")

        return positions


class SpireMaritimeSource(AISSource):
    """Spire Maritime API (enterprise)."""

    def fetch_positions(self, mmsi_list):
        config = self.config.get('spire', {})
        if not config.get('enabled') or not config.get('api_key'):
            return []

        positions = []
        headers = {
            'Authorization': f"Bearer {config['api_key']}",
            'User-Agent': 'ArsenalTracker/1.0'
        }

        for mmsi in mmsi_list:
            try:
                url = f"{config['api_url']}?mmsi={mmsi}"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = json.loads(response.read().decode())

                if data.get('data'):
                    record = data['data'][0]
                    pos = record.get('last_known_position', {})
                    positions.append({
                        'mmsi': mmsi,
                        'latitude': pos.get('latitude'),
                        'longitude': pos.get('longitude'),
                        'heading': pos.get('heading'),
                        'speed': pos.get('speed'),
                        'timestamp': pos.get('timestamp')
                    })
                time.sleep(0.5)

            except Exception as e:
                print(f"[Spire Error] MMSI {mmsi}: {e}")

        return positions


class MarineTrafficScraper(AISSource):
    """MarineTraffic scraper (against ToS - use at own risk)."""

    def fetch_positions(self, mmsi_list):
        # Note: Scraping MarineTraffic violates their ToS
        # This is included for reference only
        config = self.config.get('marinetraffic', {})
        if not config.get('enabled'):
            return []

        print("[Warning] MarineTraffic scraping violates ToS")
        return []


class NMEAParser:
    """Parser for raw NMEA/AIS messages."""

    @staticmethod
    def parse_message(nmea_str):
        """Parse NMEA sentence. Returns dict or None."""
        # Simplified - full implementation would decode AIS payload
        if not nmea_str.startswith('!AIVDM'):
            return None

        parts = nmea_str.split(',')
        if len(parts) < 6:
            return None

        return {
            'raw': nmea_str,
            'fragment_count': int(parts[1]) if parts[1] else 1,
            'fragment_num': int(parts[2]) if parts[2] else 1,
            'channel': parts[4],
            'payload': parts[5].split('*')[0]
        }


# =============================================================================
# Main Ingestion Loop
# =============================================================================

def run_ingestion_with_new_sources(config):
    """
    Main ingestion loop using new AISSourceManager.

    Uses AISStream.io (WebSocket) as primary source with
    Marinesia (REST) as fallback.
    """
    print("=" * 60)
    print("Arsenal Ship Tracker - AIS Ingestion (v2)")
    print("=" * 60)
    print("Using new source manager: AISStream + Marinesia fallback")

    # Ensure database exists
    ensure_database()

    # Initialize source manager from config
    manager = AISSourceManager.from_config(CONFIG_PATH)

    # Get watchlist
    watchlist = get_watchlist()
    mmsi_list = list(watchlist.keys())

    if not mmsi_list:
        print("\n[Warning] Watchlist is empty. Add vessels to track.")
        return

    print(f"\nTracking {len(mmsi_list)} vessels:")
    for mmsi, info in watchlist.items():
        print(f"  - {info['name']} (MMSI: {mmsi})")

    # Subscribe to vessels
    manager.subscribe(mmsi_list)

    # Start sources
    if not manager.start():
        print("\n[Warning] Could not connect to any AIS sources.")
        print("Check API keys in ais_config.json or set environment variables:")
        print("  - AISSTREAM_API_KEY (get from https://aisstream.io/)")
        print("  - GFW_API_KEY (get from https://globalfishingwatch.org/)")

    # Get shipyards for geofence checking
    shipyards = get_shipyards()

    poll_interval = config.get('poll_interval', config.get('poll_interval_seconds', 60))

    # Position update callback for real-time data
    def on_position(position: AISPosition):
        """Handle real-time position update."""
        mmsi = position.mmsi
        vessel_info = watchlist.get(mmsi)
        if not vessel_info:
            return

        vessel_id = vessel_info['id']
        lat, lon = position.latitude, position.longitude

        # Log position
        log_position(
            vessel_id, lat, lon,
            position.heading, position.speed_knots,
            position.source
        )
        print(f"  [{vessel_info['name']}] {lat:.4f}, {lon:.4f} (via {position.source})")

        # Check geofences
        if vessel_info['alert_on_geofence']:
            geofence = check_geofences(vessel_id, lat, lon, shipyards)
            if geofence:
                print(f"  [ALERT] {vessel_info['name']} in geofence: {geofence['name']}")
                log_event(
                    vessel_id, 'geofence_enter', 'high',
                    f"Entered {geofence['name']} geofence",
                    f"Vessel detected within {geofence['geofence_radius_km']}km of {geofence['name']}",
                    lat, lon, position.source
                )
                create_alert(
                    vessel_id, 'geofence', 'high',
                    f"{vessel_info['name']} entered {geofence['name']}",
                    f"Vessel detected at {lat:.4f}, {lon:.4f} - within {geofence['name']} geofence"
                )

    # Register callback for real-time updates
    manager.add_callback(on_position)

    print("\nStarting AIS ingestion (Ctrl+C to stop)...")
    print(f"Sources: {list(manager.sources.keys())}")

    try:
        while True:
            # Status check
            status = manager.get_status()
            primary = manager.get_primary_source()
            source_name = primary.name if primary else "none"

            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"\n[{timestamp}] Active source: {source_name} | Cached: {status['cached_positions']} positions")

            # For REST fallback, manually fetch positions
            if not primary or not primary.is_realtime():
                print("  Polling REST sources...")
                positions = manager.get_positions(mmsi_list)
                for pos in positions:
                    on_position(pos)

            # Check for dark periods
            for mmsi, vessel_info in watchlist.items():
                if vessel_info['alert_on_dark'] and check_dark_period(vessel_info['id'], config):
                    print(f"  [WARNING] {vessel_info['name']} has gone dark")

            # Refresh watchlist periodically
            watchlist = get_watchlist()
            new_mmsi_list = list(watchlist.keys())
            if set(new_mmsi_list) != set(mmsi_list):
                mmsi_list = new_mmsi_list
                manager.subscribe(mmsi_list)
                print(f"  Updated subscription: {len(mmsi_list)} vessels")

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\n[Shutdown] Stopping ingestion...")
    finally:
        manager.stop()


def run_ingestion(config):
    """Main ingestion loop."""
    # Use new source manager if available
    if NEW_SOURCES_AVAILABLE:
        return run_ingestion_with_new_sources(config)

    # Legacy ingestion for backward compatibility
    print("=" * 60)
    print("Arsenal Ship Tracker - AIS Ingestion (Legacy)")
    print("=" * 60)
    print("[Note] Upgrade to new sources: pip install websocket-client")

    # Ensure database exists
    ensure_database()

    # Initialize data sources
    sources = []
    if config['sources'].get('aishub', {}).get('enabled'):
        sources.append(('AISHub', AISHubSource(config['sources'])))
    if config['sources'].get('vesselfinder', {}).get('enabled'):
        sources.append(('VesselFinder', VesselFinderSource(config['sources'])))
    if config['sources'].get('spire', {}).get('enabled'):
        sources.append(('Spire', SpireMaritimeSource(config['sources'])))

    if not sources:
        print("\n[Warning] No AIS sources enabled. Configure ais_config.json")
        print("Running in monitoring-only mode (no live data).\n")

    poll_interval = config.get('poll_interval_seconds', 300)

    while True:
        try:
            watchlist = get_watchlist()
            shipyards = get_shipyards()
            mmsi_list = list(watchlist.keys())

            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Polling {len(mmsi_list)} vessels...")

            for source_name, source in sources:
                print(f"  Querying {source_name}...")
                positions = source.fetch_positions(mmsi_list)

                for pos in positions:
                    mmsi = pos['mmsi']
                    vessel_info = watchlist.get(mmsi)
                    if not vessel_info:
                        continue

                    vessel_id = vessel_info['id']
                    lat, lon = pos['latitude'], pos['longitude']

                    # Log position
                    log_position(vessel_id, lat, lon, pos.get('heading'), pos.get('speed'), source_name.lower())
                    print(f"    [{vessel_info['name']}] Position: {lat:.4f}, {lon:.4f}")

                    # Check geofences
                    if vessel_info['alert_on_geofence']:
                        geofence = check_geofences(vessel_id, lat, lon, shipyards)
                        if geofence:
                            print(f"    [ALERT] {vessel_info['name']} in geofence: {geofence['name']}")
                            log_event(
                                vessel_id, 'geofence_enter', 'high',
                                f"Entered {geofence['name']} geofence",
                                f"Vessel detected within {geofence['geofence_radius_km']}km of {geofence['name']}",
                                lat, lon, source_name
                            )
                            create_alert(
                                vessel_id, 'geofence', 'high',
                                f"{vessel_info['name']} entered {geofence['name']}",
                                f"Vessel detected at {lat:.4f}, {lon:.4f} - within {geofence['name']} geofence"
                            )

            # Check for dark periods
            for mmsi, vessel_info in watchlist.items():
                if vessel_info['alert_on_dark'] and check_dark_period(vessel_info['id'], config):
                    print(f"  [WARNING] {vessel_info['name']} has gone dark (>{config['dark_period_hours']}h)")

            print(f"  Next poll in {poll_interval}s")
            time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\n[Shutdown] Stopping ingestion...")
            break
        except Exception as e:
            print(f"[Error] {e}")
            time.sleep(60)


def test_connectivity():
    """Test AIS source connectivity."""
    ensure_database()
    config = load_config()
    print("Testing AIS source connectivity...\n")

    watchlist = get_watchlist()
    print(f"Watchlist: {len(watchlist)} vessels with MMSI")
    for mmsi, info in watchlist.items():
        print(f"  - {info['name']} (MMSI: {mmsi})")

    # Test new source manager if available
    if NEW_SOURCES_AVAILABLE:
        print("\n--- New AIS Source Manager ---")
        manager = AISSourceManager.from_config(CONFIG_PATH)

        print(f"Configured sources: {list(manager.sources.keys())}")
        print(f"Priority order: {manager.source_priority}")

        print("\nTesting connections:")
        for name, source in manager.sources.items():
            try:
                connected = source.connect()
                status = "CONNECTED" if connected else "FAILED"
                print(f"  - {name}: {status}")
                if connected:
                    source.disconnect()
            except Exception as e:
                print(f"  - {name}: ERROR - {e}")

        print("\nTo configure sources, edit ais_config.json")
        print("Environment variables:")
        print("  - AISSTREAM_API_KEY: Get from https://aisstream.io/")
        print("  - GFW_API_KEY: Get from https://globalfishingwatch.org/")
    else:
        print("\n--- Legacy Sources ---")
        print("Configured sources:")
        for name, cfg in config['sources'].items():
            status = "ENABLED" if cfg.get('enabled') else "disabled"
            print(f"  - {name}: {status}")

        print("\nTo enable sources, edit ais_config.json")
        print("\n[Tip] Install websocket-client for real-time data:")
        print("  pip install websocket-client")


def init_config():
    """Initialize configuration file."""
    if os.path.exists(CONFIG_PATH):
        print(f"Config already exists: {CONFIG_PATH}")
        return

    save_config(DEFAULT_CONFIG)
    print(f"Created config file: {CONFIG_PATH}")
    print("Edit this file to configure AIS data sources.")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'init':
            init_config()
        elif cmd == 'test':
            test_connectivity()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python ais_ingest.py [init|test]")
    else:
        config = load_config()
        run_ingestion(config)
