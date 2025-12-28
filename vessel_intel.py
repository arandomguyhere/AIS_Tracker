#!/usr/bin/env python3
"""
Vessel Intelligence Module
AI-powered maritime intelligence analysis using OpenAI
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

# Try to import OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


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


def get_openai_client():
    """Get OpenAI client if available."""
    if not OPENAI_AVAILABLE:
        return None

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return None

    return OpenAI(api_key=api_key)


def ai_generate_search_plan(client, vessel_data):
    """Use AI to generate intelligent search queries for a vessel."""

    prompt = f"""You are an OSINT analyst specializing in maritime intelligence.

Given the following vessel data, generate search queries to find relevant news and intelligence.

Vessel Data:
{json.dumps(vessel_data, indent=2)}

Generate JSON with these fields:
- direct_queries: exact vessel name/MMSI/IMO searches (3-5 queries)
- operator_queries: searches for the owner/operator if known (2-3 queries)
- risk_queries: incident/security related searches for this vessel type/region (2-3 queries)
- context_queries: broader geopolitical context searches (2-3 queries)

Return ONLY valid JSON, no markdown or explanation."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )

        result = response.choices[0].message.content
        # Clean up potential markdown
        result = re.sub(r'^```json\s*', '', result)
        result = re.sub(r'\s*```$', '', result)

        return json.loads(result)

    except Exception as e:
        print(f"[AI Search Plan Error] {e}")
        # Fallback to basic queries
        name = vessel_data.get('name', '')
        mmsi = vessel_data.get('mmsi', '')
        return {
            "direct_queries": [name, f"MMSI {mmsi}", f"{name} ship"],
            "operator_queries": [],
            "risk_queries": [f"{name} incident", f"{name} accident"],
            "context_queries": []
        }


def ai_analyze_vessel(client, vessel_data, news_articles=None):
    """Use AI to perform strategic analysis of a vessel."""

    news_context = ""
    if news_articles:
        news_context = f"""

Recent News Articles Found:
{json.dumps(news_articles[:10], indent=2)}"""

    prompt = f"""You are a maritime intelligence analyst.

Analyze the following vessel and determine whether it has strategic, security, or geopolitical relevance.

Vessel Data:
{json.dumps(vessel_data, indent=2)}{news_context}

Tasks:
1. Assess whether this vessel or its operator has links to state logistics, civil-military fusion, or gray-zone maritime operations.
2. Evaluate the significance of its construction origin, classification society, and flag state.
3. Analyze operational patterns or status that may have security implications.
4. Identify any potential dual-use or rapid-mobilization roles this vessel type could support.
5. Assess the news coverage (or lack thereof) and what it indicates.
6. Conclude with a concise BLUF (Bottom Line Up Front) summarizing risk level.

Risk Levels: LOW | MODERATE | HIGH | CRITICAL

If no evidence of strategic relevance exists, explicitly state that and explain why.

Format your response as:
## BLUF
[One paragraph summary with risk level]

## Analysis
[Detailed analysis organized by the tasks above]

## Monitoring Recommendations
[What to watch for going forward]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=2000
        )

        return {
            "status": "success",
            "analysis": response.choices[0].message.content,
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

    1. Generate AI search plan
    2. Execute news searches
    3. AI analysis of vessel + news
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
        "search_plan": None,
        "news_results": [],
        "analysis": None
    }

    # Step 1: Generate search plan
    print(f"[Intel] Generating search plan for {vessel_data.get('name', 'Unknown')}")
    search_plan = ai_generate_search_plan(client, vessel_data)
    result["search_plan"] = search_plan

    # Step 2: Execute searches
    all_articles = []
    all_queries = (
        search_plan.get("direct_queries", []) +
        search_plan.get("operator_queries", []) +
        search_plan.get("risk_queries", [])
    )

    for query in all_queries[:8]:  # Limit to avoid rate issues
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

    # Step 3: AI Analysis
    print(f"[Intel] Running AI analysis...")
    analysis = ai_analyze_vessel(client, vessel_data, all_articles)
    result["analysis"] = analysis

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
    test_vessel = {
        "name": "ZHONG DA 79",
        "mmsi": "413000000",
        "vessel_type": "Container Feeder",
        "flag_state": "China",
        "length_m": 97,
        "classification": "confirmed",
        "threat_level": "critical",
        "intel_notes": "Commercial container feeder converted to arsenal ship with containerized VLS"
    }

    print("Testing vessel intelligence analysis...")
    result = analyze_vessel_intel(test_vessel)
    print(json.dumps(result, indent=2))
