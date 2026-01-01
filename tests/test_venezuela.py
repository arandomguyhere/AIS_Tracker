"""
Tests for Venezuela Dark Fleet Detection Module

Tests cover:
- Venezuela zone detection
- AIS spoofing detection
- Circle spoofing detection
- Alert generation
- Risk scoring
- Known vessel matching
"""

import unittest
from datetime import datetime, timedelta

# Import from parent directory
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from venezuela import (
    # Zone detection
    is_in_venezuela_zone,
    VENEZUELA_BOUNDS,
    VENEZUELA_KEY_POINTS,

    # Deception detection
    detect_ais_spoofing,
    detect_circle_spoofing,
    detect_identity_laundering,
    DeceptionType,

    # Alert system
    check_venezuela_alerts,
    AlertType,
    VenezuelaAlert,

    # Risk scoring
    calculate_venezuela_risk_score,

    # Known vessels
    KNOWN_DARK_FLEET_VESSELS,
    VENEZUELA_DARK_FLEET_FLAGS,
    VesselStatus,

    # Configuration
    get_venezuela_monitoring_config
)


class TestVenezuelaZone(unittest.TestCase):
    """Test Venezuela zone detection."""

    def test_jose_terminal_in_zone(self):
        """Jose Terminal should be within Venezuela zone."""
        # Jose Terminal coordinates
        self.assertTrue(is_in_venezuela_zone(10.15, -64.68))

    def test_la_borracha_in_zone(self):
        """La Borracha STS zone should be within Venezuela zone."""
        self.assertTrue(is_in_venezuela_zone(10.08, -64.89))

    def test_amuay_refinery_in_zone(self):
        """Amuay Refinery should be within Venezuela zone."""
        self.assertTrue(is_in_venezuela_zone(11.74, -70.21))

    def test_new_york_not_in_zone(self):
        """New York should not be in Venezuela zone."""
        self.assertFalse(is_in_venezuela_zone(40.7, -74.0))

    def test_china_not_in_zone(self):
        """China should not be in Venezuela zone."""
        self.assertFalse(is_in_venezuela_zone(31.2, 121.5))

    def test_guyana_offshore_not_in_zone(self):
        """Guyana offshore is outside Venezuela monitoring zone."""
        # Skipper spoofed position near Guyana (outside monitoring zone)
        # This is intentional - spoofing targets outside the zone
        self.assertFalse(is_in_venezuela_zone(7.5, -57.5))

    def test_zone_boundary_north(self):
        """Test northern boundary of zone."""
        self.assertTrue(is_in_venezuela_zone(15.0, -65.0))  # On boundary
        self.assertFalse(is_in_venezuela_zone(15.1, -65.0))  # Just outside

    def test_zone_boundary_south(self):
        """Test southern boundary of zone."""
        self.assertTrue(is_in_venezuela_zone(8.0, -65.0))  # On boundary
        self.assertFalse(is_in_venezuela_zone(7.9, -65.0))  # Just outside


