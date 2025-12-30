# Arsenal Ship Tracker

Maritime gray zone monitoring system for tracking vessels suspected of civilian-to-military conversion, containerized weapons systems, and dual-use activity.

## Live Demo

**[View Static Demo on GitHub Pages](https://arandomguyhere.github.io/AIS_Tracker/)**

## Overview

This proof-of-concept tracker monitors vessels like **ZHONG DA 79** - a Chinese container feeder converted to an arsenal ship carrying 60+ containerized missiles, CIWS, and radar while retaining civilian classification.

## Features

### Core Tracking
- **VesselFinder-style UI** - Full-screen dark map with slide-in panels
- **Live AIS streaming** - Real-time vessel positions via aisstream.io WebSocket
- **Multi-source AIS** - Support for AISStream, AISHub, and Marinesia APIs
- **Ship markers with heading** - Vessel icons rotate based on course
- **Vessel-type color coding** - Different colors for cargo, tanker, passenger, military, etc.
- **Viewport-optimized rendering** - Handles 10,000+ live vessels without browser lag
- **SQLite WAL mode** - Better concurrent database access

### Vessel Management
- **Add/Edit/Delete vessels** - Full CRUD operations with UI forms
- **Track live vessels** - Add any AIS vessel to your tracking database
- **Photo upload** - Attach vessel images with base64 storage
- **Comprehensive vessel forms** - Track weapons config, classification, threat levels
- **MMSI-based enrichment** - Auto-populate vessel data from tracking databases

### Intelligence Features
- **AI-powered vessel analysis** - OpenAI integration for strategic intelligence
- **MMSI vessel lookups** - Query VesselFinder, MarineTraffic, ITU MARS databases
- **Auto-update fields** - Automatically populate flag, type, IMO from lookups
- **Targeted search queries** - Uses exact vessel names and IMO for accurate results
- **BLUF assessments** - Bottom Line Up Front risk analysis (LOW/MODERATE/HIGH/CRITICAL)
- **Analysis persistence** - Save and retrieve AI analysis for each vessel
- **News correlation** - Automated news search with relevance filtering
- **OSINT integration** - Link to news articles and intelligence reports

### Weather & Environment
- **Weather enrichment** - Open-Meteo API integration (no API key required)
- **Marine conditions** - Wave height, sea state, swell data
- **Vessel weather** - Get weather at any vessel's current position

### Geospatial
- **Shipyard geofences** - Monitor vessel proximity to facilities of interest
- **Position tracking** - Historical vessel track display
- **Bounding box configuration** - Define AIS streaming areas via UI

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database with seed data
python3 server.py init

# Start live AIS streaming (in separate terminal)
python3 stream_area.py

# Start the web server
python3 server.py

# Open http://localhost:8080 in browser
```

### Environment Variables

```bash
# Required for AI intelligence features
export OPENAI_API_KEY="your-openai-api-key"

# Required for live AIS streaming (primary source)
export AISSTREAM_API_KEY="your-aisstream-api-key"

# Optional: AISHub community data sharing (register at aishub.net)
export AISHUB_USERNAME="your-aishub-username"
```

## Components

| File | Description |
|------|-------------|
| `server.py` | REST API server with vessel intel, weather & news search |
| `vessel_intel.py` | AI-powered vessel intelligence with MMSI lookups |
| `weather.py` | Weather enrichment via Open-Meteo API |
| `stream_area.py` | Live AIS streaming from aisstream.io |
| `schema.sql` | SQLite database schema + seed data |
| `static/index.html` | VesselFinder-style interactive dashboard |
| `docs/index.html` | Static GitHub Pages demo version |
| `requirements.txt` | Python dependencies (openai) |
| `ais_ingest.py` | AIS data ingestion module |
| `ais_config.json` | AIS source configuration (auto-created) |
| `ais_sources/` | Multi-source AIS integration (AISStream, AISHub, Marinesia) |
| `osint/` | OSINT correlation and monitoring tools |

## API Endpoints

### Vessel Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vessels` | All vessels with latest position |
| GET | `/api/vessels/:id` | Single vessel details |
| GET | `/api/vessels/:id/track?days=90` | Position history |
| GET | `/api/vessels/:id/events` | Event timeline |
| POST | `/api/vessels` | Add vessel |
| PUT | `/api/vessels/:id` | Update vessel |
| DELETE | `/api/vessels/:id` | Delete vessel |
| POST | `/api/vessels/:id/position` | Log position |
| POST | `/api/vessels/:id/event` | Log event |
| POST | `/api/track-vessel` | Add live vessel to tracking |

### Intelligence Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/vessel-intel` | Full AI analysis with news search |
| POST | `/api/vessel-bluf` | Quick BLUF risk assessment |
| POST | `/api/search-news` | Search Google News for vessel |
| GET | `/api/osint?vessel_id=1` | OSINT reports |
| POST | `/api/osint` | Add OSINT report |

### Weather Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/weather?lat=31.2&lon=121.4` | Weather at coordinates |
| GET | `/api/vessels/:id/weather` | Weather at vessel position |

### Other Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/shipyards` | Monitored facilities |
| GET | `/api/events?severity=critical&limit=50` | All events (filterable) |
| GET | `/api/alerts` | Unacknowledged alerts |
| GET | `/api/watchlist` | Watchlist with vessel details |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/live-vessels` | Live AIS streaming vessels |
| GET | `/api/vessels/:id/analysis` | Get saved AI analysis |
| POST | `/api/alerts/:id/acknowledge` | Acknowledge alert |
| POST | `/api/save-config` | Save AIS bounding box config |
| POST | `/api/upload-photo/:id` | Upload vessel photo |

### Example API Calls

```bash
# Get all vessels
curl http://localhost:8080/api/vessels

# Full AI analysis for a vessel
curl -X POST http://localhost:8080/api/vessel-intel \
  -H "Content-Type: application/json" \
  -d '{"vessel": {"name": "ZHONG DA 79", "mmsi": "413000000", "vessel_type": "Container Feeder", "flag_state": "China"}}'

# Quick BLUF assessment
curl -X POST http://localhost:8080/api/vessel-bluf \
  -H "Content-Type: application/json" \
  -d '{"vessel": {"name": "ZHONG DA 79", "classification": "confirmed", "threat_level": "critical"}}'

# Add position update
curl -X POST http://localhost:8080/api/vessels/1/position \
  -H "Content-Type: application/json" \
  -d '{"latitude": 31.24, "longitude": 121.49, "source": "manual"}'

# Update vessel
curl -X PUT http://localhost:8080/api/vessels/1 \
  -H "Content-Type: application/json" \
  -d '{"threat_level": "critical", "intel_notes": "Updated intelligence"}'
```

## AI Intelligence Features

The vessel intelligence module (`vessel_intel.py`) provides:

### MMSI-Based Vessel Lookups
When you run AI Analysis, the system queries multiple vessel tracking databases:
- **VesselFinder** - Vessel details, IMO, flag
- **MarineTraffic** - Comprehensive vessel data, dimensions, year built
- **ITU MARS** - Official MMSI registry with owner information
- **MyShipTracking** - Additional vessel data

### Auto-Update Fields
After analysis, the system automatically updates the vessel record with:
- Flag state, vessel type, IMO number
- Callsign, owner, dimensions
- Classification and threat level recommendations

### Targeted Search Queries
Improved search accuracy with:
- Exact vessel name searches: `"GRACEFUL STARS" vessel`
- IMO-based searches: `IMO 9123456 ship`
- Relevance filtering (only shows articles mentioning the vessel)

### Strategic Analysis
Full vessel analysis with structured output:
- State logistics and civil-military fusion assessment
- Construction origin and flag state significance
- Operational patterns and security implications
- Dual-use and rapid-mobilization potential
- News coverage analysis

### Risk Levels
- **LOW** - No significant concerns
- **MODERATE** - Some factors warrant monitoring
- **HIGH** - Significant security implications
- **CRITICAL** - Immediate attention required

### Analysis Persistence
- AI analysis results are saved to the database
- BLUF summaries are extracted and stored
- Retrieve previous analysis via `/api/vessels/:id/analysis`

## Demo Data

The tracker includes comprehensive demo data for ZHONG DA 79:

```json
{
  "description": "Tracked vessels for OSINT correlation",
  "vessels": [
    {
      "id": 1,
      "name": "ZHONG DA 79",
      "mmsi": "413000000",
      "flag_state": "China",
      "vessel_type": "Container Feeder",
      "aliases": ["ZHONGDA 79", "ZHONGDA79", "ZHONG DA79"],
      "keywords": ["arsenal ship", "containerized missile", "VLS", "CIWS", "Type 1130"],
      "related_locations": ["Shanghai", "Longhai", "Fujian", "Huangpu River", "Hudong-Zhonghua"]
    }
  ]
}
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                       Arsenal Ship Tracker                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │
│  │ AISStream   │ │   AISHub    │ │  Marinesia  │ │  Open-Meteo │     │
│  │ (WebSocket) │ │   (REST)    │ │   (REST)    │ │  (Weather)  │     │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘     │
│         │               │               │               │            │
│         └───────────────┼───────────────┼───────────────┘            │
│                         │               │                            │
│  ┌──────────────────────▼───────────────▼──────────────────────┐     │
│  │                  AIS Source Manager                          │     │
│  │            (Priority-based fallback system)                  │     │
│  └──────────────────────────┬───────────────────────────────────┘     │
│                             │                                        │
│   ┌─────────────────────────┼─────────────────────────┐              │
│   │                         │                         │              │
│   ▼                         ▼                         ▼              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐        │
│  │ Live Vessel  │  │  Geofence    │  │   AI Intelligence    │        │
│  │  Tracking    │  │  Detection   │  │  (OpenAI + MMSI      │        │
│  │              │  │              │  │   Lookups)           │        │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘        │
│         │                 │                     │                    │
│         └─────────────────┼─────────────────────┘                    │
│                           │                                          │
│                    ┌──────▼──────┐                                   │
│                    │   SQLite    │                                   │
│                    │  (WAL Mode) │                                   │
│                    └──────┬──────┘                                   │
│                           │                                          │
│                    ┌──────▼──────┐                                   │
│                    │  REST API   │                                   │
│                    │   Server    │                                   │
│                    └──────┬──────┘                                   │
│                           │                                          │
│                    ┌──────▼──────┐                                   │
│                    │  Dashboard  │                                   │
│                    │    (Web)    │                                   │
│                    └─────────────┘                                   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

## Key Intelligence: ZHONG DA 79

| Attribute | Value |
|-----------|-------|
| Vessel Type | Container Feeder |
| Length | 97 meters |
| Flag State | China |
| Classification | Confirmed Arsenal Ship |
| VLS Cells | 48-60 (containerized) |
| CIWS | Type 1130 30mm |
| Decoys | Type 726 |
| Possible Missiles | CJ-10, YJ-18, YJ-21 |
| Refit Location | Longhai Shipyard (Apr-Aug 2025) |
| Current Location | Shanghai Huangpu River |
| PLAN Registry | NOT LISTED (civilian status) |

## Sources

- [United24 Media - Cargo Ship or Warship?](https://united24media.com/latest-news/cargo-ship-or-warship-china-arms-civilian-vessel-with-60-missiles-in-plain-sight-14585)
- [Naval News - Container Ship Turned Missile Battery](https://www.navalnews.com/naval-news/2025/12/container-ship-turned-missile-battery-spotted-in-china/)
- [The War Zone - Modular Missile Launchers](https://www.twz.com/sea/chinese-cargo-ship-packed-full-of-modular-missile-launchers-emerges)
- [Newsweek - Photos Show Chinese Cargo Ship Armed](https://www.newsweek.com/photos-chinese-cargo-ship-missile-launchers-11270114)

## License

Internal use only. OSINT compilation for research purposes.
