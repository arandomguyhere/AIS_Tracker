#!/usr/bin/env python3
"""
Satellite Intelligence Integration Module

Provides framework for integrating satellite imagery analysis:
1. Optical satellite imagery (Planet, Maxar, Sentinel-2)
2. SAR satellite imagery (Sentinel-1, ICEYE, Capella)
3. Automated laden status detection from imagery
4. Dark vessel detection from SAR

This module provides the data structures and integration points
for satellite imagery providers. Actual API calls require provider keys.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Tuple
import json
import os


class SatelliteProvider(Enum):
    """Available satellite imagery providers."""
    PLANET = "planet"           # Planet Labs (optical)
    MAXAR = "maxar"             # Maxar (optical, high-res)
    SENTINEL2 = "sentinel2"     # ESA Sentinel-2 (optical, free)
    SENTINEL1 = "sentinel1"     # ESA Sentinel-1 (SAR, free)
    ICEYE = "iceye"             # ICEYE (SAR, tasked)
    CAPELLA = "capella"         # Capella Space (SAR, tasked)
    SPIRE = "spire"             # Spire (RF/AIS tracking)


class ImageType(Enum):
    """Type of satellite image."""
    OPTICAL = "optical"         # Visible light imagery
    SAR = "sar"                 # Synthetic Aperture Radar
    INFRARED = "infrared"       # Thermal/IR imagery
    MULTISPECTRAL = "multispectral"  # Multiple bands


@dataclass
class SatelliteImage:
    """Satellite image metadata and analysis."""
    id: str
    provider: SatelliteProvider
    image_type: ImageType
    timestamp: datetime
    latitude: float
    longitude: float
    bbox: Tuple[float, float, float, float]  # min_lat, min_lon, max_lat, max_lon
    resolution_m: float
    cloud_cover_pct: Optional[float] = None  # For optical
    thumbnail_url: Optional[str] = None
    full_url: Optional[str] = None
    analysis: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'provider': self.provider.value,
            'image_type': self.image_type.value,
            'timestamp': self.timestamp.isoformat(),
            'latitude': self.latitude,
            'longitude': self.longitude,
            'bbox': list(self.bbox),
            'resolution_m': self.resolution_m,
            'cloud_cover_pct': self.cloud_cover_pct,
            'thumbnail_url': self.thumbnail_url,
            'full_url': self.full_url,
            'analysis': self.analysis
        }


@dataclass
class VesselDetection:
    """Vessel detected in satellite imagery."""
    image_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    length_m: float
    width_m: Optional[float] = None
    heading: Optional[float] = None
    confidence: float = 0.8
    vessel_type: Optional[str] = None
    matched_mmsi: Optional[str] = None
    matched_name: Optional[str] = None
    laden_status: Optional[str] = None  # 'laden', 'ballast', 'unknown'
    estimated_draft_m: Optional[float] = None
    wake_detected: bool = False
    speed_estimate_knots: Optional[float] = None
    is_dark: bool = False  # No AIS match
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            'image_id': self.image_id,
            'timestamp': self.timestamp.isoformat(),
            'latitude': self.latitude,
            'longitude': self.longitude,
            'length_m': self.length_m,
            'width_m': self.width_m,
            'heading': self.heading,
            'confidence': self.confidence,
            'vessel_type': self.vessel_type,
            'matched_mmsi': self.matched_mmsi,
            'matched_name': self.matched_name,
            'laden_status': self.laden_status,
            'estimated_draft_m': self.estimated_draft_m,
            'wake_detected': self.wake_detected,
            'speed_estimate_knots': self.speed_estimate_knots,
            'is_dark': self.is_dark,
            'notes': self.notes
        }


@dataclass
class STSDetection:
    """Ship-to-ship transfer detected in satellite imagery."""
    image_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    vessel1: VesselDetection
    vessel2: VesselDetection
    separation_m: float
    confidence: float = 0.7
    transfer_type: str = "unknown"  # 'sts_oil', 'sts_cargo', 'bunkering'
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            'image_id': self.image_id,
            'timestamp': self.timestamp.isoformat(),
            'latitude': self.latitude,
            'longitude': self.longitude,
            'vessel1': self.vessel1.to_dict(),
            'vessel2': self.vessel2.to_dict(),
            'separation_m': self.separation_m,
            'confidence': self.confidence,
            'transfer_type': self.transfer_type,
            'notes': self.notes
        }


@dataclass
class OilSpillDetection:
    """Oil spill detected in SAR imagery."""
    image_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    area_sq_km: float
    confidence: float
    associated_vessel_mmsi: Optional[str] = None
    severity: str = "unknown"  # 'minor', 'moderate', 'major'

    def to_dict(self) -> dict:
        return {
            'image_id': self.image_id,
            'timestamp': self.timestamp.isoformat(),
            'latitude': self.latitude,
            'longitude': self.longitude,
            'area_sq_km': self.area_sq_km,
            'confidence': self.confidence,
            'associated_vessel_mmsi': self.associated_vessel_mmsi,
            'severity': self.severity
        }


class SatelliteImageryService:
    """
    Satellite imagery integration service.

    Provides unified interface for:
    - Searching imagery archives
    - Tasking new imagery collection
    - Processing vessel detections
    - Correlating with AIS data
    """

    def __init__(self):
        self.providers = {}
        self._load_config()

    def _load_config(self):
        """Load API keys and configuration."""
        # Check for provider API keys in environment
        self.providers = {
            'planet': os.environ.get('PLANET_API_KEY'),
            'maxar': os.environ.get('MAXAR_API_KEY'),
            'sentinel': True,  # Copernicus Open Access Hub (free)
            'iceye': os.environ.get('ICEYE_API_KEY'),
            'capella': os.environ.get('CAPELLA_API_KEY'),
            'spire': os.environ.get('SPIRE_API_KEY')
        }

    def get_available_providers(self) -> List[str]:
        """Return list of configured providers."""
        return [k for k, v in self.providers.items() if v]

    def search_imagery(self,
                      latitude: float,
                      longitude: float,
                      radius_km: float = 50,
                      start_date: datetime = None,
                      end_date: datetime = None,
                      providers: List[str] = None,
                      max_cloud_cover: float = 20,
                      image_type: ImageType = None) -> List[SatelliteImage]:
        """
        Search for available satellite imagery in area.

        This is a framework method - actual implementation requires
        provider API integration.
        """
        # Default to last 7 days
        if not end_date:
            end_date = datetime.now()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        results = []

        # For demo/POC - return simulated Sentinel-2 imagery
        if not providers or 'sentinel' in providers:
            # Sentinel-2 has ~5 day revisit time
            current = start_date
            while current <= end_date:
                results.append(SatelliteImage(
                    id=f"S2_{current.strftime('%Y%m%d')}_{int(latitude*100)}_{int(longitude*100)}",
                    provider=SatelliteProvider.SENTINEL2,
                    image_type=ImageType.OPTICAL,
                    timestamp=current,
                    latitude=latitude,
                    longitude=longitude,
                    bbox=(latitude - 0.5, longitude - 0.5, latitude + 0.5, longitude + 0.5),
                    resolution_m=10,
                    cloud_cover_pct=15.0,  # Simulated
                    thumbnail_url=f"/api/satellite/thumbnail/S2_{current.strftime('%Y%m%d')}",
                    analysis={'status': 'available', 'source': 'Copernicus Open Access Hub'}
                ))
                current += timedelta(days=5)

        # Sentinel-1 SAR (all weather, day/night)
        if not providers or 'sentinel' in providers:
            current = start_date
            while current <= end_date:
                results.append(SatelliteImage(
                    id=f"S1_{current.strftime('%Y%m%d')}_{int(latitude*100)}_{int(longitude*100)}",
                    provider=SatelliteProvider.SENTINEL1,
                    image_type=ImageType.SAR,
                    timestamp=current,
                    latitude=latitude,
                    longitude=longitude,
                    bbox=(latitude - 0.5, longitude - 0.5, latitude + 0.5, longitude + 0.5),
                    resolution_m=20,
                    cloud_cover_pct=None,  # SAR not affected by clouds
                    thumbnail_url=f"/api/satellite/thumbnail/S1_{current.strftime('%Y%m%d')}",
                    analysis={'status': 'available', 'source': 'Copernicus Open Access Hub', 'polarization': 'VV+VH'}
                ))
                current += timedelta(days=6)

        return results

    def get_vessel_detections(self,
                             image_id: str,
                             ais_data: List[dict] = None) -> List[VesselDetection]:
        """
        Get vessel detections from a satellite image.

        Correlates with AIS data to identify dark vessels.
        """
        # This would call actual vessel detection API
        # For demo, return empty - actual integration needed
        return []

    def detect_sts_operations(self,
                             image_id: str,
                             min_separation_m: float = 50,
                             max_separation_m: float = 300) -> List[STSDetection]:
        """
        Detect ship-to-ship transfer operations in imagery.

        Looks for:
        - Two vessels in close proximity
        - Parallel orientation
        - Fenders/hoses visible (high-res optical)
        - Oil sheen (SAR)
        """
        return []

    def analyze_laden_status(self,
                            image_id: str,
                            vessel_detection: VesselDetection) -> dict:
        """
        Analyze vessel laden status from imagery.

        Methods:
        - Optical: Freeboard measurement, waterline analysis
        - SAR: Radar cross-section analysis
        - Multispectral: Thermal signature analysis

        Returns estimated draft and confidence.
        """
        # Freeboard analysis requires high-res imagery
        return {
            'method': 'freeboard_analysis',
            'estimated_draft_m': None,
            'laden_status': 'unknown',
            'confidence': 0.0,
            'notes': 'Requires high-resolution imagery (< 1m) for accurate analysis'
        }


# Global service instance
_satellite_service = None


def get_satellite_service() -> SatelliteImageryService:
    """Get or create satellite imagery service."""
    global _satellite_service
    if _satellite_service is None:
        _satellite_service = SatelliteImageryService()
    return _satellite_service


def search_vessel_imagery(mmsi: str,
                         latitude: float,
                         longitude: float,
                         days: int = 30) -> dict:
    """
    Search for satellite imagery showing a specific vessel.

    Returns available imagery and any automated detections.
    """
    service = get_satellite_service()

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Search for imagery in vessel's area
    imagery = service.search_imagery(
        latitude=latitude,
        longitude=longitude,
        radius_km=50,
        start_date=start_date,
        end_date=end_date
    )

    return {
        'mmsi': mmsi,
        'search_center': {'lat': latitude, 'lon': longitude},
        'search_period_days': days,
        'available_imagery': [img.to_dict() for img in imagery],
        'providers': service.get_available_providers(),
        'total_images': len(imagery),
        'optical_images': len([i for i in imagery if i.image_type == ImageType.OPTICAL]),
        'sar_images': len([i for i in imagery if i.image_type == ImageType.SAR])
    }


def get_area_imagery(min_lat: float, min_lon: float,
                    max_lat: float, max_lon: float,
                    days: int = 7) -> dict:
    """
    Get satellite imagery coverage for an area.

    Used for infrastructure monitoring, dark vessel detection, etc.
    """
    service = get_satellite_service()

    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    imagery = service.search_imagery(
        latitude=center_lat,
        longitude=center_lon,
        radius_km=100,
        start_date=start_date,
        end_date=end_date
    )

    return {
        'bbox': [min_lat, min_lon, max_lat, max_lon],
        'center': {'lat': center_lat, 'lon': center_lon},
        'search_period_days': days,
        'available_imagery': [img.to_dict() for img in imagery],
        'coverage': {
            'total_images': len(imagery),
            'latest_optical': max([i.timestamp for i in imagery if i.image_type == ImageType.OPTICAL], default=None),
            'latest_sar': max([i.timestamp for i in imagery if i.image_type == ImageType.SAR], default=None)
        }
    }


# Storage facility monitoring
@dataclass
class StorageFacility:
    """Oil/fuel storage facility for monitoring."""
    id: str
    name: str
    latitude: float
    longitude: float
    facility_type: str  # 'tank_farm', 'refinery', 'terminal', 'floating_storage'
    country: str
    capacity_barrels: Optional[int] = None
    num_tanks: Optional[int] = None
    owner: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'facility_type': self.facility_type,
            'country': self.country,
            'capacity_barrels': self.capacity_barrels,
            'num_tanks': self.num_tanks,
            'owner': self.owner,
            'notes': self.notes
        }


@dataclass
class StorageReading:
    """Storage facility level reading from satellite."""
    facility_id: str
    timestamp: datetime
    image_id: str
    estimated_fill_pct: float
    confidence: float
    method: str = "shadow_analysis"  # 'shadow_analysis', 'floating_roof', 'thermal'

    def to_dict(self) -> dict:
        return {
            'facility_id': self.facility_id,
            'timestamp': self.timestamp.isoformat(),
            'image_id': self.image_id,
            'estimated_fill_pct': self.estimated_fill_pct,
            'confidence': self.confidence,
            'method': self.method
        }


# Key storage facilities for dark fleet monitoring
MONITORED_STORAGE_FACILITIES = [
    # Venezuela
    StorageFacility("VE001", "Jose Oil Terminal", 10.15, -64.68, "terminal", "Venezuela",
                   capacity_barrels=50000000, notes="Main Venezuela crude export terminal"),
    StorageFacility("VE002", "Amuay Refinery Tank Farm", 11.74, -70.21, "tank_farm", "Venezuela",
                   capacity_barrels=30000000, notes="Part of Paraguana refinery complex"),

    # Malaysia STS Hub (for Iran sanctions evasion)
    StorageFacility("MY001", "Tanjung Pelepas Anchorage", 1.35, 103.55, "floating_storage", "Malaysia",
                   notes="Major STS hub for Iranian oil - multiple FSOs"),

    # Russia Shadow Fleet Storage
    StorageFacility("GR001", "Kalamata Anchorage", 36.95, 22.10, "floating_storage", "Greece",
                   notes="STS hub for Russian Urals crude"),
    StorageFacility("TK001", "Ceuta Anchorage", 35.89, -5.32, "floating_storage", "Spain/Morocco",
                   notes="STS hub for Russian oil re-export"),

    # China Import Terminals
    StorageFacility("CN001", "Ningbo-Zhoushan Tank Farm", 29.87, 122.10, "terminal", "China",
                   capacity_barrels=100000000, notes="Major import terminal for Iranian/Russian oil"),
    StorageFacility("CN002", "Qingdao Tank Farm", 36.07, 120.38, "terminal", "China",
                   capacity_barrels=80000000, notes="Major crude import terminal"),
]


def get_storage_facilities(region: str = None) -> List[dict]:
    """Get monitored storage facilities."""
    facilities = MONITORED_STORAGE_FACILITIES

    if region:
        region_map = {
            'venezuela': ['VE'],
            'iran': ['MY', 'UAE'],
            'russia': ['GR', 'TK'],
            'china': ['CN']
        }
        prefixes = region_map.get(region.lower(), [])
        if prefixes:
            facilities = [f for f in facilities if any(f.id.startswith(p) for p in prefixes)]

    return [f.to_dict() for f in facilities]


def analyze_storage_levels(facility_id: str, days: int = 30) -> dict:
    """
    Analyze storage facility levels over time using satellite imagery.

    Uses floating roof tank shadow analysis or fixed tank thermal signatures.
    """
    # Find facility
    facility = next((f for f in MONITORED_STORAGE_FACILITIES if f.id == facility_id), None)
    if not facility:
        return {'error': f'Facility {facility_id} not found'}

    service = get_satellite_service()

    # Get imagery
    imagery = service.search_imagery(
        latitude=facility.latitude,
        longitude=facility.longitude,
        radius_km=5,
        start_date=datetime.now() - timedelta(days=days),
        end_date=datetime.now()
    )

    # For demo - generate simulated readings
    readings = []
    for img in imagery:
        if img.image_type == ImageType.OPTICAL and (img.cloud_cover_pct or 0) < 30:
            # Simulate shadow analysis reading
            import random
            readings.append(StorageReading(
                facility_id=facility_id,
                timestamp=img.timestamp,
                image_id=img.id,
                estimated_fill_pct=random.uniform(40, 80),  # Simulated
                confidence=0.7 if img.resolution_m <= 10 else 0.5,
                method='shadow_analysis'
            ))

    return {
        'facility': facility.to_dict(),
        'analysis_period_days': days,
        'readings': [r.to_dict() for r in readings],
        'imagery_count': len(imagery),
        'reading_count': len(readings),
        'notes': 'Readings are simulated - requires satellite imagery API integration'
    }


if __name__ == '__main__':
    # Test satellite imagery search
    result = search_vessel_imagery(
        mmsi="123456789",
        latitude=10.15,
        longitude=-64.68,
        days=14
    )
    print(json.dumps(result, indent=2, default=str))

    # Test storage facility analysis
    storage = analyze_storage_levels("VE001", days=30)
    print(json.dumps(storage, indent=2, default=str))
