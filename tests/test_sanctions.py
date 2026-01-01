"""
Tests for Sanctions Database Integration Module

Tests cover:
- Sanctioned vessel data structures
- Database operations
- Vessel lookup by IMO, MMSI, name
- Known vessels database
- Venezuela integration
"""

import unittest
import tempfile
import os
from datetime import datetime

# Import from parent directory
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sanctions import (
    SanctionedVessel,
    SanctionAuthority,
    SanctionsDatabase,
    KNOWN_SANCTIONED_VESSELS,
    check_venezuela_sanctions
)


class TestSanctionedVessel(unittest.TestCase):
    """Test SanctionedVessel data class."""

    def test_vessel_creation(self):
        """Test creating a sanctioned vessel record."""
        vessel = SanctionedVessel(
            imo="9328716",
            name="BLUE GULF",
            flag="Palau",
            vessel_type="Crude Oil Tanker",
            sanctioned_by=["OFAC"]
        )

        self.assertEqual(vessel.imo, "9328716")
        self.assertEqual(vessel.name, "BLUE GULF")
        self.assertIn("OFAC", vessel.sanctioned_by)

    def test_vessel_to_dict(self):
        """Test serialization to dict."""
        vessel = SanctionedVessel(
            imo="9179834",
            name="SKIPPER",
            former_names=["ADISA"],
            flag="Cameroon",
            sanctioned_by=["OFAC", "UK"]
        )

        data = vessel.to_dict()

        self.assertEqual(data["imo"], "9179834")
        self.assertEqual(data["name"], "SKIPPER")
        self.assertIn("ADISA", data["former_names"])
        self.assertIn("OFAC", data["sanctioned_by"])

    def test_vessel_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "imo": "9274668",
            "name": "CAROLINE BEZENGI",
            "sanctioned_by": ["EU"],
            "sanction_programs": ["CFSP 2025/2032"]
        }

        vessel = SanctionedVessel.from_dict(data)

        self.assertEqual(vessel.imo, "9274668")
        self.assertEqual(vessel.name, "CAROLINE BEZENGI")
        self.assertIn("EU", vessel.sanctioned_by)


class TestKnownVessels(unittest.TestCase):
    """Test known sanctioned vessels database."""

    def test_skipper_in_database(self):
        """Skipper should be in known vessels."""
        names = [v.name for v in KNOWN_SANCTIONED_VESSELS]
        self.assertIn("SKIPPER", names)

    def test_skipper_has_former_name(self):
        """Skipper should have former name ADISA."""
        skipper = next(v for v in KNOWN_SANCTIONED_VESSELS if v.name == "SKIPPER")
        self.assertIn("ADISA", skipper.former_names)

    def test_skipper_sanctions(self):
        """Skipper should be sanctioned by OFAC and UK."""
        skipper = next(v for v in KNOWN_SANCTIONED_VESSELS if v.name == "SKIPPER")
        self.assertIn("OFAC", skipper.sanctioned_by)
        self.assertIn("UK", skipper.sanctioned_by)

    def test_blue_gulf_imo(self):
        """Blue Gulf should have correct IMO."""
        blue_gulf = next(v for v in KNOWN_SANCTIONED_VESSELS if v.name == "BLUE GULF")
        self.assertEqual(blue_gulf.imo, "9328716")

    def test_eu_package_19_vessels(self):
        """EU Package 19 vessels should be present."""
        names = [v.name for v in KNOWN_SANCTIONED_VESSELS]
        self.assertIn("CAROLINE BEZENGI", names)
        self.assertIn("IVAN KRAMSKOY", names)

    def test_known_vessels_have_source(self):
        """All known vessels should have source."""
        for vessel in KNOWN_SANCTIONED_VESSELS:
            self.assertTrue(vessel.source, f"{vessel.name} missing source")


