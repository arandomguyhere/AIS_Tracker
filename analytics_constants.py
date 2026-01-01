"""
Centralized Analytics Constants

All threshold values, scoring weights, and detection parameters used across
analytics modules. Import from here to ensure consistency.

Modules using these constants:
- behavior.py
- dark_fleet.py
- gfw_integration.py
- venezuela.py
- laden_status.py
"""

# =============================================================================
# Risk Level Thresholds (score 0-100)
# =============================================================================
# All modules must use these consistent breakpoints

RISK_LEVEL_CRITICAL = 70  # 70-100: High probability of illicit activity
RISK_LEVEL_HIGH = 50      # 50-69: Multiple concerning indicators
RISK_LEVEL_MEDIUM = 30    # 30-49: Some concerning indicators
RISK_LEVEL_LOW = 15       # 15-29: Minor risk factors
RISK_LEVEL_MINIMAL = 0    # 0-14: No significant indicators


def get_risk_level(score: int) -> str:
    """
    Convert numeric score to standardized risk level.

    Use this function in all modules to ensure consistent classification.
    """
    if score >= RISK_LEVEL_CRITICAL:
        return 'critical'
    elif score >= RISK_LEVEL_HIGH:
        return 'high'
    elif score >= RISK_LEVEL_MEDIUM:
        return 'medium'
    elif score >= RISK_LEVEL_LOW:
        return 'low'
    else:
        return 'minimal'


# =============================================================================
# AIS Gap Detection Thresholds
# =============================================================================

# Minimum gap to consider significant (minutes)
AIS_GAP_MIN_MINUTES = 60          # Gaps shorter than this are normal

# Reporting thresholds (minutes)
AIS_GAP_REPORT_THRESHOLD = 60     # Report gaps >= 1 hour
AIS_GAP_SUSPICIOUS_HOURS = 12     # Gaps > 12 hours are suspicious
AIS_GAP_CRITICAL_HOURS = 48       # Gaps > 48 hours are highly suspicious

# Scoring (hours-based, standardized)
AIS_GAP_SCORE_CRITICAL = 20       # Points for > 48 hours total gap time
AIS_GAP_SCORE_HIGH = 15           # Points for > 12 hours total gap time
AIS_GAP_SCORE_MEDIUM = 10         # Points for any gaps detected


# =============================================================================
# Encounter/STS Detection Thresholds
# =============================================================================

# Distance thresholds
ENCOUNTER_MAX_DISTANCE_KM = 0.5   # 500m - vessels must be within this distance
STS_MAX_DISTANCE_KM = 0.5         # Same as encounter (500m)

# Speed thresholds (knots)
ENCOUNTER_MAX_SPEED_KNOTS = 2.0   # Both vessels must be < 2 knots
STS_MAX_SPEED_KNOTS = 3.0         # Slightly higher for STS (allows drift)
# Note: STS uses 3.0 based on arXiv 2024 research - vessels have small drift during oil transfer

# Duration thresholds (hours)
ENCOUNTER_MIN_DURATION_HOURS = 2.0    # Minimum time for encounter
STS_MIN_DURATION_HOURS = 4.0          # STS needs longer duration
STS_MAX_DURATION_HOURS = 48.0         # Maximum realistic STS duration

# Scoring
ENCOUNTER_SCORE_MULTIPLE = 25     # Points for > 3 encounters
ENCOUNTER_SCORE_SINGLE = 10       # Points for 1-3 encounters
STS_SCORE_MULTIPLE = 15           # Points for >= 2 STS transfers
STS_SCORE_SINGLE = 10             # Points for 1 STS transfer


# =============================================================================
# Loitering Detection Thresholds
# =============================================================================

LOITERING_MAX_SPEED_KNOTS = 2.0       # Speed threshold for loitering
LOITERING_MIN_DURATION_HOURS = 3.0    # Minimum duration to flag
LOITERING_MIN_DISTANCE_FROM_PORT_NM = 20.0  # Must be away from ports

# Scoring (hours-based, standardized)
LOITERING_SCORE_EXTENDED = 20     # Points for > 72 hours total
LOITERING_SCORE_MODERATE = 10     # Points for > 24 hours total


