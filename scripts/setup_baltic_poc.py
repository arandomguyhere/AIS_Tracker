#!/usr/bin/env python3
"""
Baltic Cable Incident POC Setup

Sets up AIS_Tracker for analyzing the Finland undersea cable incident (Dec 2025).
- Adds the Fitburg vessel to tracking
- Configures Baltic Sea / Gulf of Finland area monitoring
- Adds undersea cable infrastructure locations
- Creates incident timeline events

Incident Context:
- Date: December 31, 2025
- Location: Gulf of Finland, Baltic Sea
- Vessel: Fitburg (cargo ship)
- Incident: Suspected anchor-dragging damage to undersea telecom cable
- Status: Vessel seized by Finnish authorities

Usage:
    python scripts/setup_baltic_poc.py
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(SCRIPT_DIR, 'arsenal_tracker.db')
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'ais_config.json')


# =============================================================================
# Vessel Data - Fitburg
# =============================================================================

FITBURG_VESSEL = {
    "name": "FITBURG",
    "mmsi": "518100989",  # Cook Islands registered
    "imo": "9187629",
    "flag_state": "Cook Islands",
    "vessel_type": "Cargo Ship",
    "classification": "suspected",
    "threat_level": "high",
    "intel_notes": """Baltic Cable Incident - December 31, 2025

INCIDENT SUMMARY:
Finnish authorities seized the cargo ship Fitburg after an undersea telecom
cable was damaged in the Gulf of Finland. The ship was found with its anchor
dragging near the suspected damage zone.

KEY FACTS:
- Vessel departed from Russian port
- Anchor found dragging across seabed
- Undersea cable damage detected same timeframe
- Criminal investigation opened for interference and aggravated damage
- Treated as potential hybrid threat / sabotage incident

BEHAVIORAL INDICATORS:
- Unusual course deviation
- Anchor deployment in deep water shipping lane
- Proximity to critical infrastructure
- Route from Russian territory

