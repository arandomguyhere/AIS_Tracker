#!/usr/bin/env python3
"""
Arsenal Ship Tracker API Server
Zero external dependencies - uses only Python standard library
"""

import gzip
import json
import os
import sqlite3
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from utils import haversine

# Import vessel intelligence module
try:
    from vessel_intel import analyze_vessel_intel, quick_vessel_bluf
    INTEL_AVAILABLE = True
except ImportError:
    INTEL_AVAILABLE = False

# Import weather module
try:
    from weather import get_weather_service, enrich_position_with_weather
    WEATHER_AVAILABLE = True
except ImportError:
    WEATHER_AVAILABLE = False

# Import SAR detection module
try:
    from sar_import import (
        get_sar_detections, get_dark_vessels, import_sar_file,
        parse_detections, correlate_with_ais, save_detections_to_db
    )
    SAR_AVAILABLE = True
except ImportError:
    SAR_AVAILABLE = False

# Import confidence scoring module
try:
    from confidence import (
        calculate_vessel_confidence, save_confidence_to_db,
        get_vessel_confidence
    )
    CONFIDENCE_AVAILABLE = True
except ImportError:
    CONFIDENCE_AVAILABLE = False

# Import intelligence module
try:
    from intelligence import produce_vessel_intelligence, get_intel_summary
    INTELLIGENCE_AVAILABLE = True
except ImportError:
    INTELLIGENCE_AVAILABLE = False

# Import behavior detection module
try:
    from behavior import (
        validate_mmsi, get_flag_country, analyze_vessel_behavior,
        detect_encounters, detect_loitering, detect_ais_gaps, detect_spoofing,
        downsample_track, segment_track
    )
    BEHAVIOR_AVAILABLE = True
except ImportError:
    BEHAVIOR_AVAILABLE = False

# Import Venezuela dark fleet detection module
try:
    from venezuela import (
        is_in_venezuela_zone, check_venezuela_alerts,
        calculate_venezuela_risk_score, detect_ais_spoofing,
        detect_circle_spoofing, KNOWN_DARK_FLEET_VESSELS,
        get_venezuela_monitoring_config
    )
    VENEZUELA_AVAILABLE = True
except ImportError:
    VENEZUELA_AVAILABLE = False

# Import sanctions database module
try:
    from sanctions import (
        SanctionsDatabase, check_venezuela_sanctions,
        calculate_sanction_confidence, enrich_vessel_with_sanctions,
        fetch_fleetleaks_map_data
    )
    SANCTIONS_AVAILABLE = True
except ImportError:
    SANCTIONS_AVAILABLE = False

# Import multi-region dark fleet detection module
try:
    from dark_fleet import (
        Region, is_in_region_zone, is_in_any_monitored_zone,
        get_nearby_key_points, calculate_dark_fleet_risk_score,
        check_dark_fleet_alerts, get_dark_fleet_config,
        get_known_vessels_by_region, get_dark_fleet_statistics,
        KNOWN_DARK_FLEET_VESSELS as DARK_FLEET_VESSELS
    )
    DARK_FLEET_AVAILABLE = True
except ImportError:
    DARK_FLEET_AVAILABLE = False

# Import infrastructure threat analysis module
try:
    from infra_analysis import (
        get_baltic_infrastructure, analyze_vessel_for_incident,
        analyze_infrastructure_incident, BALTIC_INFRASTRUCTURE
    )
    INFRA_ANALYSIS_AVAILABLE = True
except ImportError:
    INFRA_ANALYSIS_AVAILABLE = False

# Import laden status detection module
try:
    from laden_status import (
        analyze_laden_status, get_laden_status_summary,
        LadenState, CargoEventType
    )
    LADEN_STATUS_AVAILABLE = True
except ImportError:
    LADEN_STATUS_AVAILABLE = False

# Import satellite intelligence module
try:
    from satellite_intel import (
        get_satellite_service, search_vessel_imagery, get_area_imagery,
        get_storage_facilities, analyze_storage_levels
    )
    SATELLITE_AVAILABLE = True
except ImportError:
    SATELLITE_AVAILABLE = False

# Import shoreside photography module
try:
    from shoreside_photos import get_photo_service
    PHOTOS_AVAILABLE = True
except ImportError:
    PHOTOS_AVAILABLE = False

# Import Global Fishing Watch integration
try:
    from gfw_integration import (
        is_configured as gfw_is_configured,
        search_vessel as gfw_search_vessel,
        get_vessel_events as gfw_get_vessel_events,
        get_dark_fleet_indicators as gfw_get_dark_fleet_indicators,
        check_sts_zone as gfw_check_sts_zone,
        save_token as gfw_save_token
    )
    GFW_AVAILABLE = True
except ImportError:
    GFW_AVAILABLE = False

# Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'arsenal_tracker.db')
SCHEMA_PATH = os.path.join(SCRIPT_DIR, 'schema.sql')
STATIC_DIR = os.path.join(SCRIPT_DIR, 'static')
DOCS_DIR = os.path.join(SCRIPT_DIR, 'docs')
PHOTOS_DIR = os.path.join(STATIC_DIR, 'photos')
LIVE_VESSELS_PATH = os.path.join(DOCS_DIR, 'live_vessels.json')
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'ais_config.json')
PORT = 8080

# Database connection pool (thread-local storage)
_db_local = threading.local()


def get_db():
    """Get database connection with row factory (thread-safe with connection reuse)."""
    # Check if we have a cached connection and if it's still valid
    if hasattr(_db_local, 'conn') and _db_local.conn is not None:
        try:
            # Test if connection is still valid
            _db_local.conn.execute("SELECT 1")
            return _db_local.conn
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            # Connection is closed or invalid, clear it
            _db_local.conn = None

    # Create new connection
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still safe
    conn.execute("PRAGMA cache_size=-64000")   # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")   # Temp tables in memory
    conn.row_factory = sqlite3.Row
    _db_local.conn = conn
    return _db_local.conn


@contextmanager
def db_connection():
    """Context manager for database operations with automatic error handling."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e


def dict_from_row(row):
    """Convert sqlite3.Row to dictionary."""
    return dict(zip(row.keys(), row)) if row else None


# =============================================================================
# AIS Source Manager (parallel API usage)
# =============================================================================

_ais_manager = None
_ais_manager_lock = threading.Lock()


def get_ais_manager():
    """
    Get or create the AIS source manager instance.

    Uses both APIs in parallel:
    - AISStream for real-time position streaming
    - Marinesia for ports, area queries, vessel images, history
    """
    global _ais_manager

    with _ais_manager_lock:
        if _ais_manager is not None:
            return _ais_manager

        try:
            from ais_sources.manager import create_manager
            import os

            # Load API keys from environment
            aisstream_key = os.environ.get('AISSTREAM_API_KEY')
            marinesia_key = os.environ.get('MARINESIA_API_KEY')
            gfw_key = os.environ.get('GFW_API_KEY')

            # Create manager with available sources
            _ais_manager = create_manager(
                aisstream_key=aisstream_key,
                marinesia_key=marinesia_key,
                gfw_key=gfw_key,
                enable_marinesia=True  # Always enable Marinesia for ports/images
            )

            # Connect sources
            _ais_manager.start()

            print(f"[AIS Manager] Initialized with sources: {list(_ais_manager.sources.keys())}")
            return _ais_manager

        except ImportError as e:
            print(f"[AIS Manager] Module not available: {e}")
            return None
        except Exception as e:
            print(f"[AIS Manager] Failed to initialize: {e}")
            return None


def init_database():
    """Initialize database with schema."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing database: {DB_PATH}")

    conn = get_db()
    with open(SCHEMA_PATH, 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


# =============================================================================
# API Handlers
# =============================================================================

def get_vessels():
    """Get all vessels with their latest position."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT v.*,
               p.latitude as last_lat,
               p.longitude as last_lon,
               p.heading as last_heading,
               p.speed_knots as last_speed,
               p.timestamp as last_position_time,
               p.source as position_source
        FROM vessels v
        LEFT JOIN (
            SELECT vessel_id, latitude, longitude, heading, speed_knots, timestamp, source,
                   ROW_NUMBER() OVER (PARTITION BY vessel_id ORDER BY timestamp DESC) as rn
            FROM positions
        ) p ON v.id = p.vessel_id AND p.rn = 1
        ORDER BY v.threat_level DESC, v.name
    ''')
    vessels = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return vessels


def get_vessel(vessel_id):
    """Get single vessel with full details."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT v.*,
               p.latitude as last_lat,
               p.longitude as last_lon,
               p.heading as last_heading,
               p.speed_knots as last_speed,
               p.timestamp as last_position_time
        FROM vessels v
        LEFT JOIN (
            SELECT vessel_id, latitude, longitude, heading, speed_knots, timestamp,
                   ROW_NUMBER() OVER (PARTITION BY vessel_id ORDER BY timestamp DESC) as rn
            FROM positions
        ) p ON v.id = p.vessel_id AND p.rn = 1
        WHERE v.id = ?
    ''', (vessel_id,))
    vessel = dict_from_row(cursor.fetchone())
    conn.close()
    return vessel


def get_vessel_track(vessel_id, days=90):
    """Get position history for vessel."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT * FROM positions
        WHERE vessel_id = ?
        AND timestamp >= datetime('now', ?)
        ORDER BY timestamp ASC
    ''', (vessel_id, f'-{days} days'))
    positions = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return positions


