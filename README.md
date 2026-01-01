# Arsenal Ship Tracker

![Tests](https://github.com/arandomguyhere/AIS_Tracker/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-internal-red)

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

### SAR Ship Detection (NEW)
- **ESA SNAP integration** - Import ship detections from ESA Sentinel-1 SAR imagery
- **CSV/XML parsing** - Parse SNAP Ship Detection toolbox output files
- **AIS correlation** - Match SAR detections with AIS positions (configurable time/distance thresholds)
- **Dark vessel detection** - Identify vessels visible on SAR but not transmitting AIS
- **Detection metadata** - Track detection time, coordinates, estimated length, confidence
- **SAR layer toggle** - View SAR detections on map (purple=matched, red=dark vessel)
- **EO Browser integration** - One-click access to Sentinel-1 SAR imagery for current map view
- **Satellite overlay** - NASA daily satellite imagery with adjustable opacity

### Vessel Confidence Scoring (NEW)
- **AIS consistency score** - Analyze position reporting gaps and jumps
- **Behavioral normalcy score** - Detect unusual speed/course changes
- **SAR corroboration score** - Cross-reference with SAR detections
- **Deception likelihood** - Calculate probability of AIS spoofing/manipulation
- **Overall confidence** - Weighted composite score (0.0-1.0)
- **Cached scoring** - Scores cached and refreshable on demand
- **UI confidence panel** - Visual confidence display in vessel details with refresh button

### Testing
- **117 unit tests** - Comprehensive test coverage
- **Test runner** - `python3 run_tests.py` to run all tests
- **Module tests** - Database, API, SAR import, confidence scoring, intelligence

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
| `requirements.txt` | Python dependencies (gnews, openai) |
| `ais_ingest.py` | AIS data ingestion module |
| `ais_config.json` | AIS source configuration (auto-created) |
| `ais_sources/` | Multi-source AIS integration (AISStream, AISHub, Marinesia) |
| `osint/` | OSINT correlation and monitoring tools |
| `sar_import.py` | SAR ship detection import and AIS correlation |
| `confidence.py` | Vessel confidence scoring and deception detection |
| `intelligence.py` | Formal intelligence output with analyst-visible breakdown |
| `behavior.py` | Behavior detection: loitering, AIS gaps, STS transfers, dark fleet scoring |
| `run_tests.py` | Test runner script |
| `tests/` | Unit tests for database, API, SAR, confidence, and intelligence |

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
| GET | `/api/vessels/:id/intel` | Formal intelligence assessment with breakdown |
| GET | `/api/vessels/:id/intel?summary=true` | Quick intel summary |
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

### SAR Detection Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sar-detections` | List SAR ship detections |
| GET | `/api/dark-vessels` | List dark vessels (SAR without AIS match) |

### Confidence Scoring Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vessels/:id/confidence` | Get cached confidence score |
| GET | `/api/vessels/:id/confidence?refresh=true` | Calculate fresh confidence score |

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
| POST | `/api/config/bounding-box` | Save AIS bounding box config |
| POST | `/api/vessels/:id/photo` | Upload vessel photo |

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

# Get vessel confidence score
curl http://localhost:8080/api/vessels/1/confidence

# Get SAR detections
curl http://localhost:8080/api/sar-detections

# Get dark vessels (SAR without AIS)
curl http://localhost:8080/api/dark-vessels
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

## SAR Ship Detection

The SAR import module (`sar_import.py`) enables integration with ESA Sentinel-1 SAR imagery:

### Supported Formats
- **CSV** - SNAP Ship Detection toolbox CSV export
- **XML** - SNAP detection XML output

### Detection Fields
| Field | Description |
|-------|-------------|
| `detection_time` | Timestamp of SAR image acquisition |
| `latitude/longitude` | Detection coordinates |
| `estimated_length` | Estimated vessel length in meters |
| `detection_confidence` | Algorithm confidence score |
| `matched_mmsi` | AIS vessel if correlation found |

### AIS Correlation
Detections are correlated with AIS positions using configurable thresholds:
- **Time window**: ±30 minutes (default)
- **Distance threshold**: 5km (default)
- Unmatched detections flagged as potential "dark vessels"

### Usage
```python
from sar_import import import_sar_file, get_dark_vessels

# Import SNAP detection file
results = import_sar_file('detections.csv', source='sentinel-1')

# Get vessels detected by SAR but not transmitting AIS
dark_vessels = get_dark_vessels(since='2025-01-01')
```

## Vessel Confidence Scoring

The confidence module (`confidence.py`) provides trust assessment for vessel data:

### Score Components
| Component | Weight | Description |
|-----------|--------|-------------|
| AIS Consistency | 40% | Position reporting regularity, gap analysis |
| Behavioral Normalcy | 30% | Speed/course change patterns |
| SAR Corroboration | 30% | Cross-reference with SAR detections |

### Scoring Algorithm
- **AIS Consistency**: Penalizes large gaps (>1hr) and position jumps (>50nm)
- **Behavioral Normalcy**: Flags unusual speed (>30kt) or rapid course changes
- **SAR Corroboration**: Boosts score when SAR confirms vessel presence
- **Deception Likelihood**: Combines factors indicating potential AIS manipulation

### API Response
```json
{
  "vessel_id": 1,
  "overall_confidence": 0.72,
  "ais_consistency": 0.85,
  "behavioral_normalcy": 0.65,
  "sar_corroboration": 0.50,
  "deception_likelihood": 0.15,
  "calculated_at": "2025-12-31T00:00:00Z"
}
```

## Behavior Detection & Dark Fleet Analysis

The behavior detection module (`behavior.py`) provides vessel behavior analysis based on peer-reviewed research:

### Detection Capabilities
| Detection | Description | Reference |
|-----------|-------------|-----------|
| **AIS Gaps** | Identify vessels "going dark" | Global Fishing Watch (2024) |
| **Loitering** | Detect stationary behavior indicating STS transfers | GFW Nature Study |
| **Position Spoofing** | Flag impossible vessel movements | MDPI (2021) |
| **STS Transfers** | Ship-to-ship transfer detection | arXiv (2024) |
| **Dark Fleet Score** | Multi-factor risk assessment | MDPI (2023, 2025) |

### Dark Fleet Risk Scoring
Combines multiple indicators based on shadow fleet research:
- **Flag of Convenience** (0-25 pts) - FOC and emerging shadow fleet flags
- **Vessel Age** (0-20 pts) - Old vessels (>15-25 years) common in shadow fleets
- **Ownership Opacity** (0-15 pts) - Shell companies, hidden ownership
- **AIS Gaps** (0-20 pts) - Primary shadow fleet tactic
- **Position Spoofing** (0-15 pts) - Intentional deception
- **STS Transfers** (0-15 pts) - Sanctions evasion indicator
- **Vessel Type** (0-5 pts) - Tankers higher risk

### Risk Levels
| Score | Level | Assessment |
|-------|-------|------------|
| 70-100 | Critical | High probability of shadow fleet involvement |
| 50-69 | High | Multiple dark fleet indicators present |
| 30-49 | Medium | Some concerning indicators detected |
| 15-29 | Low | Minor risk factors present |
| 0-14 | Minimal | No significant dark fleet indicators |

### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vessels/:id/behavior` | Full behavior analysis |
| GET | `/api/mmsi/validate?mmsi=XXX` | MMSI validation |
| GET | `/api/mmsi/country?mmsi=XXX` | Flag country lookup |

### Academic References

The behavior detection algorithms are based on peer-reviewed research:

#### Foundational Studies
1. **Global Fishing Watch Nature Study (2024)** - "Satellite mapping reveals global scope of hidden fishing activity"
   - Finding: 75% of industrial fishing vessels not publicly tracked
   - Method: SAR/GPS correlation with machine learning
   - URL: https://globalfishingwatch.org/research/global-footprint-of-fisheries/

2. **MPA Compliance Study (Science, July 2025)** - First demonstration that SAR can detect fishing in protected areas
   - Finding: AIS missed 90% of SAR-based detections in MPAs
   - URL: https://www.science.org/

#### AIS Manipulation Research
3. **"AIS Data Manipulation in the Illicit Global Oil Trade"** (MDPI JMSE, 2023)
   - Focus: Russian sanctions evasion via tanker AIS spoofing
   - URL: https://www.mdpi.com/2077-1312/12/1/6

4. **"AIS Data Vulnerability Indicated by a Spoofing Case-Study"** (MDPI, 2021)
   - Finding: Chinese GPS spoofing devices creating "crop circle" patterns
   - URL: https://www.mdpi.com/2076-3417/11/11/5015

#### Shadow Fleet Analysis
5. **"Shadow Fleets: A Growing Challenge in Global Maritime Commerce"** (MDPI Applied Sciences, 2025)
   - Framework: Distinguishes "dark fleets" from "gray fleets"
   - Finding: Shadow fleets now ~10% of global seaborne oil transport
   - URL: https://www.mdpi.com/2076-3417/15/12/6424

#### STS Transfer Detection
6. **"Automatic Detection of Dark Ship-to-Ship Transfers"** (arXiv, 2024)
   - Method: SAR/AIS correlation for sanctions evasion detection
   - URL: https://arxiv.org/html/2404.07607v1

#### Operational Systems
7. **"INSURE System for Ghana IUU Fishing Monitoring"** (MDPI Remote Sensing, 2019)
   - Performance: 91% detection rate, 75% SAR detections had no AIS
   - URL: https://www.mdpi.com/2072-4292/11/3/293

## Intelligence Output

The intelligence module (`intelligence.py`) produces standardized, defensible assessments:

### Intelligence Object
```json
{
  "vessel_id": 1,
  "assessment": "Likely gray-zone logistics. Key indicators: AIS gap detected, loitering behavior",
  "assessment_level": "suspicious",
  "confidence": 0.73,
  "deception_likelihood": 0.45,
  "indicators": [
    {"name": "ais_gap_significant", "weight": 0.15, "description": "Significant AIS gap detected (36 hours)"},
    {"name": "loitering_detected", "weight": 0.12, "description": "Loitering behavior detected"}
  ],
  "confidence_breakdown": {
    "confidence": 73,
    "breakdown": [
      {"component": "AIS Consistency", "score": 0.6, "weight": 0.35, "contribution": "+0.21"},
      {"component": "Behavioral Normalcy", "score": 0.7, "weight": 0.35, "contribution": "+0.25"},
      {"component": "SAR Corroboration", "score": 0.5, "weight": 0.30, "contribution": "+0.15"}
    ],
    "adjustments": [
      {"name": "Signal quality", "source": "medium", "adjustment": "-0.03"},
      {"name": "Data freshness", "adjustment": "-0.05"}
    ]
  },
  "data_sources": ["AIS", "SAR"],
  "last_updated": "2025-12-31T12:00:00Z"
}
```

### Assessment Levels
| Level | Description |
|-------|-------------|
| `benign` | Normal operating pattern |
| `monitoring` | Insufficient data for assessment |
| `anomalous` | Single behavioral deviation detected |
| `suspicious` | Multiple indicators triggered |
| `likely_gray_zone` | High deception likelihood with technical/behavioral anomalies |
| `confirmed_threat` | Vessel classified as confirmed threat |

### Indicator Types
| Type | Examples |
|------|----------|
| `behavioral` | AIS gaps, speed anomalies, loitering |
| `technical` | Position jumps, SAR mismatches |
| `ownership` | Flag of convenience, ownership opacity |

## Running Tests

```bash
# Run all tests
python3 run_tests.py

# Run with verbose output
python3 run_tests.py -v

# Run specific test module
python3 run_tests.py test_confidence
python3 run_tests.py test_intelligence
python3 run_tests.py test_sar_import
python3 run_tests.py test_database
python3 run_tests.py test_api
```

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
┌─────────────────────────────────────────────────────────────────────────┐
│                         Arsenal Ship Tracker                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │ AISStream   │ │   AISHub    │ │  Marinesia  │ │  Open-Meteo │        │
│  │ (WebSocket) │ │   (REST)    │ │   (REST)    │ │  (Weather)  │        │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘        │
│         │               │               │               │               │
│         └───────────────┼───────────────┼───────────────┘               │
│                         │               │                               │
│  ┌──────────────────────▼───────────────▼──────────────────────┐        │
│  │                  AIS Source Manager                          │        │
│  │            (Priority-based fallback system)                  │        │
│  └──────────────────────────┬───────────────────────────────────┘        │
│                             │                                           │
│   ┌─────────────────────────┼─────────────────────────┐                 │
│   │                         │                         │                 │
│   ▼                         ▼                         ▼                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐           │
│  │ Live Vessel  │  │  Geofence    │  │   AI Intelligence    │           │
│  │  Tracking    │  │  Detection   │  │  (OpenAI + MMSI      │           │
│  │              │  │              │  │   Lookups)           │           │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘           │
│         │                 │                     │                       │
│   ┌─────▼─────┐     ┌─────▼─────┐         ┌─────▼─────┐                 │
│   │ SAR Ship  │     │ Confidence│         │   OSINT   │                 │
│   │ Detection │     │  Scoring  │         │ Correlator│                 │
│   │ (SNAP)    │     │           │         │           │                 │
│   └─────┬─────┘     └─────┬─────┘         └─────┬─────┘                 │
│         │                 │                     │                       │
│         └─────────────────┼─────────────────────┘                       │
│                           │                                             │
│                    ┌──────▼──────┐                                      │
│                    │   SQLite    │                                      │
│                    │  (WAL Mode) │                                      │
│                    └──────┬──────┘                                      │
│                           │                                             │
│                    ┌──────▼──────┐                                      │
│                    │  REST API   │                                      │
│                    │   Server    │                                      │
│                    └──────┬──────┘                                      │
│                           │                                             │
│                    ┌──────▼──────┐                                      │
│                    │  Dashboard  │                                      │
│                    │    (Web)    │                                      │
│                    └─────────────┘                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
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
