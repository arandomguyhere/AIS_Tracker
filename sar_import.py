#!/usr/bin/env python3
"""
SAR (Synthetic Aperture Radar) Ship Detection Import Module

Parses ship detections from ESA SNAP toolbox output and correlates with AIS data.
Supports CSV and XML formats from SNAP's Ocean Object Detection processor.

Free data sources:
- Sentinel-1 imagery: https://scihub.copernicus.eu/
- SNAP Toolbox: https://step.esa.int/main/download/snap-download/

No external dependencies - uses only Python standard library.
"""

import csv
import json
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, List, Optional, Tuple, Any

# Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'arsenal_tracker.db')

# Correlation thresholds
DEFAULT_TIME_WINDOW_MINUTES = 30  # Max time difference for SAR-AIS match
DEFAULT_DISTANCE_THRESHOLD_KM = 2.0  # Max distance for SAR-AIS match


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers."""
    R = 6371  # Earth's radius in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c


class SARDetection:
    """Represents a single SAR ship detection."""

    def __init__(
        self,
        latitude: float,
        longitude: float,
        timestamp: str,
        length_m: Optional[float] = None,
        width_m: Optional[float] = None,
        confidence: float = 0.8,
        source_file: Optional[str] = None,
        detection_id: Optional[str] = None
    ):
        self.latitude = latitude
        self.longitude = longitude
        self.timestamp = timestamp
        self.length_m = length_m
        self.width_m = width_m
        self.confidence = confidence
        self.source_file = source_file
        self.detection_id = detection_id
        self.matched_vessel_id: Optional[int] = None
        self.match_distance_km: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'latitude': self.latitude,
            'longitude': self.longitude,
            'timestamp': self.timestamp,
            'length_m': self.length_m,
            'width_m': self.width_m,
            'confidence': self.confidence,
            'source_file': self.source_file,
            'detection_id': self.detection_id,
            'matched_vessel_id': self.matched_vessel_id,
            'match_distance_km': self.match_distance_km,
            'is_dark_vessel': self.matched_vessel_id is None
        }


def parse_snap_csv(
    filepath: str,
    acquisition_time: Optional[str] = None
) -> List[SARDetection]:
    """
    Parse SNAP CSV export format.

    SNAP CSV format (field positions based on ESA tutorial):
    - field_6 (index 5): latitude
    - field_8 (index 7): longitude
    - field_12 (index 11): estimated length in meters

    Args:
        filepath: Path to CSV file
        acquisition_time: SAR image acquisition time (ISO format)

    Returns:
        List of SARDetection objects
    """
    detections = []
    timestamp = acquisition_time or datetime.utcnow().isoformat()

    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        for row_num, row in enumerate(reader, 1):
            try:
                # Skip empty rows
                if not row or len(row) < 12:
                    continue

                # Extract values (SNAP format: field_6=lat, field_8=lon, field_12=length)
                lat_str = row[5].strip().strip('"')
                lon_str = row[7].strip().strip('"')
                length_str = row[11].strip().strip('"') if len(row) > 11 else None

                # Skip if coordinates are empty
                if not lat_str or not lon_str:
                    continue

                latitude = float(lat_str)
                longitude = float(lon_str)
                length_m = float(length_str) if length_str else None

                detection = SARDetection(
                    latitude=latitude,
                    longitude=longitude,
                    timestamp=timestamp,
                    length_m=length_m,
                    confidence=0.8,  # Default confidence for CSV
                    source_file=os.path.basename(filepath),
                    detection_id=f"csv_{row_num}"
                )
                detections.append(detection)

            except (ValueError, IndexError) as e:
                print(f"[SAR Import] Warning: Skipping row {row_num}: {e}")
                continue

    return detections


def parse_snap_xml(filepath: str) -> List[SARDetection]:
    """
    Parse SNAP XML detection report format.

    Args:
        filepath: Path to XML file

    Returns:
        List of SARDetection objects
    """
    detections = []

    tree = ET.parse(filepath)
    root = tree.getroot()

    # Try to get acquisition time from product metadata
    acquisition_time = None
    acq_elem = root.find('.//acquisition_time')
    if acq_elem is not None and acq_elem.text:
        acquisition_time = acq_elem.text

    timestamp = acquisition_time or datetime.utcnow().isoformat()

    # Find all detection elements
    for det_elem in root.findall('.//detection'):
        try:
            latitude = float(det_elem.get('lat', 0))
            longitude = float(det_elem.get('lon', 0))
            length_m = float(det_elem.get('length', 0)) if det_elem.get('length') else None
            width_m = float(det_elem.get('width', 0)) if det_elem.get('width') else None
            confidence = float(det_elem.get('confidence', 0.8))
            detection_id = det_elem.get('id', '')

            if latitude == 0 and longitude == 0:
                continue

            detection = SARDetection(
                latitude=latitude,
                longitude=longitude,
                timestamp=timestamp,
                length_m=length_m,
                width_m=width_m,
                confidence=confidence,
                source_file=os.path.basename(filepath),
                detection_id=f"xml_{detection_id}"
            )
            detections.append(detection)

        except (ValueError, TypeError) as e:
            print(f"[SAR Import] Warning: Skipping detection: {e}")
            continue

    return detections


def parse_detections(
    filepath: str,
    acquisition_time: Optional[str] = None
) -> List[SARDetection]:
    """
    Auto-detect format and parse SAR detections.

    Args:
        filepath: Path to detection file (CSV or XML)
        acquisition_time: Override acquisition time (ISO format)

    Returns:
        List of SARDetection objects
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Detection file not found: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.xml':
        return parse_snap_xml(filepath)
    elif ext == '.csv':
        return parse_snap_csv(filepath, acquisition_time)
    else:
        # Try CSV first, then XML
        try:
            return parse_snap_csv(filepath, acquisition_time)
        except Exception:
            return parse_snap_xml(filepath)


