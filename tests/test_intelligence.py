#!/usr/bin/env python3
"""Tests for the intelligence module."""

import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.base import BaseTestCase


class TestVesselIntelligence(BaseTestCase):
    """Test VesselIntelligence data class."""

    def test_intelligence_creation(self):
        """Test creating a VesselIntelligence object."""
        from intelligence import VesselIntelligence

        intel = VesselIntelligence(
            vessel_id=1,
            mmsi="123456789",
            name="Test Vessel",
            assessment="Normal operating pattern",
            confidence=0.75
        )

        self.assertEqual(intel.vessel_id, 1)
        self.assertEqual(intel.mmsi, "123456789")
        self.assertEqual(intel.confidence, 0.75)

    def test_intelligence_to_dict(self):
        """Test serialization to dictionary."""
        from intelligence import VesselIntelligence

        intel = VesselIntelligence(
            vessel_id=1,
            assessment="Test assessment",
            confidence=0.8,
            deception_likelihood=0.2
        )

        d = intel.to_dict()
        self.assertEqual(d['vessel_id'], 1)
        self.assertEqual(d['confidence'], 0.8)
        self.assertEqual(d['deception_likelihood'], 0.2)
        self.assertIn('last_updated', d)

    def test_intelligence_to_json(self):
        """Test JSON serialization."""
        from intelligence import VesselIntelligence
        import json

        intel = VesselIntelligence(
            vessel_id=1,
            assessment="Test"
        )

        json_str = intel.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed['vessel_id'], 1)


class TestConfidenceBreakdown(BaseTestCase):
    """Test ConfidenceBreakdown class."""

    def test_breakdown_calculation(self):
        """Test confidence breakdown calculation."""
        from intelligence import ConfidenceBreakdown

        bd = ConfidenceBreakdown(
            ais_consistency=0.8,
            behavioral_normalcy=0.7,
            sar_corroboration=0.6
        )

        score = bd.calculate()
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 1)

    def test_penalties_applied(self):
        """Test that penalties reduce score."""
        from intelligence import ConfidenceBreakdown

        bd_no_penalty = ConfidenceBreakdown(
            ais_consistency=0.8,
            behavioral_normalcy=0.8,
            sar_corroboration=0.8
        )
        score_no_penalty = bd_no_penalty.calculate()

        bd_with_penalty = ConfidenceBreakdown(
            ais_consistency=0.8,
            behavioral_normalcy=0.8,
            sar_corroboration=0.8,
            signal_quality_penalty=-0.1,
            data_freshness_penalty=-0.05
        )
        score_with_penalty = bd_with_penalty.calculate()

        self.assertLess(score_with_penalty, score_no_penalty)

    def test_display_format(self):
        """Test analyst display format."""
        from intelligence import ConfidenceBreakdown

        bd = ConfidenceBreakdown(
            ais_consistency=0.7,
            behavioral_normalcy=0.6,
            sar_corroboration=0.5,
            source_reliability="medium"
        )
        bd.calculate()

        display = bd.to_display()
        self.assertIn('confidence', display)
        self.assertIn('breakdown', display)
        self.assertIn('adjustments', display)


class TestIndicatorExtraction(BaseTestCase):
    """Test indicator extraction logic."""

    def test_extract_gap_indicator(self):
        """Test AIS gap indicator extraction."""
        from intelligence import extract_indicators, Indicator

        ais_factors = {
            'gap_count': 2,
            'gaps': [{'hours': 36}, {'hours': 12}],
            'total_gap_hours': 48,
            'anomalies': []
        }

        indicators = extract_indicators(
            vessel_id=1,
            ais_factors=ais_factors,
            behavioral_factors={},
            sar_factors={},
            vessel_data={}
        )

        # Should have at least one gap indicator
        gap_indicators = [i for i in indicators if 'gap' in i.name]
        self.assertGreater(len(gap_indicators), 0)

    def test_extract_speed_anomaly(self):
        """Test speed anomaly indicator."""
        from intelligence import extract_indicators

        behavioral_factors = {
            'speed_changes': [{'change_knots': 20}],
            'course_changes': [],
            'loitering_events': []
        }

        indicators = extract_indicators(
            vessel_id=1,
            ais_factors={'gaps': [], 'anomalies': []},
            behavioral_factors=behavioral_factors,
            sar_factors={},
            vessel_data={}
        )

        speed_indicators = [i for i in indicators if 'speed' in i.name]
        self.assertGreater(len(speed_indicators), 0)


class TestAssessmentGeneration(BaseTestCase):
    """Test assessment generation."""

    def test_generate_benign_assessment(self):
        """Test generating benign assessment."""
        from intelligence import generate_assessment, Indicator

        assessment, level = generate_assessment(
            confidence=0.85,
            deception_likelihood=0.1,
            indicators=[],
            vessel_data={'classification': 'monitoring', 'threat_level': 'unknown'}
        )

        self.assertEqual(level, 'benign')
        self.assertIn('Normal', assessment)

    def test_generate_suspicious_assessment(self):
        """Test generating suspicious assessment."""
        from intelligence import generate_assessment, Indicator

        indicators = [
            Indicator(
                type='behavioral',
                name='test1',
                description='Test indicator 1',
                weight=0.1,
                triggered=True
            ),
            Indicator(
                type='technical',
                name='test2',
                description='Test indicator 2',
                weight=0.1,
                triggered=True
            ),
            Indicator(
                type='ownership',
                name='test3',
                description='Test indicator 3',
                weight=0.1,
                triggered=True
            ),
        ]

        assessment, level = generate_assessment(
            confidence=0.5,
            deception_likelihood=0.45,
            indicators=indicators,
            vessel_data={'classification': 'monitoring', 'threat_level': 'unknown'}
        )

        self.assertEqual(level, 'suspicious')


class TestIntelligenceProduction(BaseTestCase):
    """Test full intelligence production."""

    def test_produce_intelligence_missing_vessel(self):
        """Test producing intelligence for non-existent vessel."""
        from intelligence import produce_vessel_intelligence

        intel = produce_vessel_intelligence(999999, db_path=self.db.path)

        self.assertEqual(intel.vessel_id, 999999)
        self.assertIn('not found', intel.assessment.lower())


if __name__ == '__main__':
    unittest.main()
