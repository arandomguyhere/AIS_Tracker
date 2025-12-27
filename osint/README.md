# OSINT Correlation Module

OSINT correlation layer for the Arsenal Ship Tracker. This module extracts entities from news articles, scores their relevance to tracked vessels, and generates timeline events with full provenance chains.

## Design Principles

1. **Interpretability**: Every extraction and correlation decision is explainable
2. **Provenance**: Full audit trails from source to conclusion
3. **Analyst-Centric**: Output designed for human review, not automation
4. **Conservative Precision**: Better to miss a correlation than generate false positives

## Architecture

```
osint/
├── __init__.py          # Module exports
├── models.py            # Data models (Article, Entity, TimelineEvent, etc.)
├── entities.py          # Entity extraction (vessels, shipyards, weapons, etc.)
├── scoring.py           # Relevance scoring engine
├── correlator.py        # Main orchestration
├── sources/             # Data source adapters
│   ├── google_news.py   # Google News scraper integration
│   ├── rss.py           # RSS/Atom feed adapter
│   └── manual.py        # Manual article curation
└── examples/            # Example inputs/outputs
    ├── input_articles.json
    ├── output_events.json
    └── run_example.py
```

## Quick Start

```python
from osint import OSINTCorrelator
from osint.models import TrackedVessel
from osint.sources import ManualAdapter

# 1. Define vessels to track
vessels = [
    TrackedVessel(
        id=1,
        name="ZHONG DA 79",
        mmsi="413000000",
        aliases=["ZHONGDA 79"],
        keywords=["arsenal ship", "containerized missile"],
        related_locations=["Shanghai", "Longhai"]
    )
]

# 2. Load articles
adapter = ManualAdapter()
articles = adapter.load_from_file("articles.json")

# 3. Run correlation
correlator = OSINTCorrelator(vessels)
events = correlator.process_articles(articles)

# 4. Export results
correlator.export_events("timeline_events.json")
```

## Correlation Logic

### Entity Extraction

The `EntityExtractor` identifies the following entity types:

| Entity Type | Extraction Method | Example |
|-------------|------------------|---------|
| VESSEL | Pattern matching + known list | "ZHONG DA 79", "MV Example" |
| SHIPYARD | Dictionary lookup | "Hudong-Zhonghua", "Longhai" |
| WEAPON_SYSTEM | Dictionary lookup | "VLS", "CIWS", "YJ-18" |
| LOCATION | Dictionary lookup | "Taiwan Strait", "Shanghai" |
| KEYWORD | Activity indicators | "converted", "armed", "refit" |

**Extraction Confidence Levels:**
- **0.95**: Known tracked vessel matched
- **0.90**: Dictionary match (shipyard, location)
- **0.85**: Weapon system identified
- **0.50-0.80**: Pattern-matched vessel (contextual boost)
- **0.70**: Activity keyword

### Relevance Scoring

The `RelevanceScorer` calculates article-to-vessel relevance using weighted components:

```
Total Score = (Name × 0.40) + (Keywords × 0.25) + (Location × 0.15)
            + (Temporal × 0.10) + (Context × 0.10)
```

**Component Scoring:**

| Component | Weight | Scoring Logic |
|-----------|--------|---------------|
| Name Match | 40% | 1.0 exact match, 0.9 alias, 0.6 partial |
| Keywords | 25% | 0.3 per high-signal, 0.15 medium, 0.05 context |
| Location | 15% | 0.4 vessel's known locations, 0.2 high-relevance areas |
| Temporal | 10% | 1.0 <24h, 0.8 <1wk, 0.5 <1mo, 0.2 older |
| Context | 10% | Shipyard mentions, entity diversity, activity keywords |

### Confidence Levels

Confidence scores map to analyst-friendly levels:

| Level | Score Range | Interpretation |
|-------|-------------|----------------|
| HIGH | 0.80 - 1.00 | Multiple corroborating signals, high confidence |
| MEDIUM | 0.50 - 0.80 | Single reliable signal or indirect evidence |
| LOW | 0.30 - 0.50 | Uncorroborated, requires review |
| SPECULATIVE | 0.00 - 0.30 | Inference only, likely noise |

Events with scores below 0.50 are flagged `requires_review: true`.

## Data Models

### Article

```python
Article(
    id="article-001",
    title="...",
    content="Full article text...",
    url="https://...",
    source_name="Naval News",
    published_at=datetime(2025, 12, 26),
    retrieved_at=datetime.utcnow()
)
```

### Entity

```python
Entity(
    text="ZHONG DA 79",           # As appears in text
    normalized="ZHONG DA 79",      # Standardized form
    entity_type=EntityType.VESSEL,
    confidence=0.95,
    provenance=Provenance(
        source_url="https://...",
        source_name="United24 Media",
        retrieved_at=datetime.utcnow(),
        original_text="...identified as ZHONG DA 79...",
        extraction_method="known_vessel_match",
        reasoning="Matched known tracked vessel 'ZHONG DA 79'"
    )
)
```

