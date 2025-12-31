#!/usr/bin/env python3
"""
Vessel Intelligence Module

Produces standardized, defensible intelligence assessments.
Separates collection from assessment for clarity and auditability.

Output Format:
{
  "vessel_id": "MMSI/IMO",
  "assessment": "Likely gray-zone logistics",
  "confidence": 0.73,
  "indicators": [...],
  "deception_likelihood": 0.61,
  "confidence_breakdown": {...},
  "last_updated": "UTC"
}
"""

import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

# Import confidence scoring
from confidence import (
    calculate_ais_consistency,
    calculate_behavioral_normalcy,
    calculate_sar_corroboration,
    calculate_deception_likelihood,
    WEIGHT_AIS_CONSISTENCY,
    WEIGHT_BEHAVIORAL_NORMALCY,
    WEIGHT_SAR_CORROBORATION,
    DB_PATH
)

# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class AssessmentLevel(Enum):
    """Standardized assessment levels."""
    BENIGN = "benign"
    MONITORING = "monitoring"
    ANOMALOUS = "anomalous"
    SUSPICIOUS = "suspicious"
    LIKELY_GRAY_ZONE = "likely_gray_zone"
    CONFIRMED_THREAT = "confirmed_threat"


class IndicatorType(Enum):
    """Types of intelligence indicators."""
    BEHAVIORAL = "behavioral"
    TECHNICAL = "technical"
    GEOSPATIAL = "geospatial"
    OWNERSHIP = "ownership"
    HISTORICAL = "historical"
    EXTERNAL = "external"


class SignalQuality(Enum):
    """AIS source reliability grades."""
    HIGH = "high"          # Real-time verified sources
    MEDIUM = "medium"      # REST API sources with some delay
    LOW = "low"            # Manual/historical data
    DEGRADED = "degraded"  # Stale or incomplete data


# Indicator weights for scoring transparency
INDICATOR_WEIGHTS = {
    # Behavioral indicators
    "ais_gap_significant": 0.15,
    "ais_gap_minor": 0.05,
    "position_jump": 0.20,
    "speed_anomaly": 0.10,
    "course_anomaly": 0.10,
    "loitering_detected": 0.12,

    # Geospatial indicators
    "near_exclusion_zone": 0.15,
    "near_military_facility": 0.12,
    "unusual_route": 0.10,
    "dark_in_sensitive_area": 0.25,

    # Ownership indicators
    "flag_mismatch": 0.18,
    "ownership_opacity": 0.15,
    "shell_company": 0.20,
    "sanctioned_entity": 0.30,

    # Technical indicators
    "sar_no_ais": 0.22,
    "sar_position_mismatch": 0.15,
    "mmsi_spoofing": 0.25,
    "identity_change": 0.20,
}

