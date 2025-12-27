"""
Manual Source Adapter

For manually curated articles and intelligence reports.
Useful for high-value sources that aren't available via feeds.
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from ..models import Article


class ManualAdapter:
    """
    Adapter for manually curated articles.

    Usage:
        adapter = ManualAdapter()

        # Add single article
        adapter.add_article(
            title="Chinese Arsenal Ship Spotted",
            url="https://...",
            content="Full article text...",
            source_name="Naval News",
            published_at="2025-12-26"
        )

        # Load from JSON file
        adapter.load_from_file("curated_articles.json")

        # Get all articles
        articles = adapter.get_articles()
    """

    def __init__(self):
        self.articles: Dict[str, Article] = {}  # id -> Article

    def add_article(
        self,
        title: str,
        url: str,
        content: str,
        source_name: str,
        published_at: Optional[str] = None,
        article_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Article:
        """
        Add a manually curated article.

        Args:
            title: Article title
            url: Source URL
            content: Full article text
            source_name: Name of the source (e.g., "Naval News")
            published_at: Publication date (ISO format or YYYY-MM-DD)
            article_id: Custom ID (auto-generated if not provided)
            metadata: Additional metadata dict

        Returns:
            The created Article object
        """
        # Generate ID if not provided
        if not article_id:
            article_id = self._generate_id(url)

        # Parse date
        pub_date = None
        if published_at:
            pub_date = self._parse_date(published_at)

        article = Article(
            id=article_id,
            title=title,
            content=content,
            url=url,
            source_name=source_name,
            published_at=pub_date,
            retrieved_at=datetime.utcnow(),
            metadata=metadata or {}
        )

        self.articles[article_id] = article
        return article

    def load_from_file(self, file_path: str) -> List[Article]:
        """
        Load articles from a JSON file.

        Expected format:
        {
            "articles": [
                {
                    "title": "...",
                    "url": "...",
                    "content": "...",
                    "source_name": "...",
                    "published_at": "2025-12-26"
                },
                ...
            ]
        }
        """
        path = Path(file_path)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        articles_data = data.get("articles", data) if isinstance(data, dict) else data

        loaded = []
        for item in articles_data:
            article = self.add_article(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                source_name=item.get("source_name", item.get("source", "Unknown")),
                published_at=item.get("published_at", item.get("date")),
                article_id=item.get("id"),
                metadata=item.get("metadata", {})
            )
            loaded.append(article)

        return loaded

    def save_to_file(self, file_path: str) -> None:
        """Save all articles to JSON file."""
        path = Path(file_path)

        data = {
            "exported_at": datetime.utcnow().isoformat(),
            "article_count": len(self.articles),
            "articles": [
                {
                    "id": a.id,
                    "title": a.title,
                    "url": a.url,
                    "content": a.content,
                    "source_name": a.source_name,
                    "published_at": a.published_at.isoformat() if a.published_at else None,
                    "metadata": a.metadata
                }
                for a in self.articles.values()
            ]
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_articles(self) -> List[Article]:
        """Get all loaded articles."""
        return list(self.articles.values())

    def get_article(self, article_id: str) -> Optional[Article]:
        """Get article by ID."""
        return self.articles.get(article_id)

    def remove_article(self, article_id: str) -> bool:
        """Remove article by ID."""
        if article_id in self.articles:
            del self.articles[article_id]
            return True
        return False

    def clear(self) -> None:
        """Remove all articles."""
        self.articles.clear()

    def _generate_id(self, url: str) -> str:
        """Generate article ID from URL."""
        hash_val = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"manual-{hash_val}"

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string."""
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None


# Convenience function for quick article creation
def create_article(
    title: str,
    url: str,
    content: str,
    source_name: str = "Manual",
    published_at: str = None
) -> Article:
    """
    Quick helper to create a single Article.

    Usage:
        from osint.sources.manual import create_article

        article = create_article(
            title="China's Arsenal Ship",
            url="https://...",
            content="Full text...",
            source_name="Naval News"
        )
    """
    adapter = ManualAdapter()
    return adapter.add_article(
        title=title,
        url=url,
        content=content,
        source_name=source_name,
        published_at=published_at
    )