def correlate_with_ais(
    detections: List[SARDetection],
    time_window_minutes: int = DEFAULT_TIME_WINDOW_MINUTES,
    distance_threshold_km: float = DEFAULT_DISTANCE_THRESHOLD_KM,
    db_path: str = DB_PATH
) -> Tuple[List[SARDetection], List[SARDetection]]:
    """
    Correlate SAR detections with AIS vessel positions.

    Args:
        detections: List of SAR detections to correlate
        time_window_minutes: Max time difference for match
        distance_threshold_km: Max distance for match
        db_path: Path to database

    Returns:
        Tuple of (matched_detections, unmatched_detections)
    """
    matched = []
    unmatched = []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    for detection in detections:
        # Parse detection timestamp
        try:
            det_time = datetime.fromisoformat(detection.timestamp.replace('Z', '+00:00'))
        except ValueError:
            det_time = datetime.utcnow()

        # Time window for AIS position search
        time_start = (det_time - timedelta(minutes=time_window_minutes)).isoformat()
        time_end = (det_time + timedelta(minutes=time_window_minutes)).isoformat()

        # Find nearest AIS positions within time window
        cursor = conn.execute('''
            SELECT
                v.id as vessel_id,
                v.name as vessel_name,
                v.mmsi,
                v.length_m,
                p.latitude,
                p.longitude,
                p.timestamp
            FROM positions p
            JOIN vessels v ON p.vessel_id = v.id
            WHERE p.timestamp BETWEEN ? AND ?
            ORDER BY p.timestamp DESC
        ''', (time_start, time_end))

        best_match = None
        best_distance = float('inf')

        for row in cursor:
            distance = haversine(
                detection.latitude, detection.longitude,
                row['latitude'], row['longitude']
            )

            if distance < distance_threshold_km and distance < best_distance:
                best_distance = distance
                best_match = row

        if best_match:
            detection.matched_vessel_id = best_match['vessel_id']
            detection.match_distance_km = best_distance
            matched.append(detection)
        else:
            unmatched.append(detection)

    conn.close()
    return matched, unmatched


