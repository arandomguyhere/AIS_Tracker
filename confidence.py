#!/usr/bin/env python3
"""
Vessel Confidence Scoring Module

Provides quantitative trust metrics for vessel intelligence:
- AIS consistency score (gap analysis, transmission regularity)
- Behavioral normalcy score (pattern-of-life deviation)
- SAR corroboration score (independent verification)
- Overall confidence score

Based on MISP-style confidence taxonomy without the full MISP dependency.

No external dependencies - uses only Python standard library.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from utils import haversine

# Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'arsenal_tracker.db')

# Scoring weights (sum to 1.0)
WEIGHT_AIS_CONSISTENCY = 0.35
WEIGHT_BEHAVIORAL_NORMALCY = 0.35
WEIGHT_SAR_CORROBORATION = 0.30

# Thresholds
AIS_GAP_THRESHOLD_HOURS = 6  # Gaps longer than this reduce score
AIS_EXPECTED_INTERVAL_MINUTES = 10  # Expected AIS transmission interval
SPEED_CHANGE_THRESHOLD_KNOTS = 15  # Sudden speed changes
COURSE_CHANGE_THRESHOLD_DEGREES = 90  # Sudden course changes


class ConfidenceScore:
    """Represents a vessel's confidence metrics."""

    def __init__(
        self,
        vessel_id: int,
        ais_consistency: float = 0.5,
        behavioral_normalcy: float = 0.5,
        sar_corroboration: float = 0.5,
        deception_likelihood: float = 0.0,
        last_calculated: Optional[str] = None,
        factors: Optional[Dict[str, Any]] = None
    ):
        self.vessel_id = vessel_id
        self.ais_consistency = self._clamp(ais_consistency)
        self.behavioral_normalcy = self._clamp(behavioral_normalcy)
        self.sar_corroboration = self._clamp(sar_corroboration)
        self.deception_likelihood = self._clamp(deception_likelihood)
        self.last_calculated = last_calculated or datetime.utcnow().isoformat()
        self.factors = factors or {}

    @staticmethod
    def _clamp(value: float) -> float:
        """Clamp value between 0 and 1."""
        return max(0.0, min(1.0, value))

    @property
    def overall_confidence(self) -> float:
        """Calculate weighted overall confidence score."""
        return self._clamp(
            self.ais_consistency * WEIGHT_AIS_CONSISTENCY +
            self.behavioral_normalcy * WEIGHT_BEHAVIORAL_NORMALCY +
            self.sar_corroboration * WEIGHT_SAR_CORROBORATION
        )

    @property
    def confidence_level(self) -> str:
        """Convert numeric score to categorical level."""
        score = self.overall_confidence
        if score >= 0.8:
            return 'high'
        elif score >= 0.6:
            return 'medium'
        elif score >= 0.4:
            return 'low'
        else:
            return 'very_low'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'vessel_id': self.vessel_id,
            'ais_consistency': round(self.ais_consistency, 3),
            'behavioral_normalcy': round(self.behavioral_normalcy, 3),
            'sar_corroboration': round(self.sar_corroboration, 3),
            'overall_confidence': round(self.overall_confidence, 3),
            'confidence_level': self.confidence_level,
            'deception_likelihood': round(self.deception_likelihood, 3),
            'last_calculated': self.last_calculated,
            'factors': self.factors
        }


