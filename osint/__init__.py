"""
OSINT Correlation Module for Arsenal Ship Tracker

This module provides:
- Entity extraction from news articles and intelligence reports
- Relevance scoring between articles and tracked vessels
- Timeline event generation with confidence scores and provenance

Designed for analyst interpretability and audit trails.
"""

from .models import (
    Article,
    Entity,
    EntityType,
    CorrelationResult,
    TimelineEvent,
    ConfidenceLevel,
    Provenance
)
from .entities import EntityExtractor
from .scoring import RelevanceScorer
from .correlator import OSINTCorrelator

__version__ = "0.1.0"
__all__ = [
    "Article",
    "Entity",
    "EntityType",
    "CorrelationResult",
    "TimelineEvent",
    "ConfidenceLevel",
    "Provenance",
    "EntityExtractor",
    "RelevanceScorer",
    "OSINTCorrelator"
]
