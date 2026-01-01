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
    BehaviorType,
    # Dark fleet detection
    is_flag_of_convenience, is_shadow_fleet_flag,
    calculate_dark_fleet_score, detect_sts_transfers,
    FLAGS_OF_CONVENIENCE, SHADOW_FLEET_FLAGS
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


class TestFlagOfConvenience(unittest.TestCase):
    """Test Flag of Convenience detection."""

    def test_panama_is_foc(self):
        """Panama is a well-known FOC."""
        self.assertTrue(is_flag_of_convenience("Panama"))

    def test_liberia_is_foc(self):
        """Liberia is a major FOC registry."""
        self.assertTrue(is_flag_of_convenience("Liberia"))

    def test_usa_not_foc(self):
        """USA is not a FOC."""
        self.assertFalse(is_flag_of_convenience("USA"))

    def test_gabon_is_shadow_fleet_flag(self):
        """Gabon is associated with shadow fleet operations."""
        self.assertTrue(is_shadow_fleet_flag("Gabon"))
        self.assertTrue(is_flag_of_convenience("Gabon"))

    def test_cameroon_is_shadow_fleet_flag(self):
        """Cameroon is associated with shadow fleet operations."""
        self.assertTrue(is_shadow_fleet_flag("Cameroon"))

    def test_panama_not_shadow_fleet(self):
        """Panama is FOC but not specifically shadow fleet."""
        self.assertTrue(is_flag_of_convenience("Panama"))
        self.assertFalse(is_shadow_fleet_flag("Panama"))

    def test_none_handling(self):
        """None and empty strings handled gracefully."""
        self.assertFalse(is_flag_of_convenience(None))
        self.assertFalse(is_flag_of_convenience(""))
        self.assertFalse(is_shadow_fleet_flag(None))


class TestDarkFleetScore(unittest.TestCase):
    """Test dark fleet risk scoring."""

    def test_clean_vessel_minimal_risk(self):
        """Vessel with no risk factors gets minimal score."""
        result = calculate_dark_fleet_score(
            mmsi="366000001",
            flag="USA",
            year_built=2020,
            owner="Maersk Line",
            ais_gap_count=0,
            loitering_count=0,
            spoofing_count=0
        )
        self.assertEqual(result['risk_level'], 'minimal')
        self.assertLess(result['score'], 15)

    def test_shadow_fleet_flag_high_score(self):
        """Shadow fleet flag adds 25 points."""
        result = calculate_dark_fleet_score(flag="Gabon", owner="Known Owner")
        self.assertEqual(result['score'], 25)
        self.assertIn('shadow_fleet_flag', [f['factor'] for f in result['factors']])

    def test_foc_flag_moderate_score(self):
        """Regular FOC flag adds 15 points."""
        result = calculate_dark_fleet_score(flag="Panama", owner="Known Owner")
        self.assertEqual(result['score'], 15)
        self.assertIn('flag_of_convenience', [f['factor'] for f in result['factors']])

    def test_old_vessel_high_score(self):
        """Old vessel (25+ years) adds 20 points."""
        result = calculate_dark_fleet_score(year_built=1995, owner="Known Owner")
        self.assertEqual(result['score'], 20)
        self.assertIn('vessel_age', [f['factor'] for f in result['factors']])

    def test_unknown_owner_adds_points(self):
        """Unknown owner adds 15 points."""
        result = calculate_dark_fleet_score(owner="")
        self.assertEqual(result['score'], 15)
        self.assertIn('unknown_owner', [f['factor'] for f in result['factors']])

    def test_multiple_ais_gaps_high_score(self):
        """Multiple AIS gaps indicate dark fleet activity."""
        result = calculate_dark_fleet_score(ais_gap_count=5, owner="Known Owner")
        self.assertEqual(result['score'], 20)
        self.assertIn('ais_gaps', [f['factor'] for f in result['factors']])

    def test_combined_factors_critical_risk(self):
        """Multiple risk factors produce critical score."""
        result = calculate_dark_fleet_score(
            flag="Gabon",  # 25 points
            year_built=1998,  # 20 points (27 years old)
            owner="",  # 15 points
            ais_gap_count=5,  # 20 points
            spoofing_count=3,  # 15 points
            vessel_type="Crude Oil Tanker"  # 5 points
        )
        self.assertEqual(result['risk_level'], 'critical')
        self.assertGreaterEqual(result['score'], 70)

    def test_tanker_type_adds_points(self):
        """Tanker vessels get additional risk points."""
        result = calculate_dark_fleet_score(vessel_type="Crude Oil Tanker", owner="Known Owner")
        self.assertEqual(result['score'], 5)

    def test_sts_transfers_add_points(self):
        """STS transfers are high-risk indicator."""
        result = calculate_dark_fleet_score(sts_transfer_count=2, owner="Known Owner")
        self.assertEqual(result['score'], 15)

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        result = calculate_dark_fleet_score(
            flag="Gabon",
            year_built=1990,
            owner="",
            ais_gap_count=10,
            spoofing_count=10,
            loitering_count=10,
            sts_transfer_count=10,
            vessel_type="Tanker"
        )
        self.assertLessEqual(result['score'], 100)


