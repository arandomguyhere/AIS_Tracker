"""
Tests for SAR detection import and correlation.
"""

import os
import sys
import unittest
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import BaseTestCase, generate_snap_csv_output, generate_snap_xml_output
from sar_import import (
    SARDetection,
    parse_snap_csv,
    parse_snap_xml,
    parse_detections,
    correlate_with_ais,
    save_detections_to_db,
    haversine
)


class TestSARDetection(unittest.TestCase):
    """Test SARDetection class."""

    def test_detection_creation(self):
        """Test creating a SAR detection."""
        det = SARDetection(
            latitude=45.5,
            longitude=13.5,
            timestamp='2025-01-01T10:30:00Z',
            length_m=100.0,
            confidence=0.9
        )
        self.assertEqual(det.latitude, 45.5)
        self.assertEqual(det.longitude, 13.5)
        self.assertEqual(det.length_m, 100.0)
        self.assertEqual(det.confidence, 0.9)
        self.assertIsNone(det.matched_vessel_id)

    def test_detection_to_dict(self):
        """Test converting detection to dictionary."""
        det = SARDetection(
            latitude=45.5,
            longitude=13.5,
            timestamp='2025-01-01T10:30:00Z',
            length_m=100.0
        )
        d = det.to_dict()
        self.assertEqual(d['latitude'], 45.5)
        self.assertEqual(d['is_dark_vessel'], True)

    def test_matched_detection(self):
        """Test that matched detection is not dark vessel."""
        det = SARDetection(
            latitude=45.5,
            longitude=13.5,
            timestamp='2025-01-01T10:30:00Z'
        )
        det.matched_vessel_id = 1
        d = det.to_dict()
        self.assertEqual(d['is_dark_vessel'], False)


class TestSNAPParsing(unittest.TestCase):
    """Test SNAP output parsing."""

    def setUp(self):
        """Create temp files for testing."""
        self.csv_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False
        )
        self.csv_file.write(generate_snap_csv_output())
        self.csv_file.close()

        self.xml_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.xml', delete=False
        )
        self.xml_file.write(generate_snap_xml_output())
        self.xml_file.close()

    def tearDown(self):
        """Clean up temp files."""
        os.unlink(self.csv_file.name)
        os.unlink(self.xml_file.name)

    def test_parse_csv(self):
        """Test parsing SNAP CSV format."""
        detections = parse_snap_csv(
            self.csv_file.name,
            acquisition_time='2025-01-01T10:30:00Z'
        )
        self.assertGreater(len(detections), 0)
        # First detection should be at Gulf of Trieste coordinates
        self.assertAlmostEqual(detections[0].latitude, 45.6234, places=3)
        self.assertAlmostEqual(detections[0].longitude, 13.7456, places=3)

    def test_parse_xml(self):
        """Test parsing SNAP XML format."""
        detections = parse_snap_xml(self.xml_file.name)
        self.assertGreater(len(detections), 0)
        # Check first detection
        self.assertAlmostEqual(detections[0].latitude, 45.6234, places=3)

    def test_auto_detect_csv(self):
        """Test auto-detection of CSV format."""
        detections = parse_detections(self.csv_file.name)
        self.assertGreater(len(detections), 0)

    def test_auto_detect_xml(self):
        """Test auto-detection of XML format."""
        detections = parse_detections(self.xml_file.name)
        self.assertGreater(len(detections), 0)

    def test_csv_length_extraction(self):
        """Test that length is extracted from CSV."""
        detections = parse_snap_csv(self.csv_file.name)
        # First detection should have length 85.5m
        self.assertIsNotNone(detections[0].length_m)
        self.assertAlmostEqual(detections[0].length_m, 85.5, places=1)

    def test_xml_confidence_extraction(self):
        """Test that confidence is extracted from XML."""
        detections = parse_snap_xml(self.xml_file.name)
        # Check that confidence was extracted (should be 0.92 from our sample)
        # If confidence attribute exists, it should be parsed
        self.assertIsNotNone(detections[0].confidence)
        # Confidence should be between 0 and 1
        self.assertGreaterEqual(detections[0].confidence, 0)
        self.assertLessEqual(detections[0].confidence, 1)


class TestHaversine(unittest.TestCase):
    """Test haversine distance calculation."""

    def test_same_point(self):
        """Test distance between same point is zero."""
        distance = haversine(45.0, 13.0, 45.0, 13.0)
        self.assertEqual(distance, 0)

    def test_known_distance(self):
        """Test a known distance calculation."""
        # Approximately 1 degree latitude = 111 km
        distance = haversine(45.0, 13.0, 46.0, 13.0)
        self.assertGreater(distance, 110)
        self.assertLess(distance, 112)

    def test_short_distance(self):
        """Test short distance in meters range."""
        # Very close points
        distance = haversine(45.0, 13.0, 45.001, 13.001)
        self.assertGreater(distance, 0)
        self.assertLess(distance, 1)  # Less than 1 km


