#!/usr/bin/env python3
"""
Arsenal Ship Tracker API Server
Zero external dependencies - uses only Python standard library
"""

import json
import os
import sqlite3
import sys
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from math import radians, sin, cos, sqrt, atan2
from urllib.parse import urlparse, parse_qs

# Configuration
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'arsenal_tracker.db')
SCHEMA_PATH = os.path.join(SCRIPT_DIR, 'schema.sql')
STATIC_DIR = os.path.join(SCRIPT_DIR, 'static')
DOCS_DIR = os.path.join(SCRIPT_DIR, 'docs')
PHOTOS_DIR = os.path.join(STATIC_DIR, 'photos')
LIVE_VESSELS_PATH = os.path.join(DOCS_DIR, 'live_vessels.json')
CONFIG_PATH = os.path.join(SCRIPT_DIR, 'ais_config.json')
PORT = 8080


def get_db():
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in kilometers."""
    R = 6371  # Earth's radius in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c


def dict_from_row(row):
    """Convert sqlite3.Row to dictionary."""
    return dict(zip(row.keys(), row)) if row else None


def init_database():
    """Initialize database with schema."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing database: {DB_PATH}")

    conn = get_db()
    with open(SCHEMA_PATH, 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


# =============================================================================
# API Handlers
# =============================================================================

def get_vessels():
    """Get all vessels with their latest position."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT v.*,
               p.latitude as last_lat,
               p.longitude as last_lon,
               p.heading as last_heading,
               p.speed_knots as last_speed,
               p.timestamp as last_position_time,
               p.source as position_source
        FROM vessels v
        LEFT JOIN (
            SELECT vessel_id, latitude, longitude, heading, speed_knots, timestamp, source,
                   ROW_NUMBER() OVER (PARTITION BY vessel_id ORDER BY timestamp DESC) as rn
            FROM positions
        ) p ON v.id = p.vessel_id AND p.rn = 1
        ORDER BY v.threat_level DESC, v.name
    ''')
    vessels = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return vessels


def get_vessel(vessel_id):
    """Get single vessel with full details."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT v.*,
               p.latitude as last_lat,
               p.longitude as last_lon,
               p.heading as last_heading,
               p.speed_knots as last_speed,
               p.timestamp as last_position_time
        FROM vessels v
        LEFT JOIN (
            SELECT vessel_id, latitude, longitude, heading, speed_knots, timestamp,
                   ROW_NUMBER() OVER (PARTITION BY vessel_id ORDER BY timestamp DESC) as rn
            FROM positions
        ) p ON v.id = p.vessel_id AND p.rn = 1
        WHERE v.id = ?
    ''', (vessel_id,))
    vessel = dict_from_row(cursor.fetchone())
    conn.close()
    return vessel


def get_vessel_track(vessel_id, days=90):
    """Get position history for vessel."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT * FROM positions
        WHERE vessel_id = ?
        AND timestamp >= datetime('now', ?)
        ORDER BY timestamp ASC
    ''', (vessel_id, f'-{days} days'))
    positions = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return positions