# Data freshness penalties
FRESHNESS_PENALTIES = {
    "< 1 hour": 0.00,
    "1-6 hours": -0.02,
    "6-24 hours": -0.05,
    "> 24 hours": -0.10,
    "> 7 days": -0.20,
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Indicator:
    """Single intelligence indicator with weight and evidence."""
    type: str
    name: str
    description: str
    weight: float
    triggered: bool
    evidence: Optional[str] = None
    timestamp: Optional[str] = None

    def contribution(self) -> float:
        """Calculate this indicator's contribution to overall score."""
        return self.weight if self.triggered else 0.0


@dataclass
class ConfidenceBreakdown:
    """Analyst-visible confidence breakdown showing work."""

    # Component scores
    ais_consistency: float = 0.5
    behavioral_normalcy: float = 0.5
    sar_corroboration: float = 0.5

    # Weights (for transparency)
    ais_weight: float = WEIGHT_AIS_CONSISTENCY
    behavioral_weight: float = WEIGHT_BEHAVIORAL_NORMALCY
    sar_weight: float = WEIGHT_SAR_CORROBORATION

    # Penalties and adjustments
    signal_quality_penalty: float = 0.0
    data_freshness_penalty: float = 0.0
    source_reliability: str = "medium"

    # Indicator contributions
    indicator_contributions: List[Dict[str, Any]] = field(default_factory=list)

    # Raw calculation
    raw_score: float = 0.0
    adjusted_score: float = 0.0

    def calculate(self) -> float:
        """Calculate final confidence with all adjustments."""
        # Base weighted score
        self.raw_score = (
            self.ais_consistency * self.ais_weight +
            self.behavioral_normalcy * self.behavioral_weight +
            self.sar_corroboration * self.sar_weight
        )

        # Apply penalties
        self.adjusted_score = max(0.0, min(1.0,
            self.raw_score +
            self.signal_quality_penalty +
            self.data_freshness_penalty
        ))

        return self.adjusted_score

    def to_display(self) -> Dict[str, Any]:
        """Format for analyst display."""
        return {
            "confidence": round(self.adjusted_score * 100),
            "breakdown": [
                {
                    "component": "AIS Consistency",
                    "score": round(self.ais_consistency, 2),
                    "weight": self.ais_weight,
                    "contribution": f"+{self.ais_consistency * self.ais_weight:.2f}"
                },
                {
                    "component": "Behavioral Normalcy",
                    "score": round(self.behavioral_normalcy, 2),
                    "weight": self.behavioral_weight,
                    "contribution": f"+{self.behavioral_normalcy * self.behavioral_weight:.2f}"
                },
                {
                    "component": "SAR Corroboration",
                    "score": round(self.sar_corroboration, 2),
                    "weight": self.sar_weight,
                    "contribution": f"+{self.sar_corroboration * self.sar_weight:.2f}"
                }
            ],
            "adjustments": [
                {
                    "name": "Signal quality",
                    "source": self.source_reliability,
                    "adjustment": f"{self.signal_quality_penalty:+.2f}"
                },
                {
                    "name": "Data freshness",
                    "adjustment": f"{self.data_freshness_penalty:+.2f}"
                }
            ],
            "indicator_contributions": self.indicator_contributions
        }


@dataclass
class VesselIntelligence:
    """
    Standardized vessel intelligence output.

    This is the formal, defensible intelligence product.
    """
    # Identity
    vessel_id: int
    mmsi: Optional[str] = None
    imo: Optional[str] = None
    name: Optional[str] = None

    # Assessment
    assessment: str = "Insufficient data for assessment"
    assessment_level: str = AssessmentLevel.MONITORING.value
    confidence: float = 0.5
    deception_likelihood: float = 0.0

    # Indicators (explicit reasoning)
    indicators: List[Dict[str, Any]] = field(default_factory=list)

    # Confidence breakdown (show your work)
    confidence_breakdown: Optional[Dict[str, Any]] = None

    # Metadata
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    data_sources: List[str] = field(default_factory=list)
    analysis_version: str = "1.0"

    # Raw factors for debugging
    _factors: Dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "vessel_id": self.vessel_id,
            "mmsi": self.mmsi,
            "imo": self.imo,
            "name": self.name,
            "assessment": self.assessment,
            "assessment_level": self.assessment_level,
            "confidence": round(self.confidence, 2),
            "deception_likelihood": round(self.deception_likelihood, 2),
            "indicators": self.indicators,
            "confidence_breakdown": self.confidence_breakdown,
            "last_updated": self.last_updated,
            "data_sources": self.data_sources,
            "analysis_version": self.analysis_version
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# =============================================================================
# SIGNAL EXTRACTION
# =============================================================================

def extract_indicators(
    vessel_id: int,
    ais_factors: Dict[str, Any],
    behavioral_factors: Dict[str, Any],
    sar_factors: Dict[str, Any],
    vessel_data: Dict[str, Any]
) -> List[Indicator]:
    """
    Extract explicit indicators from raw scoring factors.

    Converts implicit signals into explicit, weighted indicators
    that analysts can review and verify.
    """
    indicators = []

    # AIS Gap Indicators
    gap_count = ais_factors.get('gap_count', 0)
    if gap_count > 0:
        gaps = ais_factors.get('gaps', [])
        max_gap = max((g.get('hours', 0) for g in gaps), default=0)

        if max_gap > 24:
            indicators.append(Indicator(
                type=IndicatorType.BEHAVIORAL.value,
                name="ais_gap_significant",
                description=f"Significant AIS gap detected ({max_gap:.0f} hours)",
                weight=INDICATOR_WEIGHTS["ais_gap_significant"],
                triggered=True,
                evidence=f"{gap_count} gaps totaling {ais_factors.get('total_gap_hours', 0):.1f} hours"
            ))
        elif max_gap > 6:
            indicators.append(Indicator(
                type=IndicatorType.BEHAVIORAL.value,
                name="ais_gap_minor",
                description=f"Minor AIS gap detected ({max_gap:.0f} hours)",
                weight=INDICATOR_WEIGHTS["ais_gap_minor"],
                triggered=True,
                evidence=f"{gap_count} gaps detected"
            ))

    # Position Jump Indicators (possible spoofing)
    anomalies = ais_factors.get('anomalies', [])
    position_jumps = [a for a in anomalies if a.get('type') == 'position_jump']
    if position_jumps:
        indicators.append(Indicator(
            type=IndicatorType.TECHNICAL.value,
            name="position_jump",
            description=f"Position jump detected ({len(position_jumps)} instances)",
            weight=INDICATOR_WEIGHTS["position_jump"],
            triggered=True,
            evidence=f"Max jump: {max(j.get('distance_km', 0) for j in position_jumps):.1f} km"
        ))

    # Speed Anomaly Indicators
    speed_changes = behavioral_factors.get('speed_changes', [])
    if speed_changes:
        max_change = max((s.get('change_knots', 0) for s in speed_changes), default=0)
        indicators.append(Indicator(
            type=IndicatorType.BEHAVIORAL.value,
            name="speed_anomaly",
            description=f"Unusual speed change detected ({max_change:.0f} knots)",
            weight=INDICATOR_WEIGHTS["speed_anomaly"],
            triggered=True,
            evidence=f"{len(speed_changes)} sudden speed changes"
        ))

    # Course Anomaly Indicators
    course_changes = behavioral_factors.get('course_changes', [])
    if course_changes:
        max_change = max((c.get('change_degrees', 0) for c in course_changes), default=0)
        indicators.append(Indicator(
            type=IndicatorType.BEHAVIORAL.value,
            name="course_anomaly",
            description=f"Unusual course change detected ({max_change:.0f}°)",
            weight=INDICATOR_WEIGHTS["course_anomaly"],
            triggered=True,
            evidence=f"{len(course_changes)} sudden course changes"
        ))

    # Loitering Indicator
    loitering = behavioral_factors.get('loitering_events', [])
    if loitering:
        indicators.append(Indicator(
            type=IndicatorType.BEHAVIORAL.value,
            name="loitering_detected",
            description="Loitering behavior detected",
            weight=INDICATOR_WEIGHTS["loitering_detected"],
            triggered=True,
            evidence=f"Low speed ratio: {loitering[0].get('ratio', 0):.0%}"
        ))

    # SAR Corroboration Indicators
    if sar_factors.get('corroboration') == 'positive':
        # SAR confirms AIS - this is good, reduces deception likelihood
        pass
    elif sar_factors.get('sar_matches', 0) == 0 and sar_factors.get('ais_positions', 0) > 0:
        # Has AIS but no SAR matches - could indicate position manipulation
        if sar_factors.get('total_sar_detections', 0) > 0:
            indicators.append(Indicator(
                type=IndicatorType.TECHNICAL.value,
                name="sar_position_mismatch",
                description="SAR detections in area but vessel not matched",
                weight=INDICATOR_WEIGHTS["sar_position_mismatch"],
                triggered=True,
                evidence=f"{sar_factors.get('total_sar_detections', 0)} SAR detections nearby"
            ))

    # Ownership/Flag Indicators (from vessel data)
    flag_state = vessel_data.get('flag_state', '')
    owner = vessel_data.get('owner', '')

    # Flag of convenience check
    foc_flags = ['PA', 'LR', 'MH', 'BS', 'MT', 'CY', 'VU', 'KN', 'AG']  # Panama, Liberia, Marshall Islands, etc.
    if flag_state and any(flag_state.upper().startswith(f) for f in foc_flags):
        # Check if ownership suggests different nationality
        if owner and not any(f.lower() in owner.lower() for f in [flag_state]):
            indicators.append(Indicator(
                type=IndicatorType.OWNERSHIP.value,
                name="flag_mismatch",
                description=f"Flag of convenience ({flag_state}) with non-matching ownership",
                weight=INDICATOR_WEIGHTS["flag_mismatch"],
                triggered=True,
                evidence=f"Flag: {flag_state}, Owner: {owner[:50]}..."
            ))

    return indicators


def calculate_signal_quality_penalty(vessel_id: int, db_path: str = DB_PATH) -> Tuple[float, str]:
    """
    Calculate signal quality penalty based on data sources.

    Returns (penalty, quality_level)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get recent positions and their sources
    cursor = conn.execute('''
        SELECT source, COUNT(*) as count
        FROM positions
        WHERE vessel_id = ?
        AND timestamp > datetime('now', '-7 days')
        GROUP BY source
    ''', (vessel_id,))

    sources = {row['source']: row['count'] for row in cursor}
    conn.close()

    total = sum(sources.values())
    if total == 0:
        return -0.10, SignalQuality.DEGRADED.value

    # Calculate weighted quality
    quality_weights = {
        'aisstream': 1.0,
        'ais': 0.9,
        'satellite': 0.8,
        'marinesia': 0.7,
        'manual': 0.5,
        'historical': 0.4
    }

    weighted_sum = sum(
        quality_weights.get(src, 0.5) * count
        for src, count in sources.items()
    )
    avg_quality = weighted_sum / total

    # Convert to penalty
    if avg_quality >= 0.9:
        return 0.0, SignalQuality.HIGH.value
    elif avg_quality >= 0.7:
        return -0.03, SignalQuality.MEDIUM.value
    elif avg_quality >= 0.5:
        return -0.07, SignalQuality.LOW.value
    else:
        return -0.10, SignalQuality.DEGRADED.value


def calculate_freshness_penalty(vessel_id: int, db_path: str = DB_PATH) -> Tuple[float, str]:
    """
    Calculate data freshness penalty.

    Returns (penalty, freshness_description)
    """
    conn = sqlite3.connect(db_path)

    cursor = conn.execute('''
        SELECT MAX(timestamp) as latest
        FROM positions
        WHERE vessel_id = ?
    ''', (vessel_id,))

    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        return -0.20, "> 7 days"

    try:
        latest = datetime.fromisoformat(row[0].replace('Z', '+00:00'))
        age = datetime.now(latest.tzinfo) - latest

        if age < timedelta(hours=1):
            return 0.0, "< 1 hour"
        elif age < timedelta(hours=6):
            return -0.02, "1-6 hours"
        elif age < timedelta(hours=24):
            return -0.05, "6-24 hours"
        elif age < timedelta(days=7):
            return -0.10, "> 24 hours"
        else:
            return -0.20, "> 7 days"
    except:
        return -0.10, "unknown"


def generate_assessment(
    confidence: float,
    deception_likelihood: float,
    indicators: List[Indicator],
    vessel_data: Dict[str, Any]
) -> Tuple[str, str]:
    """
    Generate natural language assessment and level from indicators.

    Returns (assessment_text, assessment_level)
    """
    triggered = [i for i in indicators if i.triggered]
    threat_level = vessel_data.get('threat_level', 'unknown')
    classification = vessel_data.get('classification', 'monitoring')

    # Count indicator types
    behavioral_count = len([i for i in triggered if i.type == IndicatorType.BEHAVIORAL.value])
    technical_count = len([i for i in triggered if i.type == IndicatorType.TECHNICAL.value])
    ownership_count = len([i for i in triggered if i.type == IndicatorType.OWNERSHIP.value])

    # Determine assessment level
    if classification == 'confirmed' or threat_level == 'critical':
        level = AssessmentLevel.CONFIRMED_THREAT
    elif deception_likelihood > 0.6 or (technical_count >= 2 and behavioral_count >= 2):
        level = AssessmentLevel.LIKELY_GRAY_ZONE
    elif deception_likelihood > 0.4 or len(triggered) >= 3:
        level = AssessmentLevel.SUSPICIOUS
    elif len(triggered) >= 1:
        level = AssessmentLevel.ANOMALOUS
    elif confidence > 0.7:
        level = AssessmentLevel.BENIGN
    else:
        level = AssessmentLevel.MONITORING

    # Generate assessment text
    if level == AssessmentLevel.CONFIRMED_THREAT:
        assessment = f"Confirmed threat vessel. {len(triggered)} active indicators."
    elif level == AssessmentLevel.LIKELY_GRAY_ZONE:
        primary_indicators = ", ".join([i.description for i in triggered[:3]])
        assessment = f"Likely gray-zone logistics. Key indicators: {primary_indicators}"
    elif level == AssessmentLevel.SUSPICIOUS:
        assessment = f"Suspicious activity pattern. {len(triggered)} indicators triggered including {triggered[0].description if triggered else 'behavioral anomalies'}."
    elif level == AssessmentLevel.ANOMALOUS:
        assessment = f"Anomalous behavior detected: {triggered[0].description if triggered else 'pattern deviation'}"
    elif level == AssessmentLevel.BENIGN:
        assessment = "Normal operating pattern. No significant indicators."
    else:
        assessment = "Insufficient data for definitive assessment. Continued monitoring recommended."

    return assessment, level.value


# =============================================================================
# MAIN INTELLIGENCE PRODUCER
# =============================================================================

def produce_vessel_intelligence(
    vessel_id: int,
    days: int = 30,
    db_path: str = DB_PATH
) -> VesselIntelligence:
    """
    Produce formal intelligence assessment for a vessel.

    This is the main entry point that:
    1. Collects raw signals
    2. Extracts explicit indicators
    3. Calculates confidence with visible breakdown
    4. Generates defensible assessment

    Args:
        vessel_id: Database vessel ID
        days: Analysis window in days
        db_path: Database path

    Returns:
        VesselIntelligence object ready for API/UI consumption
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get vessel data
    cursor = conn.execute('''
        SELECT * FROM vessels WHERE id = ?
    ''', (vessel_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return VesselIntelligence(
            vessel_id=vessel_id,
            assessment="Vessel not found",
            assessment_level="unknown"
        )

    vessel_data = dict(row)

    # Calculate component scores
    ais_score, ais_factors = calculate_ais_consistency(vessel_id, days, db_path)
    behavioral_score, behavioral_factors = calculate_behavioral_normalcy(vessel_id, days, db_path)
    sar_score, sar_factors = calculate_sar_corroboration(vessel_id, days, db_path)

    # Extract explicit indicators
    indicators = extract_indicators(
        vessel_id, ais_factors, behavioral_factors, sar_factors, vessel_data
    )

    # Calculate penalties
    signal_penalty, signal_quality = calculate_signal_quality_penalty(vessel_id, db_path)
    freshness_penalty, freshness_desc = calculate_freshness_penalty(vessel_id, db_path)

    # Build confidence breakdown
    breakdown = ConfidenceBreakdown(
        ais_consistency=ais_score,
        behavioral_normalcy=behavioral_score,
        sar_corroboration=sar_score,
        signal_quality_penalty=signal_penalty,
        data_freshness_penalty=freshness_penalty,
        source_reliability=signal_quality,
        indicator_contributions=[
            {
                "indicator": i.name,
                "weight": f"+{i.weight:.2f}" if i.triggered else "0.00",
                "triggered": i.triggered,
                "description": i.description
            }
            for i in indicators
        ]
    )
    confidence = breakdown.calculate()

    # Calculate deception likelihood
    all_factors = {
        'ais_consistency': ais_factors,
        'behavioral_normalcy': behavioral_factors,
        'sar_corroboration': sar_factors
    }
    deception = calculate_deception_likelihood(
        ais_score, behavioral_score, sar_score, all_factors
    )

    # Generate assessment
    assessment_text, assessment_level = generate_assessment(
        confidence, deception, indicators, vessel_data
    )

    # Determine data sources
    sources = []
    if ais_factors.get('position_count', 0) > 0:
        sources.append("AIS")
    if sar_factors.get('sar_matches', 0) > 0:
        sources.append("SAR")
    if vessel_data.get('intel_notes'):
        sources.append("OSINT")

    # Build final intelligence object
    intel = VesselIntelligence(
        vessel_id=vessel_id,
        mmsi=vessel_data.get('mmsi'),
        imo=vessel_data.get('imo'),
        name=vessel_data.get('name'),
        assessment=assessment_text,
        assessment_level=assessment_level,
        confidence=confidence,
        deception_likelihood=deception,
        indicators=[asdict(i) for i in indicators if i.triggered],
        confidence_breakdown=breakdown.to_display(),
        data_sources=sources,
        _factors=all_factors
    )

    return intel


def get_intel_summary(vessel_id: int, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Get quick intelligence summary for UI display.

    Returns a simplified view suitable for dashboards.
    """
    intel = produce_vessel_intelligence(vessel_id, db_path=db_path)

    return {
        "vessel_id": intel.vessel_id,
        "name": intel.name,
        "assessment": intel.assessment,
        "confidence": f"{intel.confidence:.0%}",
        "deception_risk": f"{intel.deception_likelihood:.0%}",
        "indicator_count": len(intel.indicators),
        "level": intel.assessment_level
    }


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Produce vessel intelligence assessment')
    parser.add_argument('vessel_id', type=int, help='Vessel ID to analyze')
    parser.add_argument('--days', type=int, default=30, help='Analysis window (days)')
    parser.add_argument('--db', default=DB_PATH, help='Database path')
    parser.add_argument('--json', action='store_true', help='Output as JSON')

    args = parser.parse_args()

    intel = produce_vessel_intelligence(args.vessel_id, args.days, args.db)

    if args.json:
        print(intel.to_json())
    else:
        print("\n" + "=" * 60)
        print(f"VESSEL INTELLIGENCE: {intel.name or f'ID {intel.vessel_id}'}")
        print("=" * 60)
        print(f"\nMMSI: {intel.mmsi or 'Unknown'}")
        print(f"IMO: {intel.imo or 'Unknown'}")
        print(f"\nASSESSMENT: {intel.assessment}")
        print(f"LEVEL: {intel.assessment_level.upper()}")
        print(f"\nCONFIDENCE: {intel.confidence:.0%}")
        print(f"DECEPTION LIKELIHOOD: {intel.deception_likelihood:.0%}")

        if intel.indicators:
            print(f"\nINDICATORS ({len(intel.indicators)}):")
            for ind in intel.indicators:
                print(f"  • {ind['description']}")
                if ind.get('evidence'):
                    print(f"    Evidence: {ind['evidence']}")

        if intel.confidence_breakdown:
            print("\nCONFIDENCE BREAKDOWN:")
            bd = intel.confidence_breakdown
            for comp in bd.get('breakdown', []):
                print(f"  {comp['component']}: {comp['score']:.2f} (weight: {comp['weight']}) → {comp['contribution']}")
            for adj in bd.get('adjustments', []):
                print(f"  {adj['name']}: {adj['adjustment']}")

        print("\n" + "=" * 60)
