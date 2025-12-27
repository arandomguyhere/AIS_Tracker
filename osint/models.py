"""
Data models for OSINT correlation.

These models prioritize:
- Interpretability: Clear field names and documentation
- Provenance: Every conclusion traces back to source evidence
- Serialization: Easy JSON export for UI consumption
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import json


class EntityType(Enum):
    """Types of entities we extract from text."""
    VESSEL = "vessel"
    SHIPYARD = "shipyard"
    PORT = "port"
    ORGANIZATION = "organization"
    WEAPON_SYSTEM = "weapon_system"
    LOCATION = "location"
    PERSON = "person"
    DATE = "date"
    KEYWORD = "keyword"


class ConfidenceLevel(Enum):
    """
    Analyst-friendly confidence levels with numeric ranges.

    Based on intelligence community standards:
    - HIGH: Multiple corroborating sources, direct evidence
    - MEDIUM: Single reliable source, or indirect evidence
    - LOW: Uncorroborated, or source reliability unknown
    - SPECULATIVE: Inference based on patterns, not direct evidence
    """
    HIGH = "high"           # 0.8 - 1.0
    MEDIUM = "medium"       # 0.5 - 0.8
    LOW = "low"             # 0.3 - 0.5
    SPECULATIVE = "speculative"  # 0.0 - 0.3

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        """Convert numeric score to confidence level."""
        if score >= 0.8:
            return cls.HIGH
        elif score >= 0.5:
            return cls.MEDIUM
        elif score >= 0.3:
            return cls.LOW
        else:
            return cls.SPECULATIVE


@dataclass
class Provenance:
    """
    Tracks the origin and chain of reasoning for any conclusion.

    Essential for analyst review and audit trails.
    """
    source_url: str
    source_name: str
    retrieved_at: datetime
    original_text: str  # The exact text that led to this conclusion
    extraction_method: str  # How was this extracted? (regex, NER, keyword, etc.)
    reasoning: str  # Human-readable explanation of why this was extracted

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_url": self.source_url,
            "source_name": self.source_name,
            "retrieved_at": self.retrieved_at.isoformat(),
            "original_text": self.original_text,
            "extraction_method": self.extraction_method,
            "reasoning": self.reasoning
        }


@dataclass
class Entity:
    """
    An extracted entity from text with full provenance.
    """
    text: str  # The entity as it appears in text
    normalized: str  # Standardized form (e.g., "ZHONG DA 79" -> "ZHONGDA79")
    entity_type: EntityType
    confidence: float  # 0.0 to 1.0
    provenance: Provenance
    aliases: List[str] = field(default_factory=list)  # Known alternative names
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "normalized": self.normalized,
            "entity_type": self.entity_type.value,
            "confidence": self.confidence,
            "confidence_level": ConfidenceLevel.from_score(self.confidence).value,
            "provenance": self.provenance.to_dict(),
            "aliases": self.aliases,
            "metadata": self.metadata
        }


@dataclass
class Article:
    """
    A news article or intelligence report for processing.
    """
    id: str
    title: str
    content: str
    url: str
    source_name: str
    published_at: Optional[datetime] = None
    retrieved_at: datetime = field(default_factory=datetime.utcnow)
    language: str = "en"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source_name": self.source_name,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "retrieved_at": self.retrieved_at.isoformat(),
            "language": self.language,
            "content_length": len(self.content),
            "metadata": self.metadata
        }


@dataclass
class CorrelationResult:
    """
    Result of correlating an article with a tracked vessel.

    Contains detailed scoring breakdown for analyst review.
    """
    article_id: str
    vessel_id: Optional[int]
    vessel_name: Optional[str]

    # Scoring breakdown
    relevance_score: float  # Overall score 0.0 to 1.0
    name_match_score: float  # Did vessel name appear?
    keyword_score: float  # Relevant keywords present?
    location_score: float  # Geographic relevance?
    temporal_score: float  # Time relevance?
    context_score: float  # Semantic context relevance?

    # Evidence
    matched_entities: List[Entity] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    reasoning: str = ""  # Human-readable explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "article_id": self.article_id,
            "vessel_id": self.vessel_id,
            "vessel_name": self.vessel_name,
            "relevance_score": round(self.relevance_score, 4),
            "confidence_level": ConfidenceLevel.from_score(self.relevance_score).value,
            "scoring_breakdown": {
                "name_match": round(self.name_match_score, 4),
                "keywords": round(self.keyword_score, 4),
                "location": round(self.location_score, 4),
                "temporal": round(self.temporal_score, 4),
                "context": round(self.context_score, 4)
            },
            "matched_entities": [e.to_dict() for e in self.matched_entities],
            "matched_keywords": self.matched_keywords,
            "reasoning": self.reasoning
        }


@dataclass
class TimelineEvent:
    """
    An OSINT-derived timeline event ready for UI consumption.

    Mirrors the existing event format in the tracker but adds
    OSINT-specific fields for provenance and confidence.
    """
    id: str
    vessel_id: Optional[int]
    vessel_name: Optional[str]

    # Event details
    event_type: str  # osint_report, media_coverage, activity_detected, etc.
    severity: str  # critical, high, medium, low, info
    title: str
    description: str
    event_date: datetime

    # OSINT-specific fields
    confidence_score: float
    confidence_level: ConfidenceLevel
    source_articles: List[str]  # Article IDs that contributed
    provenance_chain: List[Provenance]
    extracted_entities: List[Entity]
    correlation_reasoning: str

    # Analyst fields
    requires_review: bool = False
    analyst_notes: str = ""
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Export as JSON-serializable dict for UI consumption."""
        return {
            "id": self.id,
            "vessel_id": self.vessel_id,
            "vessel_name": self.vessel_name,
            "event_type": self.event_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "event_date": self.event_date.isoformat(),
            "confidence": {
                "score": round(self.confidence_score, 4),
                "level": self.confidence_level.value,
                "requires_review": self.requires_review
            },
            "sources": {
                "article_ids": self.source_articles,
                "provenance": [p.to_dict() for p in self.provenance_chain]
            },
            "entities": [e.to_dict() for e in self.extracted_entities],
            "analysis": {
                "reasoning": self.correlation_reasoning,
                "analyst_notes": self.analyst_notes,
                "verified": self.verified
            }
        }

    def to_json(self, indent: int = 2) -> str:
        """Export as formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class TrackedVessel:
    """
    Vessel data structure for correlation matching.
    Mirrors the database schema but optimized for matching.
    """
    id: int
    name: str
    mmsi: Optional[str] = None
    imo: Optional[str] = None
    flag_state: Optional[str] = None
    vessel_type: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)  # Terms associated with this vessel
    related_locations: List[str] = field(default_factory=list)  # Ports, shipyards, etc.

    def get_all_names(self) -> List[str]:
        """Get all possible name variations for matching."""
        names = [self.name] + self.aliases
        # Add normalized versions
        for name in list(names):
            # Remove spaces
            names.append(name.replace(" ", ""))
            # Remove hyphens
            names.append(name.replace("-", ""))
            # Lowercase
            names.append(name.lower())
        return list(set(names))
