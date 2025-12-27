"""
OSINT Data Source Adapters

This package provides adapters for various news and intelligence sources.
Each adapter normalizes data into the Article model for processing.

Available adapters:
- GoogleNewsAdapter: Integrates with Google News scraper
- RSSAdapter: Generic RSS feed adapter
- ManualAdapter: For manually curated articles
"""

from .google_news import GoogleNewsAdapter
from .rss import RSSAdapter
from .manual import ManualAdapter

__all__ = ["GoogleNewsAdapter", "RSSAdapter", "ManualAdapter"]