def get_vessel_events(vessel_id):
    """Get events timeline for vessel."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT * FROM events
        WHERE vessel_id = ?
        ORDER BY event_date DESC
    ''', (vessel_id,))
    events = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return events


def get_shipyards():
    """Get all monitored shipyards."""
    conn = get_db()
    cursor = conn.execute('SELECT * FROM shipyards ORDER BY name')
    shipyards = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return shipyards


def get_events(severity=None, limit=50):
    """Get all events, optionally filtered by severity."""
    conn = get_db()
    if severity:
        cursor = conn.execute('''
            SELECT e.*, v.name as vessel_name
            FROM events e
            JOIN vessels v ON e.vessel_id = v.id
            WHERE e.severity = ?
            ORDER BY e.event_date DESC
            LIMIT ?
        ''', (severity, limit))
    else:
        cursor = conn.execute('''
            SELECT e.*, v.name as vessel_name
            FROM events e
            JOIN vessels v ON e.vessel_id = v.id
            ORDER BY e.event_date DESC
            LIMIT ?
        ''', (limit,))
    events = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return events


def get_alerts(acknowledged=False):
    """Get alerts, by default unacknowledged only."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT a.*, v.name as vessel_name
        FROM alerts a
        LEFT JOIN vessels v ON a.vessel_id = v.id
        WHERE a.acknowledged = ?
        ORDER BY a.created_at DESC
    ''', (1 if acknowledged else 0,))
    alerts = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return alerts


def get_osint_reports(vessel_id=None):
    """Get OSINT reports, optionally filtered by vessel."""
    conn = get_db()
    if vessel_id:
        cursor = conn.execute('''
            SELECT o.*, v.name as vessel_name
            FROM osint_reports o
            LEFT JOIN vessels v ON o.vessel_id = v.id
            WHERE o.vessel_id = ?
            ORDER BY o.publish_date DESC
        ''', (vessel_id,))
    else:
        cursor = conn.execute('''
            SELECT o.*, v.name as vessel_name
            FROM osint_reports o
            LEFT JOIN vessels v ON o.vessel_id = v.id
            ORDER BY o.publish_date DESC
        ''')
    reports = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return reports


def get_watchlist():
    """Get watchlist with vessel details."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT w.*, v.name, v.mmsi, v.classification, v.threat_level,
               p.latitude as last_lat, p.longitude as last_lon, p.timestamp as last_seen
        FROM watchlist w
        JOIN vessels v ON w.vessel_id = v.id
        LEFT JOIN (
            SELECT vessel_id, latitude, longitude, timestamp,
                   ROW_NUMBER() OVER (PARTITION BY vessel_id ORDER BY timestamp DESC) as rn
            FROM positions
        ) p ON v.id = p.vessel_id AND p.rn = 1
        ORDER BY w.priority ASC
    ''')
    watchlist = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return watchlist


def get_stats():
    """Get dashboard statistics."""
    conn = get_db()
    stats = {}

    cursor = conn.execute('SELECT COUNT(*) as count FROM vessels')
    stats['total_vessels'] = cursor.fetchone()['count']

    cursor = conn.execute("SELECT COUNT(*) as count FROM vessels WHERE classification = 'confirmed'")
    stats['confirmed_arsenal'] = cursor.fetchone()['count']

    cursor = conn.execute("SELECT COUNT(*) as count FROM vessels WHERE threat_level = 'critical'")
    stats['critical_threats'] = cursor.fetchone()['count']

    cursor = conn.execute('SELECT COUNT(*) as count FROM alerts WHERE acknowledged = 0')
    stats['active_alerts'] = cursor.fetchone()['count']

    cursor = conn.execute('SELECT COUNT(*) as count FROM watchlist')
    stats['watchlist_count'] = cursor.fetchone()['count']

    cursor = conn.execute('SELECT COUNT(*) as count FROM osint_reports')
    stats['osint_reports'] = cursor.fetchone()['count']

    cursor = conn.execute('SELECT COUNT(*) as count FROM events')
    stats['total_events'] = cursor.fetchone()['count']

    cursor = conn.execute("SELECT COUNT(*) as count FROM events WHERE severity IN ('critical', 'high')")
    stats['high_severity_events'] = cursor.fetchone()['count']

    conn.close()
    return stats


def get_live_vessels():
    """Get live vessels from stream_area.py output file."""
    if not os.path.exists(LIVE_VESSELS_PATH):
        return {'timestamp': None, 'vessel_count': 0, 'vessels': []}

    try:
        with open(LIVE_VESSELS_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[Error] Failed to read live vessels: {e}")
        return {'timestamp': None, 'vessel_count': 0, 'vessels': []}


def add_vessel(data):
    """Add new vessel to tracking."""
    conn = get_db()
    cursor = conn.execute('''
        INSERT INTO vessels (name, mmsi, imo, flag_state, vessel_type, classification, threat_level, intel_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name'),
        data.get('mmsi'),
        data.get('imo'),
        data.get('flag_state'),
        data.get('vessel_type'),
        data.get('classification', 'monitoring'),
        data.get('threat_level', 'unknown'),
        data.get('intel_notes')
    ))
    vessel_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {'id': vessel_id, 'status': 'created'}


def add_position(vessel_id, data):
    """Add position update for vessel."""
    conn = get_db()
    conn.execute('''
        INSERT INTO positions (vessel_id, latitude, longitude, heading, speed_knots, source)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        vessel_id,
        data.get('latitude'),
        data.get('longitude'),
        data.get('heading'),
        data.get('speed_knots'),
        data.get('source', 'manual')
    ))
    conn.execute('UPDATE vessels SET last_updated = CURRENT_TIMESTAMP WHERE id = ?', (vessel_id,))
    conn.commit()
    conn.close()
    return {'status': 'position_logged'}


def add_event(vessel_id, data):
    """Add event for vessel."""
    conn = get_db()
    conn.execute('''
        INSERT INTO events (vessel_id, event_type, severity, title, description, source, source_url, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        vessel_id,
        data.get('event_type'),
        data.get('severity', 'info'),
        data.get('title'),
        data.get('description'),
        data.get('source'),
        data.get('source_url'),
        data.get('latitude'),
        data.get('longitude')
    ))
    conn.commit()
    conn.close()
    return {'status': 'event_logged'}


def add_osint_report(data):
    """Add OSINT report."""
    conn = get_db()
    cursor = conn.execute('''
        INSERT INTO osint_reports (vessel_id, title, source_name, source_url, publish_date, summary, full_content, key_findings, reliability, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('vessel_id'),
        data.get('title'),
        data.get('source_name'),
        data.get('source_url'),
        data.get('publish_date'),
        data.get('summary'),
        data.get('full_content'),
        json.dumps(data.get('key_findings', [])),
        data.get('reliability', 'unconfirmed'),
        data.get('tags')
    ))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {'id': report_id, 'status': 'created'}


def acknowledge_alert(alert_id):
    """Acknowledge an alert."""
    conn = get_db()
    conn.execute('''
        UPDATE alerts SET acknowledged = 1, acknowledged_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (alert_id,))
    conn.commit()
    conn.close()
    return {'status': 'acknowledged'}


def load_poc_scenario(poc_name):
    """Load a POC scenario into the database."""
    if poc_name == 'baltic':
        return _load_baltic_poc()
    elif poc_name == 'venezuela':
        return _load_venezuela_poc()
    elif poc_name == 'china':
        return _load_china_poc()
    else:
        return {'error': f'Unknown POC: {poc_name}', 'available': ['baltic', 'venezuela', 'china']}


def _load_baltic_poc():
    """Load Baltic Cable Incident POC data."""
    conn = get_db()
    results = {'vessels_added': [], 'infrastructure_added': [], 'events_added': []}

    # Vessel data
    vessels = [
        {
            "name": "FITBURG",
            "mmsi": "518100989",
            "imo": "9187629",
            "flag_state": "Cook Islands",
            "vessel_type": "Cargo Ship",
            "classification": "suspected",
            "threat_level": "high",
            "intel_notes": "Baltic Cable Incident - Dec 31, 2025. Seized by Finnish authorities after C-Lion1 cable damage. Anchor dragging detected in cable zone."
        },
        {
            "name": "EAGLE S",
            "mmsi": "255806583",
            "imo": "9037155",
            "flag_state": "Malta",
            "vessel_type": "Oil Tanker",
            "classification": "suspected",
            "threat_level": "high",
            "intel_notes": "Estlink-2 cable incident - Dec 25, 2025. Shadow fleet tanker, anchor dragged damaging Finland-Estonia power cable."
        }
    ]

    for v in vessels:
        cursor = conn.execute("SELECT id FROM vessels WHERE mmsi = ?", (v['mmsi'],))
        existing = cursor.fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO vessels (name, mmsi, imo, flag_state, vessel_type, classification, threat_level, intel_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (v['name'], v['mmsi'], v['imo'], v['flag_state'], v['vessel_type'], v['classification'], v['threat_level'], v['intel_notes']))
            results['vessels_added'].append(v['name'])

    # Infrastructure locations (as shipyards)
    infrastructure = [
        {"name": "C-Lion1 Cable Zone", "latitude": 59.45, "longitude": 24.75, "geofence_radius_km": 10.0,
         "facility_type": "anchorage", "notes": "Finland-Germany telecom cable. Damaged Dec 31, 2025."},
        {"name": "Estlink-2 Cable Zone", "latitude": 59.55, "longitude": 25.00, "geofence_radius_km": 10.0,
         "facility_type": "anchorage", "notes": "650MW HVDC power cable. Damaged Dec 25, 2025."},
        {"name": "Balticconnector Zone", "latitude": 59.60, "longitude": 24.80, "geofence_radius_km": 15.0,
         "facility_type": "anchorage", "notes": "Finland-Estonia gas pipeline. Damaged Oct 2023."},
    ]

    for infra in infrastructure:
        cursor = conn.execute("SELECT id FROM shipyards WHERE name = ?", (infra['name'],))
        existing = cursor.fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO shipyards (name, latitude, longitude, geofence_radius_km, facility_type, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (infra['name'], infra['latitude'], infra['longitude'], infra['geofence_radius_km'], infra['facility_type'], infra['notes']))
            results['infrastructure_added'].append(infra['name'])

    # Get vessel IDs for events
    cursor = conn.execute("SELECT id FROM vessels WHERE name = 'FITBURG'")
    fitburg = cursor.fetchone()
    fitburg_id = fitburg['id'] if fitburg else None

    if fitburg_id:
        events = [
            {"event_type": "anomaly_detected", "severity": "critical", "title": "C-Lion1 cable damage detected",
             "description": "Finnish authorities detect damage to undersea telecom cable.", "latitude": 59.45, "longitude": 24.75},
            {"event_type": "geofence_enter", "severity": "high", "title": "Fitburg enters cable zone",
             "description": "Vessel enters Gulf of Finland cable protection zone.", "latitude": 59.55, "longitude": 25.00},
        ]
        for e in events:
            conn.execute('''
                INSERT INTO events (vessel_id, event_type, severity, title, description, latitude, longitude)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (fitburg_id, e['event_type'], e['severity'], e['title'], e['description'], e['latitude'], e['longitude']))
            results['events_added'].append(e['title'])

    # Update config for Baltic Sea
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)

    config['area_tracking'] = {
        'enabled': True,
        'bounding_box': {
            'lat_min': 53.0, 'lon_min': 9.0, 'lat_max': 66.0, 'lon_max': 30.0,
            'description': 'Baltic Sea - Cable Infrastructure Monitoring Zone'
        }
    }
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

    conn.commit()
    conn.close()

    return {
        'status': 'success',
        'poc': 'baltic',
        'name': 'Baltic Cable Incident',
        'results': results,
        'message': 'POC loaded. Refresh the page to see vessels and infrastructure.'
    }