class TestSTSTransferDetection(unittest.TestCase):
    """Test ship-to-ship transfer detection."""

    def test_detect_sts_long_encounter(self):
        """Detect STS when two vessels meet for extended period."""
        base_time = datetime.now()

        # Two vessels stationary together for 6 hours
        track1 = [
            {'lat': 10.0, 'lon': 50.0, 'speed': 0.5, 'timestamp': base_time + timedelta(hours=i)}
            for i in range(7)
        ]
        track2 = [
            {'lat': 10.0001, 'lon': 50.0001, 'speed': 0.3, 'timestamp': base_time + timedelta(hours=i)}
            for i in range(7)
        ]

        tracks = {
            "111111111": track1,
            "222222222": track2
        }

        events = detect_sts_transfers(tracks, min_duration_hours=4)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].details['event_subtype'], 'sts_transfer')

    def test_no_sts_short_encounter(self):
        """Short encounters don't trigger STS detection."""
        base_time = datetime.now()

        # Only 2 hours together - too short for STS
        track1 = [
            {'lat': 10.0, 'lon': 50.0, 'speed': 0.5, 'timestamp': base_time + timedelta(hours=i)}
            for i in range(3)
        ]
        track2 = [
            {'lat': 10.0001, 'lon': 50.0001, 'speed': 0.3, 'timestamp': base_time + timedelta(hours=i)}
            for i in range(3)
        ]

        tracks = {
            "111111111": track1,
            "222222222": track2
        }

        events = detect_sts_transfers(tracks, min_duration_hours=4)
        self.assertEqual(len(events), 0)

    def test_no_sts_moving_vessels(self):
        """Moving vessels don't trigger STS detection."""
        base_time = datetime.now()

        # Vessels moving too fast for STS
        track1 = [
            {'lat': 10.0 + i*0.1, 'lon': 50.0, 'speed': 12.0, 'timestamp': base_time + timedelta(hours=i)}
            for i in range(7)
        ]
        track2 = [
            {'lat': 10.0 + i*0.1, 'lon': 50.001, 'speed': 11.0, 'timestamp': base_time + timedelta(hours=i)}
            for i in range(7)
        ]

        tracks = {
            "111111111": track1,
            "222222222": track2
        }

        events = detect_sts_transfers(tracks, min_duration_hours=4)
        self.assertEqual(len(events), 0)


class TestDarkFleetScoreInBehaviorAnalysis(unittest.TestCase):
    """Test that dark fleet score is included in behavior analysis."""

    def test_behavior_analysis_includes_dark_fleet_score(self):
        """analyze_vessel_behavior should include dark_fleet_score."""
        base_time = datetime.now()
        track = [
            {'lat': 31.0, 'lon': 121.0, 'speed': 10.0, 'timestamp': base_time},
            {'lat': 31.1, 'lon': 121.1, 'speed': 12.0, 'timestamp': base_time + timedelta(hours=1)},
        ]

        result = analyze_vessel_behavior(track, "366000001")

        self.assertIn('dark_fleet_score', result)
        self.assertIn('score', result['dark_fleet_score'])
        self.assertIn('risk_level', result['dark_fleet_score'])


if __name__ == '__main__':
    unittest.main()
