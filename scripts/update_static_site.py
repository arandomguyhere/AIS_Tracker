#!/usr/bin/env python3
"""
Update Static Site from Dynamic Template

This script syncs static/index.html to docs/index.html by:
1. Reading the dynamic template from static/index.html
2. Converting API calls to use hardcoded static data
3. Injecting OSINT events from data/output/events_lightweight.json
4. Writing the result to docs/index.html for GitHub Pages
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


def get_static_vessel_data() -> dict:
    """Return hardcoded vessel data for static site."""
    return {
        "vessels": [{
            "id": 1,
            "name": "ZHONG DA 79",
            "mmsi": "413000000",
            "flag_state": "China",
            "vessel_type": "Container Feeder",
            "length_m": 97.0,
            "classification": "confirmed",
            "threat_level": "critical",
            "intel_notes": "Commercial container feeder converted to arsenal ship. Observed with containerized VLS, CIWS, and radar systems at Shanghai shipyard. Underwent refit at Longhai shipyard April-August 2025. Currently moored at industrial pier on Huangpu River, Shanghai. NOT listed in PLAN registry - retains civilian designation despite visible military modifications.",
            "weapons_config": json.dumps({
                "vls_cells": 60,
                "vls_type": "Containerized VLS (4 cells per container)",
                "ciws": "Type 1130 30mm",
                "decoys": "Type 726",
                "possible_missiles": ["CJ-10", "YJ-18", "YJ-21"]
            }),
            "last_lat": 31.2456,
            "last_lon": 121.4890,
            "last_heading": 0
        }],
        "shipyards": [
            {"name": "Hudong-Zhonghua Shipbuilding", "location": "Shanghai", "latitude": 31.3456, "longitude": 121.5234, "geofence_radius_km": 3.0},
            {"name": "Longhai Shipyard", "location": "Fujian", "latitude": 24.4456, "longitude": 117.8234, "geofence_radius_km": 2.0},
            {"name": "Jiangnan Shipyard", "location": "Shanghai", "latitude": 31.3789, "longitude": 121.5678, "geofence_radius_km": 4.0},
            {"name": "Dalian Shipbuilding", "location": "Liaoning", "latitude": 38.9234, "longitude": 121.6345, "geofence_radius_km": 4.0},
            {"name": "Shanghai Huangpu River Pier", "location": "Shanghai", "latitude": 31.2456, "longitude": 121.4890, "geofence_radius_km": 1.5}
        ],
        "positions": [
            {"latitude": 24.4456, "longitude": 117.8234},
            {"latitude": 26.1234, "longitude": 119.9876},
            {"latitude": 28.9876, "longitude": 121.2345},
            {"latitude": 31.2456, "longitude": 121.4890}
        ],
        "osint": [
            {"source_name": "United24 Media", "title": "Cargo Ship or Warship? China Arms Civilian Vessel With 60 Missiles", "source_url": "https://united24media.com/latest-news/cargo-ship-or-warship-china-arms-civilian-vessel-with-60-missiles-in-plain-sight-14585", "summary": "China converted a civilian container ship into an arsenal ship with 60 containerized missiles."},
            {"source_name": "Naval News", "title": "Container Ship Turned Missile Battery Spotted in China", "source_url": "https://www.navalnews.com/naval-news/2025/12/container-ship-turned-missile-battery-spotted-in-china/", "summary": "Naval News analysis of ZHONG DA 79 conversion."},
            {"source_name": "Newsweek", "title": "Photos Show Chinese Cargo Ship Armed With Missile Launchers", "source_url": "https://www.newsweek.com/photos-chinese-cargo-ship-missile-launchers-11270114", "summary": "Newsweek coverage with geopolitical context."},
            {"source_name": "The War Zone", "title": "Chinese Cargo Ship Packed Full Of Modular Missile Launchers", "source_url": "https://www.twz.com/sea/chinese-cargo-ship-packed-full-of-modular-missile-launchers-emerges", "summary": "Technical analysis of containerized weapons systems."}
        ]
    }


def convert_events_to_timeline(osint_data: dict) -> list:
    """Convert OSINT events to timeline format."""
    events = []
    for event in osint_data.get("events", []):
        events.append({
            "severity": event.get("severity", "info"),
            "title": event.get("title", ""),
            "description": f"{event.get('description', '')} [Source: {event.get('source_name', 'OSINT')}]",
            "event_date": event.get("event_date", "").split("T")[0]
        })
    # Sort by date (newest first)
    events.sort(key=lambda x: x.get("event_date", ""), reverse=True)
    return events


def transform_to_static(html_content: str, static_data: dict, osint_events: list, timestamp: str) -> str:
    """Transform dynamic HTML to static version with hardcoded data."""

    # Add OSINT timestamp comment
    comment = f"<!-- OSINT data last updated: {timestamp} -->"
    if "<!-- OSINT data last updated:" in html_content:
        html_content = re.sub(r'<!-- OSINT data last updated:.*?-->', comment, html_content)
    else:
        html_content = html_content.replace("<head>", f"<head>\n    {comment}")

    # Find the <script> section and replace with static version
    script_pattern = r'<script src="https://unpkg\.com/leaflet@1\.9\.4/dist/leaflet\.js"></script>\s*<script>[\s\S]*?</script>'

    # Build static JavaScript
    static_js = generate_static_javascript(static_data, osint_events)

    # Replace the script section
    html_content = re.sub(
        script_pattern,
        f'<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>\n    <script>\n{static_js}\n    </script>',
        html_content
    )

    # Update stats bar to show static counts
    html_content = re.sub(
        r'<div class="stat-value" id="stat-critical">0</div>',
        '<div class="stat-value">1</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="stat-value" id="stat-alerts">0</div>',
        '<div class="stat-value">1</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="stat-value" id="stat-vessels">0</div>',
        '<div class="stat-value" id="live-count">0</div>',
        html_content
    )
    html_content = re.sub(
        r'<div class="stat-label">Vessels</div>',
        '<div class="stat-label">Live</div>',
        html_content
    )

    # Remove add vessel button from map controls (not functional in static mode)
    html_content = re.sub(
        r'<button class="control-btn" id="add-vessel-btn" title="Add Vessel">[\s\S]*?</button>\s*',
        '',
        html_content
    )

    # Add live vessels toggle button if not present
    if 'id="toggle-live"' not in html_content:
        toggle_live_btn = '''<button class="control-btn active" id="toggle-live" title="Toggle Live Vessels" style="background:#3498db;color:white;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
        </button>'''
        html_content = re.sub(
            r'(id="toggle-shipyards"[\s\S]*?</button>)',
            r'\1\n        ' + toggle_live_btn,
            html_content
        )

    # Update list header to show static badge
    html_content = re.sub(
        r'<button class="add-vessel-btn"[^>]*>\+ Add</button>',
        '<span class="static-badge">Static Demo</span>',
        html_content
    )

    # Add static badge CSS if not present
    if '.static-badge' not in html_content:
        static_css = '''
        .static-badge {
            background: #f39c12;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }
'''
        html_content = re.sub(
            r'(\.vessel-list \{ flex: 1; overflow-y: auto; \})',
            r'\1\n' + static_css,
            html_content
        )

    # Remove add/update modals (not functional in static mode)
    html_content = re.sub(
        r'<!-- Add Vessel Modal -->[\s\S]*?<!-- Update Position Modal -->[\s\S]*?</div>\s*</div>\s*</div>',
        '',
        html_content
    )

    # Add static banner at bottom if not present
    if 'class="static-banner"' not in html_content:
        static_banner = '''
    <div class="static-banner">
        Static GitHub Pages demo - <a href="https://github.com/arandomguyhere/AIS_Tracker">View source</a> for full version
    </div>
'''
        # Add before closing body tag
        html_content = re.sub(r'(\s*<script src="https://unpkg)', static_banner + r'\1', html_content)

        # Add static banner CSS
        if '.static-banner' not in html_content:
            banner_css = '''
        .static-banner {
            position: absolute;
            bottom: 24px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(26,26,46,0.9);
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 13px;
            z-index: 1000;
        }

        .static-banner a { color: #e94560; text-decoration: none; }
'''
            html_content = re.sub(
                r'(@media \(max-width: 768px\))',
                banner_css + r'\n        \1',
                html_content
            )

    # Remove map overlay for click mode (not functional in static)
    html_content = re.sub(
        r'<div class="map-overlay"[^>]*>.*?</div>\s*',
        '',
        html_content
    )

    return html_content


def generate_static_javascript(static_data: dict, osint_events: list) -> str:
    """Generate static JavaScript with hardcoded data."""

    vessels_json = json.dumps(static_data["vessels"], indent=8)
    shipyards_json = json.dumps(static_data["shipyards"], indent=12)
    events_json = json.dumps(osint_events, indent=12)
    positions_json = json.dumps(static_data["positions"], indent=12)
    osint_json = json.dumps(static_data["osint"], indent=12)

    return f'''        const vessels = {vessels_json};

        const shipyards = {shipyards_json};

        const events = {events_json};

        const positions = {positions_json};

        const osint = {osint_json};

        let map, vesselMarkers = {{}}, liveVesselMarkers = {{}}, shipyardMarkers = [], shipyardCircles = [], trackLine = null, showShipyards = true, showLiveVessels = true;
        let liveVessels = [];

        // Load live vessels from JSON file
        async function loadLiveVessels() {{
            try {{
                const response = await fetch('live_vessels.json?t=' + Date.now());
                if (!response.ok) return;
                const data = await response.json();
                liveVessels = data.vessels || [];
                renderLiveVessels();
                document.getElementById('live-count').textContent = liveVessels.length;
            }} catch(e) {{
                console.log('No live vessel data available');
            }}
        }}

        // Render live vessels on map
        function renderLiveVessels() {{
            // Clear existing live markers
            Object.values(liveVesselMarkers).forEach(m => map.removeLayer(m));
            liveVesselMarkers = {{}};

            if (!showLiveVessels) return;

            liveVessels.forEach(v => {{
                if (!v.lat || !v.lon) return;
                const color = '#3498db'; // Blue for live vessels
                const marker = L.marker([v.lat, v.lon], {{
                    icon: createShipIcon(color, v.heading || v.course || 0)
                }}).addTo(map);
                marker.bindPopup(`<div class="popup-content">
                    <div class="popup-name">${{v.name || 'MMSI ' + v.mmsi}}</div>
                    <div class="popup-type">${{v.ship_type || 'Unknown'}} ${{v.flag || ''}}</div>
                    <div class="popup-stats">
                        <div class="popup-stat"><div class="popup-stat-value">${{v.lat.toFixed(4)}}</div><div class="popup-stat-label">Lat</div></div>
                        <div class="popup-stat"><div class="popup-stat-value">${{v.lon.toFixed(4)}}</div><div class="popup-stat-label">Lon</div></div>
                        <div class="popup-stat"><div class="popup-stat-value">${{v.speed ? v.speed.toFixed(1) : '-'}}</div><div class="popup-stat-label">Knots</div></div>
                    </div>
                    <div style="font-size:11px;color:#666;margin-top:8px">MMSI: ${{v.mmsi}}</div>
                </div>`, {{ maxWidth: 280 }});
                liveVesselMarkers[v.mmsi] = marker;
            }});
        }}

        // Delete a tracked vessel
        function deleteVessel(id) {{
            const idx = vessels.findIndex(v => v.id === id);
            if (idx > -1) {{
                if (vesselMarkers[id]) {{
                    map.removeLayer(vesselMarkers[id]);
                    delete vesselMarkers[id];
                }}
                vessels.splice(idx, 1);
                renderVesselList();
                document.getElementById('vessel-panel').classList.remove('active');
            }}
        }}

        function createShipIcon(color, heading = 0) {{
            return L.divIcon({{
                html: `<div class="ship-marker" style="transform: rotate(${{heading}}deg)"><svg viewBox="0 0 24 24" fill="${{color}}"><path d="M12 2L4 19h16L12 2z" stroke="white" stroke-width="1"/></svg></div>`,
                className: '', iconSize: [24, 24], iconAnchor: [12, 12]
            }});
        }}

        function getThreatColor(level) {{
            return {{ critical: '#e94560', high: '#f39c12', medium: '#3498db', low: '#27ae60' }}[level] || '#95a5a6';
        }}

        function initMap() {{
            map = L.map('map', {{ center: [28, 118], zoom: 5, zoomControl: false }});
            L.control.zoom({{ position: 'bottomright' }}).addTo(map);
            L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{ maxZoom: 19 }}).addTo(map);
        }}

        function renderVesselList() {{
            document.getElementById('vessel-list').innerHTML = vessels.map(v => `
                <div class="vessel-list-item">
                    <div class="vessel-list-icon ${{v.threat_level}}" onclick="selectVessel(${{v.id}})">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L4 19h16L12 2z"/></svg>
                    </div>
                    <div class="vessel-list-info" onclick="selectVessel(${{v.id}})">
                        <div class="vessel-list-name">${{v.name}}</div>
                        <div class="vessel-list-meta">${{v.flag_state}} - ${{v.vessel_type}}</div>
                        <div class="vessel-list-status">${{v.last_lat.toFixed(2)}}, ${{v.last_lon.toFixed(2)}}</div>
                    </div>
                    <button onclick="event.stopPropagation(); deleteVessel(${{v.id}})" style="background:#e94560;color:white;border:none;border-radius:4px;padding:4px 8px;cursor:pointer;font-size:11px;margin-left:auto;">X</button>
                </div>
            `).join('');
        }}

        function renderVesselMarkers() {{
            vessels.forEach(v => {{
                const marker = L.marker([v.last_lat, v.last_lon], {{ icon: createShipIcon(getThreatColor(v.threat_level), v.last_heading || 0) }}).addTo(map);
                marker.bindPopup(`<div class="popup-content"><div class="popup-header"><div class="popup-icon" style="background:${{getThreatColor(v.threat_level)}}20;color:${{getThreatColor(v.threat_level)}}"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L4 19h16L12 2z"/></svg></div><div><div class="popup-name">${{v.name}}</div><div class="popup-type">${{v.flag_state}} ${{v.vessel_type}}</div></div></div><div class="popup-stats"><div class="popup-stat"><div class="popup-stat-value">${{v.last_lat.toFixed(4)}}</div><div class="popup-stat-label">Lat</div></div><div class="popup-stat"><div class="popup-stat-value">${{v.last_lon.toFixed(4)}}</div><div class="popup-stat-label">Lon</div></div></div><button class="popup-btn" onclick="selectVessel(${{v.id}})">View Details</button></div>`, {{ maxWidth: 300 }});
                marker.on('click', () => selectVessel(v.id));
                vesselMarkers[v.id] = marker;
            }});
        }}

        function renderShipyards() {{
            shipyardMarkers.forEach(m => map.removeLayer(m));
            shipyardCircles.forEach(c => map.removeLayer(c));
            shipyardMarkers = []; shipyardCircles = [];
            if (!showShipyards) return;
            shipyards.forEach(s => {{
                const marker = L.circleMarker([s.latitude, s.longitude], {{ radius: 6, fillColor: '#f39c12', color: '#fff', weight: 2, fillOpacity: 0.8 }}).addTo(map);
                marker.bindPopup(`<b>${{s.name}}</b><br>${{s.location}}`);
                shipyardMarkers.push(marker);
                const circle = L.circle([s.latitude, s.longitude], {{ radius: s.geofence_radius_km * 1000, color: '#f39c12', fillColor: '#f39c12', fillOpacity: 0.1, weight: 1, dashArray: '4' }}).addTo(map);
                shipyardCircles.push(circle);
            }});
        }}

        function selectVessel(id) {{
            const v = vessels.find(x => x.id === id);
            if (!v) return;
            map.setView([v.last_lat, v.last_lon], 8);
            if (trackLine) map.removeLayer(trackLine);
            trackLine = L.polyline(positions.map(p => [p.latitude, p.longitude]), {{ color: getThreatColor(v.threat_level), weight: 2, opacity: 0.7, dashArray: '6' }}).addTo(map);

            let weapons = {{}}; try {{ weapons = JSON.parse(v.weapons_config || '{{}}'); }} catch(e) {{}}
            document.getElementById('vessel-panel-content').innerHTML = `
                <div class="panel-header">
                    <button class="panel-close" onclick="document.getElementById('vessel-panel').classList.remove('active')">&times;</button>
                    <div class="vessel-icon-large" style="background:${{getThreatColor(v.threat_level)}}20;color:${{getThreatColor(v.threat_level)}}"><svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L4 19h16L12 2z"/></svg></div>
                    <div class="vessel-name">${{v.name}}</div>
                    <div class="vessel-type">${{v.flag_state}} - ${{v.vessel_type}}</div>
                    <div class="threat-indicator threat-${{v.threat_level}}">${{v.threat_level}}</div>
                </div>
                <div class="panel-section"><div class="section-title">Position</div><div class="position-display"><div class="coord-box"><div class="coord-label">Latitude</div><div class="coord-value">${{v.last_lat.toFixed(4)}}</div></div><div class="coord-box"><div class="coord-label">Longitude</div><div class="coord-value">${{v.last_lon.toFixed(4)}}</div></div></div></div>
                <div class="panel-section"><div class="section-title">Details</div><div class="info-row"><span class="info-label">MMSI</span><span class="info-value">${{v.mmsi || '-'}}</span></div><div class="info-row"><span class="info-label">Classification</span><span class="info-value">${{v.classification}}</span></div><div class="info-row"><span class="info-label">Length</span><span class="info-value">${{v.length_m}}m</span></div></div>
                <div class="panel-section"><div class="section-title">Intelligence</div><div class="intel-box">${{v.intel_notes}}</div></div>
                <div class="panel-section"><div class="section-title">Weapons</div><div class="weapons-grid">${{weapons.vls_cells ? `<div class="weapon-item"><span class="weapon-name">VLS Cells</span><span class="weapon-value">${{weapons.vls_cells}}</span></div>` : ''}}${{weapons.ciws ? `<div class="weapon-item"><span class="weapon-name">CIWS</span><span class="weapon-value">${{weapons.ciws}}</span></div>` : ''}}${{weapons.decoys ? `<div class="weapon-item"><span class="weapon-name">Decoys</span><span class="weapon-value">${{weapons.decoys}}</span></div>` : ''}}${{weapons.possible_missiles ? `<div class="weapon-item"><span class="weapon-name">Missiles</span><span class="weapon-value">${{weapons.possible_missiles.join(', ')}}</span></div>` : ''}}</div></div>
                <div class="panel-section"><div class="section-title">Timeline</div><div class="timeline">${{events.slice(0, 8).map(e => `<div class="timeline-item"><div class="timeline-dot severity-${{e.severity === 'critical' ? 'critical' : e.severity === 'high' ? 'high' : e.severity === 'medium' ? 'medium' : 'info'}}"></div><div class="timeline-date">${{new Date(e.event_date).toLocaleDateString()}}</div><div class="timeline-title">${{e.title}}</div><div class="timeline-desc">${{e.description}}</div></div>`).join('')}}</div></div>
                <div class="panel-section"><div class="section-title">OSINT Reports</div>${{osint.map(r => `<div style="margin-bottom:12px;padding:12px;background:#f8f9fa;border-radius:8px"><div style="font-size:11px;color:#e94560;text-transform:uppercase;margin-bottom:4px">${{r.source_name}}</div><a href="${{r.source_url}}" target="_blank" style="font-weight:500;color:#333;text-decoration:none">${{r.title}}</a><div style="font-size:12px;color:#666;margin-top:4px">${{r.summary}}</div></div>`).join('')}}</div>`;
            document.getElementById('vessel-panel').classList.add('active');
        }}

        const searchInput = document.getElementById('search-input');
        const searchResults = document.getElementById('search-results');
        searchInput.addEventListener('input', e => {{
            const q = e.target.value.toLowerCase().trim();
            if (!q) {{ searchResults.classList.remove('active'); return; }}
            const matches = vessels.filter(v => v.name.toLowerCase().includes(q) || (v.mmsi && v.mmsi.includes(q)));
            if (!matches.length) {{ searchResults.classList.remove('active'); return; }}
            searchResults.innerHTML = matches.map(v => `<div class="search-result-item" onclick="selectVessel(${{v.id}}); searchResults.classList.remove('active'); searchInput.value = '';"><div class="result-icon" style="background:${{getThreatColor(v.threat_level)}}20;color:${{getThreatColor(v.threat_level)}}"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L4 19h16L12 2z"/></svg></div><div class="result-info"><div class="result-name">${{v.name}}</div><div class="result-meta">${{v.flag_state}} - ${{v.mmsi || ''}}</div></div></div>`).join('');
            searchResults.classList.add('active');
        }});

        document.getElementById('toggle-list').addEventListener('click', () => {{ document.getElementById('list-panel').classList.toggle('active'); document.getElementById('toggle-list').classList.toggle('active'); }});
        document.getElementById('toggle-shipyards').addEventListener('click', () => {{ showShipyards = !showShipyards; document.getElementById('toggle-shipyards').classList.toggle('active', showShipyards); renderShipyards(); }});
        document.addEventListener('keydown', e => {{ if (e.key === 'Escape') document.getElementById('vessel-panel').classList.remove('active'); }});

        document.getElementById('toggle-live').addEventListener('click', () => {{ showLiveVessels = !showLiveVessels; document.getElementById('toggle-live').classList.toggle('active', showLiveVessels); renderLiveVessels(); }});

        document.addEventListener('DOMContentLoaded', () => {{
            initMap();
            renderVesselList();
            renderVesselMarkers();
            renderShipyards();
            loadLiveVessels();
            // Auto-refresh live vessels every 10 seconds
            setInterval(loadLiveVessels, 10000);
        }});'''


def main():
    print("=" * 60)
    print("Syncing Static Site from Dynamic Template")
    print("=" * 60)

    output_dir = PROJECT_ROOT / "data" / "output"
    source_html = PROJECT_ROOT / "static" / "index.html"
    target_html = PROJECT_ROOT / "docs" / "index.html"

    # Load OSINT events
    print("\n[1] Loading OSINT events...")
    osint_data = load_osint_events(output_dir)
    event_count = len(osint_data.get("events", []))
    print(f"    Found {event_count} events")

    # Convert events to timeline format
    osint_events = convert_events_to_timeline(osint_data)

    # Read source HTML
    print("\n[2] Reading static/index.html template...")
    if not source_html.exists():
        print(f"    ERROR: Source file not found: {source_html}")
        return

    with open(source_html, "r") as f:
        html_content = f.read()
    print(f"    Read {len(html_content)} bytes")

    # Get static data
    static_data = get_static_vessel_data()

    # Get timestamp
    timestamp = osint_data.get("generated_at", datetime.utcnow().isoformat() + "Z")

    # Transform to static version
    print("\n[3] Transforming to static version...")
    html_content = transform_to_static(html_content, static_data, osint_events, timestamp)

    # Write updated HTML
    print("\n[4] Writing docs/index.html...")
    with open(target_html, "w") as f:
        f.write(html_content)
    print(f"    Wrote {len(html_content)} bytes")

    print(f"\n    Synced from static/index.html")
    print(f"    Included {len(osint_events)} OSINT events in timeline")
    print("\n" + "=" * 60)
    print("Static site sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