def get_vessel_events(vessel_id):
    """Get events timeline for vessel."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT * FROM events
        WHERE vessel_id = ?
        ORDER BY event_date DESC
    ''', (vessel_id,))
    events = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return events


def get_shipyards():
    """Get all monitored shipyards."""
    conn = get_db()
    cursor = conn.execute('SELECT * FROM shipyards ORDER BY name')
    shipyards = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return shipyards


def get_events(severity=None, limit=50):
    """Get all events, optionally filtered by severity."""
    conn = get_db()
    if severity:
        cursor = conn.execute('''
            SELECT e.*, v.name as vessel_name
            FROM events e
            JOIN vessels v ON e.vessel_id = v.id
            WHERE e.severity = ?
            ORDER BY e.event_date DESC
            LIMIT ?
        ''', (severity, limit))
    else:
        cursor = conn.execute('''
            SELECT e.*, v.name as vessel_name
            FROM events e
            JOIN vessels v ON e.vessel_id = v.id
            ORDER BY e.event_date DESC
            LIMIT ?
        ''', (limit,))
    events = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return events


def get_alerts(acknowledged=False):
    """Get alerts, by default unacknowledged only."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT a.*, v.name as vessel_name
        FROM alerts a
        LEFT JOIN vessels v ON a.vessel_id = v.id
        WHERE a.acknowledged = ?
        ORDER BY a.created_at DESC
    ''', (1 if acknowledged else 0,))
    alerts = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return alerts


def get_osint_reports(vessel_id=None):
    """Get OSINT reports, optionally filtered by vessel."""
    conn = get_db()
    if vessel_id:
        cursor = conn.execute('''
            SELECT o.*, v.name as vessel_name
            FROM osint_reports o
            LEFT JOIN vessels v ON o.vessel_id = v.id
            WHERE o.vessel_id = ?
            ORDER BY o.publish_date DESC
        ''', (vessel_id,))
    else:
        cursor = conn.execute('''
            SELECT o.*, v.name as vessel_name
            FROM osint_reports o
            LEFT JOIN vessels v ON o.vessel_id = v.id
            ORDER BY o.publish_date DESC
        ''')
    reports = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return reports


def get_watchlist():
    """Get watchlist with vessel details."""
    conn = get_db()
    cursor = conn.execute('''
        SELECT w.*, v.name, v.mmsi, v.classification, v.threat_level,
               p.latitude as last_lat, p.longitude as last_lon, p.timestamp as last_seen
        FROM watchlist w
        JOIN vessels v ON w.vessel_id = v.id
        LEFT JOIN (
            SELECT vessel_id, latitude, longitude, timestamp,
                   ROW_NUMBER() OVER (PARTITION BY vessel_id ORDER BY timestamp DESC) as rn
            FROM positions
        ) p ON v.id = p.vessel_id AND p.rn = 1
        ORDER BY w.priority ASC
    ''')
    watchlist = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return watchlist


def get_stats():
    """Get dashboard statistics."""
    conn = get_db()
    stats = {}

    cursor = conn.execute('SELECT COUNT(*) as count FROM vessels')
    stats['total_vessels'] = cursor.fetchone()['count']

    cursor = conn.execute("SELECT COUNT(*) as count FROM vessels WHERE classification = 'confirmed'")
    stats['confirmed_arsenal'] = cursor.fetchone()['count']

    cursor = conn.execute("SELECT COUNT(*) as count FROM vessels WHERE threat_level = 'critical'")
    stats['critical_threats'] = cursor.fetchone()['count']

    cursor = conn.execute('SELECT COUNT(*) as count FROM alerts WHERE acknowledged = 0')
    stats['active_alerts'] = cursor.fetchone()['count']

    cursor = conn.execute('SELECT COUNT(*) as count FROM watchlist')
    stats['watchlist_count'] = cursor.fetchone()['count']

    cursor = conn.execute('SELECT COUNT(*) as count FROM osint_reports')
    stats['osint_reports'] = cursor.fetchone()['count']

    cursor = conn.execute('SELECT COUNT(*) as count FROM events')
    stats['total_events'] = cursor.fetchone()['count']

    cursor = conn.execute("SELECT COUNT(*) as count FROM events WHERE severity IN ('critical', 'high')")
    stats['high_severity_events'] = cursor.fetchone()['count']

    conn.close()
    return stats


def get_live_vessels():
    """Get live vessels from stream_area.py output file."""
    if not os.path.exists(LIVE_VESSELS_PATH):
        return {'timestamp': None, 'vessel_count': 0, 'vessels': []}

    try:
        with open(LIVE_VESSELS_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[Error] Failed to read live vessels: {e}")
        return {'timestamp': None, 'vessel_count': 0, 'vessels': []}


def add_vessel(data):
    """Add new vessel to tracking."""
    conn = get_db()
    cursor = conn.execute('''
        INSERT INTO vessels (name, mmsi, imo, flag_state, vessel_type, classification, threat_level, intel_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name'),
        data.get('mmsi'),
        data.get('imo'),
        data.get('flag_state'),
        data.get('vessel_type'),
        data.get('classification', 'monitoring'),
        data.get('threat_level', 'unknown'),
        data.get('intel_notes')
    ))
    vessel_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {'id': vessel_id, 'status': 'created'}


