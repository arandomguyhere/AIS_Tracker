# Arsenal Ship Tracker

Maritime gray zone monitoring system for tracking vessels suspected of civilian-to-military conversion, containerized weapons systems, and dual-use activity.

## Overview

This proof-of-concept tracker monitors vessels like **ZHONG DA 79** - a Chinese container feeder converted to an arsenal ship carrying 60+ containerized missiles, CIWS, and radar while retaining civilian classification.

## Quick Start

```bash
# Initialize database with seed data
python3 server.py init

# Start the web server
python3 server.py

# Open http://localhost:8080 in browser
```

## Components

| File | Description |
|------|-------------|
| `server.py` | REST API server (Python stdlib only) |
| `schema.sql` | SQLite database schema + seed data |
| `static/index.html` | Dark intel-themed dashboard |
| `ais_ingest.py` | AIS data ingestion module |
| `ais_config.json` | AIS source configuration (auto-created) |

## API Endpoints

### Read Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vessels` | All vessels with latest position |
| GET | `/api/vessels/:id` | Single vessel details |
| GET | `/api/vessels/:id/track?days=90` | Position history |
| GET | `/api/vessels/:id/events` | Event timeline |
| GET | `/api/shipyards` | Monitored facilities |
| GET | `/api/events?severity=critical&limit=50` | All events (filterable) |
| GET | `/api/alerts` | Unacknowledged alerts |
| GET | `/api/osint?vessel_id=1` | OSINT reports |
| GET | `/api/watchlist` | Watchlist with vessel details |
| GET | `/api/stats` | Dashboard statistics |

### Write Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/vessels` | Add vessel |
| POST | `/api/vessels/:id/position` | Log position |
| POST | `/api/vessels/:id/event` | Log event |
| POST | `/api/osint` | Add OSINT report |
| POST | `/api/alerts/:id/acknowledge` | Acknowledge alert |

### Example API Calls

```bash
# Get all vessels
curl http://localhost:8080/api/vessels

# Get ZHONG DA 79 events
curl http://localhost:8080/api/vessels/1/events

# Get OSINT reports for vessel
curl "http://localhost:8080/api/osint?vessel_id=1"

# Add position update
curl -X POST http://localhost:8080/api/vessels/1/position \
  -H "Content-Type: application/json" \
  -d '{"latitude": 31.24, "longitude": 121.49, "source": "manual"}'
```

## Seed Data

The database is pre-populated with:

- **ZHONG DA 79**: Confirmed arsenal ship with full weapons configuration
- **8 Chinese shipyards**: Hudong-Zhonghua, Longhai, Jiangnan, Dalian, etc.
- **Position history**: April-December 2025 tracking data
- **Events timeline**: Shipyard entries/exits, weapons observations
- **OSINT reports**: United24 Media, Naval News, Newsweek, The War Zone articles

## AIS Ingestion

Configure live AIS data sources:

```bash
# Create config file
python3 ais_ingest.py init

# Edit ais_config.json with credentials

# Test connectivity
python3 ais_ingest.py test

# Run continuous ingestion
python3 ais_ingest.py
```

### Supported Sources

| Source | Type | Notes |
|--------|------|-------|
| AISHub | Free | Requires data sharing |
| VesselFinder | Freemium | 1000 calls/month free tier |
| Spire Maritime | Enterprise | Real-time global coverage |
| MarineTraffic | Enterprise | Reference only (ToS) |

### Features

- Watchlist filtering (only tracks vessels in DB)
- Geofence detection (shipyard entry/exit alerts)
- Dark period detection (AIS gap > 24h)
- Multi-source fusion

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Arsenal Ship Tracker                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  AIS Sources │  │   Satellite  │  │    OSINT     │       │
│  │  (API/Feed)  │  │   Imagery    │  │   Scrapers   │       │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘       │
│         │                 │                 │               │
│         └────────────────┬┴─────────────────┘               │
│                          │                                  │
│                   ┌──────▼──────┐                           │
│                   │  Ingestion  │                           │
│                   │   Layer     │                           │
│                   └──────┬──────┘                           │
│                          │                                  │
│         ┌────────────────┼────────────────┐                 │
│         │                │                │                 │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐         │
│  │  Watchlist  │  │  Geofence   │  │   Alert     │         │
│  │  Filtering  │  │  Detection  │  │  Generation │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          │                                  │
│                   ┌──────▼──────┐                           │
│                   │   SQLite    │                           │
│                   │   Database  │                           │
│                   └──────┬──────┘                           │
│                          │                                  │
│                   ┌──────▼──────┐                           │
│                   │  REST API   │                           │
│                   │   Server    │                           │
│                   └──────┬──────┘                           │
│                          │                                  │
│                   ┌──────▼──────┐                           │
│                   │  Dashboard  │                           │
│                   │    (Web)    │                           │
│                   └─────────────┘                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
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