def calculate_ais_consistency(
    vessel_id: int,
    days: int = 30,
    db_path: str = DB_PATH
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate AIS consistency score based on transmission patterns.

    Factors:
    - Gap frequency and duration
    - Transmission regularity
    - Position jump detection (possible spoofing)

    Returns:
        Tuple of (score, factors_dict)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    # Get position history
    cursor = conn.execute('''
        SELECT latitude, longitude, speed_knots, timestamp
        FROM positions
        WHERE vessel_id = ? AND timestamp > ?
        ORDER BY timestamp ASC
    ''', (vessel_id, since))

    positions = list(cursor)
    conn.close()

    if len(positions) < 2:
        return 0.5, {'reason': 'insufficient_data', 'position_count': len(positions)}

    factors = {
        'position_count': len(positions),
        'analysis_days': days,
        'gaps': [],
        'anomalies': []
    }

    # Analyze gaps
    total_gap_hours = 0
    gap_count = 0

    for i in range(1, len(positions)):
        try:
            t1 = datetime.fromisoformat(positions[i-1]['timestamp'].replace('Z', '+00:00'))
            t2 = datetime.fromisoformat(positions[i]['timestamp'].replace('Z', '+00:00'))
            gap_hours = (t2 - t1).total_seconds() / 3600

            if gap_hours > AIS_GAP_THRESHOLD_HOURS:
                gap_count += 1
                total_gap_hours += gap_hours
                factors['gaps'].append({
                    'start': positions[i-1]['timestamp'],
                    'end': positions[i]['timestamp'],
                    'hours': round(gap_hours, 1)
                })

            # Check for position jumps (possible spoofing)
            lat1, lon1 = positions[i-1]['latitude'], positions[i-1]['longitude']
            lat2, lon2 = positions[i]['latitude'], positions[i]['longitude']

            if lat1 and lon1 and lat2 and lon2:
                distance = haversine(lat1, lon1, lat2, lon2)
                speed = positions[i-1]['speed_knots'] or 0

                # Max reasonable distance based on speed and time
                max_distance = speed * 1.852 * gap_hours * 1.5  # 50% margin

                if distance > max_distance and distance > 50:  # Ignore small differences
                    factors['anomalies'].append({
                        'type': 'position_jump',
                        'timestamp': positions[i]['timestamp'],
                        'distance_km': round(distance, 1),
                        'expected_max_km': round(max_distance, 1)
                    })

        except (ValueError, TypeError):
            continue

    # Calculate score
    # Start at 1.0, reduce for gaps and anomalies
    score = 1.0

    # Reduce for gaps (each significant gap reduces by 0.1, max reduction 0.4)
    gap_penalty = min(0.4, gap_count * 0.1)
    score -= gap_penalty

    # Reduce for anomalies (each anomaly reduces by 0.15, max reduction 0.3)
    anomaly_penalty = min(0.3, len(factors['anomalies']) * 0.15)
    score -= anomaly_penalty

    factors['gap_count'] = gap_count
    factors['total_gap_hours'] = round(total_gap_hours, 1)
    factors['anomaly_count'] = len(factors['anomalies'])
    factors['gap_penalty'] = round(gap_penalty, 2)
    factors['anomaly_penalty'] = round(anomaly_penalty, 2)

    return max(0.0, min(1.0, score)), factors


def calculate_behavioral_normalcy(
    vessel_id: int,
    days: int = 30,
    db_path: str = DB_PATH
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate behavioral normalcy score based on pattern-of-life deviation.

    Factors:
    - Sudden speed changes
    - Unexpected course changes
    - Unusual operating areas
    - Loitering behavior

    Returns:
        Tuple of (score, factors_dict)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    cursor = conn.execute('''
        SELECT latitude, longitude, speed_knots, course, heading, timestamp
        FROM positions
        WHERE vessel_id = ? AND timestamp > ?
        ORDER BY timestamp ASC
    ''', (vessel_id, since))

    positions = list(cursor)
    conn.close()

    if len(positions) < 3:
        return 0.5, {'reason': 'insufficient_data', 'position_count': len(positions)}

    factors = {
        'position_count': len(positions),
        'analysis_days': days,
        'speed_changes': [],
        'course_changes': [],
        'loitering_events': []
    }

    # Analyze behavior patterns
    speeds = []
    for i in range(1, len(positions)):
        prev = positions[i-1]
        curr = positions[i]

        # Speed change analysis
        if prev['speed_knots'] is not None and curr['speed_knots'] is not None:
            speed_change = abs(curr['speed_knots'] - prev['speed_knots'])
            speeds.append(curr['speed_knots'])

            if speed_change > SPEED_CHANGE_THRESHOLD_KNOTS:
                factors['speed_changes'].append({
                    'timestamp': curr['timestamp'],
                    'change_knots': round(speed_change, 1)
                })

        # Course change analysis
        if prev['course'] is not None and curr['course'] is not None:
            course_change = abs(curr['course'] - prev['course'])
            if course_change > 180:
                course_change = 360 - course_change

            if course_change > COURSE_CHANGE_THRESHOLD_DEGREES:
                factors['course_changes'].append({
                    'timestamp': curr['timestamp'],
                    'change_degrees': round(course_change, 1)
                })

    # Detect loitering (low speed in same area for extended period)
    if speeds:
        avg_speed = sum(speeds) / len(speeds)
        low_speed_positions = sum(1 for s in speeds if s < 2)
        loiter_ratio = low_speed_positions / len(speeds)

        if loiter_ratio > 0.5:
            factors['loitering_events'].append({
                'ratio': round(loiter_ratio, 2),
                'average_speed': round(avg_speed, 1)
            })

    # Calculate score
    score = 1.0

    # Reduce for unusual speed changes (0.1 per event, max 0.3)
    speed_penalty = min(0.3, len(factors['speed_changes']) * 0.1)
    score -= speed_penalty

    # Reduce for unusual course changes (0.1 per event, max 0.3)
    course_penalty = min(0.3, len(factors['course_changes']) * 0.1)
    score -= course_penalty

    # Reduce for loitering (0.2 if significant)
    loiter_penalty = 0.2 if factors['loitering_events'] else 0.0
    score -= loiter_penalty

    factors['speed_change_count'] = len(factors['speed_changes'])
    factors['course_change_count'] = len(factors['course_changes'])
    factors['speed_penalty'] = round(speed_penalty, 2)
    factors['course_penalty'] = round(course_penalty, 2)
    factors['loiter_penalty'] = round(loiter_penalty, 2)

    return max(0.0, min(1.0, score)), factors


def calculate_sar_corroboration(
    vessel_id: int,
    days: int = 30,
    db_path: str = DB_PATH
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate SAR corroboration score based on independent SAR verification.

    Factors:
    - SAR detections matched to this vessel
    - SAR detections in area but not matched (dark activity)
    - Consistency between AIS and SAR positions

    Returns:
        Tuple of (score, factors_dict)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    # Check if SAR detections table exists
    cursor = conn.execute('''
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='sar_detections'
    ''')
    if not cursor.fetchone():
        conn.close()
        return 0.5, {'reason': 'no_sar_data', 'sar_table_exists': False}

    # Get SAR matches for this vessel
    cursor = conn.execute('''
        SELECT COUNT(*) as matched_count
        FROM sar_detections
        WHERE matched_vessel_id = ? AND timestamp > ?
    ''', (vessel_id, since))
    matched_count = cursor.fetchone()['matched_count']

    # Get total SAR detections in the time period
    cursor = conn.execute('''
        SELECT COUNT(*) as total_count
        FROM sar_detections
        WHERE timestamp > ?
    ''', (since,))
    total_count = cursor.fetchone()['total_count']

    # Get vessel position count for comparison
    cursor = conn.execute('''
        SELECT COUNT(*) as position_count
        FROM positions
        WHERE vessel_id = ? AND timestamp > ?
    ''', (vessel_id, since))
    position_count = cursor.fetchone()['position_count']

    conn.close()

    factors = {
        'analysis_days': days,
        'sar_matches': matched_count,
        'total_sar_detections': total_count,
        'ais_positions': position_count
    }

    # Calculate score
    if total_count == 0:
        # No SAR data available - neutral score
        return 0.5, {'reason': 'no_sar_coverage', **factors}

    if matched_count > 0:
        # SAR corroborates AIS - high confidence
        # More matches = higher score
        score = min(1.0, 0.6 + (matched_count * 0.1))
        factors['corroboration'] = 'positive'
    elif position_count > 0:
        # Has AIS but no SAR matches - could be normal or concerning
        # Depends on SAR coverage
        score = 0.5
        factors['corroboration'] = 'neutral'
    else:
        # No AIS positions to verify
        score = 0.3
        factors['corroboration'] = 'insufficient_data'

    return score, factors


def calculate_deception_likelihood(
    ais_consistency: float,
    behavioral_normalcy: float,
    sar_corroboration: float,
    factors: Dict[str, Any]
) -> float:
    """
    Calculate deception likelihood based on combined factors.

    High deception likelihood when:
    - AIS gaps coincide with interesting locations
    - Position jumps detected
    - Behavioral anomalies present
    - SAR doesn't corroborate AIS

    Returns:
        Deception likelihood score (0.0 to 1.0)
    """
    deception = 0.0

    # Low AIS consistency increases deception likelihood
    if ais_consistency < 0.5:
        deception += 0.3

    # Position anomalies strongly suggest deception
    ais_factors = factors.get('ais_consistency', {})
    if ais_factors.get('anomaly_count', 0) > 0:
        deception += 0.3

    # Unusual behavior patterns
    if behavioral_normalcy < 0.5:
        deception += 0.2

    # SAR doesn't corroborate
    sar_factors = factors.get('sar_corroboration', {})
    if sar_factors.get('corroboration') == 'negative':
        deception += 0.2

    return min(1.0, deception)


def calculate_vessel_confidence(
    vessel_id: int,
    days: int = 30,
    db_path: str = DB_PATH
) -> ConfidenceScore:
    """
    Calculate complete confidence score for a vessel.

    Args:
        vessel_id: Vessel ID
        days: Number of days to analyze
        db_path: Path to database

    Returns:
        ConfidenceScore object with all metrics
    """
    all_factors = {}

    # Calculate individual scores
    ais_score, ais_factors = calculate_ais_consistency(vessel_id, days, db_path)
    all_factors['ais_consistency'] = ais_factors

    behavioral_score, behavioral_factors = calculate_behavioral_normalcy(vessel_id, days, db_path)
    all_factors['behavioral_normalcy'] = behavioral_factors

    sar_score, sar_factors = calculate_sar_corroboration(vessel_id, days, db_path)
    all_factors['sar_corroboration'] = sar_factors

    # Calculate deception likelihood
    deception = calculate_deception_likelihood(
        ais_score, behavioral_score, sar_score, all_factors
    )

    return ConfidenceScore(
        vessel_id=vessel_id,
        ais_consistency=ais_score,
        behavioral_normalcy=behavioral_score,
        sar_corroboration=sar_score,
        deception_likelihood=deception,
        factors=all_factors
    )


def save_confidence_to_db(
    score: ConfidenceScore,
    db_path: str = DB_PATH
) -> bool:
    """
    Save confidence score to vessel record.

    Args:
        score: ConfidenceScore object
        db_path: Path to database

    Returns:
        True if saved successfully
    """
    conn = sqlite3.connect(db_path)

    # Check if confidence columns exist, add if not
    cursor = conn.execute("PRAGMA table_info(vessels)")
    columns = [row[1] for row in cursor]

    if 'confidence_score' not in columns:
        conn.execute('ALTER TABLE vessels ADD COLUMN confidence_score REAL')
        conn.execute('ALTER TABLE vessels ADD COLUMN ais_consistency REAL')
        conn.execute('ALTER TABLE vessels ADD COLUMN behavioral_normalcy REAL')
        conn.execute('ALTER TABLE vessels ADD COLUMN sar_corroboration REAL')
        conn.execute('ALTER TABLE vessels ADD COLUMN deception_likelihood REAL')
        conn.execute('ALTER TABLE vessels ADD COLUMN confidence_factors TEXT')
        conn.execute('ALTER TABLE vessels ADD COLUMN confidence_calculated TEXT')

    conn.execute('''
        UPDATE vessels SET
            confidence_score = ?,
            ais_consistency = ?,
            behavioral_normalcy = ?,
            sar_corroboration = ?,
            deception_likelihood = ?,
            confidence_factors = ?,
            confidence_calculated = ?
        WHERE id = ?
    ''', (
        score.overall_confidence,
        score.ais_consistency,
        score.behavioral_normalcy,
        score.sar_corroboration,
        score.deception_likelihood,
        json.dumps(score.factors),
        score.last_calculated,
        score.vessel_id
    ))

    conn.commit()
    conn.close()
    return True


def get_vessel_confidence(
    vessel_id: int,
    db_path: str = DB_PATH
) -> Optional[Dict[str, Any]]:
    """
    Get stored confidence score for a vessel.

    Args:
        vessel_id: Vessel ID
        db_path: Path to database

    Returns:
        Confidence data dict or None
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute('''
        SELECT confidence_score, ais_consistency, behavioral_normalcy,
               sar_corroboration, deception_likelihood, confidence_factors,
               confidence_calculated
        FROM vessels WHERE id = ?
    ''', (vessel_id,))

    row = cursor.fetchone()
    conn.close()

    if not row or row['confidence_score'] is None:
        return None

    return {
        'vessel_id': vessel_id,
        'overall_confidence': row['confidence_score'],
        'ais_consistency': row['ais_consistency'],
        'behavioral_normalcy': row['behavioral_normalcy'],
        'sar_corroboration': row['sar_corroboration'],
        'deception_likelihood': row['deception_likelihood'],
        'factors': json.loads(row['confidence_factors']) if row['confidence_factors'] else {},
        'last_calculated': row['confidence_calculated']
    }


# CLI interface
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Calculate vessel confidence scores')
    parser.add_argument('vessel_id', type=int, help='Vessel ID to analyze')
    parser.add_argument('--days', type=int, default=30, help='Days to analyze')
    parser.add_argument('--save', action='store_true', help='Save to database')
    parser.add_argument('--db', default=DB_PATH, help='Database path')

    args = parser.parse_args()

    score = calculate_vessel_confidence(args.vessel_id, args.days, args.db)

    print("\n" + "=" * 50)
    print(f"Confidence Score: Vessel {args.vessel_id}")
    print("=" * 50)
    print(f"  Overall Confidence: {score.overall_confidence:.2f} ({score.confidence_level})")
    print(f"  AIS Consistency:    {score.ais_consistency:.2f}")
    print(f"  Behavioral Normalcy:{score.behavioral_normalcy:.2f}")
    print(f"  SAR Corroboration:  {score.sar_corroboration:.2f}")
    print(f"  Deception Likelihood:{score.deception_likelihood:.2f}")
    print("=" * 50)

    if args.save:
        save_confidence_to_db(score, args.db)
        print("Saved to database.")