def _load_venezuela_poc():
    """Load Venezuela Dark Fleet POC data."""
    conn = get_db()
    results = {'vessels_added': [], 'infrastructure_added': [], 'events_added': []}

    # Known dark fleet vessels
    vessels = [
        {
            "name": "SKIPPER",
            "mmsi": "352001234",
            "imo": "9123456",
            "flag_state": "Cameroon",
            "vessel_type": "Oil Tanker",
            "classification": "confirmed",
            "threat_level": "critical",
            "intel_notes": "Seized dark fleet tanker. 80+ days AIS spoofing on Iran-Venezuela-China route. Sanctioned."
        },
        {
            "name": "BELLA 1",
            "mmsi": "667001234",
            "flag_state": "Cameroon",
            "vessel_type": "Oil Tanker",
            "classification": "suspected",
            "threat_level": "high",
            "intel_notes": "Currently tracked by U.S. Navy. Suspected sanctions evasion, Venezuela oil trade."
        },
        {
            "name": "CENTURIES",
            "mmsi": "538001234",
            "flag_state": "Palau",
            "vessel_type": "Oil Tanker",
            "classification": "confirmed",
            "threat_level": "critical",
            "intel_notes": "Seized December 2025. Venezuela dark fleet operator."
        }
    ]

    for v in vessels:
        cursor = conn.execute("SELECT id FROM vessels WHERE name = ?", (v['name'],))
        existing = cursor.fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO vessels (name, mmsi, imo, flag_state, vessel_type, classification, threat_level, intel_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (v['name'], v.get('mmsi'), v.get('imo'), v['flag_state'], v['vessel_type'], v['classification'], v['threat_level'], v['intel_notes']))
            results['vessels_added'].append(v['name'])

    # Venezuela monitoring zones
    infrastructure = [
        {"name": "Jose Terminal", "latitude": 10.15, "longitude": -64.68, "geofence_radius_km": 15.0,
         "facility_type": "port", "threat_association": "Critical", "notes": "Main Venezuela oil export terminal."},
        {"name": "La Borracha STS Zone", "latitude": 10.08, "longitude": -64.89, "geofence_radius_km": 20.0,
         "facility_type": "anchorage", "threat_association": "Critical", "notes": "Ship-to-ship transfer zone for dark fleet."},
        {"name": "Amuay Refinery", "latitude": 11.74, "longitude": -70.21, "geofence_radius_km": 10.0,
         "facility_type": "port", "threat_association": "High", "notes": "Major Venezuela refinery complex."},
    ]

    for infra in infrastructure:
        cursor = conn.execute("SELECT id FROM shipyards WHERE name = ?", (infra['name'],))
        existing = cursor.fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO shipyards (name, latitude, longitude, geofence_radius_km, facility_type, threat_association, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (infra['name'], infra['latitude'], infra['longitude'], infra['geofence_radius_km'],
                  infra['facility_type'], infra.get('threat_association'), infra['notes']))
            results['infrastructure_added'].append(infra['name'])

    # Update config for Caribbean/Venezuela
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)

    config['area_tracking'] = {
        'enabled': True,
        'bounding_box': {
            'lat_min': 8.0, 'lon_min': -75.0, 'lat_max': 15.0, 'lon_max': -60.0,
            'description': 'Venezuela - Dark Fleet Monitoring Zone'
        }
    }
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

    conn.commit()
    conn.close()

    return {
        'status': 'success',
        'poc': 'venezuela',
        'name': 'Venezuela Dark Fleet',
        'results': results,
        'message': 'POC loaded. Map centered on Venezuela/Caribbean.'
    }


def _load_china_poc():
    """Load China Arsenal Ship POC data."""
    conn = get_db()
    results = {'vessels_added': [], 'infrastructure_added': [], 'events_added': []}

    # Arsenal ships and related vessels
    vessels = [
        {
            "name": "ZHONG DA 79",
            "mmsi": "413456789",
            "imo": "9876543",
            "flag_state": "China",
            "vessel_type": "Container Feeder",
            "classification": "confirmed",
            "threat_level": "critical",
            "intel_notes": """Arsenal Ship - Confirmed containerized weapons platform.

WEAPONS CONFIG:
- 60+ containerized cruise/ballistic missiles
- CIWS close-in weapon systems
- Radar arrays disguised as shipping containers
- Retains civilian AIS classification

OPERATIONAL PATTERN:
- Operates in East/South China Sea
- Frequent port calls: Shanghai, Ningbo, Xiamen
- Exercises with PLAN vessels observed"""
        },
        {
            "name": "YUAN WANG 5",
            "mmsi": "413123456",
            "flag_state": "China",
            "vessel_type": "Research Vessel",
            "classification": "confirmed",
            "threat_level": "high",
            "intel_notes": "Space/missile tracking ship. Dual-use military research vessel. Monitored by regional navies."
        },
        {
            "name": "HAI YANG 26",
            "mmsi": "413789012",
            "flag_state": "China",
            "vessel_type": "Research Vessel",
            "classification": "suspected",
            "threat_level": "medium",
            "intel_notes": "Survey vessel. Possible subsea cable mapping operations. Frequent South China Sea presence."
        }
    ]

    for v in vessels:
        cursor = conn.execute("SELECT id FROM vessels WHERE name = ?", (v['name'],))
        existing = cursor.fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO vessels (name, mmsi, imo, flag_state, vessel_type, classification, threat_level, intel_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (v['name'], v.get('mmsi'), v.get('imo'), v['flag_state'], v['vessel_type'], v['classification'], v['threat_level'], v['intel_notes']))
            results['vessels_added'].append(v['name'])

    # China/Taiwan Strait facilities
    infrastructure = [
        {"name": "Shanghai Jiangnan Shipyard", "latitude": 31.35, "longitude": 121.50, "geofence_radius_km": 5.0,
         "facility_type": "shipyard", "threat_association": "Military", "notes": "Major PLAN shipbuilding. Aircraft carriers, destroyers."},
        {"name": "Ningbo-Zhoushan Port", "latitude": 29.87, "longitude": 122.10, "geofence_radius_km": 10.0,
         "facility_type": "port", "threat_association": "Dual-use", "notes": "World's largest port. Military logistics hub."},
        {"name": "Taiwan Strait Zone", "latitude": 24.50, "longitude": 119.50, "geofence_radius_km": 100.0,
         "facility_type": "anchorage", "threat_association": "Critical", "notes": "Strategic chokepoint. High military activity."},
        {"name": "Xiamen Naval Base", "latitude": 24.45, "longitude": 118.08, "geofence_radius_km": 8.0,
         "facility_type": "military", "threat_association": "Military", "notes": "PLAN Eastern Theater base. Amphibious forces."},
    ]

    for infra in infrastructure:
        cursor = conn.execute("SELECT id FROM shipyards WHERE name = ?", (infra['name'],))
        existing = cursor.fetchone()
        if not existing:
            conn.execute('''
                INSERT INTO shipyards (name, latitude, longitude, geofence_radius_km, facility_type, threat_association, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (infra['name'], infra['latitude'], infra['longitude'], infra['geofence_radius_km'],
                  infra['facility_type'], infra.get('threat_association'), infra['notes']))
            results['infrastructure_added'].append(infra['name'])

    # Update config for East China Sea / Taiwan Strait
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)

    config['area_tracking'] = {
        'enabled': True,
        'bounding_box': {
            'lat_min': 20.0, 'lon_min': 115.0, 'lat_max': 35.0, 'lon_max': 130.0,
            'description': 'East China Sea - Arsenal Ship Monitoring Zone'
        }
    }
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

    conn.commit()
    conn.close()

    return {
        'status': 'success',
        'poc': 'china',
        'name': 'China Arsenal Ships',
        'results': results,
        'message': 'POC loaded. Map centered on East China Sea.'
    }


def search_news(query, max_results=10):
    """Search Google News for vessel information."""
    try:
        from gnews import GNews
        gn = GNews(language='en', country='US', max_results=max_results)
        results = gn.get_news(query)

        articles = []
        for item in results:
            articles.append({
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'source': item.get('publisher', {}).get('title', 'Unknown'),
                'published': item.get('published date', ''),
                'description': item.get('description', '')
            })

        return {'query': query, 'count': len(articles), 'articles': articles}

    except ImportError:
        return {'error': 'gnews not installed. Run: pip install gnews', 'articles': []}
    except Exception as e:
        print(f"[Error] News search failed: {e}")
        return {'error': str(e), 'articles': []}


def track_live_vessel(data):
    """Add a live vessel to tracking with its current position."""
    conn = get_db()

    # Check if vessel already exists by MMSI
    mmsi = data.get('mmsi')
    if mmsi:
        cursor = conn.execute('SELECT id FROM vessels WHERE mmsi = ?', (str(mmsi),))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return {'error': 'Vessel with this MMSI already tracked', 'vessel_id': existing['id']}

    # Process weapons config
    weapons_config = data.get('weapons_config')
    if weapons_config and isinstance(weapons_config, dict):
        weapons_config = json.dumps(weapons_config)
    elif weapons_config:
        weapons_config = str(weapons_config)
    else:
        weapons_config = None

    # Insert new vessel with all fields
    cursor = conn.execute('''
        INSERT INTO vessels (name, mmsi, imo, flag_state, vessel_type, length_m,
                            classification, threat_level, intel_notes, weapons_config)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name', f"MMSI {mmsi}"),
        str(mmsi) if mmsi else None,
        data.get('imo'),
        data.get('flag'),
        data.get('ship_type', data.get('vessel_type')),
        data.get('length_m'),
        data.get('classification', 'monitoring'),
        data.get('threat_level', 'unknown'),
        data.get('intel_notes', 'Added from live AIS stream'),
        weapons_config
    ))
    vessel_id = cursor.lastrowid

    # Add initial position if available
    lat = data.get('lat')
    lon = data.get('lon')
    if lat and lon:
        conn.execute('''
            INSERT INTO positions (vessel_id, latitude, longitude, heading, speed_knots, source)
            VALUES (?, ?, ?, ?, ?, 'ais')
        ''', (vessel_id, lat, lon, data.get('heading'), data.get('speed')))

    conn.commit()
    conn.close()
    return {'id': vessel_id, 'status': 'created', 'name': data.get('name', f"MMSI {mmsi}")}


