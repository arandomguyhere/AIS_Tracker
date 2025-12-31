#!/usr/bin/env python3
"""
Vessel Intelligence Module
AI-powered maritime intelligence analysis using OpenAI
Enhanced with MMSI-based vessel tracking lookups
"""

import json
import os
import re
import time
import random
import urllib.request
import urllib.parse
from datetime import datetime
from html.parser import HTMLParser
from typing import Dict, Any, Optional, List

# Try to import OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# =============================================================================
# MMSI-BASED VESSEL TRACKING LOOKUPS
# =============================================================================

def lookup_vessel_by_mmsi(mmsi: str) -> Dict[str, Any]:
    """
    Look up vessel information using MMSI from multiple free sources.
    Returns enriched vessel data that can be used to update the database.
    """
    result = {
        "mmsi": mmsi,
        "sources_checked": [],
        "data": {},
        "errors": []
    }

    # Try VesselFinder (free basic info)
    vf_data = _lookup_vesselfinder(mmsi)
    if vf_data:
        result["sources_checked"].append("vesselfinder")
        result["data"].update(vf_data)

    # Try Marine Traffic public data
    mt_data = _lookup_marinetraffic_public(mmsi)
    if mt_data:
        result["sources_checked"].append("marinetraffic")
        result["data"].update(mt_data)

    # Try ITU MARS database (official MMSI registry)
    itu_data = _lookup_itu_mars(mmsi)
    if itu_data:
        result["sources_checked"].append("itu_mars")
        result["data"].update(itu_data)

    # Try MyShipTracking
    mst_data = _lookup_myshiptracking(mmsi)
    if mst_data:
        result["sources_checked"].append("myshiptracking")
        result["data"].update(mst_data)

    return result


def _lookup_vesselfinder(mmsi: str) -> Optional[Dict[str, Any]]:
    """Query VesselFinder for vessel data."""
    try:
        # VesselFinder public vessel page
        url = f"https://www.vesselfinder.com/vessels?name={mmsi}"

        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml'
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')

        # Parse basic info from HTML
        data = {}

        # Extract vessel name
        name_match = re.search(r'<td class="v2"[^>]*>([^<]+)</td>', html)
        if name_match:
            data["name"] = name_match.group(1).strip()

        # Extract IMO
        imo_match = re.search(r'IMO:\s*(\d{7})', html)
        if imo_match:
            data["imo"] = imo_match.group(1)

        # Extract flag
        flag_match = re.search(r'flag-icon-([a-z]{2})', html, re.IGNORECASE)
        if flag_match:
            data["flag_code"] = flag_match.group(1).upper()

        # Extract vessel type
        type_match = re.search(r'Ship type:\s*</td>\s*<td[^>]*>([^<]+)', html, re.IGNORECASE)
        if type_match:
            data["vessel_type"] = type_match.group(1).strip()

        return data if data else None

    except Exception as e:
        print(f"[VesselFinder] Error: {e}")
        return None


def _lookup_marinetraffic_public(mmsi: str) -> Optional[Dict[str, Any]]:
    """Query MarineTraffic public vessel page for data."""
    try:
        url = f"https://www.marinetraffic.com/en/ais/details/ships/mmsi:{mmsi}"

        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml'
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')

        data = {}

        # Extract vessel name from title
        title_match = re.search(r'<title>([^|<]+)', html)
        if title_match:
            name = title_match.group(1).strip()
            if name and name != "MarineTraffic":
                data["name"] = name

        # Extract IMO
        imo_match = re.search(r'"imo":\s*"?(\d{7})"?', html)
        if imo_match:
            data["imo"] = imo_match.group(1)

        # Extract callsign
        callsign_match = re.search(r'"callsign":\s*"([^"]+)"', html)
        if callsign_match:
            data["callsign"] = callsign_match.group(1)

        # Extract flag
        flag_match = re.search(r'"flag":\s*"([^"]+)"', html)
        if flag_match:
            data["flag_state"] = flag_match.group(1)

        # Extract vessel type
        type_match = re.search(r'"shipType":\s*"([^"]+)"', html)
        if type_match:
            data["vessel_type"] = type_match.group(1)

        # Extract dimensions
        length_match = re.search(r'"length":\s*(\d+)', html)
        if length_match:
            data["length_m"] = int(length_match.group(1))

        beam_match = re.search(r'"beam":\s*(\d+)', html)
        if beam_match:
            data["beam_m"] = int(beam_match.group(1))

        # Extract year built
        year_match = re.search(r'"yearBuilt":\s*(\d{4})', html)
        if year_match:
            data["year_built"] = int(year_match.group(1))

        # Extract gross tonnage
        gt_match = re.search(r'"gt":\s*(\d+)', html)
        if gt_match:
            data["gross_tonnage"] = int(gt_match.group(1))

        # Extract deadweight
        dwt_match = re.search(r'"dwt":\s*(\d+)', html)
        if dwt_match:
            data["deadweight"] = int(dwt_match.group(1))

        return data if data else None

    except Exception as e:
        print(f"[MarineTraffic] Error: {e}")
        return None


