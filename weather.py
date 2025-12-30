"""
Weather Enrichment Module

Fetches weather and marine data from Open-Meteo API (free, no API key required).
Used to enrich AIS position data with environmental context.

Use Cases:
- Detect vessels anchoring in unusual weather (suspicious)
- Correlate AIS dark periods with storm cover
- Monitor sea state for operations analysis
- Track visibility conditions

API: https://open-meteo.com/ (free, no registration)
"""

import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Optional, Any


class WeatherService:
    """
    Fetch weather data from Open-Meteo API.

    Free API with no key required. Rate limits are generous.

    Usage:
        weather = WeatherService()
        data = weather.get_weather(31.2456, 121.4890)
        print(data['temperature'], data['wind_speed'])
    """

    # Open-Meteo API endpoints
    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

    def __init__(self, cache_ttl: int = 600):
        """
        Initialize weather service.

        Args:
            cache_ttl: Cache time-to-live in seconds (default 10 minutes)
        """
        self._cache: Dict[str, Dict] = {}
        self._cache_times: Dict[str, float] = {}
        self._cache_ttl = cache_ttl

    def get_weather(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """
        Get current weather for a location.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Dict with weather data or None on error
        """
        cache_key = f"{lat:.2f},{lon:.2f}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # Build URL with parameters
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m,visibility",
                "wind_speed_unit": "kn",
                "timezone": "UTC"
            }

            url = f"{self.WEATHER_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

            data = self._fetch(url)
            if not data or "current" not in data:
                return None

            current = data["current"]

            result = {
                "timestamp": datetime.utcnow().isoformat(),
                "location": {"lat": lat, "lon": lon},
                "temperature_c": current.get("temperature_2m"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "precipitation_mm": current.get("precipitation"),
                "weather_code": current.get("weather_code"),
                "weather_description": self._weather_code_to_text(current.get("weather_code")),
                "cloud_cover_pct": current.get("cloud_cover"),
                "wind_speed_kn": current.get("wind_speed_10m"),
                "wind_direction_deg": current.get("wind_direction_10m"),
                "wind_gusts_kn": current.get("wind_gusts_10m"),
                "visibility_m": current.get("visibility"),
                "source": "open-meteo"
            }

            # Cache result
            self._cache[cache_key] = result
            self._cache_times[cache_key] = datetime.utcnow().timestamp()

            return result

        except Exception as e:
            print(f"[Weather] Error fetching weather: {e}")
            return None

    def get_marine(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """
        Get marine/ocean conditions for a location.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Dict with marine data or None on error
        """
        cache_key = f"marine_{lat:.2f},{lon:.2f}"

        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "wave_height,wave_direction,wave_period,swell_wave_height,swell_wave_direction,swell_wave_period",
                "timezone": "UTC"
            }

            url = f"{self.MARINE_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

            data = self._fetch(url)
            if not data or "current" not in data:
                return None

            current = data["current"]

            result = {
                "timestamp": datetime.utcnow().isoformat(),
                "location": {"lat": lat, "lon": lon},
                "wave_height_m": current.get("wave_height"),
                "wave_direction_deg": current.get("wave_direction"),
                "wave_period_s": current.get("wave_period"),
                "swell_height_m": current.get("swell_wave_height"),
                "swell_direction_deg": current.get("swell_wave_direction"),
                "swell_period_s": current.get("swell_wave_period"),
                "sea_state": self._wave_to_sea_state(current.get("wave_height")),
                "source": "open-meteo"
            }

            self._cache[cache_key] = result
            self._cache_times[cache_key] = datetime.utcnow().timestamp()

            return result

        except Exception as e:
            print(f"[Weather] Error fetching marine data: {e}")
            return None

    def get_full_conditions(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """
        Get combined weather and marine conditions.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Dict with combined weather and marine data
        """
        weather = self.get_weather(lat, lon)
        marine = self.get_marine(lat, lon)

        if not weather and not marine:
            return None

        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "location": {"lat": lat, "lon": lon},
            "weather": weather,
            "marine": marine,
            "summary": self._generate_summary(weather, marine)
        }

        return result

    def _fetch(self, url: str) -> Optional[Dict]:
        """Make HTTP request and parse JSON response."""
        try:
            request = urllib.request.Request(url)
            request.add_header("User-Agent", "ArsenalShipTracker/1.0")

            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as e:
            print(f"[Weather] HTTP error {e.code}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            print(f"[Weather] URL error: {e.reason}")
            return None
        except json.JSONDecodeError as e:
            print(f"[Weather] JSON decode error: {e}")
            return None

    def _get_cached(self, key: str) -> Optional[Dict]:
        """Get cached data if still valid."""
        if key not in self._cache:
            return None

        cache_time = self._cache_times.get(key, 0)
        if datetime.utcnow().timestamp() - cache_time > self._cache_ttl:
            del self._cache[key]
            del self._cache_times[key]
            return None

        return self._cache[key]

    def _weather_code_to_text(self, code: Optional[int]) -> str:
        """Convert WMO weather code to human-readable text."""
        if code is None:
            return "Unknown"

        codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail"
        }

        return codes.get(code, f"Code {code}")

    def _wave_to_sea_state(self, wave_height: Optional[float]) -> str:
        """Convert wave height to Douglas Sea State scale."""
        if wave_height is None:
            return "Unknown"

        if wave_height < 0.1:
            return "0 - Calm (glassy)"
        elif wave_height < 0.5:
            return "1 - Calm (rippled)"
        elif wave_height < 1.25:
            return "2 - Smooth"
        elif wave_height < 2.5:
            return "3 - Slight"
        elif wave_height < 4.0:
            return "4 - Moderate"
        elif wave_height < 6.0:
            return "5 - Rough"
        elif wave_height < 9.0:
            return "6 - Very rough"
        elif wave_height < 14.0:
            return "7 - High"
        else:
            return "8 - Very high"

    def _generate_summary(self, weather: Optional[Dict], marine: Optional[Dict]) -> str:
        """Generate human-readable conditions summary."""
        parts = []

        if weather:
            desc = weather.get("weather_description", "")
            temp = weather.get("temperature_c")
            wind = weather.get("wind_speed_kn")
            vis = weather.get("visibility_m")

            if desc:
                parts.append(desc)
            if temp is not None:
                parts.append(f"{temp}°C")
            if wind is not None:
                parts.append(f"Wind {wind}kn")
            if vis is not None:
                vis_km = vis / 1000
                parts.append(f"Vis {vis_km:.1f}km")

        if marine:
            wave = marine.get("wave_height_m")
            sea_state = marine.get("sea_state", "")

            if wave is not None:
                parts.append(f"Waves {wave}m")
            if sea_state and "Unknown" not in sea_state:
                parts.append(f"({sea_state.split(' - ')[1] if ' - ' in sea_state else sea_state})")

        return " | ".join(parts) if parts else "No data available"


# Singleton instance for easy import
_weather_service = None

def get_weather_service() -> WeatherService:
    """Get singleton weather service instance."""
    global _weather_service
    if _weather_service is None:
        _weather_service = WeatherService()
    return _weather_service


def enrich_position_with_weather(position: Dict) -> Dict:
    """
    Enrich a position dict with weather data.

    Args:
        position: Dict with 'lat'/'latitude' and 'lon'/'longitude' keys

    Returns:
        Position dict with added 'weather' key
    """
    lat = position.get("lat") or position.get("latitude")
    lon = position.get("lon") or position.get("longitude")

    if lat is None or lon is None:
        return position

    service = get_weather_service()
    weather = service.get_full_conditions(lat, lon)

    if weather:
        position["weather"] = weather

    return position


# CLI test
if __name__ == "__main__":
    print("Testing Weather Service...")

    service = WeatherService()

    # Test location: Shanghai
    lat, lon = 31.2456, 121.4890
    print(f"\nLocation: {lat}, {lon} (Shanghai)")

    print("\n--- Weather ---")
    weather = service.get_weather(lat, lon)
    if weather:
        print(json.dumps(weather, indent=2))

    print("\n--- Marine ---")
    marine = service.get_marine(lat, lon)
    if marine:
        print(json.dumps(marine, indent=2))

    print("\n--- Full Conditions ---")
    full = service.get_full_conditions(lat, lon)
    if full:
        print(f"Summary: {full['summary']}")
