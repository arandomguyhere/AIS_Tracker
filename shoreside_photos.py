#!/usr/bin/env python3
"""
Shoreside Photography Module

Manages crowdsourced port photographs for vessel verification:
1. Photo upload with geolocation
2. Vessel identification and tagging
3. Timestamp verification
4. Photo metadata extraction

Key for dark fleet detection:
- Photos can verify vessel identity when AIS is off
- Document modifications, cargo operations, STS transfers
- Crowdsourced intelligence from port workers, shipping enthusiasts
"""

import base64
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Tuple


class PhotoType(Enum):
    """Type of shoreside photo."""
    VESSEL = "vessel"           # Photo of a vessel
    PORT = "port"               # General port photo
    STS = "sts"                 # Ship-to-ship operation
    CARGO = "cargo"             # Cargo operation
    MODIFICATION = "modification"  # Vessel modification
    FACILITY = "facility"       # Storage/refinery facility


class PhotoStatus(Enum):
    """Photo verification status."""
    PENDING = "pending"         # Awaiting verification
    VERIFIED = "verified"       # Confirmed authentic
    REJECTED = "rejected"       # Fake/misleading
    FLAGGED = "flagged"         # Needs review


@dataclass
class PhotoMetadata:
    """Extracted photo metadata."""
    width: int = 0
    height: int = 0
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    taken_at: Optional[datetime] = None
    has_exif: bool = False
    file_size_bytes: int = 0
    file_hash: str = ""

    def to_dict(self) -> dict:
        return {
            'width': self.width,
            'height': self.height,
            'camera_make': self.camera_make,
            'camera_model': self.camera_model,
            'gps_latitude': self.gps_latitude,
            'gps_longitude': self.gps_longitude,
            'taken_at': self.taken_at.isoformat() if self.taken_at else None,
            'has_exif': self.has_exif,
            'file_size_bytes': self.file_size_bytes,
            'file_hash': self.file_hash
        }


@dataclass
class ShoresidePhoto:
    """Shoreside photograph record."""
    id: str
    filename: str
    photo_type: PhotoType
    status: PhotoStatus = PhotoStatus.PENDING
    uploader_id: Optional[str] = None
    uploader_name: Optional[str] = None
    title: str = ""
    description: str = ""
    # Location
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    port_name: Optional[str] = None
    # Vessel identification
    vessel_id: Optional[int] = None
    vessel_mmsi: Optional[str] = None
    vessel_name: Optional[str] = None
    # Timing
    photo_taken: Optional[datetime] = None
    uploaded_at: datetime = field(default_factory=datetime.now)
    # Metadata
    metadata: PhotoMetadata = field(default_factory=PhotoMetadata)
    # Intel value
    intel_value: str = "low"  # low, medium, high, critical
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    # Storage
    file_path: str = ""
    thumbnail_path: str = ""

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'filename': self.filename,
            'photo_type': self.photo_type.value,
            'status': self.status.value,
            'uploader_id': self.uploader_id,
            'uploader_name': self.uploader_name,
            'title': self.title,
            'description': self.description,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'location_name': self.location_name,
            'port_name': self.port_name,
            'vessel_id': self.vessel_id,
            'vessel_mmsi': self.vessel_mmsi,
            'vessel_name': self.vessel_name,
            'photo_taken': self.photo_taken.isoformat() if self.photo_taken else None,
            'uploaded_at': self.uploaded_at.isoformat(),
            'metadata': self.metadata.to_dict(),
            'intel_value': self.intel_value,
            'tags': self.tags,
            'notes': self.notes,
            'file_url': f"/photos/{self.filename}" if self.filename else None,
            'thumbnail_url': f"/photos/thumb_{self.filename}" if self.filename else None
        }


