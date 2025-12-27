"""
Relevance scoring engine for OSINT correlation.

Scores how relevant a news article is to a tracked vessel using:
- Direct name matching (highest weight)
- Keyword overlap (medium weight)
- Geographic proximity (medium weight)
- Temporal relevance (low weight)
- Contextual signals (low weight)

All scores are explainable - analysts can see exactly why an article
received its score.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import re

from .models import (
    Article, Entity, EntityType, CorrelationResult,
    TrackedVessel, Provenance, ConfidenceLevel
)


@dataclass
class ScoringWeights:
    """
    Configurable weights for scoring components.

    Default weights reflect analyst priorities:
    - Direct vessel mention is strongest signal
    - Weapon/military keywords are important context
    - Location provides geographic relevance
    - Temporal decay reduces stale correlations
    """
    name_match: float = 0.40      # 40% weight for vessel name match
    keyword: float = 0.25        # 25% for relevant keywords
    location: float = 0.15       # 15% for geographic relevance
    temporal: float = 0.10       # 10% for time relevance
    context: float = 0.10        # 10% for contextual signals

    def __post_init__(self):
        total = self.name_match + self.keyword + self.location + self.temporal + self.context
        assert abs(total - 1.0) < 0.01, f"Weights must sum to 1.0, got {total}"


class RelevanceScorer:
    """
    Scores article relevance to tracked vessels.

    Design principles:
    - Transparent scoring: Every component is individually explainable
    - Configurable weights: Analysts can adjust priorities
    - Conservative defaults: Prefer precision over recall
    """

    # Keywords that boost relevance when found with vessel mentions
    RELEVANCE_KEYWORDS = {
        "high_signal": [
            "arsenal ship", "missile", "weapon", "converted", "military",
            "CIWS", "VLS", "launcher", "armed", "warship", "navy"
        ],
        "medium_signal": [
            "cargo", "container", "shipyard", "refit", "modification",
            "satellite", "imagery", "spotted", "observed", "detected"
        ],
        "context_signal": [
            "maritime", "vessel", "ship", "port", "naval", "fleet",
            "transit", "deployment", "exercise"
        ]
    }

    # Locations associated with tracked activity
    RELEVANT_LOCATIONS = {
        "high_relevance": [
            "Shanghai", "Fujian", "Longhai", "Taiwan Strait",
            "South China Sea", "Huangpu"
        ],
        "medium_relevance": [
            "China", "Dalian", "Guangzhou", "Hainan",
            "East China Sea", "Yellow Sea"
        ]
    }

    def __init__(self, weights: Optional[ScoringWeights] = None):
        """Initialize scorer with optional custom weights."""
        self.weights = weights or ScoringWeights()

    def score(
        self,
        article: Article,
        vessel: TrackedVessel,
        extracted_entities: List[Entity]
    ) -> CorrelationResult:
        """
        Calculate relevance score between article and vessel.

        Returns a CorrelationResult with full scoring breakdown.
        """
        text = f"{article.title}\n{article.content}".lower()

        # Calculate individual component scores
        name_score, name_matches = self._score_name_match(text, vessel, extracted_entities)
        keyword_score, keyword_matches = self._score_keywords(text, extracted_entities)
        location_score = self._score_location(text, vessel, extracted_entities)
        temporal_score = self._score_temporal(article, vessel)
        context_score = self._score_context(text, extracted_entities)

        # Calculate weighted total
        total_score = (
            name_score * self.weights.name_match +
            keyword_score * self.weights.keyword +
            location_score * self.weights.location +
            temporal_score * self.weights.temporal +
            context_score * self.weights.context
        )

        # Build reasoning explanation
        reasoning = self._build_reasoning(
            name_score, keyword_score, location_score,
            temporal_score, context_score, name_matches, keyword_matches
        )

        # Filter entities that matched this vessel
        matched_entities = [
            e for e in extracted_entities
            if self._entity_matches_vessel(e, vessel)
        ]

        return CorrelationResult(
            article_id=article.id,
            vessel_id=vessel.id,
            vessel_name=vessel.name,
            relevance_score=total_score,
            name_match_score=name_score,
            keyword_score=keyword_score,
            location_score=location_score,
            temporal_score=temporal_score,
            context_score=context_score,
            matched_entities=matched_entities,
            matched_keywords=keyword_matches,
            reasoning=reasoning
        )

    def _score_name_match(
        self,
        text: str,
        vessel: TrackedVessel,
        entities: List[Entity]
    ) -> Tuple[float, List[str]]:
        """
        Score based on vessel name appearing in text.

        Scoring:
        - Exact name match: 1.0
        - Alias match: 0.9
        - Partial match (e.g., just "ZHONG DA"): 0.6
        - MMSI/IMO match: 0.95
        """
        matches = []
        best_score = 0.0

        # Check all name variations
        for name in vessel.get_all_names():
            name_lower = name.lower()
            if name_lower in text:
                matches.append(name)
                # Exact primary name gets full score
                if name.upper() == vessel.name.upper():
                    best_score = max(best_score, 1.0)
                else:
                    best_score = max(best_score, 0.9)

        # Check for MMSI match
        if vessel.mmsi and vessel.mmsi in text:
            matches.append(f"MMSI:{vessel.mmsi}")
            best_score = max(best_score, 0.95)

        # Check for IMO match
        if vessel.imo and vessel.imo in text:
            matches.append(f"IMO:{vessel.imo}")
            best_score = max(best_score, 0.95)

        # Check extracted entities for vessel matches
        for entity in entities:
            if entity.entity_type == EntityType.VESSEL:
                entity_name = entity.normalized.lower()
                vessel_name = vessel.name.lower().replace(" ", "")

                # Fuzzy match: check if significant overlap
                if (entity_name in vessel_name or
                    vessel_name in entity_name or
                    self._fuzzy_match(entity_name, vessel_name)):
                    if entity.text not in matches:
                        matches.append(entity.text)
                        best_score = max(best_score, entity.confidence * 0.9)

        return best_score, matches

    def _score_keywords(
        self,
        text: str,
        entities: List[Entity]
    ) -> Tuple[float, List[str]]:
        """
        Score based on relevant keywords present.

        Weighted by keyword importance:
        - High signal keywords: 0.3 each (max 1.0)
        - Medium signal: 0.15 each
        - Context signal: 0.05 each
        """
        found_keywords = []
        score = 0.0

        # Check high signal keywords
        for keyword in self.RELEVANCE_KEYWORDS["high_signal"]:
            if keyword.lower() in text:
                found_keywords.append(keyword)
                score += 0.3

        # Check medium signal
        for keyword in self.RELEVANCE_KEYWORDS["medium_signal"]:
            if keyword.lower() in text:
                found_keywords.append(keyword)
                score += 0.15

        # Check context signal
        for keyword in self.RELEVANCE_KEYWORDS["context_signal"]:
            if keyword.lower() in text:
                score += 0.05

        # Boost from weapon system entities
        weapon_entities = [e for e in entities if e.entity_type == EntityType.WEAPON_SYSTEM]
        for entity in weapon_entities:
            if entity.text not in found_keywords:
                found_keywords.append(entity.text)
                score += 0.2

        return min(score, 1.0), found_keywords

    def _score_location(
        self,
        text: str,
        vessel: TrackedVessel,
        entities: List[Entity]
    ) -> float:
        """
        Score based on geographic relevance.

        Higher scores for:
        - Locations in vessel's related_locations list
        - High-relevance maritime locations
        """
        score = 0.0

        # Check vessel's known locations
        for location in vessel.related_locations:
            if location.lower() in text:
                score += 0.4

        # Check high-relevance locations
        for location in self.RELEVANT_LOCATIONS["high_relevance"]:
            if location.lower() in text:
                score += 0.2

        # Check medium-relevance locations
        for location in self.RELEVANT_LOCATIONS["medium_relevance"]:
            if location.lower() in text:
                score += 0.1

        # Boost from location entities
        location_entities = [e for e in entities if e.entity_type == EntityType.LOCATION]
        score += len(location_entities) * 0.15

        return min(score, 1.0)

    def _score_temporal(self, article: Article, vessel: TrackedVessel) -> float:
        """
        Score based on article recency.

        More recent articles are more relevant:
        - Last 24 hours: 1.0
        - Last week: 0.8
        - Last month: 0.5
        - Older: 0.2
        """
        if not article.published_at:
            return 0.5  # Unknown date gets neutral score

        now = datetime.utcnow()
        age = now - article.published_at

        if age < timedelta(days=1):
            return 1.0
        elif age < timedelta(days=7):
            return 0.8
        elif age < timedelta(days=30):
            return 0.5
        elif age < timedelta(days=90):
            return 0.3
        else:
            return 0.2

    def _score_context(self, text: str, entities: List[Entity]) -> float:
        """
        Score based on contextual signals.

        Considers:
        - Shipyard mentions (indicates modification activity)
        - Multiple entity types present (richer context)
        - Activity keywords (conversion, refit, etc.)
        """
        score = 0.0

        # Shipyard mentions
        shipyard_entities = [e for e in entities if e.entity_type == EntityType.SHIPYARD]
        if shipyard_entities:
            score += 0.3

        # Entity type diversity
        entity_types = set(e.entity_type for e in entities)
        score += min(len(entity_types) * 0.1, 0.4)

        # Activity keywords
        activity_entities = [
            e for e in entities
            if e.entity_type == EntityType.KEYWORD
            and e.metadata.get("activity_type") in ["conversion", "military", "weapons"]
        ]
        score += len(activity_entities) * 0.15

        return min(score, 1.0)

    def _fuzzy_match(self, s1: str, s2: str, threshold: float = 0.8) -> bool:
        """Simple fuzzy matching using character overlap."""
        if not s1 or not s2:
            return False

        # Remove spaces and normalize
        s1 = s1.replace(" ", "").lower()
        s2 = s2.replace(" ", "").lower()

        # Check character overlap
        chars1 = set(s1)
        chars2 = set(s2)
        overlap = len(chars1 & chars2) / max(len(chars1), len(chars2))

        return overlap >= threshold

    def _entity_matches_vessel(self, entity: Entity, vessel: TrackedVessel) -> bool:
        """Check if an entity is associated with the vessel."""
        if entity.entity_type != EntityType.VESSEL:
            return False

        vessel_names = [n.lower() for n in vessel.get_all_names()]
        entity_normalized = entity.normalized.lower()

        return any(
            entity_normalized in name or name in entity_normalized
            for name in vessel_names
        )

    def _build_reasoning(
        self,
        name_score: float,
        keyword_score: float,
        location_score: float,
        temporal_score: float,
        context_score: float,
        name_matches: List[str],
        keyword_matches: List[str]
    ) -> str:
        """Build human-readable reasoning for the score."""
        parts = []

        # Name match reasoning
        if name_score >= 0.9:
            parts.append(f"STRONG vessel name match: {', '.join(name_matches)}")
        elif name_score >= 0.5:
            parts.append(f"Partial vessel name match: {', '.join(name_matches)}")
        elif name_score > 0:
            parts.append(f"Weak vessel name match: {', '.join(name_matches)}")
        else:
            parts.append("No direct vessel name match")

        # Keyword reasoning
        if keyword_score >= 0.6:
            parts.append(f"High keyword relevance: {', '.join(keyword_matches[:5])}")
        elif keyword_score >= 0.3:
            parts.append(f"Moderate keyword relevance: {', '.join(keyword_matches[:3])}")

        # Location reasoning
        if location_score >= 0.5:
            parts.append("Geographic location highly relevant")
        elif location_score >= 0.2:
            parts.append("Geographic location somewhat relevant")

        # Temporal reasoning
        if temporal_score >= 0.8:
            parts.append("Recent article (high temporal relevance)")
        elif temporal_score <= 0.3:
            parts.append("Older article (reduced temporal relevance)")

        # Context reasoning
        if context_score >= 0.5:
            parts.append("Rich contextual signals present")

        return " | ".join(parts)


class BulkScorer:
    """
    Efficiently score multiple articles against multiple vessels.
    """

    def __init__(self, scorer: Optional[RelevanceScorer] = None):
        self.scorer = scorer or RelevanceScorer()

    def score_articles(
        self,
        articles: List[Article],
        vessels: List[TrackedVessel],
        entities_by_article: Dict[str, List[Entity]],
        min_score: float = 0.3
    ) -> List[CorrelationResult]:
        """
        Score all articles against all vessels.

        Returns correlations above min_score threshold, sorted by score.
        """
        results = []

        for article in articles:
            entities = entities_by_article.get(article.id, [])

            for vessel in vessels:
                result = self.scorer.score(article, vessel, entities)

                if result.relevance_score >= min_score:
                    results.append(result)

        # Sort by score descending
        results.sort(key=lambda r: r.relevance_score, reverse=True)

        return results
