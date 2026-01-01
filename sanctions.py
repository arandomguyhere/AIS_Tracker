"""
Sanctions Database Integration Module

Integrates with multiple sanctions data sources to build comprehensive
dark fleet vessel database:

Sources:
- FleetLeaks (800+ vessels): https://fleetleaks.com/
  - Covers OFAC, EU, UK, Canada, Australia, New Zealand
  - Daily updates from official sources
  - API: /wp-json/fleetleaks/v1/vessels/map-data

- TankerTrackers (1,300+ tankers): https://tankertrackers.com/report/sanctioned
  - Officially blacklisted tankers
  - IMO numbers available separately

- OFAC SDN List: https://ofac.treasury.gov/sanctions-list-service
  - Official U.S. Treasury sanctions list
  - XML/CSV downloads available
  - Vessel type filtering supported

- OpenSanctions: https://www.opensanctions.org/
  - Maritime CSV export for bulk data
  - Consolidated from multiple jurisdictions

Usage:
    from sanctions import SanctionsDatabase, fetch_fleetleaks, fetch_ofac_vessels

    # Initialize database
    db = SanctionsDatabase()

    # Fetch from sources
    db.update_from_fleetleaks()
    db.update_from_ofac()

    # Check vessel
    result = db.check_vessel(imo="9313242")
    # Returns: {"sanctioned": True, "authorities": ["OFAC", "EU"], ...}
"""

import json
import os
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


# =============================================================================
# Sanctioning Authorities
# =============================================================================

class SanctionAuthority(Enum):
    """International sanctioning authorities."""
    OFAC = "OFAC"          # U.S. Treasury
    EU = "EU"              # European Union
    UK = "UK"              # UK OFSI
    CANADA = "CA"          # Canada SEMA
    AUSTRALIA = "AU"       # Australia DFAT
    NEW_ZEALAND = "NZ"     # New Zealand MFAT
    UN = "UN"              # United Nations


# =============================================================================
# Sanctioned Vessel Record
# =============================================================================

@dataclass
class SanctionedVessel:
    """Record of a sanctioned vessel."""
    imo: str
    name: str
    flag: Optional[str] = None
    vessel_type: Optional[str] = None
    mmsi: Optional[str] = None
    former_names: List[str] = field(default_factory=list)
    sanctioned_by: List[str] = field(default_factory=list)
    sanction_date: Optional[datetime] = None
    sanction_programs: List[str] = field(default_factory=list)
    notes: str = ""
    source: str = ""
    last_updated: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "imo": self.imo,
            "name": self.name,
            "flag": self.flag,
            "vessel_type": self.vessel_type,
            "mmsi": self.mmsi,
            "former_names": self.former_names,
            "sanctioned_by": self.sanctioned_by,
            "sanction_date": self.sanction_date.isoformat() if self.sanction_date else None,
            "sanction_programs": self.sanction_programs,
            "notes": self.notes,
            "source": self.source,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SanctionedVessel":
        return cls(
            imo=data.get("imo", ""),
            name=data.get("name", ""),
            flag=data.get("flag"),
            vessel_type=data.get("vessel_type"),
            mmsi=data.get("mmsi"),
            former_names=data.get("former_names", []),
            sanctioned_by=data.get("sanctioned_by", []),
            sanction_date=datetime.fromisoformat(data["sanction_date"]) if data.get("sanction_date") else None,
            sanction_programs=data.get("sanction_programs", []),
            notes=data.get("notes", ""),
            source=data.get("source", ""),
            last_updated=datetime.fromisoformat(data["last_updated"]) if data.get("last_updated") else None
        )


# =============================================================================
# FleetLeaks Integration
# =============================================================================

FLEETLEAKS_API = "https://fleetleaks.com/wp-json/fleetleaks/v1/vessels/map-data"
FLEETLEAKS_VESSELS = "https://fleetleaks.com/vessels/"

