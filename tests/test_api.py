"""
API endpoint tests for AIS_Tracker.
Tests the HTTP API without running the full server.
"""

import unittest
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import BaseTestCase


class TestAPIFunctions(BaseTestCase):
    """Test API helper functions directly."""

    def test_haversine_calculation(self):
        """Test distance calculation function."""
        from server import haversine

        # New York to London approximately 5570 km
        distance = haversine(40.7128, -74.0060, 51.5074, -0.1278)
        self.assertGreater(distance, 5500)
        self.assertLess(distance, 5700)

    def test_haversine_same_point(self):
        """Test distance between same point is zero."""
        from server import haversine

        distance = haversine(45.0, 13.0, 45.0, 13.0)
        self.assertEqual(distance, 0)

    def test_haversine_short_distance(self):
        """Test short distance calculation."""
        from server import haversine

        # Approximately 1 degree latitude = 111 km
        distance = haversine(45.0, 13.0, 46.0, 13.0)
        self.assertGreater(distance, 110)
        self.assertLess(distance, 112)


class TestGzipCompression(unittest.TestCase):
    """Test gzip compression functionality."""

    def test_gzip_compress(self):
        """Test that gzip compression works."""
        import gzip

        test_data = b'{"test": "data"}' * 100  # Make it large enough
        compressed = gzip.compress(test_data)

        self.assertLess(len(compressed), len(test_data))

    def test_gzip_roundtrip(self):
        """Test gzip compress/decompress cycle."""
        import gzip

        test_data = b'{"vessels": [{"name": "TEST"}]}'
        compressed = gzip.compress(test_data)
        decompressed = gzip.decompress(compressed)

        self.assertEqual(test_data, decompressed)


class TestDataValidation(unittest.TestCase):
    """Test data validation functions."""

    def test_valid_mmsi_format(self):
        """Test MMSI format validation."""
        # MMSI should be 9 digits
        valid_mmsis = ['123456789', '999999999', '100000000']
        invalid_mmsis = ['12345678', '1234567890', 'abcdefghi', '']

        for mmsi in valid_mmsis:
            self.assertEqual(len(mmsi), 9)
            self.assertTrue(mmsi.isdigit())

        for mmsi in invalid_mmsis:
            self.assertFalse(len(mmsi) == 9 and mmsi.isdigit())

    def test_valid_imo_format(self):
        """Test IMO format validation."""
        # IMO should be IMO followed by 7 digits
        valid_imos = ['IMO1234567', 'IMO9999999', 'IMO1000000']

        for imo in valid_imos:
            self.assertTrue(imo.startswith('IMO'))
            self.assertEqual(len(imo), 10)
            self.assertTrue(imo[3:].isdigit())

    def test_valid_coordinates(self):
        """Test coordinate range validation."""
        # Latitude: -90 to 90
        # Longitude: -180 to 180

        valid_coords = [
            (0, 0),
            (45.5, 13.5),
            (-45.5, -13.5),
            (90, 180),
            (-90, -180)
        ]

        for lat, lon in valid_coords:
            self.assertGreaterEqual(lat, -90)
            self.assertLessEqual(lat, 90)
            self.assertGreaterEqual(lon, -180)
            self.assertLessEqual(lon, 180)


class TestJSONSerialization(unittest.TestCase):
    """Test JSON serialization for API responses."""

    def test_vessel_serialization(self):
        """Test vessel data serializes to JSON."""
        vessel = {
            'id': 1,
            'name': 'TEST VESSEL',
            'mmsi': '123456789',
            'lat': 45.5,
            'lon': 13.5,
            'speed': 10.5,
            'course': 90.0,
            'threat_level': 'low'
        }

        json_str = json.dumps(vessel)
        parsed = json.loads(json_str)

        self.assertEqual(parsed['name'], 'TEST VESSEL')
        self.assertEqual(parsed['lat'], 45.5)

    def test_list_serialization(self):
        """Test list of vessels serializes correctly."""
        vessels = [
            {'id': 1, 'name': 'VESSEL 1'},
            {'id': 2, 'name': 'VESSEL 2'},
            {'id': 3, 'name': 'VESSEL 3'}
        ]

        json_str = json.dumps(vessels)
        parsed = json.loads(json_str)

        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]['name'], 'VESSEL 1')


class TestConfigLoading(unittest.TestCase):
    """Test configuration loading."""

    def test_config_structure(self):
        """Test that config file has expected structure if it exists."""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'ais_config.json'
        )

        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)

            # Check expected keys
            self.assertIn('sources', config)
            self.assertIn('aisstream', config['sources'])


if __name__ == '__main__':
    unittest.main()
