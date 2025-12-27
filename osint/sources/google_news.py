"""
Google News Source Adapter

Integrates with external Google News scrapers to fetch and normalize articles.

This adapter supports two integration modes:
1. Direct function call: Pass a scraper function that returns articles
2. File-based: Load pre-scraped articles from JSON files

Expected scraper output format:
{
    "title": "Article Title",
    "url": "https://...",
    "source": "Source Name",
    "published": "2025-12-26T10:00:00Z",  # ISO format
    "snippet": "Brief description...",
    "content": "Full article text..."  # Optional
}
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Callable, Optional, Any
from ..models import Article


class GoogleNewsAdapter:
    """
    Adapter for Google News scraped content.

    Usage with external scraper:
        from your_scraper import scrape_google_news

        adapter = GoogleNewsAdapter()
        adapter.set_scraper(scrape_google_news)
        articles = adapter.search("ZHONG DA 79 missile")

    Usage with pre-scraped JSON:
        adapter = GoogleNewsAdapter()
        articles = adapter.load_from_file("scraped_news.json")
    """

    def __init__(self, scraper_func: Optional[Callable] = None):
        """
        Initialize adapter with optional scraper function.

        Args:
            scraper_func: Function that takes a query string and returns
                         list of article dicts
        """
        self.scraper_func = scraper_func
        self.source_name = "Google News"

    def set_scraper(self, scraper_func: Callable[[str], List[Dict]]) -> None:
        """
        Set the scraper function.

        The function should:
        - Accept a search query string
        - Return a list of article dicts with keys:
          title, url, source, published (optional), snippet, content (optional)
        """
        self.scraper_func = scraper_func

    def search(
        self,
        query: str,
        max_results: int = 50,
        fetch_content: bool = False
    ) -> List[Article]:
        """
        Search Google News and return normalized articles.

        Args:
            query: Search query string
            max_results: Maximum number of results
            fetch_content: Whether to fetch full article content (slower)

        Returns:
            List of Article objects
        """
        if not self.scraper_func:
            raise RuntimeError(
                "No scraper function configured. "
                "Use set_scraper() or load_from_file() instead."
            )

        # Call the external scraper
        raw_results = self.scraper_func(query)

        if max_results:
            raw_results = raw_results[:max_results]

        # Normalize to Article objects
        articles = []
        for item in raw_results:
            article = self._normalize_article(item, fetch_content)
            if article:
                articles.append(article)

        return articles

    def search_multiple(
        self,
        queries: List[str],
        max_per_query: int = 20
    ) -> List[Article]:
        """
        Search multiple queries and deduplicate results.

        Useful for searching vessel names plus variations.
        """
        all_articles = []
        seen_urls = set()

        for query in queries:
            articles = self.search(query, max_results=max_per_query)

            for article in articles:
                if article.url not in seen_urls:
                    seen_urls.add(article.url)
                    all_articles.append(article)

        return all_articles

    def load_from_file(self, file_path: str) -> List[Article]:
        """
        Load pre-scraped articles from JSON file.

        Expected format:
        {
            "articles": [
                {"title": "...", "url": "...", ...},
                ...
            ]
        }
        or just a list:
        [
            {"title": "...", "url": "...", ...},
            ...
        ]
        """
        path = Path(file_path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Handle both formats
        if isinstance(data, dict):
            raw_articles = data.get("articles", [])
        else:
            raw_articles = data

        articles = []
        for item in raw_articles:
            article = self._normalize_article(item)
            if article:
                articles.append(article)

        return articles

    def load_from_dict(self, articles_data: List[Dict]) -> List[Article]:
        """
        Load articles from a list of dicts (direct integration).
        """
        articles = []
        for item in articles_data:
            article = self._normalize_article(item)
            if article:
                articles.append(article)
        return articles

    def _normalize_article(
        self,
        raw: Dict[str, Any],
        fetch_content: bool = False
    ) -> Optional[Article]:
        """
        Convert raw scraper output to Article model.
        """
        try:
            # Required fields
            title = raw.get("title", "").strip()
            url = raw.get("url", raw.get("link", "")).strip()

            if not title or not url:
                return None

            # Generate ID from URL
            article_id = self._generate_id(url)

            # Parse published date
            published_at = None
            published_str = raw.get("published", raw.get("date", raw.get("pubDate")))
            if published_str:
                published_at = self._parse_date(published_str)

            # Get content (snippet or full)
            content = raw.get("content", raw.get("snippet", raw.get("description", "")))

            # If fetch_content is True and we have a content fetcher, use it
            if fetch_content and not content:
                content = self._fetch_article_content(url)

            # Source name
            source = raw.get("source", raw.get("source_name", self.source_name))
            if isinstance(source, dict):
                source = source.get("title", source.get("name", self.source_name))

            return Article(
                id=article_id,
                title=title,
                content=content or "",
                url=url,
                source_name=source,
                published_at=published_at,
                retrieved_at=datetime.utcnow(),
                metadata={
                    "original_source": raw.get("source"),
                    "snippet": raw.get("snippet", ""),
                }
            )

        except Exception as e:
            print(f"[GoogleNewsAdapter] Error normalizing article: {e}")
            return None

    def _generate_id(self, url: str) -> str:
        """Generate unique article ID from URL."""
        hash_val = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"gn-{hash_val}"

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats."""
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S",
            "%d %b %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # Try parsing relative dates like "2 hours ago"
        return self._parse_relative_date(date_str)

    def _parse_relative_date(self, date_str: str) -> Optional[datetime]:
        """Parse relative date strings like '2 hours ago'."""
        import re
        from datetime import timedelta

        now = datetime.utcnow()
        date_str = date_str.lower().strip()

        patterns = [
            (r"(\d+)\s*min(?:ute)?s?\s*ago", lambda m: now - timedelta(minutes=int(m.group(1)))),
            (r"(\d+)\s*hours?\s*ago", lambda m: now - timedelta(hours=int(m.group(1)))),
            (r"(\d+)\s*days?\s*ago", lambda m: now - timedelta(days=int(m.group(1)))),
            (r"(\d+)\s*weeks?\s*ago", lambda m: now - timedelta(weeks=int(m.group(1)))),
            (r"yesterday", lambda m: now - timedelta(days=1)),
            (r"today", lambda m: now),
        ]

        for pattern, handler in patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    return handler(match)
                except:
                    pass

        return None

    def _fetch_article_content(self, url: str) -> str:
        """
        Fetch full article content from URL.

        This is a basic implementation - you may want to use a more
        sophisticated content extractor like newspaper3k or readability.
        """
        try:
            import urllib.request

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")

            # Basic text extraction (very simple)
            import re
            # Remove script and style elements
            html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
            # Remove tags
            text = re.sub(r"<[^>]+>", " ", html)
            # Normalize whitespace
            text = " ".join(text.split())

            return text[:10000]  # Limit length

        except Exception as e:
            print(f"[GoogleNewsAdapter] Error fetching content: {e}")
            return ""


# Example scraper integration template
def example_scraper_integration():
    """
    Example showing how to integrate an external Google News scraper.

    Replace 'your_google_news_scraper' with your actual scraper module.
    """
    # Example with gnews library (pip install gnews)
    try:
        from gnews import GNews

        def scrape_with_gnews(query: str) -> List[Dict]:
            google_news = GNews(language='en', max_results=50)
            results = google_news.get_news(query)
            return results

        adapter = GoogleNewsAdapter()
        adapter.set_scraper(scrape_with_gnews)
        return adapter

    except ImportError:
        print("gnews not installed. Use: pip install gnews")
        return None
