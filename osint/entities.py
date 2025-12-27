"""
Entity extraction from news articles and intelligence reports.

Uses a combination of:
- Pattern matching (regex for vessel names, IMO/MMSI numbers)
- Keyword dictionaries (shipyards, weapon systems, ports)
- Contextual heuristics (capitalized phrases near keywords)

No external NLP dependencies - uses Python stdlib only.
"""

import re
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple
from .models import Entity, EntityType, Provenance, Article


class EntityExtractor:
    """
    Extracts named entities from text with full provenance tracking.

    Design principles:
    - Precision over recall: Better to miss an entity than extract garbage
    - Full provenance: Every extraction traces to source text
    - Interpretable rules: Analysts can understand why something was extracted
    """

    # Vessel name patterns
    VESSEL_PATTERNS = [
        # "MV VESSEL NAME" or "M/V VESSEL NAME"
        r'\b(?:MV|M/V|MT|M/T|SS|HMS|USNS|PLA[N]?S?)\s+([A-Z][A-Z0-9\s\-]{2,30})',
        # "vessel VESSEL NAME" or "ship VESSEL NAME"
        r'\b(?:vessel|ship|carrier|tanker|freighter|cargo ship)\s+([A-Z][A-Z0-9\s\-]{2,30})',
        # Chinese vessel naming: "ZHONG DA 79" pattern (pinyin + number)
        r'\b([A-Z]{2,}(?:\s+[A-Z]+)*\s+\d{1,3})\b',
        # Quoted vessel names
        r'["\']([A-Z][A-Z0-9\s\-]{2,25})["\']',
    ]

    # MMSI pattern (9 digits, often starting with country code)
    MMSI_PATTERN = r'\b(?:MMSI[:\s]*)?(\d{9})\b'

    # IMO pattern (IMO followed by 7 digits)
    IMO_PATTERN = r'\b(?:IMO[:\s]*)(\d{7})\b'

    # Known shipyards (expandable)
    SHIPYARDS = {
        "hudong-zhonghua": ["Hudong-Zhonghua", "Hudong Zhonghua", "HDZH"],
        "jiangnan": ["Jiangnan Shipyard", "Jiangnan"],
        "dalian": ["Dalian Shipbuilding", "Dalian Shipyard", "DSIC"],
        "longhai": ["Longhai Shipyard", "Longhai"],
        "wuchang": ["Wuchang Shipbuilding", "Wuchang"],
        "guangzhou": ["Guangzhou Shipyard", "GSI"],
        "huangpu": ["Huangpu Shipbuilding", "Huangpu Wenchong"],
        "shanghai_waigaoqiao": ["Shanghai Waigaoqiao", "SWS"],
        "cosco_dalian": ["COSCO Dalian", "COSCO Shipping Dalian"],
    }

    # Weapon systems and military equipment
    WEAPON_SYSTEMS = {
        "vls": ["VLS", "Vertical Launch System", "vertical launch", "missile cells"],
        "ciws": ["CIWS", "Close-In Weapon System", "Type 1130", "Phalanx", "Goalkeeper"],
        "containerized_missiles": ["containerized missile", "container missile", "modular missile"],
        "cruise_missile": ["cruise missile", "CJ-10", "CJ-100", "YJ-18", "YJ-21", "YJ-83"],
        "anti_ship": ["anti-ship missile", "AShM", "ship-killer"],
        "radar": ["radar system", "phased array", "fire control radar"],
        "decoy": ["decoy launcher", "Type 726", "chaff", "flare"],
        "torpedo": ["torpedo", "ASW", "anti-submarine"],
    }

    # Key locations (ports, straits, seas)
    LOCATIONS = {
        "taiwan_strait": ["Taiwan Strait", "Formosa Strait"],
        "south_china_sea": ["South China Sea", "SCS", "Spratly", "Paracel"],
        "east_china_sea": ["East China Sea", "ECS"],
        "yellow_sea": ["Yellow Sea", "Bohai"],
        "shanghai": ["Shanghai", "Huangpu River", "Yangtze River Delta"],
        "fujian": ["Fujian", "Xiamen", "Fuzhou"],
        "guangdong": ["Guangdong", "Shenzhen", "Hong Kong"],
        "hainan": ["Hainan", "Sanya", "Yulin"],
    }

    # Keywords indicating military/dual-use activity
    ACTIVITY_KEYWORDS = {
        "conversion": ["converted", "conversion", "modified", "retrofitted", "refit"],
        "military": ["military", "naval", "PLAN", "PLA Navy", "warship", "arsenal"],
        "weapons": ["armed", "weaponized", "missile", "launcher", "weapon"],
        "surveillance": ["monitoring", "tracking", "surveillance", "reconnaissance"],
        "exercise": ["exercise", "drill", "maneuver", "deployment"],
        "transit": ["transit", "passage", "sailed", "departed", "arrived"],
    }

    def __init__(self, custom_vessels: Optional[List[Dict]] = None):
        """
        Initialize extractor with optional custom vessel list.

        Args:
            custom_vessels: List of vessel dicts with 'name' and optional 'aliases'
        """
        self.custom_vessels = custom_vessels or []
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self.vessel_regexes = [re.compile(p, re.IGNORECASE) for p in self.VESSEL_PATTERNS]
        self.mmsi_regex = re.compile(self.MMSI_PATTERN)
        self.imo_regex = re.compile(self.IMO_PATTERN)

    def extract_all(self, article: Article) -> List[Entity]:
        """
        Extract all entity types from an article.

        Returns entities sorted by confidence (highest first).
        """
        entities = []
        full_text = f"{article.title}\n\n{article.content}"

        # Extract each entity type
        entities.extend(self._extract_vessels(full_text, article))
        entities.extend(self._extract_shipyards(full_text, article))
        entities.extend(self._extract_weapon_systems(full_text, article))
        entities.extend(self._extract_locations(full_text, article))
        entities.extend(self._extract_identifiers(full_text, article))
        entities.extend(self._extract_activity_keywords(full_text, article))

        # Sort by confidence
        entities.sort(key=lambda e: e.confidence, reverse=True)

        return entities

    def _extract_vessels(self, text: str, article: Article) -> List[Entity]:
        """Extract vessel names with contextual confidence scoring."""
        entities = []
        seen_normalized = set()

        # First, check for known/tracked vessels
        for vessel in self.custom_vessels:
            name = vessel.get("name", "")
            aliases = vessel.get("aliases", [])
            all_names = [name] + aliases

            for check_name in all_names:
                if check_name.lower() in text.lower():
                    # Find the exact match in text for provenance
                    pattern = re.compile(re.escape(check_name), re.IGNORECASE)
                    match = pattern.search(text)
                    if match:
                        matched_text = match.group(0)
                        normalized = self._normalize_vessel_name(name)

                        if normalized not in seen_normalized:
                            seen_normalized.add(normalized)
                            context = self._get_context(text, match.start(), match.end())

                            entities.append(Entity(
                                text=matched_text,
                                normalized=normalized,
                                entity_type=EntityType.VESSEL,
                                confidence=0.95,  # High confidence for known vessels
                                provenance=Provenance(
                                    source_url=article.url,
                                    source_name=article.source_name,
                                    retrieved_at=article.retrieved_at,
                                    original_text=context,
                                    extraction_method="known_vessel_match",
                                    reasoning=f"Matched known tracked vessel '{name}'"
                                ),
                                aliases=aliases,
                                metadata={"vessel_id": vessel.get("id")}
                            ))

        # Then, extract unknown vessels using patterns
        for regex in self.vessel_regexes:
            for match in regex.finditer(text):
                if match.groups():
                    vessel_name = match.group(1).strip()
                else:
                    vessel_name = match.group(0).strip()

                # Skip if too short or common word
                if len(vessel_name) < 3 or vessel_name.lower() in self._common_words():
                    continue

                normalized = self._normalize_vessel_name(vessel_name)
                if normalized not in seen_normalized:
                    seen_normalized.add(normalized)
                    context = self._get_context(text, match.start(), match.end())

                    # Calculate confidence based on context
                    confidence = self._calculate_vessel_confidence(vessel_name, context)

                    entities.append(Entity(
                        text=vessel_name,
                        normalized=normalized,
                        entity_type=EntityType.VESSEL,
                        confidence=confidence,
                        provenance=Provenance(
                            source_url=article.url,
                            source_name=article.source_name,
                            retrieved_at=article.retrieved_at,
                            original_text=context,
                            extraction_method="pattern_match",
                            reasoning=f"Extracted via vessel name pattern"
                        )
                    ))

        return entities

    def _extract_shipyards(self, text: str, article: Article) -> List[Entity]:
        """Extract shipyard mentions."""
        entities = []
        seen = set()

        for normalized_name, variations in self.SHIPYARDS.items():
            for variation in variations:
                if variation.lower() in text.lower():
                    pattern = re.compile(re.escape(variation), re.IGNORECASE)
                    match = pattern.search(text)
                    if match and normalized_name not in seen:
                        seen.add(normalized_name)
                        context = self._get_context(text, match.start(), match.end())

                        entities.append(Entity(
                            text=match.group(0),
                            normalized=normalized_name,
                            entity_type=EntityType.SHIPYARD,
                            confidence=0.9,
                            provenance=Provenance(
                                source_url=article.url,
                                source_name=article.source_name,
                                retrieved_at=article.retrieved_at,
                                original_text=context,
                                extraction_method="dictionary_match",
                                reasoning=f"Matched known shipyard '{normalized_name}'"
                            ),
                            aliases=variations
                        ))

        return entities

    def _extract_weapon_systems(self, text: str, article: Article) -> List[Entity]:
        """Extract weapon system mentions."""
        entities = []
        seen = set()

        for system_type, keywords in self.WEAPON_SYSTEMS.items():
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                    match = pattern.search(text)
                    if match and system_type not in seen:
                        seen.add(system_type)
                        context = self._get_context(text, match.start(), match.end())

                        entities.append(Entity(
                            text=match.group(0),
                            normalized=system_type,
                            entity_type=EntityType.WEAPON_SYSTEM,
                            confidence=0.85,
                            provenance=Provenance(
                                source_url=article.url,
                                source_name=article.source_name,
                                retrieved_at=article.retrieved_at,
                                original_text=context,
                                extraction_method="dictionary_match",
                                reasoning=f"Matched weapon system keyword '{keyword}'"
                            ),
                            metadata={"category": system_type}
                        ))

        return entities

    def _extract_locations(self, text: str, article: Article) -> List[Entity]:
        """Extract geographic locations relevant to maritime tracking."""
        entities = []
        seen = set()

        for location_type, keywords in self.LOCATIONS.items():
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                    match = pattern.search(text)
                    if match and location_type not in seen:
                        seen.add(location_type)
                        context = self._get_context(text, match.start(), match.end())

                        entities.append(Entity(
                            text=match.group(0),
                            normalized=location_type,
                            entity_type=EntityType.LOCATION,
                            confidence=0.9,
                            provenance=Provenance(
                                source_url=article.url,
                                source_name=article.source_name,
                                retrieved_at=article.retrieved_at,
                                original_text=context,
                                extraction_method="dictionary_match",
                                reasoning=f"Matched known location '{keyword}'"
                            )
                        ))

        return entities

    def _extract_identifiers(self, text: str, article: Article) -> List[Entity]:
        """Extract MMSI and IMO numbers."""
        entities = []

        # MMSI numbers
        for match in self.mmsi_regex.finditer(text):
            mmsi = match.group(1)
            context = self._get_context(text, match.start(), match.end())

            entities.append(Entity(
                text=mmsi,
                normalized=mmsi,
                entity_type=EntityType.VESSEL,
                confidence=0.8,
                provenance=Provenance(
                    source_url=article.url,
                    source_name=article.source_name,
                    retrieved_at=article.retrieved_at,
                    original_text=context,
                    extraction_method="pattern_match",
                    reasoning="Extracted MMSI number (9-digit identifier)"
                ),
                metadata={"identifier_type": "mmsi"}
            ))

        # IMO numbers
        for match in self.imo_regex.finditer(text):
            imo = match.group(1)
            context = self._get_context(text, match.start(), match.end())

            entities.append(Entity(
                text=f"IMO{imo}",
                normalized=imo,
                entity_type=EntityType.VESSEL,
                confidence=0.85,
                provenance=Provenance(
                    source_url=article.url,
                    source_name=article.source_name,
                    retrieved_at=article.retrieved_at,
                    original_text=context,
                    extraction_method="pattern_match",
                    reasoning="Extracted IMO number (7-digit identifier)"
                ),
                metadata={"identifier_type": "imo"}
            ))

        return entities

    def _extract_activity_keywords(self, text: str, article: Article) -> List[Entity]:
        """Extract activity-related keywords for context."""
        entities = []
        seen = set()

        for activity_type, keywords in self.ACTIVITY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    if activity_type not in seen:
                        seen.add(activity_type)
                        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                        match = pattern.search(text)
                        if match:
                            context = self._get_context(text, match.start(), match.end())

                            entities.append(Entity(
                                text=match.group(0),
                                normalized=activity_type,
                                entity_type=EntityType.KEYWORD,
                                confidence=0.7,
                                provenance=Provenance(
                                    source_url=article.url,
                                    source_name=article.source_name,
                                    retrieved_at=article.retrieved_at,
                                    original_text=context,
                                    extraction_method="keyword_match",
                                    reasoning=f"Activity keyword '{keyword}' indicates {activity_type}"
                                ),
                                metadata={"activity_type": activity_type}
                            ))

        return entities

    def _normalize_vessel_name(self, name: str) -> str:
        """Normalize vessel name for matching."""
        # Remove common prefixes
        prefixes = ["MV", "M/V", "MT", "M/T", "SS", "HMS", "USNS"]
        normalized = name.upper().strip()
        for prefix in prefixes:
            if normalized.startswith(prefix + " "):
                normalized = normalized[len(prefix):].strip()
        # Remove extra spaces
        normalized = " ".join(normalized.split())
        return normalized

    def _calculate_vessel_confidence(self, name: str, context: str) -> float:
        """
        Calculate confidence score for extracted vessel name.

        Higher confidence if:
        - Name appears near maritime keywords
        - Name follows common vessel naming patterns
        - Context mentions ship/vessel/maritime terms
        """
        confidence = 0.5  # Base confidence

        # Boost if context contains maritime keywords
        maritime_keywords = ["ship", "vessel", "cargo", "tanker", "maritime",
                            "port", "sailed", "anchored", "moored"]
        context_lower = context.lower()
        for keyword in maritime_keywords:
            if keyword in context_lower:
                confidence += 0.1
                break

        # Boost if name matches common patterns
        if re.match(r'^[A-Z]+\s+\d+$', name):  # "ZHONG DA 79" pattern
            confidence += 0.15

        # Boost if name is all caps (formal vessel naming)
        if name.isupper():
            confidence += 0.1

        return min(confidence, 0.9)  # Cap at 0.9 for pattern-matched

    def _get_context(self, text: str, start: int, end: int, window: int = 100) -> str:
        """Extract surrounding context for provenance."""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        context = text[context_start:context_end]

        # Clean up
        context = " ".join(context.split())

        # Add ellipsis if truncated
        if context_start > 0:
            context = "..." + context
        if context_end < len(text):
            context = context + "..."

        return context

    def _common_words(self) -> Set[str]:
        """Words to exclude from vessel name extraction."""
        return {
            "the", "and", "for", "with", "from", "into", "that", "this",
            "china", "chinese", "russia", "russian", "united", "states",
            "navy", "military", "report", "news", "article", "source"
        }