### TimelineEvent

```python
TimelineEvent(
    id="osint-abc123",
    vessel_id=1,
    vessel_name="ZHONG DA 79",
    event_type="weapons_observed",
    severity="critical",
    title="Arsenal Ship Spotted in Shanghai",
    description="...",
    event_date=datetime(2025, 12, 26),
    confidence_score=0.94,
    confidence_level=ConfidenceLevel.HIGH,
    source_articles=["article-001"],
    provenance_chain=[...],
    extracted_entities=[...],
    correlation_reasoning="STRONG vessel name match | High keyword relevance...",
    requires_review=False
)
```

## Integrating Google News Scraper

The `GoogleNewsAdapter` supports external scraper integration:

```python
from osint.sources import GoogleNewsAdapter

# Option 1: Use gnews library
from gnews import GNews

def scraper(query):
    gn = GNews(language='en', max_results=50)
    return gn.get_news(query)

adapter = GoogleNewsAdapter()
adapter.set_scraper(scraper)
articles = adapter.search("ZHONG DA 79 missile")

# Option 2: Load pre-scraped JSON
adapter = GoogleNewsAdapter()
articles = adapter.load_from_file("scraped_news.json")
```

Expected scraper output format:
```json
{
  "title": "Article Title",
  "url": "https://...",
  "source": "Source Name",
  "published": "2025-12-26",
  "snippet": "Brief description..."
}
```

## Output Format

### Timeline Event JSON

```json
{
  "id": "osint-abc123",
  "vessel_id": 1,
  "vessel_name": "ZHONG DA 79",
  "event_type": "weapons_observed",
  "severity": "critical",
  "title": "...",
  "description": "...",
  "event_date": "2025-12-26T00:00:00",
  "confidence": {
    "score": 0.9425,
    "level": "high",
    "requires_review": false
  },
  "sources": {
    "article_ids": ["article-001"],
    "provenance": [
      {
        "source_url": "https://...",
        "source_name": "United24 Media",
        "retrieved_at": "2025-12-27T10:30:00Z",
        "original_text": "...",
        "extraction_method": "known_vessel_match",
        "reasoning": "Matched known tracked vessel"
      }
    ]
  },
  "entities": [...],
  "analysis": {
    "reasoning": "STRONG vessel name match | High keyword relevance...",
    "analyst_notes": "",
    "verified": false
  }
}
```

## Running the Example

```bash
cd AIS_Tracker
python -m osint.examples.run_example
```

Output:
```
============================================================
OSINT Correlation Example
============================================================

[1] Setting up tracked vessels...
   - Tracking 1 vessel(s): ['ZHONG DA 79']

[2] Loading example articles...
   - Loaded 5 articles

[3] Initializing OSINT correlator...

[4] Processing articles...
[OSINT] Extracting entities from 5 articles...
  - article-001: 12 entities extracted
  - article-002: 10 entities extracted
  ...
[OSINT] Scoring against 1 tracked vessels...
  - 4 correlations above threshold
[OSINT] Generating timeline events...
  - 3 events generated

[5] Processing summary:
   - articles_processed: 5
   - total_entities_extracted: 47
   - correlations_found: 4
   - events_generated: 3
   - high_confidence_events: 3
   - events_requiring_review: 0

[6] Generated timeline events:
------------------------------------------------------------

   EVENT: Cargo Ship or Warship? China Arms Civilian Vessel...
   Type: weapons_observed | Severity: critical
   Vessel: ZHONG DA 79
   Confidence: 94.25% (high)
   Date: 2025-12-26
   Reasoning: STRONG vessel name match: ZHONG DA 79 | High keyword relevance...
```

## Extending the Module

### Adding New Entity Types

1. Define the type in `models.py`:
```python
class EntityType(Enum):
    ...
    NEW_TYPE = "new_type"
```

2. Add extraction logic in `entities.py`:
```python
def _extract_new_type(self, text: str, article: Article) -> List[Entity]:
    ...
```

### Custom Scoring Weights

```python
from osint.scoring import RelevanceScorer, ScoringWeights

weights = ScoringWeights(
    name_match=0.50,  # Increase name match importance
    keyword=0.20,
    location=0.10,
    temporal=0.10,
    context=0.10
)

scorer = RelevanceScorer(weights)
correlator = OSINTCorrelator(vessels, scorer=scorer)
```

### Adding New Data Sources

Implement a new adapter in `sources/`:

```python
class MySourceAdapter:
    def fetch(self, query: str) -> List[Article]:
        # Fetch and normalize to Article objects
        ...
```

## Future Enhancements

- [ ] Named Entity Recognition (NER) with spaCy/NLTK
- [ ] Sentiment analysis for threat assessment
- [ ] Cross-article entity resolution
- [ ] Temporal clustering for event deduplication
- [ ] Export to STIX/TAXII formats
- [ ] Integration with existing tracker database
