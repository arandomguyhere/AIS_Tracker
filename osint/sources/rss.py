"""
RSS Feed Source Adapter

Fetches and normalizes articles from RSS/Atom feeds.
Useful for monitoring specific news outlets or aggregators.
"""

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
from ..models import Article


class RSSAdapter:
    """
    Adapter for RSS/Atom feed sources.

    Usage:
        adapter = RSSAdapter()
        adapter.add_feed("Naval News", "https://www.navalnews.com/feed/")
        adapter.add_feed("The War Zone", "https://www.thedrive.com/the-war-zone/feed")
        articles = adapter.fetch_all()
    """

    def __init__(self):
        self.feeds: Dict[str, str] = {}  # name -> url
        self.user_agent = "ArsenalTracker/1.0 OSINT Bot"

    def add_feed(self, name: str, url: str) -> None:
        """Add a feed to monitor."""
        self.feeds[name] = url

    def remove_feed(self, name: str) -> None:
        """Remove a feed."""
        self.feeds.pop(name, None)

    def fetch_all(self, max_per_feed: int = 50) -> List[Article]:
        """Fetch articles from all configured feeds."""
        all_articles = []

        for name, url in self.feeds.items():
            try:
                articles = self.fetch_feed(url, name, max_per_feed)
                all_articles.extend(articles)
                print(f"[RSS] Fetched {len(articles)} from {name}")
            except Exception as e:
                print(f"[RSS] Error fetching {name}: {e}")

        return all_articles

    def fetch_feed(
        self,
        url: str,
        source_name: str = "RSS Feed",
        max_items: int = 50
    ) -> List[Article]:
        """
        Fetch and parse a single RSS/Atom feed.
        """
        try:
            req = Request(url, headers={"User-Agent": self.user_agent})
            with urlopen(req, timeout=15) as response:
                xml_content = response.read()

            # Parse XML
            root = ET.fromstring(xml_content)

            # Detect feed type and parse
            if root.tag == "rss" or root.find("channel") is not None:
                items = self._parse_rss(root, source_name)
            elif "feed" in root.tag.lower() or root.find("{http://www.w3.org/2005/Atom}entry") is not None:
                items = self._parse_atom(root, source_name)
            else:
                items = self._parse_generic(root, source_name)

            return items[:max_items]

        except URLError as e:
            raise RuntimeError(f"Failed to fetch feed: {e}")
        except ET.ParseError as e:
            raise RuntimeError(f"Failed to parse feed XML: {e}")

    def _parse_rss(self, root: ET.Element, source_name: str) -> List[Article]:
        """Parse RSS 2.0 feed."""
        articles = []
        channel = root.find("channel")

        if channel is None:
            return articles

        for item in channel.findall("item"):
            article = self._rss_item_to_article(item, source_name)
            if article:
                articles.append(article)

        return articles

    def _rss_item_to_article(self, item: ET.Element, source_name: str) -> Optional[Article]:
        """Convert RSS item to Article."""
        title = self._get_text(item, "title")
        link = self._get_text(item, "link")

        if not title or not link:
            return None

        description = self._get_text(item, "description", "")
        content = self._get_text(item, "{http://purl.org/rss/1.0/modules/content/}encoded", description)
        pub_date = self._get_text(item, "pubDate")

        # Clean HTML from content
        content = self._strip_html(content)

        return Article(
            id=self._generate_id(link),
            title=title,
            content=content,
            url=link,
            source_name=source_name,
            published_at=self._parse_date(pub_date) if pub_date else None,
            retrieved_at=datetime.utcnow()
        )

    def _parse_atom(self, root: ET.Element, source_name: str) -> List[Article]:
        """Parse Atom feed."""
        articles = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns) or root.findall("entry"):
            article = self._atom_entry_to_article(entry, source_name, ns)
            if article:
                articles.append(article)

        return articles

    def _atom_entry_to_article(
        self,
        entry: ET.Element,
        source_name: str,
        ns: Dict
    ) -> Optional[Article]:
        """Convert Atom entry to Article."""
        title = self._get_text(entry, "atom:title", ns=ns) or self._get_text(entry, "title")

        # Get link (Atom can have multiple links)
        link = None
        for link_elem in entry.findall("atom:link", ns) or entry.findall("link"):
            href = link_elem.get("href")
            rel = link_elem.get("rel", "alternate")
            if href and rel == "alternate":
                link = href
                break
            elif href and not link:
                link = href

        if not title or not link:
            return None

        content = (
            self._get_text(entry, "atom:content", ns=ns) or
            self._get_text(entry, "atom:summary", ns=ns) or
            self._get_text(entry, "content") or
            self._get_text(entry, "summary") or
            ""
        )
        content = self._strip_html(content)

        updated = (
            self._get_text(entry, "atom:updated", ns=ns) or
            self._get_text(entry, "atom:published", ns=ns) or
            self._get_text(entry, "updated") or
            self._get_text(entry, "published")
        )

        return Article(
            id=self._generate_id(link),
            title=title,
            content=content,
            url=link,
            source_name=source_name,
            published_at=self._parse_date(updated) if updated else None,
            retrieved_at=datetime.utcnow()
        )

    def _parse_generic(self, root: ET.Element, source_name: str) -> List[Article]:
        """Attempt to parse unknown feed format."""
        articles = []

        # Look for any element that might be an article
        for elem in root.iter():
            if elem.tag.lower() in ("item", "entry", "article"):
                title = None
                link = None
                content = ""

                for child in elem:
                    tag = child.tag.lower().split("}")[-1]  # Remove namespace
                    if tag == "title" and not title:
                        title = child.text
                    elif tag == "link":
                        link = child.get("href") or child.text
                    elif tag in ("description", "content", "summary"):
                        content = child.text or ""

                if title and link:
                    articles.append(Article(
                        id=self._generate_id(link),
                        title=title,
                        content=self._strip_html(content),
                        url=link,
                        source_name=source_name,
                        retrieved_at=datetime.utcnow()
                    ))

        return articles

    def _get_text(
        self,
        elem: ET.Element,
        tag: str,
        default: str = None,
        ns: Dict = None
    ) -> Optional[str]:
        """Get text content of child element."""
        if ns:
            child = elem.find(tag, ns)
        else:
            child = elem.find(tag)

        if child is not None and child.text:
            return child.text.strip()
        return default

    def _generate_id(self, url: str) -> str:
        """Generate article ID from URL."""
        hash_val = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"rss-{hash_val}"

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats."""
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        import re
        if not text:
            return ""
        # Remove tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&nbsp;", " ").replace("&quot;", '"')
        # Normalize whitespace
        text = " ".join(text.split())
        return text
