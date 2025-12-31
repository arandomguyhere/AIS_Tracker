#!/usr/bin/env python3
"""
Stream AIS data for a geographic area.

Connects to AISStream.io and receives real-time vessel positions
for the configured bounding box. Updates docs/live_vessels.json
for the map to display.

Usage:
    # Set your API key
    export AISSTREAM_API_KEY="your-key-from-aisstream.io"

    # Run the stream
    python stream_area.py

    # Or specify a custom area (East China Sea)
    python stream_area.py --lat-min 20 --lon-min 110 --lat-max 40 --lon-max 135

Requirements:
    pip install websocket-client
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ais_sources import AISSourceManager
from ais_sources.aisstream import AISStreamSource, WEBSOCKET_AVAILABLE

# Output paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'ais_config.json')
OUTPUT_PATH = os.path.join(SCRIPT_DIR, 'docs', 'live_vessels.json')


def load_config():
    """Load configuration from ais_config.json."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}


def get_api_key():
    """Get API key from environment or config."""
    # Check environment variable first
    api_key = os.environ.get('AISSTREAM_API_KEY', '')
    if api_key:
        return api_key

    # Check config file
    config = load_config()
    key_config = config.get('sources', {}).get('aisstream', {}).get('api_key', '')

    # Resolve environment variable reference
    if key_config.startswith('${') and key_config.endswith('}'):
        var_name = key_config[2:-1]
        return os.environ.get(var_name, '')

    return key_config


def save_positions(positions, vessel_info):
    """Save positions to JSON file for the map."""
    vessels = []

    for pos in positions:
        vessel = {
            'mmsi': pos.mmsi,
            'lat': pos.latitude,
            'lon': pos.longitude,
            'speed': pos.speed_knots,
            'course': pos.course,
            'heading': pos.heading,
            'timestamp': pos.timestamp.isoformat() if pos.timestamp else None,
        }

        # Add vessel info if available
        info = vessel_info.get(pos.mmsi)
        if info:
            vessel['name'] = info.name or f"MMSI {pos.mmsi}"
            vessel['ship_type'] = info.ship_type_text or 'Unknown'
            vessel['flag'] = info.flag_state
            vessel['imo'] = info.imo
            vessel['callsign'] = info.callsign
        else:
            vessel['name'] = f"MMSI {pos.mmsi}"
            vessel['ship_type'] = 'Unknown'

        vessels.append(vessel)

    output = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'vessel_count': len(vessels),
        'vessels': vessels
    }

    # Ensure output directory exists
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2)

    return len(vessels)


def main():
    parser = argparse.ArgumentParser(description='Stream AIS data for a geographic area')
    parser.add_argument('--lat-min', type=float, help='Southern latitude boundary')
    parser.add_argument('--lon-min', type=float, help='Western longitude boundary')
    parser.add_argument('--lat-max', type=float, help='Northern latitude boundary')
    parser.add_argument('--lon-max', type=float, help='Eastern longitude boundary')
    parser.add_argument('--update-interval', type=int, default=10,
                        help='Seconds between file updates (default: 10)')
    args = parser.parse_args()

    # Check for websocket support
    if not WEBSOCKET_AVAILABLE:
        print("ERROR: websocket-client not installed")
        print("Install with: pip install websocket-client")
        sys.exit(1)

    # Get API key
    api_key = get_api_key()
    if not api_key:
        print("ERROR: No API key found")
        print("")
        print("Set your AISStream.io API key:")
        print("  export AISSTREAM_API_KEY='your-key'")
        print("")
        print("Get a free key at: https://aisstream.io/")
        sys.exit(1)

    # Load config for bounding box
    config = load_config()
    area_config = config.get('area_tracking', {}).get('bounding_box', {})

    # Use command line args or config
    lat_min = args.lat_min or area_config.get('lat_min', 20)
    lon_min = args.lon_min or area_config.get('lon_min', 110)
    lat_max = args.lat_max or area_config.get('lat_max', 40)
    lon_max = args.lon_max or area_config.get('lon_max', 135)

    print("=" * 60)
    print("Arsenal Ship Tracker - Live AIS Stream")
    print("=" * 60)
    print(f"\nBounding box: ({lat_min}, {lon_min}) to ({lat_max}, {lon_max})")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Update interval: {args.update_interval}s")
    print("")

    # Create AIS source with bounding box
    source = AISStreamSource(api_key=api_key)
    source.set_bounding_box(lat_min, lon_min, lat_max, lon_max)

    # Connect
    print("Connecting to AISStream.io...")
    if not source.connect():
        print(f"ERROR: Failed to connect - {source.error_message}")
        sys.exit(1)

    print("Connected! Streaming vessel positions...")
    print("Press Ctrl+C to stop\n")

    # Track current bounding box for change detection
    current_bbox = (lat_min, lon_min, lat_max, lon_max)

    try:
        while True:
            # Check for config changes every cycle (auto-follow viewport)
            new_config = load_config()
            new_area = new_config.get('area_tracking', {}).get('bounding_box', {})
            new_bbox = (
                new_area.get('lat_min', lat_min),
                new_area.get('lon_min', lon_min),
                new_area.get('lat_max', lat_max),
                new_area.get('lon_max', lon_max)
            )
            if new_bbox != current_bbox:
                source.set_bounding_box(*new_bbox)
                current_bbox = new_bbox
                source.disconnect()
                source.connect()  # Silent reconnect

            # Get all cached positions
            positions = source.get_all_cached_positions()

            # Get vessel info
            vessel_info = {}
            for pos in positions:
                info = source.fetch_vessel_info(pos.mmsi)
                if info:
                    vessel_info[pos.mmsi] = info

            # Save to file
            count = save_positions(positions, vessel_info)

            # Status update
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] {count} vessels | "
                  f"{source.positions_received} positions received")

            time.sleep(args.update_interval)

    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        source.disconnect()
        print("Disconnected from AISStream.io")


if __name__ == '__main__':
    main()