def _lookup_itu_mars(mmsi: str) -> Optional[Dict[str, Any]]:
    """Look up MMSI in ITU MARS database (official registry)."""
    try:
        # ITU MARS API for MMSI lookup
        url = f"https://www.itu.int/mmsapp/ShipStation/list?minMmsi={mmsi}&maxMmsi={mmsi}"

        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        if data and isinstance(data, list) and len(data) > 0:
            ship = data[0]
            return {
                "name": ship.get("name"),
                "callsign": ship.get("callSign"),
                "flag_state": ship.get("country"),
                "owner": ship.get("owner"),
                "itu_registered": True
            }

        return None

    except Exception as e:
        print(f"[ITU MARS] Error: {e}")
        return None


def _lookup_myshiptracking(mmsi: str) -> Optional[Dict[str, Any]]:
    """Query MyShipTracking for vessel data."""
    try:
        url = f"https://www.myshiptracking.com/vessels?mmsi={mmsi}"

        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')

        data = {}

        # Extract vessel name
        name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        if name_match:
            data["name"] = name_match.group(1).strip()

        # Extract destination
        dest_match = re.search(r'Destination:\s*</[^>]+>\s*<[^>]+>([^<]+)', html)
        if dest_match:
            data["destination"] = dest_match.group(1).strip()

        return data if data else None

    except Exception as e:
        print(f"[MyShipTracking] Error: {e}")
        return None