SOURCES:
- Reuters: Finland seizes ship sailing from Russia after suspected cable sabotage
- Finnish authorities statement
- Red Hot Cyber analysis
"""
}

# Other vessels of interest in the Baltic (shadow fleet / infrastructure threats)
RELATED_VESSELS = [
    {
        "name": "EAGLE S",
        "mmsi": "255806583",
        "imo": "9037155",
        "flag_state": "Malta",
        "vessel_type": "Oil Tanker",
        "classification": "suspected",
        "threat_level": "high",
        "intel_notes": "Estlink-2 cable incident (Dec 25, 2025). Shadow fleet tanker, dragged anchor damaging Finland-Estonia power cable."
    }
]


# =============================================================================
# Baltic Sea Infrastructure - Undersea Cables
# =============================================================================

UNDERSEA_CABLES = [
    {
        "name": "C-Lion1 Cable",
        "facility_type": "port",  # Using port type for infrastructure
        "location": "Helsinki-Rostock",
        "latitude": 59.45,
        "longitude": 24.75,
        "geofence_radius_km": 10.0,
        "threat_association": "Critical telecom infrastructure",
        "notes": "Finland-Germany submarine communications cable. ~1,200km. Damaged Dec 31, 2025."
    },
    {
        "name": "Estlink-2 Power Cable",
        "facility_type": "port",
        "location": "Finland-Estonia",
        "latitude": 59.55,
        "longitude": 25.00,
        "geofence_radius_km": 10.0,
        "threat_association": "Critical power infrastructure",
        "notes": "650MW HVDC power cable between Finland and Estonia. Damaged Dec 25, 2025 by Eagle S anchor."
    },
    {
        "name": "Gulf of Finland Cable Zone",
        "facility_type": "anchorage",
        "location": "Gulf of Finland",
        "latitude": 59.70,
        "longitude": 25.50,
        "geofence_radius_km": 50.0,
        "threat_association": "Multiple undersea cables intersection",
        "notes": "High-density undersea infrastructure zone. Multiple telecom and power cables."
    },
    {
        "name": "Nord Stream Pipeline Area",
        "facility_type": "anchorage",
        "location": "Baltic Sea",
        "latitude": 54.50,
        "longitude": 15.50,
        "geofence_radius_km": 30.0,
        "threat_association": "Critical energy infrastructure (damaged)",
        "notes": "Nord Stream 1 & 2 pipelines. Sabotaged September 2022. Monitoring zone."
    },
    {
        "name": "Balticconnector Pipeline",
        "facility_type": "anchorage",
        "location": "Finland-Estonia",
        "latitude": 59.60,
        "longitude": 24.80,
        "geofence_radius_km": 15.0,
        "threat_association": "Gas pipeline infrastructure",
        "notes": "Finland-Estonia gas pipeline. Damaged October 2023 by anchor dragging (Hong Kong vessel)."
    }
]


# =============================================================================
# Incident Timeline Events
# =============================================================================

INCIDENT_EVENTS = [
    {
        "event_type": "anomaly_detected",
        "severity": "critical",
        "title": "Undersea cable damage detected",
        "description": "Finnish authorities detect damage to C-Lion1 submarine telecom cable in Gulf of Finland.",
        "source": "Finnish Transport and Communications Agency",
        "latitude": 59.45,
        "longitude": 24.75,
        "event_date": "2025-12-31 08:00:00"
    },
    {
        "event_type": "anomaly_detected",
        "severity": "high",
        "title": "Fitburg anchor dragging detected",
        "description": "Coast Guard observes Fitburg with anchor deployed and dragging across seabed in cable zone.",
        "source": "Finnish Border Guard",
        "latitude": 59.50,
        "longitude": 25.10,
        "event_date": "2025-12-31 10:00:00"
    },
    {
        "event_type": "geofence_enter",
        "severity": "high",
        "title": "Fitburg enters critical infrastructure zone",
        "description": "Vessel enters Gulf of Finland cable protection zone.",
        "latitude": 59.55,
        "longitude": 25.00,
        "event_date": "2025-12-31 06:00:00"
    },
    {
        "event_type": "ais_dark",
        "severity": "medium",
        "title": "Fitburg vessel seized by Finnish authorities",
        "description": "Finnish authorities board and seize Fitburg. Vessel escorted to Kilpilahti port for investigation.",
        "source": "Reuters",
        "source_url": "https://www.reuters.com/world/finland-suspects-ship-causing-undersea-cable-damage-president-says-2025-12-31/",
        "latitude": 60.30,
        "longitude": 25.55,
        "event_date": "2025-12-31 14:00:00"
    }
]


# =============================================================================
# Baltic Sea Bounding Box Configuration
# =============================================================================

BALTIC_CONFIG = {
    "area_tracking": {
        "enabled": True,
        "auto_update": True,
        "bounding_box": {
            "lat_min": 53.0,
            "lon_min": 9.0,
            "lat_max": 66.0,
            "lon_max": 30.0,
            "description": "Baltic Sea - Cable Infrastructure Monitoring Zone"
        }
    }
}


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_vessel(conn, vessel_data):
    """Add or update a vessel in the database."""
    cursor = conn.execute(
        "SELECT id FROM vessels WHERE mmsi = ? OR imo = ?",
        (vessel_data.get("mmsi"), vessel_data.get("imo"))
    )
    existing = cursor.fetchone()

    if existing:
        print(f"  Updating existing vessel: {vessel_data['name']}")
        conn.execute("""
            UPDATE vessels SET
                name = ?, flag_state = ?, vessel_type = ?,
                classification = ?, threat_level = ?, intel_notes = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            vessel_data["name"],
            vessel_data.get("flag_state"),
            vessel_data.get("vessel_type"),
            vessel_data.get("classification", "monitoring"),
            vessel_data.get("threat_level", "unknown"),
            vessel_data.get("intel_notes"),
            existing["id"]
        ))
        return existing["id"]
    else:
        print(f"  Adding new vessel: {vessel_data['name']}")
        cursor = conn.execute("""
            INSERT INTO vessels (name, mmsi, imo, flag_state, vessel_type,
                                classification, threat_level, intel_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            vessel_data["name"],
            vessel_data.get("mmsi"),
            vessel_data.get("imo"),
            vessel_data.get("flag_state"),
            vessel_data.get("vessel_type"),
            vessel_data.get("classification", "monitoring"),
            vessel_data.get("threat_level", "unknown"),
            vessel_data.get("intel_notes")
        ))
        return cursor.lastrowid


def add_infrastructure(conn, infra_data):
    """Add infrastructure location to shipyards table."""
    cursor = conn.execute(
        "SELECT id FROM shipyards WHERE name = ?",
        (infra_data["name"],)
    )
    existing = cursor.fetchone()

    if existing:
        print(f"  Updating: {infra_data['name']}")
        conn.execute("""
            UPDATE shipyards SET
                location = ?, latitude = ?, longitude = ?,
                geofence_radius_km = ?, facility_type = ?,
                threat_association = ?, notes = ?
            WHERE id = ?
        """, (
            infra_data.get("location"),
            infra_data["latitude"],
            infra_data["longitude"],
            infra_data.get("geofence_radius_km", 5.0),
            infra_data.get("facility_type", "port"),
            infra_data.get("threat_association"),
            infra_data.get("notes"),
            existing["id"]
        ))
    else:
        print(f"  Adding: {infra_data['name']}")
        conn.execute("""
            INSERT INTO shipyards (name, location, latitude, longitude,
                                  geofence_radius_km, facility_type,
                                  threat_association, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            infra_data["name"],
            infra_data.get("location"),
            infra_data["latitude"],
            infra_data["longitude"],
            infra_data.get("geofence_radius_km", 5.0),
            infra_data.get("facility_type", "port"),
            infra_data.get("threat_association"),
            infra_data.get("notes")
        ))


