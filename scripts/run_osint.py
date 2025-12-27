#!/usr/bin/env python3
"""
OSINT Runner for GitHub Actions

This script:
1. Loads articles from data/articles/ directory
2. Loads vessel configuration from data/vessels.json
3. Runs OSINT correlation
4. Exports results to data/output/
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from osint import OSINTCorrelator
from osint.models import TrackedVessel
from osint.sources import ManualAdapter, GoogleNewsAdapter


def load_vessels(config_path: Path) -> list:
    """Load tracked vessels from config file."""
    if not config_path.exists():
        # Default vessels if no config
        return [
            TrackedVessel(
                id=1,
                name="ZHONG DA 79",
                mmsi="413000000",
                imo=None,
                flag_state="China",
                vessel_type="Container Feeder",
                aliases=["ZHONGDA 79", "ZHONGDA79", "ZHONG DA79"],
                keywords=["arsenal ship", "containerized missile", "VLS", "CIWS"],
                related_locations=["Shanghai", "Longhai", "Fujian", "Huangpu River", "Hudong-Zhonghua"]
            )
        ]

    with open(config_path) as f:
        data = json.load(f)

    vessels = []
    for v in data.get("vessels", []):
        vessels.append(TrackedVessel(
            id=v["id"],
            name=v["name"],
            mmsi=v.get("mmsi"),
            imo=v.get("imo"),
            flag_state=v.get("flag_state"),
            vessel_type=v.get("vessel_type"),
            aliases=v.get("aliases", []),
            keywords=v.get("keywords", []),
            related_locations=v.get("related_locations", [])
        ))

    return vessels


def load_articles(articles_dir: Path) -> list:
    """Load articles from JSON files in directory."""
    adapter = ManualAdapter()

    # Load all JSON files in articles directory
    for json_file in articles_dir.glob("*.json"):
        print(f"  Loading {json_file.name}...")
        adapter.load_from_file(str(json_file))

    return adapter.get_articles()


def main():
    print("=" * 60)
    print("OSINT Correlation Runner")
    print(f"Time: {datetime.utcnow().isoformat()}Z")
    print("=" * 60)

    # Paths
    data_dir = PROJECT_ROOT / "data"
    articles_dir = data_dir / "articles"
    output_dir = data_dir / "output"
    vessels_config = data_dir / "vessels.json"

    # Ensure directories exist
    articles_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load vessels
    print("\n[1] Loading tracked vessels...")
    vessels = load_vessels(vessels_config)
    print(f"    Tracking {len(vessels)} vessel(s): {[v.name for v in vessels]}")

    # Load articles
    print("\n[2] Loading articles...")
    articles = load_articles(articles_dir)
    print(f"    Loaded {len(articles)} article(s)")

    if not articles:
        print("\n    No articles found in data/articles/")
        print("    Add JSON files with articles to process")

        # Create sample file for reference
        sample_file = articles_dir / "_sample_articles.json"
        if not sample_file.exists():
            with open(sample_file, "w") as f:
                json.dump({
                    "_comment": "Add your articles here. This is a sample format.",
                    "articles": [
                        {
                            "title": "Article Title Here",
                            "url": "https://example.com/article",
                            "source_name": "Source Name",
                            "published_at": "2025-12-26",
                            "content": "Full article text goes here..."
                        }
                    ]
                }, f, indent=2)
            print(f"    Created sample file: {sample_file}")

        # Still run with example articles for demo
        print("\n    Using built-in example articles for demo...")
        example_file = PROJECT_ROOT / "osint" / "examples" / "input_articles.json"
        if example_file.exists():
            adapter = ManualAdapter()
            articles = adapter.load_from_file(str(example_file))
            print(f"    Loaded {len(articles)} example article(s)")

    if not articles:
        print("\nNo articles to process. Exiting.")
        return

    # Run correlation
    print("\n[3] Running OSINT correlation...")
    correlator = OSINTCorrelator(vessels)
    events = correlator.process_articles(articles, min_score=0.3)

    # Print summary
    print("\n[4] Results:")
    summary = correlator.get_summary()
    print(f"    Articles processed: {summary['articles_processed']}")
    print(f"    Entities extracted: {summary['total_entities_extracted']}")
    print(f"    Correlations found: {summary['correlations_found']}")
    print(f"    Events generated: {summary['events_generated']}")
    print(f"    High confidence: {summary['high_confidence_events']}")
    print(f"    Needs review: {summary['events_requiring_review']}")

    # Export results
    print("\n[5] Exporting results...")

    # Full events with provenance
    events_file = output_dir / "timeline_events.json"
    correlator.export_events(str(events_file))

    # Lightweight version for static site
    lightweight_file = output_dir / "events_lightweight.json"
    lightweight_events = []
    for event in events:
        lightweight_events.append({
            "id": event.id,
            "vessel_id": event.vessel_id,
            "vessel_name": event.vessel_name,
            "event_type": event.event_type,
            "severity": event.severity,
            "title": event.title,
            "description": event.description,
            "event_date": event.event_date.isoformat(),
            "confidence_score": round(event.confidence_score, 4),
            "confidence_level": event.confidence_level.value,
            "source_url": event.provenance_chain[0].source_url if event.provenance_chain else None,
            "source_name": event.provenance_chain[0].source_name if event.provenance_chain else None
        })

    with open(lightweight_file, "w") as f:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "event_count": len(lightweight_events),
            "events": lightweight_events
        }, f, indent=2)

    print(f"    Saved: {events_file}")
    print(f"    Saved: {lightweight_file}")

    print("\n" + "=" * 60)
    print("OSINT correlation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