class TestAISSpoofingDetection(unittest.TestCase):
    """Test AIS spoofing detection via satellite comparison."""

    def test_detect_major_spoofing(self):
        """Detect spoofing when AIS and satellite differ by >500km."""
        # Simulating Skipper case: AIS near Guyana, satellite at Jose
        ais_positions = [
            {
                "timestamp": datetime(2025, 12, 15, 10, 0, 0),
                "lat": 7.5,  # Near Guyana
                "lon": -57.5
            }
        ]
        satellite_positions = [
            {
                "timestamp": datetime(2025, 12, 15, 10, 5, 0),
                "lat": 10.15,  # Jose Terminal
                "lon": -64.68,
                "source": "sentinel-1"
            }
        ]

        events = detect_ais_spoofing(ais_positions, satellite_positions, "123456789")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].deception_type, DeceptionType.AIS_SPOOFING)
        self.assertEqual(events[0].severity, "critical")
        self.assertGreater(events[0].evidence["discrepancy_km"], 500)

    def test_no_spoofing_matching_positions(self):
        """No spoofing detected when AIS matches satellite."""
        ais_positions = [
            {
                "timestamp": datetime(2025, 12, 15, 10, 0, 0),
                "lat": 10.15,
                "lon": -64.68
            }
        ]
        satellite_positions = [
            {
                "timestamp": datetime(2025, 12, 15, 10, 5, 0),
                "lat": 10.16,  # Very close
                "lon": -64.67,
                "source": "sentinel-1"
            }
        ]

        events = detect_ais_spoofing(ais_positions, satellite_positions, "123456789")

        self.assertEqual(len(events), 0)

    def test_medium_discrepancy_detection(self):
        """Detect medium-severity spoofing (50-100km discrepancy)."""
        ais_positions = [
            {
                "timestamp": datetime(2025, 12, 15, 10, 0, 0),
                "lat": 10.5,
                "lon": -65.0
            }
        ]
        satellite_positions = [
            {
                "timestamp": datetime(2025, 12, 15, 10, 5, 0),
                "lat": 11.0,  # ~60km away
                "lon": -65.5,
                "source": "optical"
            }
        ]

        events = detect_ais_spoofing(
            ais_positions, satellite_positions, "123456789",
            max_discrepancy_km=10.0
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].severity, "medium")


class TestCircleSpoofingDetection(unittest.TestCase):
    """Test circle spoofing pattern detection."""

    def test_detect_circular_pattern(self):
        """Detect circular spoofing pattern."""
        # Create positions in a circle
        import math
        center_lat, center_lon = 10.0, -65.0
        radius_deg = 0.01  # About 1km

        positions = []
        for i in range(12):
            angle = 2 * math.pi * i / 12
            lat = center_lat + radius_deg * math.cos(angle)
            lon = center_lon + radius_deg * math.sin(angle)
            positions.append({
                "timestamp": datetime(2025, 12, 15, 10, 0, 0) + timedelta(minutes=i*5),
                "lat": lat,
                "lon": lon
            })

        events = detect_circle_spoofing(positions, "123456789", min_points=10)

        # Sliding window may detect multiple overlapping circular patterns
        self.assertGreater(len(events), 0)
        self.assertEqual(events[0].deception_type, DeceptionType.CIRCLE_SPOOFING)
        self.assertGreater(events[0].confidence, 0.85)

    def test_no_circle_linear_track(self):
        """No circle spoofing for linear vessel track."""
        positions = []
        for i in range(15):
            positions.append({
                "timestamp": datetime(2025, 12, 15, 10, 0, 0) + timedelta(minutes=i*10),
                "lat": 10.0 + i * 0.01,  # Moving north
                "lon": -65.0
            })

        events = detect_circle_spoofing(positions, "123456789", min_points=10)

        # Should not detect circles in linear movement
        self.assertEqual(len(events), 0)

    def test_insufficient_points(self):
        """No detection with insufficient points."""
        positions = [
            {"timestamp": datetime(2025, 12, 15, 10, 0), "lat": 10.0, "lon": -65.0},
            {"timestamp": datetime(2025, 12, 15, 10, 5), "lat": 10.01, "lon": -65.01},
        ]

        events = detect_circle_spoofing(positions, "123456789", min_points=10)

        self.assertEqual(len(events), 0)