class ShoresidePhotoService:
    """
    Service for managing shoreside photographs.

    Features:
    - Photo upload and storage
    - EXIF metadata extraction
    - Vessel identification
    - Location verification
    - Intel value assessment
    """

    def __init__(self, db_path: str = None, photos_dir: str = None):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = db_path or os.path.join(script_dir, 'arsenal_tracker.db')
        self.photos_dir = photos_dir or os.path.join(script_dir, 'static', 'photos')
        os.makedirs(self.photos_dir, exist_ok=True)
        self._ensure_tables()

    def _ensure_tables(self):
        """Create shoreside photos table if not exists."""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS shoreside_photos (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                photo_type TEXT DEFAULT 'vessel',
                status TEXT DEFAULT 'pending',
                uploader_id TEXT,
                uploader_name TEXT,
                title TEXT,
                description TEXT,
                latitude REAL,
                longitude REAL,
                location_name TEXT,
                port_name TEXT,
                vessel_id INTEGER,
                vessel_mmsi TEXT,
                vessel_name TEXT,
                photo_taken TIMESTAMP,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata TEXT,
                intel_value TEXT DEFAULT 'low',
                tags TEXT,
                notes TEXT,
                file_path TEXT,
                thumbnail_path TEXT,
                FOREIGN KEY (vessel_id) REFERENCES vessels(id) ON DELETE SET NULL
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_photos_vessel ON shoreside_photos(vessel_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_photos_mmsi ON shoreside_photos(vessel_mmsi)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_photos_location ON shoreside_photos(latitude, longitude)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_photos_status ON shoreside_photos(status)')
        conn.commit()
        conn.close()

    def _extract_metadata(self, image_data: bytes) -> PhotoMetadata:
        """Extract metadata from image bytes."""
        metadata = PhotoMetadata()
        metadata.file_size_bytes = len(image_data)
        metadata.file_hash = hashlib.sha256(image_data).hexdigest()[:16]

        # Try to extract EXIF data
        try:
            # Check for JPEG
            if image_data[:2] == b'\xff\xd8':
                # JPEG file - could extract EXIF with PIL if available
                pass

            # For now, basic detection
            metadata.has_exif = b'Exif' in image_data[:100]

        except Exception as e:
            print(f"Metadata extraction failed: {e}")

        return metadata

    def _generate_id(self) -> str:
        """Generate unique photo ID."""
        import uuid
        return f"photo_{uuid.uuid4().hex[:12]}"

    def _assess_intel_value(self, photo: ShoresidePhoto) -> str:
        """Assess intelligence value of photo."""
        score = 0

        # Vessel identification
        if photo.vessel_mmsi or photo.vessel_name:
            score += 2

        # Location data
        if photo.latitude and photo.longitude:
            score += 1
        if photo.port_name:
            score += 1

        # Photo type
        if photo.photo_type in [PhotoType.STS, PhotoType.MODIFICATION]:
            score += 3
        elif photo.photo_type == PhotoType.CARGO:
            score += 2

        # Metadata quality
        if photo.metadata.has_exif:
            score += 1
        if photo.photo_taken:
            score += 1

        # Tags
        high_value_tags = ['dark_fleet', 'sanctions', 'sts', 'modification', 'weapons']
        if any(tag in photo.tags for tag in high_value_tags):
            score += 2

        if score >= 8:
            return 'critical'
        elif score >= 5:
            return 'high'
        elif score >= 3:
            return 'medium'
        return 'low'

    def upload_photo(self,
                    image_data: bytes,
                    filename: str,
                    photo_type: str = "vessel",
                    uploader_name: str = None,
                    title: str = "",
                    description: str = "",
                    latitude: float = None,
                    longitude: float = None,
                    location_name: str = None,
                    port_name: str = None,
                    vessel_mmsi: str = None,
                    vessel_name: str = None,
                    photo_taken: str = None,
                    tags: List[str] = None) -> dict:
        """
        Upload a new shoreside photo.

        Args:
            image_data: Raw image bytes or base64 string
            filename: Original filename
            photo_type: Type of photo (vessel, port, sts, cargo, modification)
            uploader_name: Name/handle of uploader
            title: Photo title
            description: Photo description
            latitude, longitude: GPS coordinates
            location_name: Human-readable location
            port_name: Port/terminal name
            vessel_mmsi: MMSI of vessel in photo
            vessel_name: Name of vessel in photo
            photo_taken: When photo was taken (ISO format)
            tags: List of tags

        Returns:
            Photo record dict
        """
        # Handle base64 input
        if isinstance(image_data, str):
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            image_data = base64.b64decode(image_data)

        # Generate ID
        photo_id = self._generate_id()

        # Extract metadata
        metadata = self._extract_metadata(image_data)

        # Determine file extension
        ext = os.path.splitext(filename)[1].lower() or '.jpg'
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            ext = '.jpg'

        # Save file
        safe_filename = f"{photo_id}{ext}"
        file_path = os.path.join(self.photos_dir, safe_filename)
        with open(file_path, 'wb') as f:
            f.write(image_data)

        # Parse photo_taken
        taken_dt = None
        if photo_taken:
            try:
                taken_dt = datetime.fromisoformat(photo_taken.replace('Z', '+00:00'))
            except:
                pass

        # Create photo record
        photo = ShoresidePhoto(
            id=photo_id,
            filename=safe_filename,
            photo_type=PhotoType(photo_type) if photo_type else PhotoType.VESSEL,
            uploader_name=uploader_name,
            title=title,
            description=description,
            latitude=latitude or metadata.gps_latitude,
            longitude=longitude or metadata.gps_longitude,
            location_name=location_name,
            port_name=port_name,
            vessel_mmsi=vessel_mmsi,
            vessel_name=vessel_name,
            photo_taken=taken_dt or metadata.taken_at,
            metadata=metadata,
            tags=tags or [],
            file_path=file_path
        )

        # Assess intel value
        photo.intel_value = self._assess_intel_value(photo)

        # Save to database
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO shoreside_photos
            (id, filename, photo_type, status, uploader_name, title, description,
             latitude, longitude, location_name, port_name, vessel_mmsi, vessel_name,
             photo_taken, metadata, intel_value, tags, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            photo.id, photo.filename, photo.photo_type.value, photo.status.value,
            photo.uploader_name, photo.title, photo.description,
            photo.latitude, photo.longitude, photo.location_name, photo.port_name,
            photo.vessel_mmsi, photo.vessel_name,
            photo.photo_taken.isoformat() if photo.photo_taken else None,
            json.dumps(photo.metadata.to_dict()),
            photo.intel_value, json.dumps(photo.tags), photo.file_path
        ))
        conn.commit()
        conn.close()

        return photo.to_dict()

    def get_photo(self, photo_id: str) -> Optional[dict]:
        """Get single photo by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            'SELECT * FROM shoreside_photos WHERE id = ?', (photo_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_dict(row)

    def get_vessel_photos(self, vessel_id: int = None, mmsi: str = None,
                         vessel_name: str = None) -> List[dict]:
        """Get photos for a vessel."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        conditions = []
        params = []

        if vessel_id:
            conditions.append("vessel_id = ?")
            params.append(vessel_id)
        if mmsi:
            conditions.append("vessel_mmsi = ?")
            params.append(mmsi)
        if vessel_name:
            conditions.append("vessel_name LIKE ?")
            params.append(f"%{vessel_name}%")

        if not conditions:
            return []

        query = f"SELECT * FROM shoreside_photos WHERE {' OR '.join(conditions)} ORDER BY photo_taken DESC"
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_location_photos(self, latitude: float, longitude: float,
                           radius_km: float = 50) -> List[dict]:
        """Get photos near a location."""
        # Approximate degree to km conversion
        lat_range = radius_km / 111
        lon_range = radius_km / (111 * abs(latitude) if latitude else 111)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT * FROM shoreside_photos
            WHERE latitude BETWEEN ? AND ?
            AND longitude BETWEEN ? AND ?
            ORDER BY photo_taken DESC
        ''', (
            latitude - lat_range, latitude + lat_range,
            longitude - lon_range, longitude + lon_range
        ))
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_recent_photos(self, limit: int = 20, status: str = None,
                         photo_type: str = None) -> List[dict]:
        """Get recent photos."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if photo_type:
            conditions.append("photo_type = ?")
            params.append(photo_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        cursor = conn.execute(
            f"SELECT * FROM shoreside_photos {where} ORDER BY uploaded_at DESC LIMIT ?",
            params
        )
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def update_photo_status(self, photo_id: str, status: str,
                           notes: str = None) -> dict:
        """Update photo verification status."""
        conn = sqlite3.connect(self.db_path)
        if notes:
            conn.execute(
                "UPDATE shoreside_photos SET status = ?, notes = ? WHERE id = ?",
                (status, notes, photo_id)
            )
        else:
            conn.execute(
                "UPDATE shoreside_photos SET status = ? WHERE id = ?",
                (status, photo_id)
            )
        conn.commit()
        conn.close()
        return self.get_photo(photo_id)

    def link_vessel(self, photo_id: str, vessel_id: int) -> dict:
        """Link photo to a vessel record."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE shoreside_photos SET vessel_id = ? WHERE id = ?",
            (vessel_id, photo_id)
        )
        conn.commit()
        conn.close()
        return self.get_photo(photo_id)

    def search_photos(self, query: str = None, tags: List[str] = None,
                     port_name: str = None, start_date: str = None,
                     end_date: str = None) -> List[dict]:
        """Search photos by various criteria."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        conditions = []
        params = []

        if query:
            conditions.append("(title LIKE ? OR description LIKE ? OR vessel_name LIKE ?)")
            params.extend([f"%{query}%"] * 3)

        if tags:
            tag_conditions = []
            for tag in tags:
                tag_conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            conditions.append(f"({' OR '.join(tag_conditions)})")

        if port_name:
            conditions.append("port_name LIKE ?")
            params.append(f"%{port_name}%")

        if start_date:
            conditions.append("photo_taken >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("photo_taken <= ?")
            params.append(end_date)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cursor = conn.execute(
            f"SELECT * FROM shoreside_photos {where} ORDER BY photo_taken DESC LIMIT 100",
            params
        )
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_stats(self) -> dict:
        """Get photo collection statistics."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        stats = {
            'total_photos': 0,
            'by_status': {},
            'by_type': {},
            'by_intel_value': {},
            'vessels_with_photos': 0,
            'photos_with_location': 0
        }

        # Total count
        cursor = conn.execute("SELECT COUNT(*) as count FROM shoreside_photos")
        stats['total_photos'] = cursor.fetchone()['count']

        # By status
        cursor = conn.execute(
            "SELECT status, COUNT(*) as count FROM shoreside_photos GROUP BY status"
        )
        stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}

        # By type
        cursor = conn.execute(
            "SELECT photo_type, COUNT(*) as count FROM shoreside_photos GROUP BY photo_type"
        )
        stats['by_type'] = {row['photo_type']: row['count'] for row in cursor.fetchall()}

        # By intel value
        cursor = conn.execute(
            "SELECT intel_value, COUNT(*) as count FROM shoreside_photos GROUP BY intel_value"
        )
        stats['by_intel_value'] = {row['intel_value']: row['count'] for row in cursor.fetchall()}

        # Unique vessels
        cursor = conn.execute(
            "SELECT COUNT(DISTINCT vessel_mmsi) as count FROM shoreside_photos WHERE vessel_mmsi IS NOT NULL"
        )
        stats['vessels_with_photos'] = cursor.fetchone()['count']

        # Photos with location
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM shoreside_photos WHERE latitude IS NOT NULL"
        )
        stats['photos_with_location'] = cursor.fetchone()['count']

        conn.close()
        return stats

    def _row_to_dict(self, row) -> dict:
        """Convert database row to dictionary."""
        d = dict(row)

        # Parse JSON fields
        if d.get('metadata'):
            try:
                d['metadata'] = json.loads(d['metadata'])
            except:
                d['metadata'] = {}

        if d.get('tags'):
            try:
                d['tags'] = json.loads(d['tags'])
            except:
                d['tags'] = []

        # Add URLs
        if d.get('filename'):
            d['file_url'] = f"/photos/{d['filename']}"
            d['thumbnail_url'] = f"/photos/thumb_{d['filename']}"

        return d


# Global service instance
_photo_service = None


def get_photo_service(db_path: str = None) -> ShoresidePhotoService:
    """Get or create photo service."""
    global _photo_service
    if _photo_service is None:
        _photo_service = ShoresidePhotoService(db_path)
    return _photo_service


if __name__ == '__main__':
    # Test photo service
    service = ShoresidePhotoService()

    # Get stats
    stats = service.get_stats()
    print(json.dumps(stats, indent=2))
