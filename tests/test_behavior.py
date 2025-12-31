"""Tests for the behavior detection module."""

import unittest
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from behavior import (
    validate_mmsi, get_flag_country,
    detect_loitering, detect_ais_gaps, detect_spoofing,
    downsample_track, segment_track, filter_by_distance,
    deduplicate_positions, analyze_vessel_behavior,
    BehaviorType
)


class TestMMSIValidation(unittest.TestCase):
    """Test MMSI validation functions."""

    def test_valid_us_mmsi(self):
        """Test valid US MMSI."""
        result = validate_mmsi("366000001")
        self.assertTrue(result['valid'])
        self.assertEqual(result['country'], 'USA')
        self.assertEqual(result['type'], 'vessel')

    def test_valid_china_mmsi(self):
        """Test valid China MMSI."""
        result = validate_mmsi("413000000")
        self.assertTrue(result['valid'])
        self.assertEqual(result['country'], 'China')

    def test_valid_panama_mmsi(self):
        """Test valid Panama MMSI (common flag of convenience)."""
        result = validate_mmsi("351000001")
        self.assertTrue(result['valid'])
        self.assertEqual(result['country'], 'Panama')

    def test_invalid_length(self):
        """Test MMSI with invalid length."""
        result = validate_mmsi("12345")
        self.assertFalse(result['valid'])
        self.assertIn('Invalid length', result['reason'])

    def test_empty_mmsi(self):
        """Test empty MMSI."""
        result = validate_mmsi("")
        self.assertFalse(result['valid'])

    def test_known_fake_mmsi(self):
        """Test known fake/test MMSI."""
        result = validate_mmsi("123456789")
        self.assertFalse(result['valid'])
        self.assertIn('fake', result['reason'].lower())

    def test_coast_station_mmsi(self):
        """Test coast station MMSI (starts with 00)."""
        result = validate_mmsi("003669999")
        self.assertTrue(result['valid'])
        self.assertEqual(result['type'], 'coast_station')

    def test_sar_aircraft_mmsi(self):
        """Test SAR aircraft MMSI (starts with 111)."""
        result = validate_mmsi("111366000")
        self.assertTrue(result['valid'])
        self.assertEqual(result['type'], 'sar_aircraft')

    def test_get_flag_country(self):
        """Test get_flag_country helper."""
        self.assertEqual(get_flag_country("366000001"), "USA")
        self.assertEqual(get_flag_country("413000000"), "China")
        self.assertIsNone(get_flag_country("invalid"))


class TestLoiteringDetection(unittest.TestCase):
    """Test loitering detection."""

    def test_detect_loitering(self):
        """Test basic loitering detection."""
        base_time = datetime.now()
        track = [
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.5, 'timestamp': base_time},
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.3, 'timestamp': base_time + timedelta(hours=1)},
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.2, 'timestamp': base_time + timedelta(hours=2)},
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.4, 'timestamp': base_time + timedelta(hours=3)},
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.1, 'timestamp': base_time + timedelta(hours=4)},
        ]

        events = detect_loitering(track, "413000000", min_duration_hours=3)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, BehaviorType.LOITERING)

    def test_no_loitering_fast_vessel(self):
        """Test that fast-moving vessel doesn't trigger loitering."""
        base_time = datetime.now()
        track = [
            {'lat': 31.0, 'lon': 121.0, 'speed': 12.0, 'timestamp': base_time},
            {'lat': 31.5, 'lon': 121.5, 'speed': 14.0, 'timestamp': base_time + timedelta(hours=1)},
            {'lat': 32.0, 'lon': 122.0, 'speed': 13.0, 'timestamp': base_time + timedelta(hours=2)},
        ]

        events = detect_loitering(track, "413000000")
        self.assertEqual(len(events), 0)


class TestAISGapDetection(unittest.TestCase):
    """Test AIS gap detection."""

    def test_detect_gap(self):
        """Test basic AIS gap detection."""
        base_time = datetime.now()
        track = [
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time},
            {'lat': 31.5, 'lon': 121.5, 'timestamp': base_time + timedelta(hours=3)},  # 3-hour gap
        ]

        events = detect_ais_gaps(track, "413000000", max_gap_minutes=60)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, BehaviorType.AIS_GAP)
        self.assertGreater(events[0].details['gap_minutes'], 60)

    def test_no_gap_continuous_transmission(self):
        """Test that continuous transmission doesn't trigger gap detection."""
        base_time = datetime.now()
        track = [
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time},
            {'lat': 31.1, 'lon': 121.1, 'timestamp': base_time + timedelta(minutes=5)},
            {'lat': 31.2, 'lon': 121.2, 'timestamp': base_time + timedelta(minutes=10)},
        ]

        events = detect_ais_gaps(track, "413000000", max_gap_minutes=60)
        self.assertEqual(len(events), 0)