def add_position(vessel_id, data):
    """Add position update for vessel."""
    conn = get_db()
    conn.execute('''
        INSERT INTO positions (vessel_id, latitude, longitude, heading, speed_knots, source)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        vessel_id,
        data.get('latitude'),
        data.get('longitude'),
        data.get('heading'),
        data.get('speed_knots'),
        data.get('source', 'manual')
    ))
    conn.execute('UPDATE vessels SET last_updated = CURRENT_TIMESTAMP WHERE id = ?', (vessel_id,))
    conn.commit()
    conn.close()
    return {'status': 'position_logged'}


def add_event(vessel_id, data):
    """Add event for vessel."""
    conn = get_db()
    conn.execute('''
        INSERT INTO events (vessel_id, event_type, severity, title, description, source, source_url, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        vessel_id,
        data.get('event_type'),
        data.get('severity', 'info'),
        data.get('title'),
        data.get('description'),
        data.get('source'),
        data.get('source_url'),
        data.get('latitude'),
        data.get('longitude')
    ))
    conn.commit()
    conn.close()
    return {'status': 'event_logged'}


def add_osint_report(data):
    """Add OSINT report."""
    conn = get_db()
    cursor = conn.execute('''
        INSERT INTO osint_reports (vessel_id, title, source_name, source_url, publish_date, summary, full_content, key_findings, reliability, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('vessel_id'),
        data.get('title'),
        data.get('source_name'),
        data.get('source_url'),
        data.get('publish_date'),
        data.get('summary'),
        data.get('full_content'),
        json.dumps(data.get('key_findings', [])),
        data.get('reliability', 'unconfirmed'),
        data.get('tags')
    ))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {'id': report_id, 'status': 'created'}


def acknowledge_alert(alert_id):
    """Acknowledge an alert."""
    conn = get_db()
    conn.execute('''
        UPDATE alerts SET acknowledged = 1, acknowledged_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (alert_id,))
    conn.commit()
    conn.close()
    return {'status': 'acknowledged'}


def search_news(query, max_results=10):
    """Search Google News for vessel information."""
    try:
        from gnews import GNews
        gn = GNews(language='en', country='US', max_results=max_results)
        results = gn.get_news(query)

        articles = []
        for item in results:
            articles.append({
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'source': item.get('publisher', {}).get('title', 'Unknown'),
                'published': item.get('published date', ''),
                'description': item.get('description', '')
            })

        return {'query': query, 'count': len(articles), 'articles': articles}

    except ImportError:
        return {'error': 'gnews not installed. Run: pip install gnews', 'articles': []}
    except Exception as e:
        print(f"[Error] News search failed: {e}")
        return {'error': str(e), 'articles': []}