def fetch_fleetleaks(api_key: Optional[str] = None) -> List[SanctionedVessel]:
    """
    Fetch sanctioned vessels from FleetLeaks API.

    FleetLeaks tracks 800+ vessels designated by:
    - OFAC (United States)
    - EU (European Union)
    - UK (OFSI)
    - Canada (SEMA)
    - Australia (DFAT)
    - New Zealand (MFAT)

    Args:
        api_key: Optional API key for authenticated access

    Returns:
        List of SanctionedVessel records

    Note:
        API may require authentication. If 403 received, use manual import
        or contact FleetLeaks for API access.
    """
    vessels = []

    headers = {
        "User-Agent": "ArsenalTracker/1.0",
        "Accept": "application/json"
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req = urllib.request.Request(FLEETLEAKS_API, headers=headers)

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))

            for vessel_data in data:
                vessels.append(SanctionedVessel(
                    imo=vessel_data.get("imo", ""),
                    name=vessel_data.get("name", ""),
                    flag=vessel_data.get("flag"),
                    vessel_type=vessel_data.get("vessel_type"),
                    sanctioned_by=vessel_data.get("sanctioners", []),
                    source="fleetleaks",
                    last_updated=datetime.utcnow()
                ))

    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(f"FleetLeaks API requires authentication. Visit {FLEETLEAKS_VESSELS}")
        else:
            print(f"FleetLeaks API error: {e.code}")
    except Exception as e:
        print(f"FleetLeaks fetch error: {e}")

    return vessels


# =============================================================================
# OFAC SDN List Integration
# =============================================================================

# OFAC provides multiple download formats
OFAC_SDN_XML = "https://www.treasury.gov/ofac/downloads/sdn.xml"
OFAC_SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
OFAC_ADVANCED_XML = "https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml"