class TestSpoofingDetection(unittest.TestCase):
    """Test spoofing/impossible movement detection."""

    def test_detect_impossible_speed(self):
        """Test detection of impossible vessel speed."""
        base_time = datetime.now()
        # Vessel appears to move 1000km in 1 hour (impossible)
        track = [
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time},
            {'lat': 40.0, 'lon': 121.0, 'timestamp': base_time + timedelta(hours=1)},
        ]

        events = detect_spoofing(track, "413000000", max_speed_knots=50)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, BehaviorType.IMPOSSIBLE_SPEED)

    def test_no_spoofing_normal_speed(self):
        """Test that normal vessel speed doesn't trigger spoofing."""
        base_time = datetime.now()
        # Normal ~20 knot travel
        track = [
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time},
            {'lat': 31.3, 'lon': 121.3, 'timestamp': base_time + timedelta(hours=1)},
        ]

        events = detect_spoofing(track, "413000000", max_speed_knots=50)
        self.assertEqual(len(events), 0)


class TestTrackUtilities(unittest.TestCase):
    """Test track utility functions."""

    def test_downsample_track(self):
        """Test track downsampling."""
        base_time = datetime.now()
        track = [
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time},
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time + timedelta(seconds=10)},
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time + timedelta(seconds=20)},
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time + timedelta(seconds=70)},
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time + timedelta(seconds=130)},
        ]

        downsampled = downsample_track(track, interval_seconds=60)
        self.assertEqual(len(downsampled), 3)  # Positions at 0s, 70s, 130s

    def test_segment_track(self):
        """Test track segmentation by time gaps."""
        base_time = datetime.now()
        track = [
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time},
            {'lat': 31.1, 'lon': 121.1, 'timestamp': base_time + timedelta(hours=1)},
            {'lat': 31.2, 'lon': 121.2, 'timestamp': base_time + timedelta(hours=30)},  # New segment
            {'lat': 31.3, 'lon': 121.3, 'timestamp': base_time + timedelta(hours=31)},
        ]

        segments = segment_track(track, max_gap_hours=24)
        self.assertEqual(len(segments), 2)
        self.assertEqual(len(segments[0]), 2)
        self.assertEqual(len(segments[1]), 2)

    def test_filter_by_distance(self):
        """Test distance-based filtering."""
        positions = [
            {'lat': 31.0, 'lon': 121.0},  # Reference point
            {'lat': 31.1, 'lon': 121.1},  # ~14km away
            {'lat': 32.0, 'lon': 122.0},  # ~150km away
        ]

        filtered = filter_by_distance(positions, 31.0, 121.0, max_distance_km=50)
        self.assertEqual(len(filtered), 2)  # Only first two

    def test_deduplicate_positions(self):
        """Test position deduplication."""
        base_time = datetime.now()
        positions = [
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time},
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time + timedelta(seconds=5)},  # Duplicate
            {'lat': 31.0, 'lon': 121.0, 'timestamp': base_time + timedelta(seconds=15)},  # Keep
        ]

        deduped = deduplicate_positions(positions, window_seconds=10)
        self.assertEqual(len(deduped), 2)


class TestBatchAnalysis(unittest.TestCase):
    """Test batch analysis function."""

    def test_analyze_vessel_behavior(self):
        """Test comprehensive vessel behavior analysis."""
        base_time = datetime.now()
        track = [
            {'lat': 31.0, 'lon': 121.0, 'speed': 10.0, 'timestamp': base_time},
            {'lat': 31.1, 'lon': 121.1, 'speed': 12.0, 'timestamp': base_time + timedelta(hours=1)},
            {'lat': 31.2, 'lon': 121.2, 'speed': 11.0, 'timestamp': base_time + timedelta(hours=2)},
        ]

        result = analyze_vessel_behavior(track, "366000001")

        self.assertIn('mmsi_validation', result)
        self.assertTrue(result['mmsi_validation']['valid'])
        self.assertEqual(result['mmsi_validation']['country'], 'USA')

        self.assertIn('track_statistics', result)
        self.assertEqual(result['track_statistics']['position_count'], 3)

        self.assertIn('events', result)
        self.assertIn('risk_indicators', result)


class TestStringTimestamps(unittest.TestCase):
    """Test that functions handle string timestamps correctly."""

    def test_loitering_with_string_timestamps(self):
        """Test loitering detection with ISO string timestamps."""
        track = [
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.5, 'timestamp': '2025-01-01T00:00:00Z'},
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.3, 'timestamp': '2025-01-01T01:00:00Z'},
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.2, 'timestamp': '2025-01-01T02:00:00Z'},
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.4, 'timestamp': '2025-01-01T03:00:00Z'},
            {'lat': 31.0, 'lon': 121.0, 'speed': 0.1, 'timestamp': '2025-01-01T04:00:00Z'},
        ]

        events = detect_loitering(track, "413000000", min_duration_hours=3)
        self.assertEqual(len(events), 1)

    def test_gap_detection_with_string_timestamps(self):
        """Test gap detection with ISO string timestamps."""
        track = [
            {'lat': 31.0, 'lon': 121.0, 'timestamp': '2025-01-01T00:00:00Z'},
            {'lat': 31.5, 'lon': 121.5, 'timestamp': '2025-01-01T03:00:00Z'},  # 3-hour gap
        ]

        events = detect_ais_gaps(track, "413000000", max_gap_minutes=60)
        self.assertEqual(len(events), 1)


if __name__ == '__main__':
    unittest.main()
