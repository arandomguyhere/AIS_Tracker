#!/usr/bin/env python3
"""
Update Static Site with OSINT Data

This script reads the generated OSINT events and injects them
into docs/index.html for GitHub Pages display.
"""

import json
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def load_osint_events(output_dir: Path) -> dict:
    """Load generated OSINT events."""
    events_file = output_dir / "events_lightweight.json"

    if not events_file.exists():
        print(f"No events file found at {events_file}")
        return {"events": [], "generated_at": None}

    with open(events_file) as f:
        return json.load(f)


def update_html(html_path: Path, osint_data: dict) -> bool:
    """
    Update the HTML file with OSINT events.

    Injects events into a JavaScript variable in the HTML.
    """
    if not html_path.exists():
        print(f"HTML file not found: {html_path}")
        return False

    with open(html_path, "r") as f:
        html_content = f.read()

    # Convert OSINT events to the format expected by the UI
    osint_events = []
    for event in osint_data.get("events", []):
        osint_events.append({
            "severity": event.get("severity", "info"),
            "title": event.get("title", "OSINT Report"),
            "description": event.get("description", ""),
            "event_date": event.get("event_date", "").split("T")[0],
            "source_url": event.get("source_url"),
            "source_name": event.get("source_name"),
            "confidence": event.get("confidence_level", "medium")
        })

    # Create the JavaScript to inject
    osint_js = f"""
        // OSINT Events - Auto-generated {osint_data.get('generated_at', 'unknown')}
        const osintEvents = {json.dumps(osint_events, indent=8)};
"""

    # Check if we already have an osintEvents section
    osint_pattern = r'// OSINT Events.*?const osintEvents = \[.*?\];'

    if re.search(osint_pattern, html_content, re.DOTALL):
        # Replace existing
        html_content = re.sub(osint_pattern, osint_js.strip(), html_content, flags=re.DOTALL)
        print("Updated existing OSINT events in HTML")
    else:
        # Insert after the events array
        events_pattern = r'(const events = \[[\s\S]*?\];)'
        match = re.search(events_pattern, html_content)

        if match:
            insert_point = match.end()
            html_content = html_content[:insert_point] + "\n\n" + osint_js + html_content[insert_point:]
            print("Inserted OSINT events into HTML")
        else:
            print("Could not find insertion point in HTML")
            return False

    # Also update the events array to include OSINT events in the timeline
    # Find the existing events and append OSINT ones
    # This merges them for display

    # Write updated HTML
    with open(html_path, "w") as f:
        f.write(html_content)

    return True


def generate_osint_timeline_html(osint_data: dict) -> str:
    """Generate HTML for OSINT timeline section."""
    events = osint_data.get("events", [])

    if not events:
        return ""

    html_parts = ['<div class="panel-section"><div class="section-title">OSINT Intelligence</div><div class="timeline">']

    for event in events[:5]:  # Limit to 5 most recent
        severity = event.get("severity", "info")
        severity_class = {
            "critical": "severity-critical",
            "high": "severity-high",
            "medium": "severity-medium"
        }.get(severity, "severity-info")

        date_str = event.get("event_date", "")[:10]
        title = event.get("title", "OSINT Report")[:60]
        description = event.get("description", "")[:150]
        source = event.get("source_name", "")
        url = event.get("source_url", "#")
        confidence = event.get("confidence_level", "medium")

        html_parts.append(f'''
            <div class="timeline-item">
                <div class="timeline-dot {severity_class}"></div>
                <div class="timeline-date">{date_str} | {confidence.upper()} confidence</div>
                <div class="timeline-title"><a href="{url}" target="_blank" style="color:inherit;text-decoration:none">{title}</a></div>
                <div class="timeline-desc">{description}</div>
                <div style="font-size:10px;color:#999;margin-top:4px">Source: {source}</div>
            </div>
        ''')

    html_parts.append('</div></div>')

    return '\n'.join(html_parts)


def main():
    print("=" * 60)
    print("Updating Static Site with OSINT Data")
    print("=" * 60)

    output_dir = PROJECT_ROOT / "data" / "output"
    html_path = PROJECT_ROOT / "docs" / "index.html"

    # Load OSINT events
    print("\n[1] Loading OSINT events...")
    osint_data = load_osint_events(output_dir)
    event_count = len(osint_data.get("events", []))
    print(f"    Found {event_count} events")

    if event_count == 0:
        print("    No events to update")
        return

    # Read current HTML
    print("\n[2] Reading docs/index.html...")
    with open(html_path, "r") as f:
        html_content = f.read()

    # Find the events array and merge OSINT events
    print("\n[3] Merging OSINT events into timeline...")

    # Convert to timeline event format
    new_events = []
    for event in osint_data.get("events", []):
        new_events.append({
            "severity": event.get("severity", "info"),
            "title": event.get("title", ""),
            "description": f"{event.get('description', '')} [Source: {event.get('source_name', 'OSINT')}]",
            "event_date": event.get("event_date", "").split("T")[0]
        })

    # Find existing events array
    events_match = re.search(r'const events = (\[[\s\S]*?\]);', html_content)

    if events_match:
        try:
            existing_events = json.loads(events_match.group(1))
        except:
            existing_events = []

        # Merge: add OSINT events that aren't duplicates
        existing_titles = {e.get("title", "").lower() for e in existing_events}

        for event in new_events:
            if event["title"].lower() not in existing_titles:
                existing_events.append(event)

        # Sort by date (newest first)
        existing_events.sort(key=lambda x: x.get("event_date", ""), reverse=True)

        # Replace in HTML
        new_events_js = json.dumps(existing_events, indent=12)
        html_content = re.sub(
            r'const events = \[[\s\S]*?\];',
            f'const events = {new_events_js};',
            html_content
        )

    # Add generation timestamp comment
    timestamp = osint_data.get("generated_at", datetime.utcnow().isoformat())
    comment = f"<!-- OSINT data last updated: {timestamp} -->"

    if "<!-- OSINT data last updated:" in html_content:
        html_content = re.sub(r'<!-- OSINT data last updated:.*?-->', comment, html_content)
    else:
        html_content = html_content.replace("<head>", f"<head>\n    {comment}")

    # Write updated HTML
    print("\n[4] Writing updated docs/index.html...")
    with open(html_path, "w") as f:
        f.write(html_content)

    print(f"    Added {len(new_events)} OSINT events to timeline")
    print("\n" + "=" * 60)
    print("Static site update complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