# =============================================================================
# Spoofing Detection Thresholds
# =============================================================================

# Position discrepancy thresholds (km)
SPOOFING_CRITICAL_DISCREPANCY_KM = 100    # Almost certainly spoofing
SPOOFING_HIGH_DISCREPANCY_KM = 50         # Likely spoofing
SPOOFING_MEDIUM_DISCREPANCY_KM = 20       # Possible spoofing

# Speed-based spoofing (knots)
SPOOFING_MAX_REALISTIC_SPEED_KNOTS = 50   # Max realistic vessel speed
SPOOFING_SPEED_BUFFER = 1.5               # Allow 50% buffer for GPS errors

# Scoring
SPOOFING_SCORE_CRITICAL = 30      # Points for > 100km discrepancy
SPOOFING_SCORE_HIGH = 15          # Points for > 20km discrepancy


# =============================================================================
# Vessel Age Thresholds
# =============================================================================

VESSEL_AGE_CRITICAL = 25          # 25+ years = highest risk (shadow fleet uses old tankers)
VESSEL_AGE_HIGH = 20              # 20-24 years = high risk
VESSEL_AGE_MEDIUM = 15            # 15-19 years = moderate risk

# Scoring
VESSEL_AGE_SCORE_CRITICAL = 20    # Points for >= 25 years
VESSEL_AGE_SCORE_HIGH = 15        # Points for >= 20 years
VESSEL_AGE_SCORE_MEDIUM = 10      # Points for >= 15 years


# =============================================================================
# Zone Detection Radii (km)
# =============================================================================

DETECTION_RADIUS_TERMINAL = 10.0      # Oil/cargo terminals
DETECTION_RADIUS_STS_ZONE = 25.0      # STS transfer zones (standardized)
DETECTION_RADIUS_ANCHORAGE = 15.0     # Anchorage areas
DETECTION_RADIUS_REFINERY = 15.0      # Refinery facilities
DETECTION_RADIUS_SPOOFING_TARGET = 50.0  # Spoofing destination checks


# =============================================================================
# Regional Presence Scoring
# =============================================================================

REGIONAL_PRESENCE_LOOKBACK = 200      # Number of positions to analyze
REGIONAL_PRESENCE_MIN_POSITIONS = 20  # Min positions to trigger scoring
REGIONAL_PRESENCE_MAX_POINTS = 15     # Max points per region


# =============================================================================
# Flag Risk Scoring
# =============================================================================

# See behavior.py FLAGS_OF_CONVENIENCE and SHADOW_FLEET_FLAGS for flag lists
FLAG_SCORE_SHADOW_FLEET = 25      # Known shadow fleet registry
FLAG_SCORE_FOC = 15               # General flag of convenience
FLAG_SCORE_FRAUDULENT = 35        # Fraudulent/emerging dark registry


# =============================================================================
# Ownership Risk Scoring
# =============================================================================

OWNERSHIP_SCORE_UNKNOWN = 15      # No owner information
OWNERSHIP_SCORE_OBSCURED = 10     # Owner info appears hidden


# =============================================================================
# Combined Risk Weights
# =============================================================================
# Used in combined-risk endpoint for weighted averaging

WEIGHT_BEHAVIOR = 1.0             # Local analysis weight
WEIGHT_DARK_FLEET = 1.2           # Regional intelligence weight
WEIGHT_GFW = 1.5                  # Verified external data weight (highest)


# =============================================================================
# Utility Functions
# =============================================================================

def calculate_risk_assessment(score: int) -> dict:
    """
    Generate standardized risk assessment from score.

    Returns dict with score, level, and description.
    """
    level = get_risk_level(score)

    assessments = {
        'critical': 'High probability of dark fleet / sanctions evasion activity',
        'high': 'Multiple dark fleet indicators present',
        'medium': 'Some concerning indicators detected',
        'low': 'Minor risk factors present',
        'minimal': 'No significant dark fleet indicators'
    }

    return {
        'score': min(score, 100),
        'risk_level': level,
        'assessment': assessments.get(level, 'Unknown')
    }
