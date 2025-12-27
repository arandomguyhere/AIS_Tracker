#!/usr/bin/env python3
"""
Example script demonstrating the OSINT correlation pipeline.

This script:
1. Loads example articles from input_articles.json
2. Defines tracked vessels (ZHONG DA 79)
3. Runs entity extraction and correlation
4. Exports timeline events to output.json

Run from the AIS_Tracker directory:
    python -m osint.examples.run_example
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from osint import OSINTCorrelator
from osint.models import TrackedVessel, Article
from osint.sources import ManualAdapter


def main():
    print("=" * 60)
    print("OSINT Correlation Example")
    print("=" * 60)

    # Define tracked vessels
    print("\n[1] Setting up tracked vessels...")
    vessels = [
        TrackedVessel(
            id=1,
            name="ZHONG DA 79",
            mmsi="413000000",
            imo=None,
            flag_state="China",
            vessel_type="Container Feeder",
            aliases=["ZHONGDA 79", "ZHONGDA79"],
            keywords=["arsenal ship", "containerized missile", "VLS"],
            related_locations=["Shanghai", "Longhai", "Fujian", "Huangpu River"]
        )
    ]
    print(f"   - Tracking {len(vessels)} vessel(s): {[v.name for v in vessels]}")

    # Load example articles
    print("\n[2] Loading example articles...")
    example_dir = Path(__file__).parent
    input_file = example_dir / "input_articles.json"

    adapter = ManualAdapter()
    articles = adapter.load_from_file(str(input_file))
    print(f"   - Loaded {len(articles)} articles")

    # Initialize correlator
    print("\n[3] Initializing OSINT correlator...")
    correlator = OSINTCorrelator(vessels)

    # Process articles
    print("\n[4] Processing articles...")
    events = correlator.process_articles(articles, min_score=0.3)

    # Print summary
    print("\n[5] Processing summary:")
    summary = correlator.get_summary()
    for key, value in summary.items():
        if isinstance(value, dict):
            print(f"   - {key}:")
            for k, v in value.items():
                print(f"      {k}: {v}")
        else:
            print(f"   - {key}: {value}")

    # Print events
    print("\n[6] Generated timeline events:")
    print("-" * 60)
    for event in events:
        print(f"\n   EVENT: {event.title[:60]}...")
        print(f"   Type: {event.event_type} | Severity: {event.severity}")
        print(f"   Vessel: {event.vessel_name}")
        print(f"   Confidence: {event.confidence_score:.2%} ({event.confidence_level.value})")
        print(f"   Date: {event.event_date.strftime('%Y-%m-%d')}")
        print(f"   Reasoning: {event.correlation_reasoning[:80]}...")

        if event.requires_review:
            print("   ⚠️  REQUIRES ANALYST REVIEW")

    # Export to file
    print("\n[7] Exporting events...")
    output_file = example_dir / "generated_output.json"
    correlator.export_events(str(output_file))

    # Also export detailed correlation results
    print("\n[8] Exporting detailed correlations...")
    correlations_file = example_dir / "correlations_detail.json"
    with open(correlations_file, "w") as f:
        json.dump({
            "correlations": [c.to_dict() for c in correlator.correlations],
            "generated_at": datetime.utcnow().isoformat()
        }, f, indent=2, default=str)
    print(f"   - Saved to {correlations_file}")

    print("\n" + "=" * 60)
    print("OSINT correlation complete!")
    print("=" * 60)

    return events


if __name__ == "__main__":
    main()