def enrich_vessel_data(vessel_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich vessel data using MMSI lookups.
    Returns the enriched data along with fields that should be updated.
    """
    mmsi = vessel_data.get("mmsi")
    if not mmsi:
        return {
            "status": "error",
            "error": "No MMSI provided",
            "enriched": vessel_data,
            "updates": {}
        }

    print(f"[Intel] Looking up vessel MMSI: {mmsi}")
    lookup_result = lookup_vessel_by_mmsi(mmsi)

    enriched = vessel_data.copy()
    updates = {}

    # Merge in looked-up data (only if field is empty/unknown)
    for key, value in lookup_result.get("data", {}).items():
        if value:
            current = enriched.get(key)
            # Update if current value is empty, None, or "Unknown"
            if not current or current == "Unknown" or current == "unknown":
                enriched[key] = value
                updates[key] = value

    return {
        "status": "success",
        "sources": lookup_result.get("sources_checked", []),
        "enriched": enriched,
        "updates": updates,
        "raw_lookup": lookup_result
    }


# =============================================================================
# NEWS SEARCH (Improved)
# =============================================================================

class GoogleNewsParser(HTMLParser):
    """Simple parser to extract news from Google News HTML."""

    def __init__(self):
        super().__init__()
        self.articles = []
        self.current_article = {}
        self.in_article = False
        self.capture_text = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'a' and 'href' in attrs_dict:
            href = attrs_dict['href']
            if href.startswith('./articles/') or href.startswith('./read/'):
                self.in_article = True
                self.current_article = {'url': f"https://news.google.com{href[1:]}"}

    def handle_data(self, data):
        if self.in_article and data.strip():
            if 'title' not in self.current_article:
                self.current_article['title'] = data.strip()
            elif 'source' not in self.current_article:
                self.current_article['source'] = data.strip()

    def handle_endtag(self, tag):
        if tag == 'a' and self.in_article:
            if 'title' in self.current_article:
                self.articles.append(self.current_article)
            self.in_article = False
            self.current_article = {}


def search_google_news(query, max_results=10):
    """Search Google News without external dependencies."""
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/search?q={encoded_query}&hl=en&gl=US&ceid=US:en"

        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')

        parser = GoogleNewsParser()
        parser.feed(html)

        return parser.articles[:max_results]

    except Exception as e:
        print(f"[News Search Error] {e}")
        return []


def generate_targeted_queries(vessel_data: Dict[str, Any]) -> List[str]:
    """
    Generate targeted search queries based on enriched vessel data.
    Uses MMSI, IMO, and exact vessel name for more accurate results.
    """
    queries = []

    name = vessel_data.get("name", "").strip()
    mmsi = vessel_data.get("mmsi", "")
    imo = vessel_data.get("imo", "")
    flag = vessel_data.get("flag_state", "")
    vessel_type = vessel_data.get("vessel_type", "")
    owner = vessel_data.get("owner", "")

    # Direct vessel searches (most specific)
    if imo:
        queries.append(f"IMO {imo} ship")

    if name:
        # Exact name search with quotes
        queries.append(f'"{name}" vessel')
        queries.append(f'"{name}" ship news')

        # Name + flag for disambiguation
        if flag:
            queries.append(f'"{name}" {flag} ship')

    # Owner/operator searches
    if owner:
        queries.append(f'"{owner}" shipping company')

    # Type + flag for context (only if we have good data)
    if vessel_type and flag and vessel_type not in ["Unknown", "Passenger"]:
        queries.append(f'{flag} {vessel_type} vessel military')

    # Security/incident searches
    if name:
        queries.append(f'"{name}" incident OR accident OR detained')

    return queries[:6]  # Limit to 6 queries


# =============================================================================
# OPENAI INTEGRATION
# =============================================================================

def get_openai_client():
    """Get OpenAI client if available."""
    if not OPENAI_AVAILABLE:
        return None

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return None

    return OpenAI(api_key=api_key)


def ai_analyze_vessel(client, vessel_data, news_articles=None, enrichment_data=None):
    """Use AI to perform strategic analysis of a vessel."""

    news_context = ""
    if news_articles:
        # Filter to only relevant articles (those matching vessel name/IMO)
        name = vessel_data.get("name", "").lower()
        relevant = [a for a in news_articles if name in a.get("title", "").lower()]
        if relevant:
            news_context = f"\n\nRelevant News Articles Found:\n{json.dumps(relevant[:5], indent=2)}"
        elif news_articles:
            news_context = f"\n\nNote: {len(news_articles)} news articles found but none directly mention this vessel."

    enrichment_context = ""
    if enrichment_data:
        sources = enrichment_data.get("sources", [])
        if sources:
            enrichment_context = f"\n\nVessel Data Sources: {', '.join(sources)}"
            updates = enrichment_data.get("updates", {})
            if updates:
                enrichment_context += f"\nEnriched Fields: {json.dumps(updates, indent=2)}"

    prompt = f"""You are a maritime intelligence analyst.

Analyze the following vessel and determine whether it has strategic, security, or geopolitical relevance.

Vessel Data:
{json.dumps(vessel_data, indent=2)}{enrichment_context}{news_context}

Tasks:
1. Assess whether this vessel or its operator has links to state logistics, civil-military fusion, or gray-zone maritime operations.
2. Evaluate the significance of its construction origin, classification society, and flag state.
3. Analyze operational patterns or status that may have security implications.
4. Identify any potential dual-use or rapid-mobilization roles this vessel type could support.
5. Assess the news coverage (or lack thereof) and what it indicates.
6. Conclude with a concise BLUF (Bottom Line Up Front) summarizing risk level.

Risk Levels: LOW | MODERATE | HIGH | CRITICAL

If no evidence of strategic relevance exists, explicitly state that and explain why.

IMPORTANT: If you have enriched data from vessel tracking databases, extract and recommend updates for these fields:
- flag_state
- vessel_type
- classification (confirmed/suspected/monitoring/cleared)
- threat_level (critical/high/medium/low/unknown)

Format your response as:
## BLUF
[One paragraph summary with risk level]

## Analysis
[Detailed analysis organized by the tasks above]

## Recommended Updates
[JSON object with field updates, e.g. {{"threat_level": "low", "classification": "monitoring"}}]

## Monitoring Recommendations
[What to watch for going forward]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2000
        )

        content = response.choices[0].message.content

        # Parse out the BLUF section
        bluf = None
        bluf_match = re.search(r'## BLUF\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        if bluf_match:
            bluf_text = bluf_match.group(1).strip()
            # Extract threat level from BLUF
            level_match = re.search(r'\b(LOW|MODERATE|HIGH|CRITICAL)\b', bluf_text)
            threat_level = level_match.group(1) if level_match else "UNKNOWN"
            bluf = {
                "assessment": bluf_text,
                "threat_level": threat_level,
                "confidence": 0.8 if news_context else 0.6
            }

        # Parse recommended updates
        recommended_updates = {}
        # Try to extract JSON from code block first
        updates_match = re.search(r'## Recommended Updates\s*\n.*?```json?\s*(\{[\s\S]*?\})\s*```', content, re.DOTALL)
        if updates_match:
            try:
                recommended_updates = json.loads(updates_match.group(1))
            except:
                pass

        if not recommended_updates:
            # Try without code block - match multi-line JSON
            updates_match = re.search(r'## Recommended Updates\s*\n\s*(\{[\s\S]*?\})\s*(?:\n##|\n\n|\Z)', content, re.DOTALL)
            if updates_match:
                try:
                    recommended_updates = json.loads(updates_match.group(1))
                except:
                    pass

        if not recommended_updates:
            # Last resort - find any JSON object after Recommended Updates
            updates_match = re.search(r'## Recommended Updates[\s\S]*?(\{"[^"]+"\s*:\s*"[^"]+(?:"[\s\S]*?"[^"]+"\s*:\s*"[^"]+")*\s*\})', content)
            if updates_match:
                try:
                    recommended_updates = json.loads(updates_match.group(1))
                except:
                    pass

        return {
            "status": "success",
            "analysis": content,
            "bluf": bluf,
            "recommended_updates": recommended_updates,
            "model": "gpt-4o",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def analyze_vessel_intel(vessel_data):
    """
    Main function: Perform full AI-powered vessel intelligence analysis.

    1. Enrich vessel data via MMSI lookups
    2. Generate targeted search queries
    3. Execute news searches
    4. AI analysis of vessel + news + enrichment
    5. Return results with recommended field updates
    """

    client = get_openai_client()

    if not client:
        return {
            "status": "error",
            "error": "OpenAI API key not configured. Set OPENAI_API_KEY environment variable.",
            "fallback_available": True
        }

    result = {
        "vessel": vessel_data,
        "timestamp": datetime.now().isoformat(),
        "enrichment": None,
        "news_results": [],
        "analysis": None,
        "field_updates": {}
    }

    # Step 1: Enrich vessel data via MMSI lookups
    print(f"[Intel] Enriching vessel data for {vessel_data.get('name', 'Unknown')}")
    enrichment = enrich_vessel_data(vessel_data)
    result["enrichment"] = enrichment

    # Use enriched data for analysis
    enriched_vessel = enrichment.get("enriched", vessel_data)

    # Collect field updates from enrichment
    result["field_updates"].update(enrichment.get("updates", {}))

    # Step 2: Generate targeted search queries
    queries = generate_targeted_queries(enriched_vessel)
    print(f"[Intel] Generated {len(queries)} search queries")

    # Step 3: Execute searches
    all_articles = []
    for query in queries:
        print(f"[Intel] Searching: {query}")
        articles = search_google_news(query, max_results=5)
        for article in articles:
            article["search_query"] = query
            # Dedupe by title
            if not any(a.get("title") == article.get("title") for a in all_articles):
                all_articles.append(article)
        time.sleep(random.uniform(0.5, 1.0))

    result["news_results"] = all_articles
    print(f"[Intel] Found {len(all_articles)} unique articles")

    # Step 4: AI Analysis
    print(f"[Intel] Running AI analysis...")
    analysis = ai_analyze_vessel(client, enriched_vessel, all_articles, enrichment)
    result["analysis"] = analysis

    # Merge AI recommended updates
    if analysis.get("recommended_updates"):
        result["field_updates"].update(analysis["recommended_updates"])

    # Add BLUF to top level for easy access
    if analysis.get("bluf"):
        result["bluf"] = analysis["bluf"]

    result["status"] = "success"
    return result


def quick_vessel_bluf(vessel_data):
    """Quick BLUF assessment without full news search."""

    client = get_openai_client()

    if not client:
        return {
            "status": "error",
            "error": "OpenAI API key not configured"
        }

    prompt = f"""You are a maritime intelligence analyst. Provide a brief BLUF (Bottom Line Up Front) assessment.

Vessel:
{json.dumps(vessel_data, indent=2)}

In 2-3 sentences, assess:
- Risk level (LOW/MODERATE/HIGH/CRITICAL)
- Key factors driving that assessment
- Whether further investigation is warranted

Be concise and direct."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300
        )

        return {
            "status": "success",
            "bluf": response.choices[0].message.content,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


# CLI testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Test MMSI lookup
        mmsi = sys.argv[1]
        print(f"Testing MMSI lookup for: {mmsi}")
        result = lookup_vessel_by_mmsi(mmsi)
        print(json.dumps(result, indent=2))
    else:
        test_vessel = {
            "name": "GRACEFUL STARS",
            "mmsi": "548295100",
            "vessel_type": "Passenger",
            "flag_state": "",
            "classification": "monitoring",
            "threat_level": "unknown"
        }

        print("Testing vessel enrichment...")
        enrichment = enrich_vessel_data(test_vessel)
        print(json.dumps(enrichment, indent=2))

        print("\nGenerating search queries...")
        queries = generate_targeted_queries(enrichment.get("enriched", test_vessel))
        for q in queries:
            print(f"  - {q}")
