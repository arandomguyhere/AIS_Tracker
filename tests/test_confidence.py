"""
Tests for vessel confidence scoring module.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import TestDatabase
from confidence import (
    ConfidenceScore,
    calculate_ais_consistency,
    calculate_behavioral_normalcy,
    calculate_sar_corroboration,
    calculate_deception_likelihood,
    calculate_vessel_confidence,
    save_confidence_to_db,
    get_vessel_confidence
)


class TestConfidenceScore(unittest.TestCase):
    """Test ConfidenceScore class."""

    def test_score_creation(self):
        """Test creating a confidence score."""
        score = ConfidenceScore(
            vessel_id=1,
            ais_consistency=0.8,
            behavioral_normalcy=0.7,
            sar_corroboration=0.9
        )
        self.assertEqual(score.vessel_id, 1)
        self.assertEqual(score.ais_consistency, 0.8)

    def test_overall_confidence_calculation(self):
        """Test weighted overall confidence."""
        score = ConfidenceScore(
            vessel_id=1,
            ais_consistency=1.0,
            behavioral_normalcy=1.0,
            sar_corroboration=1.0
        )
        self.assertEqual(score.overall_confidence, 1.0)

    def test_confidence_level_high(self):
        """Test high confidence level."""
        score = ConfidenceScore(
            vessel_id=1,
            ais_consistency=0.9,
            behavioral_normalcy=0.9,
            sar_corroboration=0.9
        )
        self.assertEqual(score.confidence_level, 'high')

    def test_confidence_level_low(self):
        """Test low confidence level."""
        score = ConfidenceScore(
            vessel_id=1,
            ais_consistency=0.3,
            behavioral_normalcy=0.3,
            sar_corroboration=0.3
        )
        self.assertEqual(score.confidence_level, 'very_low')

    def test_score_clamping(self):
        """Test that scores are clamped between 0 and 1."""
        score = ConfidenceScore(
            vessel_id=1,
            ais_consistency=1.5,
            behavioral_normalcy=-0.5,
            sar_corroboration=0.5
        )
        self.assertEqual(score.ais_consistency, 1.0)
        self.assertEqual(score.behavioral_normalcy, 0.0)

    def test_to_dict(self):
        """Test dictionary serialization."""
        score = ConfidenceScore(
            vessel_id=1,
            ais_consistency=0.8,
            behavioral_normalcy=0.7,
            sar_corroboration=0.6
        )
        d = score.to_dict()
        self.assertIn('vessel_id', d)
        self.assertIn('overall_confidence', d)
        self.assertIn('confidence_level', d)


class TestAISConsistency(unittest.TestCase):
    """Test AIS consistency scoring."""

    def setUp(self):
        """Create fresh database for each test."""
        self.db = TestDatabase().initialize()
        self.vessel_id = self._insert_vessel()

    def tearDown(self):
        """Clean up."""
        self.db.cleanup()

    def _insert_vessel(self):
        """Insert a test vessel."""
        cursor = self.db.execute('''
            INSERT INTO vessels (name, mmsi, classification, threat_level)
            VALUES (?, ?, ?, ?)
        ''', ('TEST VESSEL', '123456789', 'monitoring', 'low'))
        self.db.commit()
        return cursor.lastrowid

    def _insert_position(self, lat, lon, timestamp, speed=10.0):
        """Insert a position record."""
        self.db.execute('''
            INSERT INTO positions (vessel_id, latitude, longitude, speed_knots, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (self.vessel_id, lat, lon, speed, timestamp))
        self.db.commit()

    def test_insufficient_data(self):
        """Test scoring with insufficient data."""
        score, factors = calculate_ais_consistency(
            self.vessel_id, days=30, db_path=self.db.path
        )
        self.assertEqual(score, 0.5)
        self.assertEqual(factors['reason'], 'insufficient_data')

    def test_consistent_positions(self):
        """Test scoring with consistent AIS transmission."""
        # Add positions every hour for the past day
        now = datetime.utcnow()
        for i in range(24):
            ts = (now - timedelta(hours=i)).isoformat()
            self._insert_position(45.0 + i*0.01, 13.0, ts)

        score, factors = calculate_ais_consistency(
            self.vessel_id, days=7, db_path=self.db.path
        )
        # Should have high score with regular transmissions
        self.assertGreater(score, 0.7)

    def test_ais_gaps_reduce_score(self):
        """Test that AIS gaps reduce score."""
        now = datetime.utcnow()
        # Position 1 day ago
        self._insert_position(45.0, 13.0, (now - timedelta(days=1)).isoformat())
        # Gap of 12 hours (> 6 hour threshold)
        self._insert_position(45.1, 13.1, (now - timedelta(hours=12)).isoformat())
        # Recent position
        self._insert_position(45.2, 13.2, now.isoformat())

        score, factors = calculate_ais_consistency(
            self.vessel_id, days=7, db_path=self.db.path
        )
        # Should have reduced score due to gap
        self.assertLess(score, 1.0)
        self.assertGreater(factors['gap_count'], 0)


class TestBehavioralNormalcy(unittest.TestCase):
    """Test behavioral normalcy scoring."""

    def setUp(self):
        """Create fresh database for each test."""
        self.db = TestDatabase().initialize()
        self.vessel_id = self._insert_vessel()

    def tearDown(self):
        """Clean up."""
        self.db.cleanup()

    def _insert_vessel(self):
        """Insert a test vessel."""
        cursor = self.db.execute('''
            INSERT INTO vessels (name, mmsi, classification, threat_level)
            VALUES (?, ?, ?, ?)
        ''', ('TEST VESSEL', '123456789', 'monitoring', 'low'))
        self.db.commit()
        return cursor.lastrowid

    def _insert_position(self, lat, lon, timestamp, speed=10.0, course=90.0):
        """Insert a position record."""
        self.db.execute('''
            INSERT INTO positions (vessel_id, latitude, longitude, speed_knots, course, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (self.vessel_id, lat, lon, speed, course, timestamp))
        self.db.commit()

    def test_insufficient_data(self):
        """Test scoring with insufficient data."""
        score, factors = calculate_behavioral_normalcy(
            self.vessel_id, days=30, db_path=self.db.path
        )
        self.assertEqual(score, 0.5)

    def test_normal_behavior(self):
        """Test scoring with normal behavior."""
        now = datetime.utcnow()
        for i in range(10):
            ts = (now - timedelta(hours=i)).isoformat()
            self._insert_position(45.0 + i*0.01, 13.0, ts, speed=12.0, course=90.0)

        score, factors = calculate_behavioral_normalcy(
            self.vessel_id, days=7, db_path=self.db.path
        )
        # Normal steady course should have high score
        self.assertGreater(score, 0.8)

    def test_sudden_speed_changes(self):
        """Test that sudden speed changes reduce score."""
        now = datetime.utcnow()
        self._insert_position(45.0, 13.0, (now - timedelta(hours=3)).isoformat(), speed=5.0)
        self._insert_position(45.1, 13.1, (now - timedelta(hours=2)).isoformat(), speed=25.0)  # Big change
        self._insert_position(45.2, 13.2, (now - timedelta(hours=1)).isoformat(), speed=3.0)   # Big change

        score, factors = calculate_behavioral_normalcy(
            self.vessel_id, days=7, db_path=self.db.path
        )
        self.assertLess(score, 1.0)
        self.assertGreater(factors['speed_change_count'], 0)


class TestSARCorroboration(unittest.TestCase):
    """Test SAR corroboration scoring."""

    def setUp(self):
        """Create fresh database for each test."""
        self.db = TestDatabase().initialize()
        self.vessel_id = self._insert_vessel()
        self._create_sar_table()

    def tearDown(self):
        """Clean up."""
        self.db.cleanup()

    def _insert_vessel(self):
        """Insert a test vessel."""
        cursor = self.db.execute('''
            INSERT INTO vessels (name, mmsi, classification, threat_level)
            VALUES (?, ?, ?, ?)
        ''', ('TEST VESSEL', '123456789', 'monitoring', 'low'))
        self.db.commit()
        return cursor.lastrowid

    def _create_sar_table(self):
        """Create SAR detections table."""
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS sar_detections (
                id INTEGER PRIMARY KEY,
                latitude REAL,
                longitude REAL,
                timestamp TEXT,
                matched_vessel_id INTEGER,
                is_dark_vessel INTEGER DEFAULT 1
            )
        ''')
        self.db.commit()

    def test_no_sar_data(self):
        """Test scoring with no SAR data."""
        score, factors = calculate_sar_corroboration(
            self.vessel_id, days=30, db_path=self.db.path
        )
        # Should return neutral score with no SAR coverage
        self.assertEqual(factors.get('reason'), 'no_sar_coverage')

    def test_sar_match_increases_score(self):
        """Test that SAR matches increase confidence."""
        now = datetime.utcnow()
        # Add SAR detection matched to this vessel
        self.db.execute('''
            INSERT INTO sar_detections (latitude, longitude, timestamp, matched_vessel_id, is_dark_vessel)
            VALUES (?, ?, ?, ?, ?)
        ''', (45.0, 13.0, now.isoformat(), self.vessel_id, 0))
        self.db.commit()

        score, factors = calculate_sar_corroboration(
            self.vessel_id, days=7, db_path=self.db.path
        )
        self.assertGreater(score, 0.5)
        self.assertEqual(factors['sar_matches'], 1)


class TestDeceptionLikelihood(unittest.TestCase):
    """Test deception likelihood calculation."""

    def test_low_ais_consistency_increases_deception(self):
        """Test that low AIS consistency increases deception likelihood."""
        deception = calculate_deception_likelihood(
            ais_consistency=0.3,
            behavioral_normalcy=0.8,
            sar_corroboration=0.8,
            factors={}
        )
        self.assertGreater(deception, 0)

    def test_high_scores_low_deception(self):
        """Test that high scores result in low deception likelihood."""
        deception = calculate_deception_likelihood(
            ais_consistency=0.9,
            behavioral_normalcy=0.9,
            sar_corroboration=0.9,
            factors={}
        )
        self.assertEqual(deception, 0.0)

    def test_anomalies_increase_deception(self):
        """Test that anomalies increase deception likelihood."""
        factors = {
            'ais_consistency': {'anomaly_count': 2}
        }
        deception = calculate_deception_likelihood(
            ais_consistency=0.7,
            behavioral_normalcy=0.8,
            sar_corroboration=0.8,
            factors=factors
        )
        self.assertGreater(deception, 0)


class TestConfidenceDatabase(unittest.TestCase):
    """Test confidence database operations."""

    def setUp(self):
        """Create fresh database for each test."""
        self.db = TestDatabase().initialize()
        self.vessel_id = self._insert_vessel()

    def tearDown(self):
        """Clean up."""
        self.db.cleanup()

    def _insert_vessel(self):
        """Insert a test vessel."""
        cursor = self.db.execute('''
            INSERT INTO vessels (name, mmsi, classification, threat_level)
            VALUES (?, ?, ?, ?)
        ''', ('TEST VESSEL', '123456789', 'monitoring', 'low'))
        self.db.commit()
        return cursor.lastrowid

    def test_save_and_retrieve_confidence(self):
        """Test saving and retrieving confidence score."""
        score = ConfidenceScore(
            vessel_id=self.vessel_id,
            ais_consistency=0.8,
            behavioral_normalcy=0.7,
            sar_corroboration=0.9,
            deception_likelihood=0.1,
            factors={'test': 'data'}
        )

        save_confidence_to_db(score, self.db.path)
        retrieved = get_vessel_confidence(self.vessel_id, self.db.path)

        self.assertIsNotNone(retrieved)
        self.assertAlmostEqual(retrieved['ais_consistency'], 0.8, places=2)
        self.assertAlmostEqual(retrieved['behavioral_normalcy'], 0.7, places=2)


if __name__ == '__main__':
    unittest.main()