class TestVenezuelaAlerts(unittest.TestCase):
    """Test Venezuela alert system."""

    def test_alert_jose_terminal_arrival(self):
        """Alert when vessel arrives at Jose Terminal."""
        current_position = {
            "timestamp": datetime(2025, 12, 20, 10, 0, 0),
            "lat": 10.15,  # Jose Terminal
            "lon": -64.68
        }
        track_history = []  # No prior track (dark arrival)

        alerts = check_venezuela_alerts(
            "413000000",
            "Test Tanker",
            current_position,
            track_history
        )

        terminal_alerts = [a for a in alerts if a.alert_type == AlertType.TERMINAL_ARRIVAL]
        self.assertGreater(len(terminal_alerts), 0)
        self.assertEqual(terminal_alerts[0].severity, "critical")

    def test_alert_sts_zone_entry(self):
        """Alert when vessel enters STS transfer zone."""
        current_position = {
            "timestamp": datetime(2025, 12, 20, 10, 0, 0),
            "lat": 10.08,  # La Borracha STS Zone
            "lon": -64.89
        }

        alerts = check_venezuela_alerts(
            "413000000",
            "Test Tanker",
            current_position,
            track_history=[]
        )

        sts_alerts = [a for a in alerts if a.alert_type == AlertType.STS_ZONE_ENTRY]
        self.assertGreater(len(sts_alerts), 0)

    def test_alert_known_dark_fleet_vessel(self):
        """Alert when known dark fleet vessel detected."""
        current_position = {
            "timestamp": datetime(2025, 12, 20, 10, 0, 0),
            "lat": 10.5,
            "lon": -65.0
        }

        # Use known vessel name
        alerts = check_venezuela_alerts(
            "123456789",
            "Skipper",  # Known dark fleet vessel
            current_position,
            track_history=[]
        )

        sanctioned_alerts = [a for a in alerts if a.alert_type == AlertType.SANCTIONED_VESSEL]
        self.assertGreater(len(sanctioned_alerts), 0)
        self.assertEqual(sanctioned_alerts[0].severity, "critical")

    def test_no_alert_outside_zone(self):
        """No alerts for vessels outside Venezuela zone."""
        current_position = {
            "timestamp": datetime(2025, 12, 20, 10, 0, 0),
            "lat": 40.0,  # New York area
            "lon": -74.0
        }

        alerts = check_venezuela_alerts(
            "123456789",
            "Normal Tanker",
            current_position,
            track_history=[]
        )

        self.assertEqual(len(alerts), 0)


class TestVenezuelaRiskScoring(unittest.TestCase):
    """Test Venezuela risk scoring."""

    def test_high_risk_dark_fleet_flag(self):
        """High risk score for Venezuela dark fleet flag."""
        vessel_info = {
            "flag_state": "Cameroon",  # Skipper's flag
            "name": "Unknown Tanker"
        }

        result = calculate_venezuela_risk_score(
            "123456789",
            vessel_info=vessel_info
        )

        self.assertGreaterEqual(result["score"], 30)
        self.assertIn("venezuela_dark_fleet_flag", [f["factor"] for f in result["factors"]])

    def test_high_risk_known_vessel(self):
        """High risk for known dark fleet vessel."""
        vessel_info = {
            "name": "Skipper",
            "flag_state": "Cameroon"  # Add flag for higher score
        }

        result = calculate_venezuela_risk_score(
            "123456789",
            vessel_info=vessel_info
        )

        # Known vessel (40pts) + dark fleet flag (30pts) = 70+ = critical
        self.assertGreaterEqual(result["score"], 70)
        self.assertEqual(result["risk_level"], "critical")

    def test_low_risk_clean_vessel(self):
        """Low risk for vessel with no indicators."""
        vessel_info = {
            "flag_state": "United States",
            "name": "Clean Tanker"
        }

        result = calculate_venezuela_risk_score(
            "366123456",  # US MMSI
            vessel_info=vessel_info,
            track_history=[]
        )

        self.assertLess(result["score"], 15)
        self.assertEqual(result["risk_level"], "minimal")

    def test_combined_factors_scoring(self):
        """Combined risk factors produce higher score."""
        vessel_info = {
            "flag_state": "Gabon",  # Shadow fleet flag
            "name": "Suspicious Tanker"
        }

        # Track with AIS gaps
        track_history = [
            {"timestamp": datetime(2025, 12, 15, 10, 0), "lat": 10.0, "lon": -65.0},
            {"timestamp": datetime(2025, 12, 15, 15, 0), "lat": 10.5, "lon": -65.5},  # 5hr gap
            {"timestamp": datetime(2025, 12, 16, 10, 0), "lat": 11.0, "lon": -66.0},  # 19hr gap
        ]

        result = calculate_venezuela_risk_score(
            "123456789",
            vessel_info=vessel_info,
            track_history=track_history
        )

        # Should have flag points + AIS gap points
        self.assertGreater(result["score"], 30)