def fetch_ofac_vessels() -> List[SanctionedVessel]:
    """
    Fetch vessels from OFAC SDN list.

    The SDN (Specially Designated Nationals) list includes:
    - Individuals and entities
    - Vessels with IMO numbers
    - Aircraft

    Vessel records include:
    - IMO number
    - Vessel name
    - Flag
    - Vessel type
    - Sanction program (IRAN, RUSSIA, etc.)

    Returns:
        List of SanctionedVessel records (vessels only)
    """
    vessels = []

    try:
        # Fetch CSV format (simpler to parse)
        req = urllib.request.Request(
            OFAC_SDN_CSV,
            headers={"User-Agent": "ArsenalTracker/1.0"}
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read().decode("utf-8", errors="ignore")

            # Parse CSV
            lines = content.split("\n")
            for line in lines:
                # OFAC CSV format varies, look for vessel indicators
                if "vessel" in line.lower() or "imo" in line.lower():
                    fields = line.split(",")
                    # Extract vessel data (format varies by entry type)
                    # This is a simplified parser - production would use xml
                    if len(fields) >= 3:
                        vessels.append(SanctionedVessel(
                            imo=_extract_imo(line),
                            name=fields[1].strip('"') if len(fields) > 1 else "",
                            source="ofac_sdn",
                            sanctioned_by=["OFAC"],
                            last_updated=datetime.utcnow()
                        ))

    except urllib.error.HTTPError as e:
        print(f"OFAC SDN fetch error: {e.code}")
    except Exception as e:
        print(f"OFAC fetch error: {e}")

    return vessels


def _extract_imo(text: str) -> str:
    """Extract IMO number from text."""
    import re
    match = re.search(r"IMO[:\s]*(\d{7})", text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Try just 7-digit number
    match = re.search(r"\b(\d{7})\b", text)
    if match:
        return match.group(1)

    return ""


# =============================================================================
# Known Sanctioned Vessels (Static Database)
# =============================================================================
# Compiled from FleetLeaks, OFAC, and public reporting
# Last updated: December 2025

KNOWN_SANCTIONED_VESSELS = [
    # Russia Shadow Fleet - Recently Sanctioned
    SanctionedVessel(
        imo="9328716",
        name="BLUE GULF",
        flag="Palau",
        vessel_type="Crude Oil Tanker",
        sanctioned_by=["OFAC"],
        sanction_programs=["IRAN-EO13902"],
        sanction_date=datetime(2025, 3, 13),
        source="ofac"
    ),
    SanctionedVessel(
        imo="9179834",
        name="SKIPPER",
        former_names=["ADISA"],
        flag="Cameroon",
        vessel_type="Crude Oil Tanker",
        sanctioned_by=["OFAC", "UK"],
        notes="Seized December 2025. 80+ days AIS spoofing. Iran-Venezuela-China route.",
        source="fleetleaks"
    ),

    # EU Package 19 Additions (2025)
    SanctionedVessel(
        imo="9274668",
        name="CAROLINE BEZENGI",
        sanctioned_by=["EU"],
        sanction_programs=["CFSP 2025/2032"],
        source="fleetleaks"
    ),
    SanctionedVessel(
        imo="9187629",
        name="ARMADA LEADER",
        sanctioned_by=["EU"],
        sanction_programs=["CFSP 2025/2032"],
        source="fleetleaks"
    ),
    SanctionedVessel(
        imo="9262073",
        name="IVAN KRAMSKOY",
        sanctioned_by=["EU"],
        sanction_programs=["CFSP 2025/2032"],
        source="fleetleaks"
    ),
    SanctionedVessel(
        imo="9298761",
        name="YAZ",
        sanctioned_by=["EU"],
        sanction_programs=["CFSP 2025/2032"],
        source="fleetleaks"
    ),
    SanctionedVessel(
        imo="9244765",
        name="NIKOLAY ANISHCHENKOV",
        sanctioned_by=["EU"],
        sanction_programs=["CFSP 2025/2032"],
        source="fleetleaks"
    ),

    # Venezuela-linked vessels
    SanctionedVessel(
        imo="9255589",
        name="CENTURIES",
        sanctioned_by=["OFAC"],
        notes="Seized December 2025 alongside Skipper",
        source="public_reporting"
    ),
    SanctionedVessel(
        imo="",  # IMO unknown
        name="BELLA 1",
        sanctioned_by=["OFAC"],
        notes="Currently pursued by U.S. Navy (December 2025)",
        source="public_reporting"
    ),

    # Iran-linked tankers
    SanctionedVessel(
        imo="9218699",
        name="ARMAN 114",
        flag="Iran",
        vessel_type="Crude Oil Tanker",
        sanctioned_by=["OFAC", "EU", "UK"],
        sanction_programs=["IRAN"],
        source="fleetleaks"
    ),

    # Add more vessels as identified...
]


# =============================================================================
# Sanctions Database Manager
# =============================================================================

class SanctionsDatabase:
    """
    Unified sanctions database manager.

    Aggregates data from multiple sources:
    - FleetLeaks API
    - OFAC SDN list
    - OpenSanctions
    - Manual additions

    Provides:
    - Vessel lookup by IMO, MMSI, or name
    - Sanction authority filtering
    - Name change / alias tracking
    - Integration with Venezuela detection
    """

    def __init__(self, db_path: str = "data/sanctions.db"):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """Create database tables if not exists."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sanctioned_vessels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imo TEXT UNIQUE,
                name TEXT NOT NULL,
                flag TEXT,
                vessel_type TEXT,
                mmsi TEXT,
                former_names TEXT,
                sanctioned_by TEXT,
                sanction_programs TEXT,
                sanction_date TEXT,
                notes TEXT,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_imo ON sanctioned_vessels(imo)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_mmsi ON sanctioned_vessels(mmsi)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_name ON sanctioned_vessels(name)
        """)

        conn.commit()
        conn.close()

    def add_vessel(self, vessel: SanctionedVessel) -> bool:
        """Add or update a sanctioned vessel."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO sanctioned_vessels
                (imo, name, flag, vessel_type, mmsi, former_names,
                 sanctioned_by, sanction_programs, sanction_date, notes, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(imo) DO UPDATE SET
                    name = excluded.name,
                    flag = excluded.flag,
                    vessel_type = excluded.vessel_type,
                    mmsi = excluded.mmsi,
                    former_names = excluded.former_names,
                    sanctioned_by = excluded.sanctioned_by,
                    sanction_programs = excluded.sanction_programs,
                    sanction_date = excluded.sanction_date,
                    notes = excluded.notes,
                    source = excluded.source,
                    updated_at = excluded.updated_at
            """, (
                vessel.imo,
                vessel.name,
                vessel.flag,
                vessel.vessel_type,
                vessel.mmsi,
                json.dumps(vessel.former_names),
                json.dumps(vessel.sanctioned_by),
                json.dumps(vessel.sanction_programs),
                vessel.sanction_date.isoformat() if vessel.sanction_date else None,
                vessel.notes,
                vessel.source,
                datetime.utcnow().isoformat()
            ))

            conn.commit()
            return True

        except Exception as e:
            print(f"Error adding vessel: {e}")
            return False
        finally:
            conn.close()

    def check_vessel(
        self,
        imo: Optional[str] = None,
        mmsi: Optional[str] = None,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if a vessel is sanctioned.

        Args:
            imo: IMO number (preferred)
            mmsi: MMSI number
            name: Vessel name (also checks former names)

        Returns:
            Dict with sanction status and details
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        result = {
            "sanctioned": False,
            "vessel": None,
            "authorities": [],
            "programs": [],
            "match_type": None
        }

        try:
            # Check by IMO (most reliable)
            if imo:
                cursor.execute(
                    "SELECT * FROM sanctioned_vessels WHERE imo = ?",
                    (imo,)
                )
                row = cursor.fetchone()
                if row:
                    result = self._parse_vessel_row(row)
                    result["match_type"] = "imo"
                    return result

            # Check by MMSI
            if mmsi:
                cursor.execute(
                    "SELECT * FROM sanctioned_vessels WHERE mmsi = ?",
                    (mmsi,)
                )
                row = cursor.fetchone()
                if row:
                    result = self._parse_vessel_row(row)
                    result["match_type"] = "mmsi"
                    return result

            # Check by name (including former names)
            if name:
                cursor.execute(
                    """SELECT * FROM sanctioned_vessels
                       WHERE name = ? OR former_names LIKE ?""",
                    (name, f'%"{name}"%')
                )
                row = cursor.fetchone()
                if row:
                    result = self._parse_vessel_row(row)
                    result["match_type"] = "name"
                    return result

        finally:
            conn.close()

        return result

    def _parse_vessel_row(self, row: tuple) -> Dict[str, Any]:
        """Parse database row into result dict."""
        return {
            "sanctioned": True,
            "vessel": {
                "imo": row[1],
                "name": row[2],
                "flag": row[3],
                "vessel_type": row[4],
                "mmsi": row[5],
                "former_names": json.loads(row[6]) if row[6] else [],
                "notes": row[10],
                "source": row[11]
            },
            "authorities": json.loads(row[7]) if row[7] else [],
            "programs": json.loads(row[8]) if row[8] else [],
            "sanction_date": row[9]
        }

    def get_all_vessels(
        self,
        authority: Optional[str] = None,
        vessel_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all sanctioned vessels with optional filtering."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM sanctioned_vessels WHERE 1=1"
        params = []

        if authority:
            query += " AND sanctioned_by LIKE ?"
            params.append(f'%"{authority}"%')

        if vessel_type:
            query += " AND vessel_type LIKE ?"
            params.append(f"%{vessel_type}%")

        cursor.execute(query, params)
        rows = cursor.fetchall()

        vessels = []
        for row in rows:
            vessels.append(self._parse_vessel_row(row)["vessel"])

        conn.close()
        return vessels

    def load_known_vessels(self):
        """Load static database of known sanctioned vessels."""
        count = 0
        for vessel in KNOWN_SANCTIONED_VESSELS:
            if self.add_vessel(vessel):
                count += 1
        return count

    def update_from_fleetleaks(self, api_key: Optional[str] = None) -> int:
        """Update database from FleetLeaks API."""
        vessels = fetch_fleetleaks(api_key)
        count = 0
        for vessel in vessels:
            if self.add_vessel(vessel):
                count += 1
        return count

    def update_from_ofac(self) -> int:
        """Update database from OFAC SDN list."""
        vessels = fetch_ofac_vessels()
        count = 0
        for vessel in vessels:
            if vessel.imo and self.add_vessel(vessel):
                count += 1
        return count

    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        # Total vessels
        cursor.execute("SELECT COUNT(*) FROM sanctioned_vessels")
        stats["total_vessels"] = cursor.fetchone()[0]

        # By authority
        cursor.execute("SELECT sanctioned_by FROM sanctioned_vessels")
        authority_counts = {}
        for row in cursor.fetchall():
            authorities = json.loads(row[0]) if row[0] else []
            for auth in authorities:
                authority_counts[auth] = authority_counts.get(auth, 0) + 1
        stats["by_authority"] = authority_counts

        # By flag
        cursor.execute("""
            SELECT flag, COUNT(*) as cnt
            FROM sanctioned_vessels
            WHERE flag IS NOT NULL
            GROUP BY flag
            ORDER BY cnt DESC
            LIMIT 10
        """)
        stats["top_flags"] = dict(cursor.fetchall())

        conn.close()
        return stats


# =============================================================================
# Integration with Venezuela Module
# =============================================================================

def check_venezuela_sanctions(
    mmsi: Optional[str] = None,
    imo: Optional[str] = None,
    name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check vessel against sanctions database with Venezuela context.

    Combines sanctions database lookup with Venezuela-specific risk factors.
    """
    db = SanctionsDatabase()

    # Check sanctions database
    result = db.check_vessel(imo=imo, mmsi=mmsi, name=name)

    # Add Venezuela-specific context
    if result["sanctioned"]:
        # Check if vessel is associated with Venezuela trade
        vessel = result.get("vessel", {})
        notes = vessel.get("notes", "").lower()

        result["venezuela_linked"] = any(x in notes for x in [
            "venezuela", "jose", "pdvsa", "caribbean"
        ])

        # Check for Iran-Venezuela-China route
        result["iran_venezuela_china_route"] = any(x in notes for x in [
            "iran-venezuela", "venezuela-china", "iran-china"
        ])

    return result


# =============================================================================
# CLI for Database Management
# =============================================================================

if __name__ == "__main__":
    import sys

    db = SanctionsDatabase()

    if len(sys.argv) < 2:
        print("Usage: python sanctions.py <command>")
        print("Commands:")
        print("  init      - Initialize database with known vessels")
        print("  update    - Update from FleetLeaks and OFAC")
        print("  stats     - Show database statistics")
        print("  check     - Check vessel (--imo, --mmsi, --name)")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        count = db.load_known_vessels()
        print(f"Loaded {count} known sanctioned vessels")

    elif command == "update":
        print("Updating from FleetLeaks...")
        fl_count = db.update_from_fleetleaks()
        print(f"  Added/updated {fl_count} vessels from FleetLeaks")

        print("Updating from OFAC SDN...")
        ofac_count = db.update_from_ofac()
        print(f"  Added/updated {ofac_count} vessels from OFAC")

    elif command == "stats":
        stats = db.get_statistics()
        print(f"\nSanctions Database Statistics")
        print(f"=" * 40)
        print(f"Total vessels: {stats['total_vessels']}")
        print(f"\nBy Authority:")
        for auth, count in stats.get("by_authority", {}).items():
            print(f"  {auth}: {count}")
        print(f"\nTop Flags:")
        for flag, count in stats.get("top_flags", {}).items():
            print(f"  {flag}: {count}")

    elif command == "check":
        # Parse --imo, --mmsi, --name arguments
        imo = mmsi = name = None
        for i, arg in enumerate(sys.argv[2:]):
            if arg == "--imo" and i + 1 < len(sys.argv) - 2:
                imo = sys.argv[i + 3]
            elif arg == "--mmsi" and i + 1 < len(sys.argv) - 2:
                mmsi = sys.argv[i + 3]
            elif arg == "--name" and i + 1 < len(sys.argv) - 2:
                name = sys.argv[i + 3]

        result = db.check_vessel(imo=imo, mmsi=mmsi, name=name)
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
