"""
AIS Data Sources Module

Pluggable AIS ingestion layer supporting multiple free data sources.

Sources (priority order):
1. AISStream.io - Real-time WebSocket (primary)
2. AISHub - Community data sharing (fallback)
3. Marinesia - REST API (fallback)
4. Global Fishing Watch - REST API (enrichment only)

All sources normalize output to a common format for consistent processing.
"""

from .base import AISSource, AISPosition, AISVesselInfo, SourceStatus
from .manager import AISSourceManager
from .aisstream import AISStreamSource
from .aishub import AISHubSource
from .marinesia import MarinesiaSource
from .gfw import GlobalFishingWatchSource

__all__ = [
    "AISSource",
    "AISPosition",
    "AISVesselInfo",
    "SourceStatus",
    "AISSourceManager",
    "AISStreamSource",
    "AISHubSource",
    "MarinesiaSource",
    "GlobalFishingWatchSource"
]