class TestSanctionsDatabase(unittest.TestCase):
    """Test SanctionsDatabase operations."""

    def setUp(self):
        """Create temporary database for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_sanctions.db")
        self.db = SanctionsDatabase(db_path=self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_creation(self):
        """Database file should be created."""
        self.assertTrue(os.path.exists(self.db_path))

    def test_add_vessel(self):
        """Test adding a vessel to database."""
        vessel = SanctionedVessel(
            imo="9999999",
            name="TEST VESSEL",
            sanctioned_by=["OFAC"]
        )

        result = self.db.add_vessel(vessel)
        self.assertTrue(result)

    def test_check_vessel_by_imo(self):
        """Test looking up vessel by IMO."""
        vessel = SanctionedVessel(
            imo="9328716",
            name="BLUE GULF",
            flag="Palau",
            sanctioned_by=["OFAC"]
        )
        self.db.add_vessel(vessel)

        result = self.db.check_vessel(imo="9328716")

        self.assertTrue(result["sanctioned"])
        self.assertEqual(result["vessel"]["name"], "BLUE GULF")
        self.assertEqual(result["match_type"], "imo")

    def test_check_vessel_by_name(self):
        """Test looking up vessel by name."""
        vessel = SanctionedVessel(
            imo="9179834",
            name="SKIPPER",
            sanctioned_by=["OFAC", "UK"]
        )
        self.db.add_vessel(vessel)

        result = self.db.check_vessel(name="SKIPPER")

        self.assertTrue(result["sanctioned"])
        self.assertEqual(result["match_type"], "name")

    def test_check_vessel_by_former_name(self):
        """Test looking up vessel by former name."""
        vessel = SanctionedVessel(
            imo="9179834",
            name="SKIPPER",
            former_names=["ADISA"],
            sanctioned_by=["OFAC"]
        )
        self.db.add_vessel(vessel)

        result = self.db.check_vessel(name="ADISA")

        self.assertTrue(result["sanctioned"])
        self.assertEqual(result["vessel"]["name"], "SKIPPER")

    def test_check_nonsanctioned_vessel(self):
        """Non-sanctioned vessel should return False."""
        result = self.db.check_vessel(imo="1234567")

        self.assertFalse(result["sanctioned"])
        self.assertIsNone(result["vessel"])

    def test_load_known_vessels(self):
        """Test loading known vessels database."""
        count = self.db.load_known_vessels()

        self.assertGreater(count, 0)

        # Verify Skipper was loaded
        result = self.db.check_vessel(name="SKIPPER")
        self.assertTrue(result["sanctioned"])

    def test_get_statistics(self):
        """Test getting database statistics."""
        self.db.load_known_vessels()

        stats = self.db.get_statistics()

        self.assertIn("total_vessels", stats)
        self.assertGreater(stats["total_vessels"], 0)
        self.assertIn("by_authority", stats)

    def test_update_existing_vessel(self):
        """Test updating an existing vessel."""
        vessel1 = SanctionedVessel(
            imo="9999999",
            name="OLD NAME",
            sanctioned_by=["OFAC"]
        )
        self.db.add_vessel(vessel1)

        vessel2 = SanctionedVessel(
            imo="9999999",
            name="NEW NAME",
            sanctioned_by=["OFAC", "EU"]
        )
        self.db.add_vessel(vessel2)

        result = self.db.check_vessel(imo="9999999")

        self.assertEqual(result["vessel"]["name"], "NEW NAME")
        self.assertIn("EU", result["authorities"])


class TestVenezuelaIntegration(unittest.TestCase):
    """Test Venezuela sanctions integration."""

    def setUp(self):
        """Create temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_sanctions.db")

        # Patch the default database path
        import sanctions
        self.original_init = sanctions.SanctionsDatabase.__init__

        def patched_init(self_db, db_path=None):
            self.original_init(self_db, db_path=self.db_path)

        sanctions.SanctionsDatabase.__init__ = patched_init

    def tearDown(self):
        """Clean up."""
        import shutil
        import sanctions
        sanctions.SanctionsDatabase.__init__ = self.original_init
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_venezuela_sanctions_found(self):
        """Test Venezuela sanctions check finds vessel."""
        db = SanctionsDatabase(db_path=self.db_path)
        db.add_vessel(SanctionedVessel(
            imo="9179834",
            name="SKIPPER",
            sanctioned_by=["OFAC"],
            notes="Seized in Venezuela trade"
        ))

        result = check_venezuela_sanctions(name="SKIPPER")

        self.assertTrue(result["sanctioned"])

    def test_check_venezuela_sanctions_not_found(self):
        """Test Venezuela sanctions check for clean vessel."""
        result = check_venezuela_sanctions(imo="0000000")

        self.assertFalse(result["sanctioned"])


class TestSanctionAuthority(unittest.TestCase):
    """Test SanctionAuthority enum."""

    def test_ofac_value(self):
        """OFAC should have correct value."""
        self.assertEqual(SanctionAuthority.OFAC.value, "OFAC")

    def test_eu_value(self):
        """EU should have correct value."""
        self.assertEqual(SanctionAuthority.EU.value, "EU")

    def test_all_authorities(self):
        """All expected authorities should be present."""
        authorities = [a.value for a in SanctionAuthority]
        self.assertIn("OFAC", authorities)
        self.assertIn("EU", authorities)
        self.assertIn("UK", authorities)
        self.assertIn("CA", authorities)
        self.assertIn("AU", authorities)
        self.assertIn("NZ", authorities)


if __name__ == "__main__":
    unittest.main()