def add_event(conn, vessel_id, event_data):
    """Add incident event to timeline."""
    print(f"  Adding event: {event_data['title']}")
    conn.execute("""
        INSERT INTO events (vessel_id, event_type, severity, title,
                           description, source, source_url, latitude,
                           longitude, event_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        vessel_id,
        event_data["event_type"],
        event_data.get("severity", "info"),
        event_data["title"],
        event_data.get("description"),
        event_data.get("source"),
        event_data.get("source_url"),
        event_data.get("latitude"),
        event_data.get("longitude"),
        event_data.get("event_date")
    ))


def update_config():
    """Update AIS config for Baltic Sea monitoring."""
    print("\n[3/4] Updating AIS configuration for Baltic Sea...")

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
    else:
        config = {}

    # Update area tracking
    config["area_tracking"] = BALTIC_CONFIG["area_tracking"]

    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"  Bounding box: {BALTIC_CONFIG['area_tracking']['bounding_box']['description']}")
    print(f"  Lat: {BALTIC_CONFIG['area_tracking']['bounding_box']['lat_min']} - {BALTIC_CONFIG['area_tracking']['bounding_box']['lat_max']}")
    print(f"  Lon: {BALTIC_CONFIG['area_tracking']['bounding_box']['lon_min']} - {BALTIC_CONFIG['area_tracking']['bounding_box']['lon_max']}")


def main():
    print("=" * 60)
    print("Baltic Cable Incident POC Setup")
    print("=" * 60)
    print()
    print("Configuring AIS_Tracker for Finland undersea cable incident analysis")
    print("Incident Date: December 31, 2025")
    print("Primary Vessel: Fitburg")
    print()

    # Check database exists
    if not os.path.exists(DB_PATH):
        print("ERROR: Database not found. Run 'python server.py init' first.")
        sys.exit(1)

    conn = get_db()

    try:
        # 1. Add vessels
        print("[1/4] Adding vessels to tracking...")
        fitburg_id = add_vessel(conn, FITBURG_VESSEL)

        for vessel in RELATED_VESSELS:
            add_vessel(conn, vessel)

        # 2. Add infrastructure
        print("\n[2/4] Adding undersea cable infrastructure...")
        for infra in UNDERSEA_CABLES:
            add_infrastructure(conn, infra)

        # 3. Update config
        update_config()

        # 4. Add incident timeline
        print("\n[4/4] Adding incident timeline events...")
        for event in INCIDENT_EVENTS:
            add_event(conn, fitburg_id, event)

        conn.commit()

        print()
        print("=" * 60)
        print("POC Setup Complete!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("  1. Start AIS streaming: python stream_area.py")
        print("  2. Start web server: python server.py")
        print("  3. Open browser: http://localhost:8080")
        print()
        print("The map will show:")
        print("  - Fitburg vessel (if AIS data available)")
        print("  - Undersea cable infrastructure zones")
        print("  - Incident timeline events")
        print()
        print("To search for historical AIS data for Fitburg:")
        print(f"  MMSI: {FITBURG_VESSEL['mmsi']}")
        print(f"  IMO:  {FITBURG_VESSEL['imo']}")
        print()

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