def save_detections_to_db(
    detections: List[SARDetection],
    db_path: str = DB_PATH
) -> int:
    """
    Save SAR detections to database.

    Args:
        detections: List of SARDetection objects
        db_path: Path to database

    Returns:
        Number of detections saved
    """
    conn = sqlite3.connect(db_path)

    # Create SAR detections table if it doesn't exist
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sar_detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            timestamp TEXT NOT NULL,
            length_m REAL,
            width_m REAL,
            confidence REAL DEFAULT 0.8,
            source_file TEXT,
            detection_id TEXT,
            matched_vessel_id INTEGER,
            match_distance_km REAL,
            is_dark_vessel INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (matched_vessel_id) REFERENCES vessels(id) ON DELETE SET NULL
        )
    ''')

    # Create indexes
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_sar_detections_timestamp
        ON sar_detections(timestamp)
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_sar_detections_dark
        ON sar_detections(is_dark_vessel)
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_sar_detections_coords
        ON sar_detections(latitude, longitude)
    ''')

    count = 0
    for det in detections:
        conn.execute('''
            INSERT INTO sar_detections (
                latitude, longitude, timestamp, length_m, width_m,
                confidence, source_file, detection_id,
                matched_vessel_id, match_distance_km, is_dark_vessel
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            det.latitude, det.longitude, det.timestamp,
            det.length_m, det.width_m, det.confidence,
            det.source_file, det.detection_id,
            det.matched_vessel_id, det.match_distance_km,
            1 if det.matched_vessel_id is None else 0
        ))
        count += 1

    conn.commit()
    conn.close()
    return count


def get_dark_vessels(
    since: Optional[str] = None,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    """
    Get SAR detections with no AIS match (potential dark vessels).

    Args:
        since: Only get detections after this timestamp (ISO format)
        db_path: Path to database

    Returns:
        List of dark vessel detections
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Check if table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sar_detections'"
    )
    if not cursor.fetchone():
        conn.close()
        return []

    query = '''
        SELECT * FROM sar_detections
        WHERE is_dark_vessel = 1
    '''
    params = []

    if since:
        query += ' AND timestamp > ?'
        params.append(since)

    query += ' ORDER BY timestamp DESC'

    cursor = conn.execute(query, params)
    results = [dict(row) for row in cursor]
    conn.close()

    return results


def get_sar_detections(
    since: Optional[str] = None,
    include_matched: bool = True,
    db_path: str = DB_PATH
) -> List[Dict[str, Any]]:
    """
    Get all SAR detections.

    Args:
        since: Only get detections after this timestamp (ISO format)
        include_matched: Include AIS-matched detections
        db_path: Path to database

    Returns:
        List of detections
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Check if table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sar_detections'"
    )
    if not cursor.fetchone():
        conn.close()
        return []

    query = 'SELECT * FROM sar_detections WHERE 1=1'
    params = []

    if since:
        query += ' AND timestamp > ?'
        params.append(since)

    if not include_matched:
        query += ' AND is_dark_vessel = 1'

    query += ' ORDER BY timestamp DESC'

    cursor = conn.execute(query, params)
    results = [dict(row) for row in cursor]
    conn.close()

    return results


def import_sar_file(
    filepath: str,
    acquisition_time: Optional[str] = None,
    correlate: bool = True,
    db_path: str = DB_PATH
) -> Dict[str, Any]:
    """
    Import SAR detection file and optionally correlate with AIS.

    This is the main entry point for SAR import.

    Args:
        filepath: Path to SNAP detection file (CSV or XML)
        acquisition_time: SAR image acquisition time (ISO format)
        correlate: Whether to correlate with AIS positions
        db_path: Path to database

    Returns:
        Import summary with statistics
    """
    result = {
        'file': os.path.basename(filepath),
        'timestamp': datetime.utcnow().isoformat(),
        'total_detections': 0,
        'matched': 0,
        'dark_vessels': 0,
        'saved': 0,
        'errors': []
    }

    try:
        # Parse detections
        detections = parse_detections(filepath, acquisition_time)
        result['total_detections'] = len(detections)

        if not detections:
            result['errors'].append('No detections found in file')
            return result

        # Correlate with AIS
        if correlate:
            matched, unmatched = correlate_with_ais(detections, db_path=db_path)
            result['matched'] = len(matched)
            result['dark_vessels'] = len(unmatched)
            all_detections = matched + unmatched
        else:
            result['dark_vessels'] = len(detections)
            all_detections = detections

        # Save to database
        result['saved'] = save_detections_to_db(all_detections, db_path)

        # Create events for dark vessels
        if result['dark_vessels'] > 0:
            _create_dark_vessel_events(
                [d for d in all_detections if d.matched_vessel_id is None],
                db_path
            )

    except Exception as e:
        result['errors'].append(str(e))

    return result


def _create_dark_vessel_events(
    detections: List[SARDetection],
    db_path: str
) -> None:
    """Create events for dark vessel detections."""
    conn = sqlite3.connect(db_path)

    for det in detections:
        # Create an event for each dark vessel detection
        conn.execute('''
            INSERT INTO events (
                vessel_id, event_type, severity, title, description,
                latitude, longitude, source, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            None,  # No vessel_id for dark vessels
            'anomaly_detected',
            'high',
            'Dark Vessel Detected (SAR)',
            f'SAR detection with no AIS correlation. Estimated length: {det.length_m or "unknown"}m',
            det.latitude,
            det.longitude,
            'SAR',
            json.dumps(det.to_dict())
        ))

    conn.commit()
    conn.close()


# CLI interface
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Import SAR ship detections from SNAP output'
    )
    parser.add_argument(
        'file',
        help='Path to SNAP detection file (CSV or XML)'
    )
    parser.add_argument(
        '--time', '-t',
        help='Acquisition time (ISO format, e.g., 2025-01-01T10:30:00Z)'
    )
    parser.add_argument(
        '--no-correlate',
        action='store_true',
        help='Skip AIS correlation'
    )
    parser.add_argument(
        '--db',
        default=DB_PATH,
        help='Database path'
    )

    args = parser.parse_args()

    result = import_sar_file(
        args.file,
        acquisition_time=args.time,
        correlate=not args.no_correlate,
        db_path=args.db
    )

    print("\n" + "=" * 50)
    print("SAR Import Summary")
    print("=" * 50)
    print(f"  File: {result['file']}")
    print(f"  Total detections: {result['total_detections']}")
    print(f"  AIS matched: {result['matched']}")
    print(f"  Dark vessels: {result['dark_vessels']}")
    print(f"  Saved to DB: {result['saved']}")

    if result['errors']:
        print(f"  Errors: {result['errors']}")

    print("=" * 50)