class TestKnownVessels(unittest.TestCase):
    """Test known dark fleet vessel database."""

    def test_skipper_in_database(self):
        """Skipper should be in known vessels database."""
        vessel_names = [v.name for v in KNOWN_DARK_FLEET_VESSELS]
        self.assertIn("Skipper", vessel_names)

    def test_skipper_status_seized(self):
        """Skipper should be marked as seized."""
        skipper = next(v for v in KNOWN_DARK_FLEET_VESSELS if v.name == "Skipper")
        self.assertEqual(skipper.status, VesselStatus.SEIZED)

    def test_skipper_has_former_name(self):
        """Skipper should have former name Adisa."""
        skipper = next(v for v in KNOWN_DARK_FLEET_VESSELS if v.name == "Skipper")
        self.assertIn("Adisa", skipper.former_names)

    def test_cameroon_in_dark_fleet_flags(self):
        """Cameroon should be in Venezuela dark fleet flags."""
        self.assertIn("Cameroon", VENEZUELA_DARK_FLEET_FLAGS)

    def test_gabon_in_dark_fleet_flags(self):
        """Gabon should be in Venezuela dark fleet flags."""
        self.assertIn("Gabon", VENEZUELA_DARK_FLEET_FLAGS)


class TestMonitoringConfiguration(unittest.TestCase):
    """Test monitoring configuration export."""

    def test_config_has_region(self):
        """Config should include region bounds."""
        config = get_venezuela_monitoring_config()
        self.assertIn("region", config)
        self.assertEqual(config["region"]["name"], "Venezuela Caribbean")

    def test_config_has_key_points(self):
        """Config should include key monitoring points."""
        config = get_venezuela_monitoring_config()
        self.assertIn("key_points", config)

        point_names = [p["name"] for p in config["key_points"]]
        self.assertIn("Jose Terminal", point_names)
        self.assertIn("La Borracha STS Zone", point_names)

    def test_config_has_detection_radii(self):
        """Config should include detection radii."""
        config = get_venezuela_monitoring_config()
        self.assertIn("detection_radii", config)
        self.assertIn("terminal", config["detection_radii"])
        self.assertIn("sts_zone", config["detection_radii"])

    def test_config_has_known_vessels(self):
        """Config should include known vessels."""
        config = get_venezuela_monitoring_config()
        self.assertIn("known_vessels", config)
        self.assertGreater(len(config["known_vessels"]), 0)


class TestDeceptionEventSerialization(unittest.TestCase):
    """Test deception event serialization."""

    def test_deception_event_to_dict(self):
        """DeceptionEvent should serialize to dict."""
        from venezuela import DeceptionEvent, DeceptionType

        event = DeceptionEvent(
            deception_type=DeceptionType.AIS_SPOOFING,
            mmsi="123456789",
            detected_at=datetime(2025, 12, 20, 10, 0, 0),
            location=(10.15, -64.68),
            confidence=0.95,
            severity="critical",
            evidence={"discrepancy_km": 550}
        )

        data = event.to_dict()

        self.assertEqual(data["deception_type"], "ais_spoofing")
        self.assertEqual(data["mmsi"], "123456789")
        self.assertEqual(data["severity"], "critical")
        self.assertEqual(data["location"]["lat"], 10.15)


class TestAlertSerialization(unittest.TestCase):
    """Test alert serialization."""

    def test_alert_to_dict(self):
        """VenezuelaAlert should serialize to dict."""
        alert = VenezuelaAlert(
            alert_type=AlertType.TERMINAL_ARRIVAL,
            mmsi="123456789",
            vessel_name="Test Tanker",
            timestamp=datetime(2025, 12, 20, 10, 0, 0),
            location=(10.15, -64.68),
            severity="critical",
            description="Vessel arrived at Jose Terminal"
        )

        data = alert.to_dict()

        self.assertEqual(data["alert_type"], "terminal_arrival")
        self.assertEqual(data["vessel_name"], "Test Tanker")
        self.assertEqual(data["severity"], "critical")


if __name__ == "__main__":
    unittest.main()