def update_vessel(vessel_id, data):
    """Update vessel details."""
    conn = get_db()

    # Build update query dynamically based on provided fields
    updates = []
    values = []

    # Map of allowed fields to column names
    field_map = {
        'name': 'name',
        'vessel_type': 'vessel_type',
        'flag_state': 'flag_state',
        'classification': 'classification',
        'threat_level': 'threat_level',
        'intel_notes': 'intel_notes',
        'imo': 'imo',
        'callsign': 'call_sign',
        'call_sign': 'call_sign',
        'owner': 'owner',
        'length_m': 'length_m',
        'beam_m': 'beam_m',
        'gross_tonnage': 'gross_tonnage',
    }

    for field, column in field_map.items():
        if field in data and data[field] is not None:
            updates.append(f'{column} = ?')
            values.append(data[field])

    if not updates:
        conn.close()
        return {'error': 'No fields to update'}

    updates.append('last_updated = CURRENT_TIMESTAMP')
    values.append(vessel_id)

    conn.execute(f'''
        UPDATE vessels SET {', '.join(updates)} WHERE id = ?
    ''', values)
    conn.commit()
    conn.close()
    return {'status': 'updated', 'vessel_id': vessel_id}


def delete_vessel(vessel_id):
    """Delete a vessel and all related data."""
    conn = get_db()

    # Delete related data first
    conn.execute('DELETE FROM positions WHERE vessel_id = ?', (vessel_id,))
    conn.execute('DELETE FROM events WHERE vessel_id = ?', (vessel_id,))
    conn.execute('DELETE FROM alerts WHERE vessel_id = ?', (vessel_id,))
    conn.execute('DELETE FROM watchlist WHERE vessel_id = ?', (vessel_id,))
    conn.execute('DELETE FROM osint_reports WHERE vessel_id = ?', (vessel_id,))

    # Delete the vessel
    conn.execute('DELETE FROM vessels WHERE id = ?', (vessel_id,))
    conn.commit()
    conn.close()
    return {'status': 'deleted', 'vessel_id': vessel_id}


def update_bounding_box(data):
    """Update the bounding box in ais_config.json."""
    try:
        # Load existing config
        config = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)

        # Update bounding box
        if 'area_tracking' not in config:
            config['area_tracking'] = {'enabled': True, 'bounding_box': {}}

        config['area_tracking']['bounding_box'] = {
            'lat_min': data.get('lat_min'),
            'lon_min': data.get('lon_min'),
            'lat_max': data.get('lat_max'),
            'lon_max': data.get('lon_max'),
            'description': data.get('description', 'Custom area')
        }

        # Save config
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)

        return {
            'status': 'updated',
            'message': 'Bounding box saved. Restart stream_area.py to apply.',
            'bounding_box': config['area_tracking']['bounding_box']
        }

    except Exception as e:
        return {'error': str(e)}