class TestSARCorrelation(unittest.TestCase):
    """Test SAR-AIS correlation."""

    def setUp(self):
        """Create fresh database for each test."""
        from tests.base import TestDatabase
        self.db = TestDatabase().initialize()

    def tearDown(self):
        """Clean up test database."""
        self.db.cleanup()

    def insert_test_vessel(self, **kwargs):
        """Insert a test vessel and return its ID."""
        defaults = {
            'name': 'TEST VESSEL',
            'mmsi': '123456789',
            'flag_state': 'XX',
            'vessel_type': 'Cargo',
            'length_m': 100.0,
            'classification': 'monitoring',
            'threat_level': 'low'
        }
        defaults.update(kwargs)

        cursor = self.db.execute('''
            INSERT INTO vessels (name, mmsi, flag_state, vessel_type, length_m, classification, threat_level)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (defaults['name'], defaults['mmsi'], defaults['flag_state'],
              defaults['vessel_type'], defaults['length_m'],
              defaults['classification'], defaults['threat_level']))
        self.db.commit()
        return cursor.lastrowid

    def insert_test_position(self, vessel_id, lat, lon, timestamp):
        """Insert a test position."""
        self.db.execute('''
            INSERT INTO positions (vessel_id, latitude, longitude, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (vessel_id, lat, lon, timestamp))
        self.db.commit()

    def test_correlation_finds_match(self):
        """Test that correlation finds nearby AIS position."""
        # Insert a vessel with position
        vessel_id = self.insert_test_vessel(
            name='CORRELATION TEST',
            mmsi='111111111'
        )

        # Insert position at known location
        timestamp = datetime.utcnow().isoformat()
        self.insert_test_position(
            vessel_id,
            lat=45.6234,  # Same as first SAR detection
            lon=13.7456,
            timestamp=timestamp
        )

        # Create detection at same location
        detection = SARDetection(
            latitude=45.6234,
            longitude=13.7456,
            timestamp=timestamp
        )

        # Run correlation
        matched, unmatched = correlate_with_ais(
            [detection],
            time_window_minutes=60,
            distance_threshold_km=1.0,
            db_path=self.db.path
        )

        self.assertEqual(len(matched), 1)
        self.assertEqual(len(unmatched), 0)
        self.assertEqual(matched[0].matched_vessel_id, vessel_id)

    def test_correlation_dark_vessel(self):
        """Test that distant detection is not matched."""
        # Insert a vessel with position far away
        vessel_id = self.insert_test_vessel(
            name='FAR VESSEL',
            mmsi='222222222'
        )

        timestamp = datetime.utcnow().isoformat()
        self.insert_test_position(
            vessel_id,
            lat=40.0,  # Very far from detection
            lon=10.0,
            timestamp=timestamp
        )

        # Create detection at different location
        detection = SARDetection(
            latitude=45.6234,
            longitude=13.7456,
            timestamp=timestamp
        )

        matched, unmatched = correlate_with_ais(
            [detection],
            time_window_minutes=60,
            distance_threshold_km=1.0,
            db_path=self.db.path
        )

        self.assertEqual(len(matched), 0)
        self.assertEqual(len(unmatched), 1)
        self.assertIsNone(unmatched[0].matched_vessel_id)

    def test_correlation_time_window(self):
        """Test that old positions are not matched."""
        vessel_id = self.insert_test_vessel(
            name='OLD POSITION',
            mmsi='333333333'
        )

        # Insert old position (2 hours ago)
        old_time = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        self.insert_test_position(
            vessel_id,
            lat=45.6234,
            lon=13.7456,
            timestamp=old_time
        )

        # Detection is now
        detection = SARDetection(
            latitude=45.6234,
            longitude=13.7456,
            timestamp=datetime.utcnow().isoformat()
        )

        matched, unmatched = correlate_with_ais(
            [detection],
            time_window_minutes=30,  # Only look 30 min back
            distance_threshold_km=1.0,
            db_path=self.db.path
        )

        self.assertEqual(len(matched), 0)
        self.assertEqual(len(unmatched), 1)


class TestSARDatabaseOperations(unittest.TestCase):
    """Test SAR database operations."""

    def setUp(self):
        """Create fresh database for each test."""
        from tests.base import TestDatabase
        self.db = TestDatabase().initialize()

    def tearDown(self):
        """Clean up test database."""
        self.db.cleanup()

    def test_save_detections(self):
        """Test saving detections to database."""
        detections = [
            SARDetection(
                latitude=45.5,
                longitude=13.5,
                timestamp='2025-01-01T10:30:00Z',
                length_m=100.0
            ),
            SARDetection(
                latitude=45.6,
                longitude=13.6,
                timestamp='2025-01-01T10:30:00Z',
                length_m=50.0
            )
        ]

        count = save_detections_to_db(detections, self.db.path)
        self.assertEqual(count, 2)

        # Verify in database
        cursor = self.db.execute('SELECT COUNT(*) as count FROM sar_detections')
        self.assertEqual(cursor.fetchone()['count'], 2)

    def test_dark_vessel_flag(self):
        """Test that unmatched detections are flagged as dark vessels."""
        det = SARDetection(
            latitude=45.5,
            longitude=13.5,
            timestamp='2025-01-01T10:30:00Z'
        )
        # Not matched
        det.matched_vessel_id = None

        save_detections_to_db([det], self.db.path)

        cursor = self.db.execute(
            'SELECT is_dark_vessel FROM sar_detections WHERE latitude = 45.5'
        )
        self.assertEqual(cursor.fetchone()['is_dark_vessel'], 1)

    def test_matched_vessel_not_dark(self):
        """Test that matched detections are not flagged as dark vessels."""
        det = SARDetection(
            latitude=45.5,
            longitude=13.5,
            timestamp='2025-01-01T10:30:00Z'
        )
        det.matched_vessel_id = 1

        save_detections_to_db([det], self.db.path)

        cursor = self.db.execute(
            'SELECT is_dark_vessel FROM sar_detections WHERE latitude = 45.5'
        )
        self.assertEqual(cursor.fetchone()['is_dark_vessel'], 0)


if __name__ == '__main__':
    unittest.main()
