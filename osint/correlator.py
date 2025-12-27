"""
OSINT Correlator - Main orchestration module.

Ties together entity extraction, relevance scoring, and timeline generation
to produce analyst-ready OSINT timeline events.

Usage:
    correlator = OSINTCorrelator(vessels)
    events = correlator.process_articles(articles)
    correlator.export_events("output.json")
"""

import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path

from .models import (
    Article, Entity, EntityType, TrackedVessel,
    CorrelationResult, TimelineEvent, ConfidenceLevel, Provenance
)
from .entities import EntityExtractor
from .scoring import RelevanceScorer, BulkScorer


class OSINTCorrelator:
    """
    Main OSINT correlation engine.

    Processes news articles to:
    1. Extract relevant entities (vessels, shipyards, weapons, etc.)
    2. Score relevance to tracked vessels
    3. Generate timeline events with confidence scores
    4. Export analyst-ready JSON

    All operations preserve full provenance for audit trails.
    """

    # Thresholds for event generation
    CORRELATION_THRESHOLD = 0.3   # Minimum score to consider
    HIGH_CONFIDENCE_THRESHOLD = 0.7  # Score for high-confidence events
    REVIEW_THRESHOLD = 0.5  # Below this, flag for analyst review

    # Event type mappings based on content
    EVENT_TYPE_KEYWORDS = {
        "weapons_observed": ["missile", "armed", "weapon", "VLS", "CIWS", "launcher"],
        "modification_detected": ["converted", "modified", "refit", "retrofit", "upgrade"],
        "shipyard_activity": ["shipyard", "drydock", "dock", "repair", "maintenance"],
        "media_coverage": ["report", "news", "article", "coverage", "published"],
        "satellite_observation": ["satellite", "imagery", "observed", "spotted", "detected"],
        "transit_activity": ["transit", "sailed", "departed", "arrived", "passage"],
        "exercise_activity": ["exercise", "drill", "maneuver", "deployment"],
    }

    # Severity mappings
    SEVERITY_KEYWORDS = {
        "critical": ["missile", "weapon", "armed", "arsenal", "military conversion"],
        "high": ["modified", "shipyard", "refit", "CIWS", "radar"],
        "medium": ["transit", "observed", "detected", "activity"],
        "low": ["report", "coverage", "mentioned"],
    }

    def __init__(
        self,
        vessels: List[TrackedVessel],
        extractor: Optional[EntityExtractor] = None,
        scorer: Optional[RelevanceScorer] = None
    ):
        """
        Initialize correlator with tracked vessels.

        Args:
            vessels: List of vessels to correlate against
            extractor: Custom entity extractor (optional)
            scorer: Custom relevance scorer (optional)
        """
        self.vessels = vessels
        self.vessels_by_id = {v.id: v for v in vessels}
        self.vessels_by_name = {v.name.lower(): v for v in vessels}

        # Initialize components
        vessel_dicts = [
            {"id": v.id, "name": v.name, "aliases": v.aliases}
            for v in vessels
        ]
        self.extractor = extractor or EntityExtractor(custom_vessels=vessel_dicts)
        self.scorer = scorer or RelevanceScorer()
        self.bulk_scorer = BulkScorer(self.scorer)

        # State
        self.processed_articles: Dict[str, Article] = {}
        self.extracted_entities: Dict[str, List[Entity]] = {}
        self.correlations: List[CorrelationResult] = []
        self.timeline_events: List[TimelineEvent] = []

    def process_articles(
        self,
        articles: List[Article],
        min_score: float = None
    ) -> List[TimelineEvent]:
        """
        Process articles and generate timeline events.

        Args:
            articles: List of articles to process
            min_score: Minimum correlation score (default: CORRELATION_THRESHOLD)

        Returns:
            List of TimelineEvent objects
        """
        min_score = min_score or self.CORRELATION_THRESHOLD

        # Step 1: Extract entities from all articles
        print(f"[OSINT] Extracting entities from {len(articles)} articles...")
        for article in articles:
            entities = self.extractor.extract_all(article)
            self.extracted_entities[article.id] = entities
            self.processed_articles[article.id] = article
            print(f"  - {article.id}: {len(entities)} entities extracted")

        # Step 2: Score articles against vessels
        print(f"[OSINT] Scoring against {len(self.vessels)} tracked vessels...")
        self.correlations = self.bulk_scorer.score_articles(
            articles,
            self.vessels,
            self.extracted_entities,
            min_score=min_score
        )
        print(f"  - {len(self.correlations)} correlations above threshold")

        # Step 3: Generate timeline events
        print("[OSINT] Generating timeline events...")
        self.timeline_events = self._generate_timeline_events()
        print(f"  - {len(self.timeline_events)} events generated")

        return self.timeline_events

    def _generate_timeline_events(self) -> List[TimelineEvent]:
        """Generate timeline events from correlations."""
        events = []

        # Group correlations by article to avoid duplicate events
        correlations_by_article: Dict[str, List[CorrelationResult]] = {}
        for corr in self.correlations:
            if corr.article_id not in correlations_by_article:
                correlations_by_article[corr.article_id] = []
            correlations_by_article[corr.article_id].append(corr)

        for article_id, article_correlations in correlations_by_article.items():
            article = self.processed_articles[article_id]
            entities = self.extracted_entities.get(article_id, [])

            # Use highest-scoring correlation for this article
            best_corr = max(article_correlations, key=lambda c: c.relevance_score)

            # Determine event type and severity
            event_type = self._determine_event_type(article, entities)
            severity = self._determine_severity(article, entities, best_corr)

            # Build provenance chain
            provenance_chain = self._build_provenance_chain(article, best_corr)

            # Generate event ID
            event_id = self._generate_event_id(article, best_corr)

            # Determine confidence level
            confidence_level = ConfidenceLevel.from_score(best_corr.relevance_score)

            # Build description
            description = self._build_description(article, best_corr, entities)

            event = TimelineEvent(
                id=event_id,
                vessel_id=best_corr.vessel_id,
                vessel_name=best_corr.vessel_name,
                event_type=event_type,
                severity=severity,
                title=self._build_title(article, best_corr),
                description=description,
                event_date=article.published_at or article.retrieved_at,
                confidence_score=best_corr.relevance_score,
                confidence_level=confidence_level,
                source_articles=[article_id],
                provenance_chain=provenance_chain,
                extracted_entities=entities,
                correlation_reasoning=best_corr.reasoning,
                requires_review=best_corr.relevance_score < self.REVIEW_THRESHOLD
            )

            events.append(event)

        # Sort by date (most recent first)
        events.sort(key=lambda e: e.event_date, reverse=True)

        return events

    def _determine_event_type(self, article: Article, entities: List[Entity]) -> str:
        """Determine event type based on content analysis."""
        text = f"{article.title} {article.content}".lower()

        # Check each event type
        for event_type, keywords in self.EVENT_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    return event_type

        # Check entities for hints
        entity_types = set(e.entity_type for e in entities)
        if EntityType.WEAPON_SYSTEM in entity_types:
            return "weapons_observed"
        if EntityType.SHIPYARD in entity_types:
            return "shipyard_activity"

        return "osint_report"  # Default

    def _determine_severity(
        self,
        article: Article,
        entities: List[Entity],
        correlation: CorrelationResult
    ) -> str:
        """Determine severity based on content and score."""
        text = f"{article.title} {article.content}".lower()

        # Check severity keywords
        for severity, keywords in self.SEVERITY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    return severity

        # Fall back to correlation score
        if correlation.relevance_score >= 0.8:
            return "high"
        elif correlation.relevance_score >= 0.5:
            return "medium"
        else:
            return "low"

    def _build_provenance_chain(
        self,
        article: Article,
        correlation: CorrelationResult
    ) -> List[Provenance]:
        """Build provenance chain for the event."""
        provenance_list = []

        # Primary source provenance
        provenance_list.append(Provenance(
            source_url=article.url,
            source_name=article.source_name,
            retrieved_at=article.retrieved_at,
            original_text=article.title,
            extraction_method="article_ingestion",
            reasoning=f"Source article from {article.source_name}"
        ))

        # Add provenance from matched entities
        for entity in correlation.matched_entities[:3]:  # Top 3
            provenance_list.append(entity.provenance)

        return provenance_list

    def _build_title(self, article: Article, correlation: CorrelationResult) -> str:
        """Generate event title."""
        # Use article title if it mentions the vessel
        if correlation.vessel_name and correlation.vessel_name.lower() in article.title.lower():
            return article.title[:100]

        # Otherwise, construct a title
        return f"OSINT: {correlation.vessel_name} mentioned in {article.source_name}"

    def _build_description(
        self,
        article: Article,
        correlation: CorrelationResult,
        entities: List[Entity]
    ) -> str:
        """Build detailed event description."""
        parts = []

        # Summary
        parts.append(f"Article from {article.source_name} correlates with {correlation.vessel_name}.")

        # Key entities found
        vessel_entities = [e for e in entities if e.entity_type == EntityType.VESSEL]
        weapon_entities = [e for e in entities if e.entity_type == EntityType.WEAPON_SYSTEM]
        location_entities = [e for e in entities if e.entity_type == EntityType.LOCATION]

        if weapon_entities:
            weapons = ", ".join(e.text for e in weapon_entities[:3])
            parts.append(f"Weapon systems mentioned: {weapons}.")

        if location_entities:
            locations = ", ".join(e.text for e in location_entities[:3])
            parts.append(f"Locations: {locations}.")

        # Matched keywords
        if correlation.matched_keywords:
            keywords = ", ".join(correlation.matched_keywords[:5])
            parts.append(f"Key terms: {keywords}.")

        return " ".join(parts)

    def _generate_event_id(self, article: Article, correlation: CorrelationResult) -> str:
        """Generate unique event ID."""
        content = f"{article.id}:{correlation.vessel_id}:{article.url}"
        hash_val = hashlib.md5(content.encode()).hexdigest()[:12]
        return f"osint-{hash_val}"

    def export_events(
        self,
        output_path: str,
        format: str = "json",
        include_full_provenance: bool = True
    ) -> None:
        """
        Export timeline events to file.

        Args:
            output_path: Path to output file
            format: Output format ("json" or "jsonl")
            include_full_provenance: Include full provenance details
        """
        events_data = []

        for event in self.timeline_events:
            event_dict = event.to_dict()

            # Optionally trim provenance for lighter output
            if not include_full_provenance:
                event_dict["sources"]["provenance"] = [
                    {"source_url": p["source_url"], "source_name": p["source_name"]}
                    for p in event_dict["sources"]["provenance"]
                ]

            events_data.append(event_dict)

        output = Path(output_path)

        if format == "jsonl":
            with open(output, "w") as f:
                for event in events_data:
                    f.write(json.dumps(event, default=str) + "\n")
        else:
            with open(output, "w") as f:
                json.dump({
                    "generated_at": datetime.utcnow().isoformat(),
                    "event_count": len(events_data),
                    "vessels_tracked": [v.name for v in self.vessels],
                    "events": events_data
                }, f, indent=2, default=str)

        print(f"[OSINT] Exported {len(events_data)} events to {output_path}")

    def get_correlations_for_vessel(self, vessel_id: int) -> List[CorrelationResult]:
        """Get all correlations for a specific vessel."""
        return [c for c in self.correlations if c.vessel_id == vessel_id]

    def get_events_for_vessel(self, vessel_id: int) -> List[TimelineEvent]:
        """Get all events for a specific vessel."""
        return [e for e in self.timeline_events if e.vessel_id == vessel_id]

    def get_summary(self) -> Dict[str, Any]:
        """Get processing summary statistics."""
        return {
            "articles_processed": len(self.processed_articles),
            "total_entities_extracted": sum(len(e) for e in self.extracted_entities.values()),
            "correlations_found": len(self.correlations),
            "events_generated": len(self.timeline_events),
            "vessels_with_events": len(set(e.vessel_id for e in self.timeline_events if e.vessel_id)),
            "high_confidence_events": len([e for e in self.timeline_events if e.confidence_level == ConfidenceLevel.HIGH]),
            "events_requiring_review": len([e for e in self.timeline_events if e.requires_review]),
            "confidence_distribution": {
                "high": len([e for e in self.timeline_events if e.confidence_level == ConfidenceLevel.HIGH]),
                "medium": len([e for e in self.timeline_events if e.confidence_level == ConfidenceLevel.MEDIUM]),
                "low": len([e for e in self.timeline_events if e.confidence_level == ConfidenceLevel.LOW]),
                "speculative": len([e for e in self.timeline_events if e.confidence_level == ConfidenceLevel.SPECULATIVE]),
            }
        }


def load_vessels_from_db(db_path: str) -> List[TrackedVessel]:
    """
    Load tracked vessels from the SQLite database.

    Args:
        db_path: Path to arsenal_tracker.db

    Returns:
        List of TrackedVessel objects
    """
    import sqlite3

    vessels = []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT id, name, mmsi, imo, flag_state, vessel_type
        FROM vessels
    """)

    for row in cursor:
        vessel = TrackedVessel(
            id=row["id"],
            name=row["name"],
            mmsi=row["mmsi"],
            imo=row["imo"],
            flag_state=row["flag_state"],
            vessel_type=row["vessel_type"],
            aliases=[],  # Could be extended with an aliases table
            keywords=[],
            related_locations=[]
        )
        vessels.append(vessel)

    conn.close()
    return vessels