def save_vessel_photo(vessel_id, photo_data, filename):
    """Save a vessel photo and update database."""
    import base64

    # Ensure photos directory exists
    os.makedirs(PHOTOS_DIR, exist_ok=True)

    # Decode base64 image data
    try:
        # Remove data URL prefix if present
        if ',' in photo_data:
            photo_data = photo_data.split(',')[1]

        image_bytes = base64.b64decode(photo_data)

        # Generate filename
        ext = os.path.splitext(filename)[1] or '.jpg'
        photo_filename = f"vessel_{vessel_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        photo_path = os.path.join(PHOTOS_DIR, photo_filename)

        # Save file
        with open(photo_path, 'wb') as f:
            f.write(image_bytes)

        # Update database with photo path
        conn = get_db()
        conn.execute('''
            UPDATE vessels SET photo_url = ?, last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (f'/photos/{photo_filename}', vessel_id))
        conn.commit()
        conn.close()

        return {
            'status': 'uploaded',
            'photo_url': f'/photos/{photo_filename}',
            'vessel_id': vessel_id
        }

    except Exception as e:
        return {'error': str(e)}


def save_vessel_analysis(vessel_id, analysis_result):
    """Save AI analysis results to the vessel record."""
    conn = get_db()
    try:
        # Extract and store the full analysis and BLUF separately
        ai_analysis = json.dumps(analysis_result) if analysis_result else None
        ai_bluf = None

        if analysis_result and 'analysis' in analysis_result:
            bluf_data = analysis_result['analysis'].get('bluf')
            if bluf_data:
                ai_bluf = json.dumps(bluf_data)

        conn.execute('''
            UPDATE vessels
            SET ai_analysis = ?, ai_bluf = ?, ai_analyzed_at = CURRENT_TIMESTAMP, last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (ai_analysis, ai_bluf, vessel_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[Error] Failed to save analysis: {e}")
        return False
    finally:
        conn.close()


def get_vessel_analysis(vessel_id):
    """Get saved AI analysis for a vessel."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT ai_analysis, ai_bluf, ai_analyzed_at FROM vessels WHERE id = ?
    ''', (vessel_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row['ai_analysis']:
        return {
            'analysis': json.loads(row['ai_analysis']) if row['ai_analysis'] else None,
            'bluf': json.loads(row['ai_bluf']) if row['ai_bluf'] else None,
            'analyzed_at': row['ai_analyzed_at']
        }
    return None


# =============================================================================
# HTTP Handler
# =============================================================================

class TrackerHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for the tracker API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def send_json(self, data, status=200, cache_seconds=0):
        """Send JSON response with optional gzip compression and caching."""
        json_data = json.dumps(data, default=str).encode()

        # Check if client accepts gzip
        accept_encoding = self.headers.get('Accept-Encoding', '')
        use_gzip = 'gzip' in accept_encoding and len(json_data) > 1000

        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')

        # Cache control headers
        if cache_seconds > 0:
            self.send_header('Cache-Control', f'public, max-age={cache_seconds}')
        else:
            self.send_header('Cache-Control', 'no-cache')

        # Gzip compression for large responses
        if use_gzip:
            json_data = gzip.compress(json_data)
            self.send_header('Content-Encoding', 'gzip')

        self.send_header('Content-Length', len(json_data))
        self.end_headers()
        self.wfile.write(json_data)

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path == '/api/vessels':
            return self.send_json(get_vessels())

        elif path == '/api/live-vessels':
            return self.send_json(get_live_vessels())

        elif path.startswith('/api/vessels/') and path.endswith('/track'):
            vessel_id = int(path.split('/')[3])
            days = int(params.get('days', [90])[0])
            return self.send_json(get_vessel_track(vessel_id, days))

        elif path.startswith('/api/vessels/') and path.endswith('/events'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(get_vessel_events(vessel_id))

        elif path.startswith('/api/vessels/') and path.endswith('/analysis'):
            vessel_id = int(path.split('/')[3])
            saved = get_vessel_analysis(vessel_id)
            if saved:
                return self.send_json(saved)
            return self.send_json({'error': 'No saved analysis', 'vessel_id': vessel_id}, 404)

        elif path.startswith('/api/vessels/') and path.endswith('/confidence'):
            if not CONFIDENCE_AVAILABLE:
                return self.send_json({'error': 'Confidence module not available'}, 500)
            vessel_id = int(path.split('/')[3])
            recalculate = params.get('recalculate', ['false'])[0].lower() == 'true'
            days = int(params.get('days', [30])[0])

            if recalculate:
                score = calculate_vessel_confidence(vessel_id, days)
                save_confidence_to_db(score)
                return self.send_json(score.to_dict())
            else:
                cached = get_vessel_confidence(vessel_id)
                if cached:
                    return self.send_json(cached)
                else:
                    score = calculate_vessel_confidence(vessel_id, days)
                    save_confidence_to_db(score)
                    return self.send_json(score.to_dict())

        elif path.startswith('/api/vessels/') and path.endswith('/intel'):
            # Formal intelligence assessment
            if not INTELLIGENCE_AVAILABLE:
                return self.send_json({'error': 'Intelligence module not available'}, 500)
            vessel_id = int(path.split('/')[3])
            days = int(params.get('days', [30])[0])
            summary_only = params.get('summary', ['false'])[0].lower() == 'true'

            if summary_only:
                return self.send_json(get_intel_summary(vessel_id))
            else:
                intel = produce_vessel_intelligence(vessel_id, days)
                return self.send_json(intel.to_dict())

        elif path.startswith('/api/vessels/') and len(path.split('/')) == 4:
            # Only match /api/vessels/{id}, not /api/vessels/{id}/something
            vessel_id = int(path.split('/')[3])
            return self.send_json(get_vessel(vessel_id))

        elif path == '/api/shipyards':
            return self.send_json(get_shipyards(), cache_seconds=300)  # 5 min cache

        elif path == '/api/events':
            severity = params.get('severity', [None])[0]
            limit = int(params.get('limit', [50])[0])
            return self.send_json(get_events(severity, limit))

        elif path == '/api/alerts':
            acknowledged = params.get('acknowledged', ['false'])[0].lower() == 'true'
            return self.send_json(get_alerts(acknowledged))

        elif path == '/api/osint':
            vessel_id = params.get('vessel_id', [None])[0]
            if vessel_id:
                vessel_id = int(vessel_id)
            return self.send_json(get_osint_reports(vessel_id))

        elif path == '/api/watchlist':
            return self.send_json(get_watchlist())

        elif path == '/api/stats':
            return self.send_json(get_stats(), cache_seconds=10)  # 10 sec cache

        elif path == '/api/weather':
            # Get weather for a location
            if not WEATHER_AVAILABLE:
                return self.send_json({'error': 'Weather module not available'}, 500)
            lat = params.get('lat', [None])[0]
            lon = params.get('lon', [None])[0]
            if not lat or not lon:
                return self.send_json({'error': 'lat and lon required'}, 400)
            try:
                service = get_weather_service()
                weather = service.get_full_conditions(float(lat), float(lon))
                if weather:
                    return self.send_json(weather, cache_seconds=300)  # 5 min cache
                return self.send_json({'error': 'Could not fetch weather'}, 500)
            except Exception as e:
                return self.send_json({'error': str(e)}, 500)

        elif path.startswith('/api/vessels/') and path.endswith('/weather'):
            # Get weather at vessel's current position
            if not WEATHER_AVAILABLE:
                return self.send_json({'error': 'Weather module not available'}, 500)
            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel or not vessel.get('last_lat') or not vessel.get('last_lon'):
                return self.send_json({'error': 'Vessel position not available'}, 404)
            service = get_weather_service()
            weather = service.get_full_conditions(vessel['last_lat'], vessel['last_lon'])
            if weather:
                weather['vessel_id'] = vessel_id
                weather['vessel_name'] = vessel.get('name')
                return self.send_json(weather)
            return self.send_json({'error': 'Could not fetch weather'}, 500)

        # SAR detection endpoints
        elif path == '/api/sar-detections':
            if not SAR_AVAILABLE:
                return self.send_json({'error': 'SAR module not available'}, 500)
            since = params.get('since', [None])[0]
            include_matched = params.get('include_matched', ['true'])[0].lower() == 'true'
            detections = get_sar_detections(since=since, include_matched=include_matched)
            return self.send_json(detections)

        elif path == '/api/dark-vessels':
            if not SAR_AVAILABLE:
                return self.send_json({'error': 'SAR module not available'}, 500)
            since = params.get('since', [None])[0]
            dark_vessels = get_dark_vessels(since=since)
            return self.send_json(dark_vessels)

        # Behavior analysis endpoints
        elif path.startswith('/api/vessels/') and path.endswith('/behavior'):
            if not BEHAVIOR_AVAILABLE:
                return self.send_json({'error': 'Behavior module not available'}, 500)
            vessel_id = int(path.split('/')[3])
            days = int(params.get('days', [30])[0])

            # Get vessel track
            track = get_vessel_track(vessel_id, days)
            if not track:
                return self.send_json({'error': 'No track data available'}, 404)

            # Get vessel MMSI
            vessel = get_vessel(vessel_id)
            mmsi = vessel.get('mmsi', '') if vessel else ''

            # Run behavior analysis
            analysis = analyze_vessel_behavior(track, mmsi)
            analysis['vessel_id'] = vessel_id
            analysis['vessel_name'] = vessel.get('name') if vessel else None
            return self.send_json(analysis)

        elif path == '/api/mmsi/validate':
            mmsi = params.get('mmsi', [None])[0]
            if not mmsi:
                return self.send_json({'error': 'MMSI parameter required'}, 400)
            if not BEHAVIOR_AVAILABLE:
                return self.send_json({'error': 'Behavior module not available'}, 500)
            return self.send_json(validate_mmsi(mmsi))

        elif path == '/api/mmsi/country':
            mmsi = params.get('mmsi', [None])[0]
            if not mmsi:
                return self.send_json({'error': 'MMSI parameter required'}, 400)
            if not BEHAVIOR_AVAILABLE:
                return self.send_json({'error': 'Behavior module not available'}, 500)
            country = get_flag_country(mmsi)
            return self.send_json({'mmsi': mmsi, 'country': country})

        # Venezuela dark fleet detection endpoints
        elif path == '/api/venezuela/config':
            if not VENEZUELA_AVAILABLE:
                return self.send_json({'error': 'Venezuela module not available'}, 500)
            return self.send_json(get_venezuela_monitoring_config())

        elif path == '/api/venezuela/known-vessels':
            if not VENEZUELA_AVAILABLE:
                return self.send_json({'error': 'Venezuela module not available'}, 500)
            vessels = [v.to_dict() for v in KNOWN_DARK_FLEET_VESSELS]
            return self.send_json({'vessels': vessels, 'count': len(vessels)})

        elif path.startswith('/api/vessels/') and path.endswith('/venezuela'):
            if not VENEZUELA_AVAILABLE:
                return self.send_json({'error': 'Venezuela module not available'}, 500)
            vessel_id = int(path.split('/')[3])
            days = int(params.get('days', [30])[0])

            # Get vessel info and track
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            track = get_vessel_track(vessel_id, days)

            # Check if in Venezuela zone
            in_zone = False
            if track:
                latest = track[-1]
                in_zone = is_in_venezuela_zone(latest.get('lat', 0), latest.get('lon', 0))

            # Calculate risk score
            risk = calculate_venezuela_risk_score(
                mmsi=vessel.get('mmsi', ''),
                vessel_info={
                    'name': vessel.get('name', ''),
                    'flag_state': vessel.get('flag_state', ''),
                    'imo': vessel.get('imo', '')
                },
                track_history=track or []
            )

            # Check alerts
            alerts = []
            if track:
                latest_position = track[-1]
                alerts = check_venezuela_alerts(
                    mmsi=vessel.get('mmsi', ''),
                    vessel_name=vessel.get('name', ''),
                    current_position={
                        'lat': latest_position.get('latitude', latest_position.get('lat', 0)),
                        'lon': latest_position.get('longitude', latest_position.get('lon', 0)),
                        'timestamp': latest_position.get('timestamp')
                    },
                    track_history=track,
                    vessel_info={
                        'flag_state': vessel.get('flag_state', ''),
                        'imo': vessel.get('imo', '')
                    }
                )

            return self.send_json({
                'vessel_id': vessel_id,
                'vessel_name': vessel.get('name'),
                'in_venezuela_zone': in_zone,
                'risk_score': risk.get('score', 0),
                'risk_level': risk.get('risk_level', 'unknown'),
                'risk_factors': risk.get('factors', []),
                'alerts': [alert.to_dict() if hasattr(alert, 'to_dict') else alert for alert in alerts]
            })

        # Multi-region dark fleet detection endpoints
        elif path == '/api/dark-fleet/config':
            if not DARK_FLEET_AVAILABLE:
                return self.send_json({'error': 'Dark fleet module not available'}, 500)
            region_param = params.get('region', [None])[0]
            region = Region(region_param) if region_param else None
            return self.send_json(get_dark_fleet_config(region))

        elif path == '/api/dark-fleet/statistics':
            if not DARK_FLEET_AVAILABLE:
                return self.send_json({'error': 'Dark fleet module not available'}, 500)
            return self.send_json(get_dark_fleet_statistics())

        elif path == '/api/dark-fleet/known-vessels':
            if not DARK_FLEET_AVAILABLE:
                return self.send_json({'error': 'Dark fleet module not available'}, 500)
            region_param = params.get('region', [None])[0]
            region = Region(region_param) if region_param else None
            vessels = get_known_vessels_by_region(region)
            return self.send_json({'vessels': vessels, 'count': len(vessels)})

        elif path == '/api/dark-fleet/regions':
            if not DARK_FLEET_AVAILABLE:
                return self.send_json({'error': 'Dark fleet module not available'}, 500)
            return self.send_json({
                'regions': [r.value for r in Region],
                'descriptions': {
                    'russia': 'Shadow fleet evading oil price cap (3,300+ vessels)',
                    'iran': 'Sanctions evasion via Malaysia STS hub (1.6M bpd)',
                    'venezuela': 'Caribbean dark fleet operations',
                    'china': 'Destination ports receiving sanctioned oil'
                }
            })

        elif path.startswith('/api/vessels/') and path.endswith('/dark-fleet'):
            if not DARK_FLEET_AVAILABLE:
                return self.send_json({'error': 'Dark fleet module not available'}, 500)
            vessel_id = int(path.split('/')[3])
            days = int(params.get('days', [30])[0])
            region_param = params.get('region', [None])[0]
            target_region = Region(region_param) if region_param else None

            # Get vessel info and track
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            track = get_vessel_track(vessel_id, days)

            # Check which regions the vessel is in
            active_regions = []
            if track:
                latest = track[-1]
                lat = latest.get('latitude', latest.get('lat', 0))
                lon = latest.get('longitude', latest.get('lon', 0))
                active_regions = [r.value for r in is_in_any_monitored_zone(lat, lon)]

            # Calculate risk score
            risk = calculate_dark_fleet_risk_score(
                mmsi=vessel.get('mmsi', ''),
                vessel_info={
                    'name': vessel.get('name', ''),
                    'flag_state': vessel.get('flag_state', ''),
                    'imo': vessel.get('imo', ''),
                    'year_built': vessel.get('year_built')
                },
                track_history=track or [],
                target_region=target_region
            )

            # Check alerts
            alerts = []
            if track:
                latest_position = track[-1]
                alerts = check_dark_fleet_alerts(
                    mmsi=vessel.get('mmsi', ''),
                    vessel_name=vessel.get('name', ''),
                    current_position={
                        'lat': latest_position.get('latitude', latest_position.get('lat', 0)),
                        'lon': latest_position.get('longitude', latest_position.get('lon', 0)),
                        'timestamp': latest_position.get('timestamp')
                    },
                    track_history=track,
                    vessel_info={
                        'flag_state': vessel.get('flag_state', ''),
                        'imo': vessel.get('imo', '')
                    }
                )

            return self.send_json({
                'vessel_id': vessel_id,
                'vessel_name': vessel.get('name'),
                'active_regions': active_regions,
                'target_region': target_region.value if target_region else None,
                'risk_score': risk.get('score', 0),
                'risk_level': risk.get('risk_level', 'unknown'),
                'risk_factors': risk.get('factors', []),
                'region_scores': risk.get('region_scores', {}),
                'alerts': [alert.to_dict() if hasattr(alert, 'to_dict') else alert for alert in alerts]
            })

        # Sanctions database endpoints
        elif path == '/api/sanctions/check':
            if not SANCTIONS_AVAILABLE:
                return self.send_json({'error': 'Sanctions module not available'}, 500)
            imo = params.get('imo', [None])[0]
            mmsi = params.get('mmsi', [None])[0]
            name = params.get('name', [None])[0]
            if not any([imo, mmsi, name]):
                return self.send_json({'error': 'IMO, MMSI, or name parameter required'}, 400)
            result = check_venezuela_sanctions(mmsi=mmsi, imo=imo, name=name)
            return self.send_json(result)

        elif path == '/api/sanctions/stats':
            if not SANCTIONS_AVAILABLE:
                return self.send_json({'error': 'Sanctions module not available'}, 500)
            db = SanctionsDatabase()
            return self.send_json(db.get_statistics())

        elif path.startswith('/api/vessels/') and path.endswith('/sanctions'):
            if not SANCTIONS_AVAILABLE:
                return self.send_json({'error': 'Sanctions module not available'}, 500)
            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            db = SanctionsDatabase()
            enriched = enrich_vessel_with_sanctions(vessel, db)
            return self.send_json(enriched.get('sanctions', {'listed': False}))

        # ========== Marinesia-Enhanced Endpoints ==========
        # These endpoints leverage Marinesia's unique features (ports, area queries, images)

        elif path == '/api/area/vessels':
            # Get all vessels in a bounding box area
            try:
                min_lat = float(params.get('min_lat', [0])[0])
                min_lon = float(params.get('min_lon', [0])[0])
                max_lat = float(params.get('max_lat', [0])[0])
                max_lon = float(params.get('max_lon', [0])[0])
            except (ValueError, TypeError):
                return self.send_json({'error': 'Invalid coordinates'}, 400)

            if not all([min_lat, min_lon, max_lat, max_lon]):
                return self.send_json({'error': 'min_lat, min_lon, max_lat, max_lon required'}, 400)

            try:
                from ais_sources.manager import AISSourceManager
                manager = get_ais_manager()
                if manager:
                    positions = manager.get_vessels_in_area(min_lat, min_lon, max_lat, max_lon)
                    return self.send_json({
                        'vessels': [
                            {
                                'mmsi': p.mmsi,
                                'lat': p.latitude,
                                'lon': p.longitude,
                                'speed': p.speed,
                                'course': p.course,
                                'timestamp': p.timestamp.isoformat() if p.timestamp else None
                            }
                            for p in positions
                        ],
                        'count': len(positions),
                        'bounds': {'min_lat': min_lat, 'min_lon': min_lon, 'max_lat': max_lat, 'max_lon': max_lon}
                    })
                return self.send_json({'error': 'AIS manager not available'}, 500)
            except Exception as e:
                return self.send_json({'error': str(e)}, 500)

        elif path == '/api/ports/nearby':
            # Get ports near a location
            try:
                lat_param = params.get('lat', [None])[0]
                lon_param = params.get('lon', [None])[0]
                lat = float(lat_param) if lat_param else None
                lon = float(lon_param) if lon_param else None
                radius = float(params.get('radius', [50])[0])  # nautical miles
            except (ValueError, TypeError):
                return self.send_json({'error': 'Invalid coordinates'}, 400)

            if lat is None or lon is None:
                return self.send_json({'error': 'lat and lon required'}, 400)

            try:
                manager = get_ais_manager()
                if manager:
                    ports = manager.get_ports_nearby(lat, lon, radius)

                    # Calculate distance from search center to each port
                    enriched_ports = []
                    for port in ports:
                        # Handle various port data formats
                        port_lat = port.get('lat') or port.get('latitude') or port.get('location', {}).get('lat')
                        port_lon = port.get('lon') or port.get('longitude') or port.get('location', {}).get('lon')

                        if port_lat is not None and port_lon is not None:
                            # Calculate distance in nautical miles (haversine returns km)
                            distance_km = haversine(lat, lon, float(port_lat), float(port_lon))
                            port['distance_nm'] = round(distance_km / 1.852, 1)
                        else:
                            port['distance_nm'] = None

                        enriched_ports.append(port)

                    # Sort by distance (closest first)
                    enriched_ports.sort(key=lambda p: p.get('distance_nm') if p.get('distance_nm') is not None else 9999)

                    return self.send_json({
                        'ports': enriched_ports,
                        'count': len(enriched_ports),
                        'search_center': {'lat': lat, 'lon': lon},
                        'radius_nm': radius
                    })
                return self.send_json({'error': 'AIS manager not available'}, 500)
            except Exception as e:
                return self.send_json({'error': str(e)}, 500)

        elif path.startswith('/api/vessels/') and path.endswith('/image'):
            # Get vessel image URL from Marinesia
            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            mmsi = vessel.get('mmsi', '')
            if not mmsi:
                return self.send_json({'error': 'Vessel has no MMSI'}, 400)

            try:
                manager = get_ais_manager()
                if manager:
                    image_url = manager.get_vessel_image(mmsi)
                    return self.send_json({
                        'vessel_id': vessel_id,
                        'mmsi': mmsi,
                        'image_url': image_url
                    })
                return self.send_json({'error': 'AIS manager not available'}, 500)
            except Exception as e:
                return self.send_json({'error': str(e)}, 500)

        elif path.startswith('/api/vessels/') and path.endswith('/history'):
            # Get historical track from Marinesia
            vessel_id = int(path.split('/')[3])
            hours = int(params.get('hours', [24])[0])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            mmsi = vessel.get('mmsi', '')
            if not mmsi:
                return self.send_json({'error': 'Vessel has no MMSI'}, 400)

            try:
                manager = get_ais_manager()
                if manager:
                    positions = manager.get_vessel_history(mmsi, hours=hours)
                    return self.send_json({
                        'vessel_id': vessel_id,
                        'mmsi': mmsi,
                        'hours': hours,
                        'positions': [
                            {
                                'lat': p.latitude,
                                'lon': p.longitude,
                                'speed': p.speed,
                                'course': p.course,
                                'timestamp': p.timestamp.isoformat() if p.timestamp else None
                            }
                            for p in positions
                        ],
                        'count': len(positions)
                    })
                return self.send_json({'error': 'AIS manager not available'}, 500)
            except Exception as e:
                return self.send_json({'error': str(e)}, 500)

        elif path.startswith('/api/vessels/') and path.endswith('/combined'):
            # Get comprehensive vessel info from all sources
            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            mmsi = vessel.get('mmsi', '')
            if not mmsi:
                return self.send_json({'error': 'Vessel has no MMSI'}, 400)

            try:
                manager = get_ais_manager()
                if manager:
                    combined = manager.get_combined_vessel_info(mmsi)
                    combined['vessel_id'] = vessel_id
                    combined['db_info'] = {
                        'name': vessel.get('name'),
                        'imo': vessel.get('imo'),
                        'flag_state': vessel.get('flag_state'),
                        'ship_type': vessel.get('ship_type')
                    }
                    return self.send_json(combined)
                return self.send_json({'error': 'AIS manager not available'}, 500)
            except Exception as e:
                return self.send_json({'error': str(e)}, 500)

        elif path == '/api/sources/status':
            # Get status of all AIS data sources
            try:
                manager = get_ais_manager()
                if manager:
                    return self.send_json(manager.get_status())
                return self.send_json({'error': 'AIS manager not available'}, 500)
            except Exception as e:
                return self.send_json({'error': str(e)}, 500)

        # ========== Infrastructure Analysis Endpoints ==========

        elif path == '/api/infrastructure/baltic':
            # Get Baltic Sea undersea infrastructure for map overlay
            if not INFRA_ANALYSIS_AVAILABLE:
                return self.send_json({'error': 'Infrastructure analysis module not available'}, 500)
            infra = get_baltic_infrastructure()
            return self.send_json({
                'infrastructure': infra,
                'count': len(infra),
                'region': 'Baltic Sea'
            }, cache_seconds=3600)  # Cache for 1 hour

        elif path.startswith('/api/vessels/') and path.endswith('/infra-analysis'):
            # Analyze vessel behavior relative to infrastructure
            if not INFRA_ANALYSIS_AVAILABLE:
                return self.send_json({'error': 'Infrastructure analysis module not available'}, 500)

            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            days = int(params.get('days', [7])[0])
            incident_time = params.get('incident_time', [None])[0]

            # Get vessel track
            track = get_vessel_track(vessel_id, days)
            if not track:
                return self.send_json({'error': 'No track data available for analysis'}, 404)

            # Run infrastructure analysis
            result = analyze_vessel_for_incident(
                vessel_id=vessel_id,
                track_history=track,
                mmsi=vessel.get('mmsi', ''),
                vessel_name=vessel.get('name'),
                vessel_flag=vessel.get('flag_state'),
                incident_time=incident_time
            )

            return self.send_json(result)

        # ========== Laden Status Detection Endpoints ==========

        elif path.startswith('/api/vessels/') and path.endswith('/laden-status'):
            # Analyze vessel laden status from draft changes
            if not LADEN_STATUS_AVAILABLE:
                return self.send_json({'error': 'Laden status module not available'}, 500)

            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            days = int(params.get('days', [30])[0])
            track = get_vessel_track(vessel_id, days)

            if not track:
                return self.send_json({'error': 'No track data available'}, 404)

            # Run laden status analysis
            analysis = analyze_laden_status(
                vessel_id=vessel_id,
                mmsi=vessel.get('mmsi', ''),
                vessel_name=vessel.get('name', ''),
                track_history=track,
                vessel_info={
                    'vessel_type': vessel.get('vessel_type'),
                    'length_m': vessel.get('length_m'),
                    'beam_m': vessel.get('beam_m'),
                    'draught': vessel.get('draught'),
                    'max_draft': vessel.get('draught')
                }
            )

            return self.send_json(get_laden_status_summary(analysis))

        # ========== Satellite Intelligence Endpoints ==========

        elif path == '/api/satellite/search':
            # Search for satellite imagery in an area
            if not SATELLITE_AVAILABLE:
                return self.send_json({'error': 'Satellite module not available'}, 500)

            try:
                lat = float(params.get('lat', [0])[0])
                lon = float(params.get('lon', [0])[0])
                days = int(params.get('days', [7])[0])
            except (ValueError, TypeError):
                return self.send_json({'error': 'Invalid parameters'}, 400)

            if not lat or not lon:
                return self.send_json({'error': 'lat and lon required'}, 400)

            result = get_area_imagery(
                min_lat=lat - 0.5, min_lon=lon - 0.5,
                max_lat=lat + 0.5, max_lon=lon + 0.5,
                days=days
            )
            return self.send_json(result)

        elif path.startswith('/api/vessels/') and path.endswith('/satellite'):
            # Get satellite imagery for a vessel's location
            if not SATELLITE_AVAILABLE:
                return self.send_json({'error': 'Satellite module not available'}, 500)

            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            lat = vessel.get('last_lat')
            lon = vessel.get('last_lon')
            if not lat or not lon:
                return self.send_json({'error': 'Vessel has no position'}, 400)

            days = int(params.get('days', [30])[0])
            result = search_vessel_imagery(
                mmsi=vessel.get('mmsi', ''),
                latitude=lat,
                longitude=lon,
                days=days
            )
            result['vessel_id'] = vessel_id
            result['vessel_name'] = vessel.get('name')
            return self.send_json(result)

        elif path == '/api/storage-facilities':
            # Get monitored storage facilities
            if not SATELLITE_AVAILABLE:
                return self.send_json({'error': 'Satellite module not available'}, 500)

            region = params.get('region', [None])[0]
            facilities = get_storage_facilities(region)
            return self.send_json({
                'facilities': facilities,
                'count': len(facilities),
                'region': region or 'all'
            })

        elif path.startswith('/api/storage-facilities/') and path.endswith('/analysis'):
            # Analyze storage facility levels
            if not SATELLITE_AVAILABLE:
                return self.send_json({'error': 'Satellite module not available'}, 500)

            facility_id = path.split('/')[3]
            days = int(params.get('days', [30])[0])
            result = analyze_storage_levels(facility_id, days)
            return self.send_json(result)

        # ========== Shoreside Photography Endpoints ==========

        elif path == '/api/photos':
            # Get recent photos
            if not PHOTOS_AVAILABLE:
                return self.send_json({'error': 'Photos module not available'}, 500)

            service = get_photo_service()
            limit = int(params.get('limit', [20])[0])
            status = params.get('status', [None])[0]
            photo_type = params.get('type', [None])[0]

            photos = service.get_recent_photos(limit, status, photo_type)
            return self.send_json({
                'photos': photos,
                'count': len(photos)
            })

        elif path == '/api/photos/stats':
            # Get photo collection stats
            if not PHOTOS_AVAILABLE:
                return self.send_json({'error': 'Photos module not available'}, 500)

            service = get_photo_service()
            return self.send_json(service.get_stats())

        elif path.startswith('/api/photos/') and len(path.split('/')) == 4:
            # Get single photo
            if not PHOTOS_AVAILABLE:
                return self.send_json({'error': 'Photos module not available'}, 500)

            photo_id = path.split('/')[3]
            service = get_photo_service()
            photo = service.get_photo(photo_id)
            if photo:
                return self.send_json(photo)
            return self.send_json({'error': 'Photo not found'}, 404)

        elif path.startswith('/api/vessels/') and path.endswith('/photos'):
            # Get photos for a vessel
            if not PHOTOS_AVAILABLE:
                return self.send_json({'error': 'Photos module not available'}, 500)

            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            service = get_photo_service()
            photos = service.get_vessel_photos(
                vessel_id=vessel_id,
                mmsi=vessel.get('mmsi'),
                vessel_name=vessel.get('name')
            )
            return self.send_json({
                'vessel_id': vessel_id,
                'vessel_name': vessel.get('name'),
                'photos': photos,
                'count': len(photos)
            })

        elif path == '/api/photos/nearby':
            # Get photos near a location
            if not PHOTOS_AVAILABLE:
                return self.send_json({'error': 'Photos module not available'}, 500)

            try:
                lat = float(params.get('lat', [0])[0])
                lon = float(params.get('lon', [0])[0])
                radius = float(params.get('radius', [50])[0])
            except (ValueError, TypeError):
                return self.send_json({'error': 'Invalid parameters'}, 400)

            service = get_photo_service()
            photos = service.get_location_photos(lat, lon, radius)
            return self.send_json({
                'center': {'lat': lat, 'lon': lon},
                'radius_km': radius,
                'photos': photos,
                'count': len(photos)
            })

        # ========== Global Fishing Watch Endpoints ==========

        elif path == '/api/gfw/status':
            # Check GFW API status
            if not GFW_AVAILABLE:
                return self.send_json({'error': 'GFW module not available'}, 500)
            return self.send_json({
                'available': True,
                'configured': gfw_is_configured(),
                'register_url': 'https://globalfishingwatch.org/our-apis/'
            })

        elif path == '/api/gfw/search':
            # Search for vessel in GFW database
            if not GFW_AVAILABLE:
                return self.send_json({'error': 'GFW module not available'}, 500)
            if not gfw_is_configured():
                return self.send_json({'error': 'GFW API token not configured', 'register_url': 'https://globalfishingwatch.org/our-apis/'}, 400)

            query = params.get('q', [None])[0]
            mmsi = params.get('mmsi', [None])[0]
            imo = params.get('imo', [None])[0]
            name = params.get('name', [None])[0]

            result = gfw_search_vessel(query=query, mmsi=mmsi, imo=imo, name=name)
            return self.send_json(result)

        elif path.startswith('/api/vessels/') and path.endswith('/gfw-events'):
            # Get GFW events for a vessel
            if not GFW_AVAILABLE:
                return self.send_json({'error': 'GFW module not available'}, 500)
            if not gfw_is_configured():
                return self.send_json({'error': 'GFW API token not configured'}, 400)

            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            mmsi = vessel.get('mmsi')
            if not mmsi:
                return self.send_json({'error': 'Vessel has no MMSI'}, 400)

            days = int(params.get('days', [90])[0])
            result = gfw_get_vessel_events(mmsi, days)
            result['vessel_id'] = vessel_id
            result['vessel_name'] = vessel.get('name')
            return self.send_json(result)

        elif path.startswith('/api/vessels/') and path.endswith('/gfw-risk'):
            # Get dark fleet risk indicators from GFW
            if not GFW_AVAILABLE:
                return self.send_json({'error': 'GFW module not available'}, 500)
            if not gfw_is_configured():
                return self.send_json({'error': 'GFW API token not configured'}, 400)

            vessel_id = int(path.split('/')[3])
            vessel = get_vessel(vessel_id)
            if not vessel:
                return self.send_json({'error': 'Vessel not found'}, 404)

            mmsi = vessel.get('mmsi')
            if not mmsi:
                return self.send_json({'error': 'Vessel has no MMSI'}, 400)

            days = int(params.get('days', [90])[0])
            result = gfw_get_dark_fleet_indicators(mmsi, days)
            result['vessel_id'] = vessel_id
            result['vessel_name'] = vessel.get('name')
            return self.send_json(result)

        elif path == '/api/gfw/sts-zone':
            # Check for STS activity in a zone
            if not GFW_AVAILABLE:
                return self.send_json({'error': 'GFW module not available'}, 500)
            if not gfw_is_configured():
                return self.send_json({'error': 'GFW API token not configured'}, 400)

            try:
                min_lat = float(params.get('min_lat', [0])[0])
                min_lon = float(params.get('min_lon', [0])[0])
                max_lat = float(params.get('max_lat', [0])[0])
                max_lon = float(params.get('max_lon', [0])[0])
                days = int(params.get('days', [30])[0])
            except (ValueError, TypeError):
                return self.send_json({'error': 'Invalid coordinates'}, 400)

            result = gfw_check_sts_zone(min_lat, min_lon, max_lat, max_lon, days)
            return self.send_json(result)

        # ========== Feature Status Endpoint ==========

        elif path == '/api/features':
            # Return available feature modules
            return self.send_json({
                'intel': INTEL_AVAILABLE,
                'weather': WEATHER_AVAILABLE,
                'sar': SAR_AVAILABLE,
                'confidence': CONFIDENCE_AVAILABLE,
                'intelligence': INTELLIGENCE_AVAILABLE,
                'behavior': BEHAVIOR_AVAILABLE,
                'venezuela': VENEZUELA_AVAILABLE,
                'sanctions': SANCTIONS_AVAILABLE,
                'dark_fleet': DARK_FLEET_AVAILABLE,
                'infra_analysis': INFRA_ANALYSIS_AVAILABLE,
                'laden_status': LADEN_STATUS_AVAILABLE,
                'satellite': SATELLITE_AVAILABLE,
                'photos': PHOTOS_AVAILABLE,
                'gfw': GFW_AVAILABLE,
                'gfw_configured': GFW_AVAILABLE and gfw_is_configured()
            })

        # Static files
        else:
            super().do_GET()

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length else '{}'
        data = json.loads(body) if body else {}

        if path == '/api/vessels':
            return self.send_json(add_vessel(data), 201)

        elif path.startswith('/api/vessels/') and path.endswith('/position'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(add_position(vessel_id, data), 201)

        elif path.startswith('/api/vessels/') and path.endswith('/event'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(add_event(vessel_id, data), 201)

        elif path == '/api/osint':
            return self.send_json(add_osint_report(data), 201)

        elif path.startswith('/api/alerts/') and path.endswith('/acknowledge'):
            alert_id = int(path.split('/')[3])
            return self.send_json(acknowledge_alert(alert_id))

        elif path == '/api/search-news':
            query = data.get('query', '')
            max_results = data.get('max_results', 10)
            if not query:
                return self.send_json({'error': 'Query required'}, 400)
            return self.send_json(search_news(query, max_results))

        elif path == '/api/track-vessel':
            if not data.get('mmsi'):
                return self.send_json({'error': 'MMSI required'}, 400)
            return self.send_json(track_live_vessel(data), 201)

        elif path.startswith('/api/vessels/') and path.endswith('/update'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(update_vessel(vessel_id, data))

        elif path.startswith('/api/vessels/') and path.endswith('/photo'):
            vessel_id = int(path.split('/')[3])
            photo_data = data.get('photo')
            filename = data.get('filename', 'photo.jpg')
            if not photo_data:
                return self.send_json({'error': 'Photo data required'}, 400)
            return self.send_json(save_vessel_photo(vessel_id, photo_data, filename))

        elif path == '/api/config/bounding-box':
            required = ['lat_min', 'lon_min', 'lat_max', 'lon_max']
            if not all(k in data for k in required):
                return self.send_json({'error': 'lat_min, lon_min, lat_max, lon_max required'}, 400)
            return self.send_json(update_bounding_box(data))

        elif path == '/api/vessel-intel':
            # Full AI-powered vessel intelligence analysis
            if not INTEL_AVAILABLE:
                return self.send_json({'error': 'Vessel intel module not available'}, 500)
            vessel_data = data.get('vessel')
            if not vessel_data:
                return self.send_json({'error': 'Vessel data required'}, 400)

            # Run analysis
            result = analyze_vessel_intel(vessel_data)

            # Save to database if vessel has an ID
            vessel_id = vessel_data.get('id')
            if vessel_id and result.get('status') == 'success':
                save_vessel_analysis(vessel_id, result)
                result['saved'] = True

                # Auto-apply field updates from enrichment and AI recommendations
                field_updates = result.get('field_updates', {})
                if field_updates:
                    # Filter to only allowed fields
                    allowed_fields = ['flag_state', 'vessel_type', 'classification', 'threat_level', 'imo', 'callsign', 'owner', 'length_m', 'beam_m', 'gross_tonnage']
                    safe_updates = {k: v for k, v in field_updates.items() if k in allowed_fields}
                    if safe_updates:
                        update_vessel(vessel_id, safe_updates)
                        result['fields_updated'] = list(safe_updates.keys())
                        print(f"[Intel] Auto-updated vessel {vessel_id} fields: {list(safe_updates.keys())}")

            return self.send_json(result)

        elif path == '/api/vessel-bluf':
            # Quick BLUF assessment
            if not INTEL_AVAILABLE:
                return self.send_json({'error': 'Vessel intel module not available'}, 500)
            vessel_data = data.get('vessel')
            if not vessel_data:
                return self.send_json({'error': 'Vessel data required'}, 400)
            return self.send_json(quick_vessel_bluf(vessel_data))

        elif path == '/api/poc/load':
            # Load a POC scenario
            poc_name = data.get('poc', 'baltic')
            return self.send_json(load_poc_scenario(poc_name))

        elif path == '/api/poc/list':
            # List available POC scenarios
            return self.send_json({
                'scenarios': [
                    {
                        'id': 'baltic',
                        'name': 'Baltic Cable Incident',
                        'description': 'Finland undersea cable incident (Dec 2025)',
                        'region': 'Baltic Sea / Gulf of Finland',
                        'vessels': ['FITBURG', 'EAGLE S'],
                        'infrastructure': ['C-Lion1', 'Estlink-2', 'Balticconnector'],
                        'color': '#3498db'
                    },
                    {
                        'id': 'venezuela',
                        'name': 'Venezuela Dark Fleet',
                        'description': 'Sanctions evasion & oil smuggling operations',
                        'region': 'Caribbean / Venezuela',
                        'vessels': ['SKIPPER', 'BELLA 1', 'CENTURIES'],
                        'infrastructure': ['Jose Terminal', 'La Borracha STS', 'Amuay'],
                        'color': '#e67e22'
                    },
                    {
                        'id': 'china',
                        'name': 'China Arsenal Ships',
                        'description': 'Containerized weapons & dual-use vessels',
                        'region': 'East China Sea / Taiwan Strait',
                        'vessels': ['ZHONG DA 79', 'YUAN WANG 5', 'HAI YANG 26'],
                        'infrastructure': ['Shanghai Shipyard', 'Ningbo Port', 'Taiwan Strait'],
                        'color': '#e74c3c'
                    }
                ]
            })

        # ========== Shoreside Photography POST Endpoints ==========

        elif path == '/api/photos/upload':
            # Upload a new shoreside photo
            if not PHOTOS_AVAILABLE:
                return self.send_json({'error': 'Photos module not available'}, 500)

            image_data = data.get('image') or data.get('photo')
            if not image_data:
                return self.send_json({'error': 'Image data required'}, 400)

            service = get_photo_service()
            result = service.upload_photo(
                image_data=image_data,
                filename=data.get('filename', 'photo.jpg'),
                photo_type=data.get('photo_type', 'vessel'),
                uploader_name=data.get('uploader_name'),
                title=data.get('title', ''),
                description=data.get('description', ''),
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                location_name=data.get('location_name'),
                port_name=data.get('port_name'),
                vessel_mmsi=data.get('vessel_mmsi'),
                vessel_name=data.get('vessel_name'),
                photo_taken=data.get('photo_taken'),
                tags=data.get('tags', [])
            )
            return self.send_json(result, 201)

        elif path.startswith('/api/photos/') and path.endswith('/verify'):
            # Verify a photo
            if not PHOTOS_AVAILABLE:
                return self.send_json({'error': 'Photos module not available'}, 500)

            photo_id = path.split('/')[3]
            status = data.get('status', 'verified')
            notes = data.get('notes')

            service = get_photo_service()
            result = service.update_photo_status(photo_id, status, notes)
            if result:
                return self.send_json(result)
            return self.send_json({'error': 'Photo not found'}, 404)

        elif path.startswith('/api/photos/') and path.endswith('/link-vessel'):
            # Link photo to vessel
            if not PHOTOS_AVAILABLE:
                return self.send_json({'error': 'Photos module not available'}, 500)

            photo_id = path.split('/')[3]
            vessel_id = data.get('vessel_id')
            if not vessel_id:
                return self.send_json({'error': 'vessel_id required'}, 400)

            service = get_photo_service()
            result = service.link_vessel(photo_id, vessel_id)
            if result:
                return self.send_json(result)
            return self.send_json({'error': 'Photo not found'}, 404)

        # ========== GFW Configuration POST Endpoints ==========

        elif path == '/api/gfw/configure':
            # Configure GFW API token
            if not GFW_AVAILABLE:
                return self.send_json({'error': 'GFW module not available'}, 500)

            token = data.get('token')
            if not token:
                return self.send_json({'error': 'Token required'}, 400)

            if gfw_save_token(token):
                return self.send_json({'success': True, 'message': 'GFW API token configured'})
            return self.send_json({'error': 'Failed to save token'}, 500)

        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_DELETE(self):
        """Handle DELETE requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        # DELETE /api/vessels/:id
        if path.startswith('/api/vessels/'):
            parts = path.split('/')
            if len(parts) == 4:  # /api/vessels/123
                vessel_id = int(parts[3])
                return self.send_json(delete_vessel(vessel_id))

        self.send_json({'error': 'Not found'}, 404)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        """Custom log format."""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {args[0]}")


def migrate_database():
    """Run database migrations."""
    conn = get_db()

    # Add photo_url column if it doesn't exist
    try:
        conn.execute('SELECT photo_url FROM vessels LIMIT 1')
    except sqlite3.OperationalError:
        print("Adding photo_url column to vessels table...")
        conn.execute('ALTER TABLE vessels ADD COLUMN photo_url TEXT')
        conn.commit()

    # Add AI analysis columns if they don't exist
    try:
        conn.execute('SELECT ai_analysis FROM vessels LIMIT 1')
    except sqlite3.OperationalError:
        print("Adding AI analysis columns to vessels table...")
        conn.execute('ALTER TABLE vessels ADD COLUMN ai_analysis TEXT')
        conn.execute('ALTER TABLE vessels ADD COLUMN ai_bluf TEXT')
        conn.execute('ALTER TABLE vessels ADD COLUMN ai_analyzed_at TIMESTAMP')
        conn.commit()

    conn.close()


def run_server():
    """Start the HTTP server."""
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(PHOTOS_DIR, exist_ok=True)

    # Auto-initialize database if it doesn't exist
    if not os.path.exists(DB_PATH):
        print("Database not found. Initializing...")
        init_database()

    # Run migrations
    migrate_database()

    server = HTTPServer(('0.0.0.0', PORT), TrackerHandler)
    print(f"Arsenal Ship Tracker running on http://localhost:{PORT}")
    print(f"Live vessels file: {LIVE_VESSELS_PATH}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'init':
        init_database()
    else:
        run_server()
