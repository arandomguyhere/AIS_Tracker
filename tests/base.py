"""
Base test utilities and fixtures for AIS_Tracker tests.
Uses stdlib unittest - no external dependencies.
"""

import os
import sys
import json
import sqlite3
import tempfile
import unittest
import threading
import time
from http.client import HTTPConnection
from contextlib import contextmanager
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDatabase:
    """Manages a temporary test database."""

    def __init__(self):
        self.fd, self.path = tempfile.mkstemp(suffix='.db')
        self.conn = None

    def initialize(self):
        """Initialize database with schema."""
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'schema.sql'
        )
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        with open(schema_path, 'r') as f:
            self.conn.executescript(f.read())

        # Add migration columns
        try:
            self.conn.execute('ALTER TABLE vessels ADD COLUMN photo_url TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            self.conn.execute('ALTER TABLE vessels ADD COLUMN ai_analysis TEXT')
            self.conn.execute('ALTER TABLE vessels ADD COLUMN ai_analysis_date TEXT')
            self.conn.execute('ALTER TABLE vessels ADD COLUMN ai_bluf TEXT')
        except sqlite3.OperationalError:
            pass

        self.conn.commit()
        return self

    def execute(self, sql, params=None):
        """Execute SQL and return cursor."""
        if params:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    def commit(self):
        """Commit transaction."""
        self.conn.commit()

    def cleanup(self):
        """Close connection and remove temp file."""
        if self.conn:
            self.conn.close()
        os.close(self.fd)
        os.unlink(self.path)


class BaseTestCase(unittest.TestCase):
    """Base test case with common utilities."""

    @classmethod
    def setUpClass(cls):
        """Set up test database."""
        cls.db = TestDatabase().initialize()

    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        cls.db.cleanup()

    # Counter for unique IMOs
    _imo_counter = 1000000

    def insert_test_vessel(self, **kwargs):
        """Insert a test vessel and return its ID."""
        # Generate unique IMO for each test
        BaseTestCase._imo_counter += 1
        unique_imo = f'IMO{BaseTestCase._imo_counter}'

        defaults = {
            'name': 'TEST VESSEL',
            'mmsi': '123456789',
            'imo': unique_imo,
            'flag_state': 'XX',
            'vessel_type': 'Cargo',
            'length_m': 100.0,
            'beam_m': 20.0,
            'owner': 'Test Owner',
            'classification': 'monitoring',
            'threat_level': 'low',
            'intel_notes': 'Test vessel'
        }
        defaults.update(kwargs)

        cursor = self.db.execute('''
            INSERT INTO vessels (
                name, mmsi, imo, flag_state, vessel_type, length_m, beam_m,
                owner, classification, threat_level, intel_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            defaults['name'], defaults['mmsi'], defaults['imo'], defaults['flag_state'],
            defaults['vessel_type'], defaults['length_m'], defaults['beam_m'],
            defaults['owner'], defaults['classification'],
            defaults['threat_level'], defaults['intel_notes']
        ))
        self.db.commit()
        return cursor.lastrowid

    def insert_test_position(self, vessel_id, lat, lon, timestamp=None, **kwargs):
        """Insert a test position record."""
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()

        self.db.execute('''
            INSERT INTO positions (vessel_id, latitude, longitude, speed_knots, course, heading, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            vessel_id, lat, lon,
            kwargs.get('speed_knots', 10.0),
            kwargs.get('course', 90.0),
            kwargs.get('heading', 90.0),
            timestamp
        ))
        self.db.commit()


# Sample data generators
def generate_sample_sar_detections():
    """Generate sample SAR detection data matching SNAP output format."""
    # Format matches SNAP Ship Detection CSV output
    detections = [
        # field_1, field_2, ... field_6=lat, field_8=lon, field_12=length
        {
            'lat': 45.6234,
            'lon': 13.7456,
            'length_m': 85.5,
            'timestamp': '2025-01-01T10:30:00Z',
            'confidence': 0.92
        },
        {
            'lat': 45.6189,
            'lon': 13.7612,
            'length_m': 120.3,
            'timestamp': '2025-01-01T10:30:00Z',
            'confidence': 0.88
        },
        {
            'lat': 45.6301,
            'lon': 13.7234,
            'length_m': 45.0,
            'timestamp': '2025-01-01T10:30:00Z',
            'confidence': 0.75
        },
        # Dark vessel - no AIS match expected
        {
            'lat': 45.7500,
            'lon': 13.9000,
            'length_m': 65.0,
            'timestamp': '2025-01-01T10:30:00Z',
            'confidence': 0.85
        }
    ]
    return detections


def generate_snap_csv_output():
    """Generate CSV content matching actual SNAP export format."""
    # Based on ESA tutorial: field_6=lat, field_8=lon, field_12=length
    lines = [
        '"","","","","","45.6234","","13.7456","","","","85.5"',
        '"","","","","","45.6189","","13.7612","","","","120.3"',
        '"","","","","","45.6301","","13.7234","","","","45.0"',
        '"","","","","","45.7500","","13.9000","","","","65.0"',
    ]
    return '\n'.join(lines)


def generate_snap_xml_output():
    """Generate XML content matching SNAP detection report format."""
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<object_detection_report>
    <detection id="1" lat="45.6234" lon="13.7456" length="85.5" width="15.2"/>
    <detection id="2" lat="45.6189" lon="13.7612" length="120.3" width="22.1"/>
    <detection id="3" lat="45.6301" lon="13.7234" length="45.0" width="8.5"/>
    <detection id="4" lat="45.7500" lon="13.9000" length="65.0" width="12.0"/>
</object_detection_report>'''
    return xml