def track_live_vessel(data):
    """Add a live vessel to tracking with its current position."""
    conn = get_db()

    # Check if vessel already exists by MMSI
    mmsi = data.get('mmsi')
    if mmsi:
        cursor = conn.execute('SELECT id FROM vessels WHERE mmsi = ?', (str(mmsi),))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return {'error': 'Vessel with this MMSI already tracked', 'vessel_id': existing['id']}

    # Process weapons config
    weapons_config = data.get('weapons_config')
    if weapons_config and isinstance(weapons_config, dict):
        weapons_config = json.dumps(weapons_config)
    elif weapons_config:
        weapons_config = str(weapons_config)
    else:
        weapons_config = None

    # Insert new vessel with all fields
    cursor = conn.execute('''
        INSERT INTO vessels (name, mmsi, imo, flag_state, vessel_type, length_m,
                            classification, threat_level, intel_notes, weapons_config)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('name', f"MMSI {mmsi}"),
        str(mmsi) if mmsi else None,
        data.get('imo'),
        data.get('flag'),
        data.get('ship_type', data.get('vessel_type')),
        data.get('length_m'),
        data.get('classification', 'monitoring'),
        data.get('threat_level', 'unknown'),
        data.get('intel_notes', 'Added from live AIS stream'),
        weapons_config
    ))
    vessel_id = cursor.lastrowid

    # Add initial position if available
    lat = data.get('lat')
    lon = data.get('lon')
    if lat and lon:
        conn.execute('''
            INSERT INTO positions (vessel_id, latitude, longitude, heading, speed_knots, source)
            VALUES (?, ?, ?, ?, ?, 'ais')
        ''', (vessel_id, lat, lon, data.get('heading'), data.get('speed')))

    conn.commit()
    conn.close()
    return {'id': vessel_id, 'status': 'created', 'name': data.get('name', f"MMSI {mmsi}")}


def update_vessel(vessel_id, data):
    """Update vessel details."""
    conn = get_db()

    # Build update query dynamically based on provided fields
    updates = []
    values = []

    if 'name' in data:
        updates.append('name = ?')
        values.append(data['name'])
    if 'vessel_type' in data:
        updates.append('vessel_type = ?')
        values.append(data['vessel_type'])
    if 'flag_state' in data:
        updates.append('flag_state = ?')
        values.append(data['flag_state'])
    if 'classification' in data:
        updates.append('classification = ?')
        values.append(data['classification'])
    if 'threat_level' in data:
        updates.append('threat_level = ?')
        values.append(data['threat_level'])
    if 'intel_notes' in data:
        updates.append('intel_notes = ?')
        values.append(data['intel_notes'])

    if not updates:
        conn.close()
        return {'error': 'No fields to update'}

    updates.append('last_updated = CURRENT_TIMESTAMP')
    values.append(vessel_id)

    conn.execute(f'''
        UPDATE vessels SET {', '.join(updates)} WHERE id = ?
    ''', values)
    conn.commit()
    conn.close()
    return {'status': 'updated', 'vessel_id': vessel_id}


def delete_vessel(vessel_id):
    """Delete a vessel and all related data."""
    conn = get_db()

    # Delete related data first
    conn.execute('DELETE FROM positions WHERE vessel_id = ?', (vessel_id,))
    conn.execute('DELETE FROM events WHERE vessel_id = ?', (vessel_id,))
    conn.execute('DELETE FROM alerts WHERE vessel_id = ?', (vessel_id,))
    conn.execute('DELETE FROM watchlist WHERE vessel_id = ?', (vessel_id,))
    conn.execute('DELETE FROM osint_reports WHERE vessel_id = ?', (vessel_id,))

    # Delete the vessel
    conn.execute('DELETE FROM vessels WHERE id = ?', (vessel_id,))
    conn.commit()
    conn.close()
    return {'status': 'deleted', 'vessel_id': vessel_id}


def update_bounding_box(data):
    """Update the bounding box in ais_config.json."""
    try:
        # Load existing config
        config = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)

        # Update bounding box
        if 'area_tracking' not in config:
            config['area_tracking'] = {'enabled': True, 'bounding_box': {}}

        config['area_tracking']['bounding_box'] = {
            'lat_min': data.get('lat_min'),
            'lon_min': data.get('lon_min'),
            'lat_max': data.get('lat_max'),
            'lon_max': data.get('lon_max'),
            'description': data.get('description', 'Custom area')
        }

        # Save config
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)

        return {
            'status': 'updated',
            'message': 'Bounding box saved. Restart stream_area.py to apply.',
            'bounding_box': config['area_tracking']['bounding_box']
        }

    except Exception as e:
        return {'error': str(e)}


def save_vessel_photo(vessel_id, photo_data, filename):
    """Save a vessel photo and update database."""
    import base64

    # Ensure photos directory exists
    os.makedirs(PHOTOS_DIR, exist_ok=True)

    # Decode base64 image data
    try:
        # Remove data URL prefix if present
        if ',' in photo_data:
            photo_data = photo_data.split(',')[1]

        image_bytes = base64.b64decode(photo_data)

        # Generate filename
        ext = os.path.splitext(filename)[1] or '.jpg'
        photo_filename = f"vessel_{vessel_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        photo_path = os.path.join(PHOTOS_DIR, photo_filename)

        # Save file
        with open(photo_path, 'wb') as f:
            f.write(image_bytes)

        # Update database with photo path
        conn = get_db()
        conn.execute('''
            UPDATE vessels SET photo_url = ?, last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (f'/photos/{photo_filename}', vessel_id))
        conn.commit()
        conn.close()

        return {
            'status': 'uploaded',
            'photo_url': f'/photos/{photo_filename}',
            'vessel_id': vessel_id
        }

    except Exception as e:
        return {'error': str(e)}


# =============================================================================
# HTTP Handler
# =============================================================================

class TrackerHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for the tracker API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def send_json(self, data, status=200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # API routes
        if path == '/api/vessels':
            return self.send_json(get_vessels())

        elif path == '/api/live-vessels':
            return self.send_json(get_live_vessels())

        elif path.startswith('/api/vessels/') and path.endswith('/track'):
            vessel_id = int(path.split('/')[3])
            days = int(params.get('days', [90])[0])
            return self.send_json(get_vessel_track(vessel_id, days))

        elif path.startswith('/api/vessels/') and path.endswith('/events'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(get_vessel_events(vessel_id))

        elif path.startswith('/api/vessels/'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(get_vessel(vessel_id))

        elif path == '/api/shipyards':
            return self.send_json(get_shipyards())

        elif path == '/api/events':
            severity = params.get('severity', [None])[0]
            limit = int(params.get('limit', [50])[0])
            return self.send_json(get_events(severity, limit))

        elif path == '/api/alerts':
            acknowledged = params.get('acknowledged', ['false'])[0].lower() == 'true'
            return self.send_json(get_alerts(acknowledged))

        elif path == '/api/osint':
            vessel_id = params.get('vessel_id', [None])[0]
            if vessel_id:
                vessel_id = int(vessel_id)
            return self.send_json(get_osint_reports(vessel_id))

        elif path == '/api/watchlist':
            return self.send_json(get_watchlist())

        elif path == '/api/stats':
            return self.send_json(get_stats())

        # Static files
        else:
            super().do_GET()

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length else '{}'
        data = json.loads(body) if body else {}

        if path == '/api/vessels':
            return self.send_json(add_vessel(data), 201)

        elif path.startswith('/api/vessels/') and path.endswith('/position'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(add_position(vessel_id, data), 201)

        elif path.startswith('/api/vessels/') and path.endswith('/event'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(add_event(vessel_id, data), 201)

        elif path == '/api/osint':
            return self.send_json(add_osint_report(data), 201)

        elif path.startswith('/api/alerts/') and path.endswith('/acknowledge'):
            alert_id = int(path.split('/')[3])
            return self.send_json(acknowledge_alert(alert_id))

        elif path == '/api/search-news':
            query = data.get('query', '')
            max_results = data.get('max_results', 10)
            if not query:
                return self.send_json({'error': 'Query required'}, 400)
            return self.send_json(search_news(query, max_results))

        elif path == '/api/track-vessel':
            if not data.get('mmsi'):
                return self.send_json({'error': 'MMSI required'}, 400)
            return self.send_json(track_live_vessel(data), 201)

        elif path.startswith('/api/vessels/') and path.endswith('/update'):
            vessel_id = int(path.split('/')[3])
            return self.send_json(update_vessel(vessel_id, data))

        elif path.startswith('/api/vessels/') and path.endswith('/photo'):
            vessel_id = int(path.split('/')[3])
            photo_data = data.get('photo')
            filename = data.get('filename', 'photo.jpg')
            if not photo_data:
                return self.send_json({'error': 'Photo data required'}, 400)
            return self.send_json(save_vessel_photo(vessel_id, photo_data, filename))

        elif path == '/api/config/bounding-box':
            required = ['lat_min', 'lon_min', 'lat_max', 'lon_max']
            if not all(k in data for k in required):
                return self.send_json({'error': 'lat_min, lon_min, lat_max, lon_max required'}, 400)
            return self.send_json(update_bounding_box(data))

        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_DELETE(self):
        """Handle DELETE requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        # DELETE /api/vessels/:id
        if path.startswith('/api/vessels/'):
            parts = path.split('/')
            if len(parts) == 4:  # /api/vessels/123
                vessel_id = int(parts[3])
                return self.send_json(delete_vessel(vessel_id))

        self.send_json({'error': 'Not found'}, 404)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        """Custom log format."""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {args[0]}")


def migrate_database():
    """Run database migrations."""
    conn = get_db()
    # Add photo_url column if it doesn't exist
    try:
        conn.execute('SELECT photo_url FROM vessels LIMIT 1')
    except sqlite3.OperationalError:
        print("Adding photo_url column to vessels table...")
        conn.execute('ALTER TABLE vessels ADD COLUMN photo_url TEXT')
        conn.commit()
    conn.close()


def run_server():
    """Start the HTTP server."""
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(PHOTOS_DIR, exist_ok=True)

    # Auto-initialize database if it doesn't exist
    if not os.path.exists(DB_PATH):
        print("Database not found. Initializing...")
        init_database()

    # Run migrations
    migrate_database()

    server = HTTPServer(('0.0.0.0', PORT), TrackerHandler)
    print(f"Arsenal Ship Tracker running on http://localhost:{PORT}")
    print(f"Live vessels file: {LIVE_VESSELS_PATH}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'init':
        init_database()
    else:
        run_server()
