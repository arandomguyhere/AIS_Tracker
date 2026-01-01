"""
Built-in Port Database

Fallback port data when external APIs are unavailable.
Includes major world ports with focus on:
- Dark fleet monitoring regions (Baltic, Venezuela, Iran routes)
- Major shipping hubs
- STS transfer zones

Data sources: World Port Index (US NGA), UN/LOCODE
"""

from typing import List, Dict, Optional
from math import radians, sin, cos, sqrt, atan2


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers."""
    R = 6371  # Earth's radius in km

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


# Major world ports database
# Format: name, country, lat, lon, type, unlocode
PORTS_DATABASE = [
    # ============= BALTIC SEA (Cable incident monitoring) =============
    ("Helsinki", "Finland", 60.1699, 24.9384, "major", "FIHEL"),
    ("Tallinn", "Estonia", 59.4370, 24.7536, "major", "EETLL"),
    ("Riga", "Latvia", 56.9496, 24.1052, "major", "LVRIX"),
    ("Klaipeda", "Lithuania", 55.7033, 21.1443, "major", "LTKLJ"),
    ("Gdansk", "Poland", 54.3520, 18.6466, "major", "PLGDN"),
    ("Gdynia", "Poland", 54.5189, 18.5305, "major", "PLGDY"),
    ("Rostock", "Germany", 54.0887, 12.1407, "major", "DERSK"),
    ("Lubeck", "Germany", 53.8655, 10.6866, "major", "DELBC"),
    ("Kiel", "Germany", 54.3233, 10.1228, "major", "DEKEL"),
    ("Copenhagen", "Denmark", 55.6761, 12.5683, "major", "DKCPH"),
    ("Malmo", "Sweden", 55.6050, 13.0038, "major", "SEMMA"),
    ("Gothenburg", "Sweden", 57.7089, 11.9746, "major", "SEGOT"),
    ("Stockholm", "Sweden", 59.3293, 18.0686, "major", "SESTO"),
    ("St. Petersburg", "Russia", 59.9343, 30.3351, "major", "RULED"),
    ("Kaliningrad", "Russia", 54.7104, 20.4522, "major", "RUKGD"),
    ("Primorsk", "Russia", 60.3531, 28.6256, "oil_terminal", "RUPRI"),
    ("Ust-Luga", "Russia", 59.6803, 28.4006, "oil_terminal", "RUULU"),
    ("Vysotsk", "Russia", 60.6272, 28.5706, "oil_terminal", "RUVYS"),
    ("Ventspils", "Latvia", 57.3942, 21.5606, "oil_terminal", "LVVNT"),
    ("Butinge", "Lithuania", 56.0667, 21.0500, "oil_terminal", "LTBUT"),
    ("Swinoujscie", "Poland", 53.9100, 14.2472, "lng_terminal", "PLSWI"),
    ("Hanko", "Finland", 59.8236, 22.9508, "port", "FIHKO"),
    ("Turku", "Finland", 60.4518, 22.2666, "major", "FITKU"),
    ("Kotka", "Finland", 60.4667, 26.9458, "major", "FIKTK"),

    # ============= VENEZUELA / CARIBBEAN (Dark fleet ops) =============
    ("Jose Terminal", "Venezuela", 10.1500, -64.6833, "oil_terminal", "VEJOS"),
    ("Puerto La Cruz", "Venezuela", 10.2167, -64.6333, "oil_terminal", "VEPLC"),
    ("Amuay", "Venezuela", 11.7500, -70.2167, "refinery", "VEAMY"),
    ("Cardon", "Venezuela", 11.6333, -70.2500, "refinery", "VECAR"),
    ("Maracaibo", "Venezuela", 10.6500, -71.6167, "major", "VEMAR"),
    ("Puerto Cabello", "Venezuela", 10.4667, -68.0167, "major", "VEPCB"),
    ("La Guaira", "Venezuela", 10.6000, -66.9333, "major", "VELGU"),
    ("Curacao", "Curacao", 12.1696, -68.9900, "oil_terminal", "CWWIL"),
    ("Aruba", "Aruba", 12.5186, -70.0358, "oil_terminal", "AWORA"),
    ("Trinidad PPGPL", "Trinidad", 10.3833, -61.0333, "lng_terminal", "TTPTS"),
    ("Point Lisas", "Trinidad", 10.4167, -61.4833, "major", "TTPTL"),
    ("Freeport", "Bahamas", 26.5333, -78.7000, "oil_terminal", "BSFPO"),
    ("Havana", "Cuba", 23.1136, -82.3666, "major", "CUHAV"),
    ("Kingston", "Jamaica", 17.9714, -76.7931, "major", "JMKIN"),
    ("Cartagena", "Colombia", 10.3997, -75.5144, "major", "COCTG"),

    # ============= IRAN / MIDDLE EAST (Sanctions evasion) =============
    ("Bandar Abbas", "Iran", 27.1865, 56.2808, "major", "IRBND"),
    ("Kharg Island", "Iran", 29.2333, 50.3167, "oil_terminal", "IRKHI"),
    ("Kish Island", "Iran", 26.5333, 53.9833, "port", "IRKIS"),
    ("Bushehr", "Iran", 28.9833, 50.8333, "port", "IRBUZ"),
    ("Bandar Imam Khomeini", "Iran", 30.4333, 49.0667, "oil_terminal", "IRBIK"),
    ("Assaluyeh", "Iran", 27.4833, 52.6167, "lng_terminal", "IRASL"),
    ("Fujairah", "UAE", 25.1164, 56.3414, "major", "AEFJR"),
    ("Jebel Ali", "UAE", 24.9857, 55.0272, "major", "AEJEA"),
    ("Dubai", "UAE", 25.2697, 55.3094, "major", "AEDXB"),
    ("Khor Fakkan", "UAE", 25.3333, 56.3500, "port", "AEKLF"),
    ("Muscat", "Oman", 23.6100, 58.5400, "major", "OMMCT"),
    ("Sohar", "Oman", 24.3667, 56.7333, "oil_terminal", "OMSOH"),
    ("Salalah", "Oman", 16.9500, 54.0000, "major", "OMSLL"),
    ("Jeddah", "Saudi Arabia", 21.4858, 39.1925, "major", "SAJED"),
    ("Ras Tanura", "Saudi Arabia", 26.6333, 50.0333, "oil_terminal", "SARTA"),
    ("Yanbu", "Saudi Arabia", 24.0833, 38.0500, "oil_terminal", "SAYNB"),
    ("Kuwait", "Kuwait", 29.3375, 47.9144, "major", "KWKWI"),
    ("Basra", "Iraq", 30.5000, 47.8333, "oil_terminal", "IQBSR"),

    # ============= MALAYSIA / SE ASIA (STS hubs) =============
    ("Tanjung Pelepas", "Malaysia", 1.3667, 103.5500, "sts_zone", "MYTPP"),
    ("Port Klang", "Malaysia", 3.0000, 101.4000, "major", "MYPKG"),
    ("Singapore", "Singapore", 1.2644, 103.8200, "major", "SGSIN"),
    ("Jurong", "Singapore", 1.3000, 103.7167, "oil_terminal", "SGJUR"),
    ("Batam", "Indonesia", 1.0456, 104.0305, "sts_zone", "IDBTH"),
    ("Dumai", "Indonesia", 1.6833, 101.4500, "oil_terminal", "IDDUM"),
    ("Belawan", "Indonesia", 3.7833, 98.6833, "major", "IDBLW"),
    ("Palembang", "Indonesia", -2.9167, 104.7500, "oil_terminal", "IDPLM"),
    ("Tanjung Priok", "Indonesia", -6.1000, 106.8833, "major", "IDJKT"),
    ("Surabaya", "Indonesia", -7.2500, 112.7500, "major", "IDSUB"),
    ("Laem Chabang", "Thailand", 13.0833, 100.8833, "major", "THLCH"),
    ("Map Ta Phut", "Thailand", 12.7167, 101.1500, "oil_terminal", "THMTP"),
    ("Ho Chi Minh", "Vietnam", 10.7500, 106.7500, "major", "VNSGN"),
    ("Hai Phong", "Vietnam", 20.8500, 106.6833, "major", "VNHPH"),

    # ============= CHINA (Destination ports) =============
    ("Shanghai", "China", 31.2304, 121.4737, "major", "CNSHA"),
    ("Ningbo-Zhoushan", "China", 29.8683, 121.5440, "major", "CNNGB"),
    ("Qingdao", "China", 36.0671, 120.3826, "major", "CNTAO"),
    ("Tianjin", "China", 39.0842, 117.2009, "major", "CNTSN"),
    ("Dalian", "China", 38.9140, 121.6147, "major", "CNDLC"),
    ("Guangzhou", "China", 23.1291, 113.2644, "major", "CNCAN"),
    ("Shenzhen", "China", 22.5431, 114.0579, "major", "CNSZX"),
    ("Xiamen", "China", 24.4798, 118.0894, "major", "CNXMN"),
    ("Rizhao", "China", 35.4167, 119.5167, "oil_terminal", "CNRZH"),
    ("Yantai", "China", 37.4500, 121.4500, "major", "CNYNT"),
    ("Tangshan", "China", 39.0000, 118.1833, "oil_terminal", "CNTGS"),
    ("Zhanjiang", "China", 21.2000, 110.4000, "oil_terminal", "CNZHA"),

    # ============= RUSSIA (Shadow fleet origins) =============
    ("Novorossiysk", "Russia", 44.7167, 37.7833, "oil_terminal", "RUNVS"),
    ("Tuapse", "Russia", 44.1000, 39.0667, "oil_terminal", "RUTUA"),
    ("Taman", "Russia", 45.2167, 36.7167, "oil_terminal", "RUTAM"),
    ("Kavkaz", "Russia", 45.3667, 36.6500, "port", "RUKAZ"),
    ("Murmansk", "Russia", 68.9585, 33.0827, "major", "RUMMK"),
    ("Arkhangelsk", "Russia", 64.5401, 40.5433, "major", "RUARH"),
    ("Vladivostok", "Russia", 43.1056, 131.8735, "major", "RUVVO"),
    ("Nakhodka", "Russia", 42.8167, 132.8833, "oil_terminal", "RUNAH"),
    ("De-Kastri", "Russia", 51.4667, 140.7833, "oil_terminal", "RUDKS"),
    ("Kozmino", "Russia", 42.7333, 133.0167, "oil_terminal", "RUKOZ"),

    # ============= EUROPE (Transit/destination) =============
    ("Rotterdam", "Netherlands", 51.9244, 4.4777, "major", "NLRTM"),
    ("Antwerp", "Belgium", 51.2194, 4.4025, "major", "BEANR"),
    ("Hamburg", "Germany", 53.5511, 9.9937, "major", "DEHAM"),
    ("Bremerhaven", "Germany", 53.5396, 8.5809, "major", "DEBRV"),
    ("Wilhelmshaven", "Germany", 53.5200, 8.1300, "oil_terminal", "DEWVN"),
    ("Amsterdam", "Netherlands", 52.3702, 4.8952, "major", "NLAMS"),
    ("Le Havre", "France", 49.4944, 0.1079, "major", "FRLEH"),
    ("Marseille", "France", 43.2965, 5.3698, "major", "FRMRS"),
    ("Barcelona", "Spain", 41.3851, 2.1734, "major", "ESBCN"),
    ("Valencia", "Spain", 39.4699, -0.3763, "major", "ESVLC"),
    ("Algeciras", "Spain", 36.1408, -5.4536, "major", "ESALG"),
    ("Piraeus", "Greece", 37.9475, 23.6372, "major", "GRPIR"),
    ("Kalamata", "Greece", 37.0389, 22.1128, "sts_zone", "GRKLM"),
    ("Augusta", "Italy", 37.2333, 15.2167, "oil_terminal", "ITAUG"),
    ("Trieste", "Italy", 45.6495, 13.7768, "oil_terminal", "ITTRS"),
    ("Genoa", "Italy", 44.4056, 8.9463, "major", "ITGOA"),
    ("Constanta", "Romania", 44.1598, 28.6348, "major", "ROCND"),
    ("Odesa", "Ukraine", 46.4825, 30.7233, "major", "UAODS"),
    ("Istanbul", "Turkey", 41.0082, 28.9784, "major", "TRIST"),
    ("Izmir", "Turkey", 38.4192, 27.1287, "major", "TRIZM"),
    ("Ceyhan", "Turkey", 36.8833, 35.9167, "oil_terminal", "TRCEY"),

    # ============= INDIA (Growing destination) =============
    ("Mumbai (JNPT)", "India", 18.9500, 72.9500, "major", "INNSA"),
    ("Mundra", "India", 22.8333, 69.7167, "major", "INMUN"),
    ("Sikka", "India", 22.4333, 69.8333, "oil_terminal", "INSIK"),
    ("Vadinar", "India", 22.3833, 69.7000, "oil_terminal", "INVAD"),
    ("Paradip", "India", 20.2667, 86.6167, "oil_terminal", "INPRT"),
    ("Visakhapatnam", "India", 17.6868, 83.2185, "major", "INVTZ"),
    ("Chennai", "India", 13.0827, 80.2707, "major", "INMAA"),
    ("Kochi", "India", 9.9312, 76.2673, "major", "INCOK"),
    ("Kandla", "India", 23.0333, 70.2167, "major", "INKAN"),

    # ============= AFRICA (Transit points) =============
    ("Ceuta", "Spain", 35.8894, -5.3198, "sts_zone", "EACEU"),
    ("Tangier Med", "Morocco", 35.8833, -5.5000, "major", "MAPTM"),
    ("Durban", "South Africa", -29.8587, 31.0218, "major", "ZADUR"),
    ("Cape Town", "South Africa", -33.9249, 18.4241, "major", "ZACPT"),
    ("Lagos", "Nigeria", 6.4541, 3.3947, "major", "NGLOS"),
    ("Bonny", "Nigeria", 4.4333, 7.1667, "oil_terminal", "NGBON"),
    ("Luanda", "Angola", -8.8383, 13.2344, "oil_terminal", "AOLUA"),
    ("Lome", "Togo", 6.1375, 1.2125, "sts_zone", "TGLFW"),
    ("Dakar", "Senegal", 14.6928, -17.4467, "major", "SNDKR"),
    ("Suez", "Egypt", 29.9668, 32.5498, "major", "EGSUZ"),
    ("Port Said", "Egypt", 31.2653, 32.3019, "major", "EGPSD"),
]


def get_ports_nearby(lat: float, lon: float, radius_nm: float = 100) -> List[Dict]:
    """
    Get ports within radius of a point.

    Args:
        lat: Center latitude
        lon: Center longitude
        radius_nm: Search radius in nautical miles

    Returns:
        List of port dictionaries sorted by distance
    """
    radius_km = radius_nm * 1.852
    results = []

    for name, country, port_lat, port_lon, port_type, unlocode in PORTS_DATABASE:
        distance_km = haversine_distance(lat, lon, port_lat, port_lon)

        if distance_km <= radius_km:
            results.append({
                'name': name,
                'country': country,
                'lat': port_lat,
                'lon': port_lon,
                'type': port_type,
                'unlocode': unlocode,
                'distance_km': round(distance_km, 1),
                'distance_nm': round(distance_km / 1.852, 1),
                'source': 'built-in'
            })

    # Sort by distance
    results.sort(key=lambda p: p['distance_km'])

    return results


def get_port_by_unlocode(code: str) -> Optional[Dict]:
    """Get port by UN/LOCODE."""
    for name, country, lat, lon, port_type, unlocode in PORTS_DATABASE:
        if unlocode == code.upper():
            return {
                'name': name,
                'country': country,
                'lat': lat,
                'lon': lon,
                'type': port_type,
                'unlocode': unlocode
            }
    return None


def get_ports_by_country(country: str) -> List[Dict]:
    """Get all ports in a country."""
    results = []
    for name, cntry, lat, lon, port_type, unlocode in PORTS_DATABASE:
        if cntry.lower() == country.lower():
            results.append({
                'name': name,
                'country': cntry,
                'lat': lat,
                'lon': lon,
                'type': port_type,
                'unlocode': unlocode
            })
    return results


def get_ports_by_type(port_type: str) -> List[Dict]:
    """Get ports by type (oil_terminal, sts_zone, major, etc.)."""
    results = []
    for name, country, lat, lon, ptype, unlocode in PORTS_DATABASE:
        if ptype == port_type:
            results.append({
                'name': name,
                'country': country,
                'lat': lat,
                'lon': lon,
                'type': ptype,
                'unlocode': unlocode
            })
    return results


def get_sts_zones() -> List[Dict]:
    """Get known STS transfer zones."""
    return get_ports_by_type('sts_zone')


def get_oil_terminals() -> List[Dict]:
    """Get oil terminals."""
    return get_ports_by_type('oil_terminal')


# Statistics
def get_database_stats() -> Dict:
    """Get database statistics."""
    types = {}
    countries = set()

    for _, country, _, _, port_type, _ in PORTS_DATABASE:
        countries.add(country)
        types[port_type] = types.get(port_type, 0) + 1

    return {
        'total_ports': len(PORTS_DATABASE),
        'countries': len(countries),
        'by_type': types,
        'source': 'Built-in (World Port Index / UN-LOCODE)'
    }


if __name__ == '__main__':
    # Test
    print("Port Database Stats:")
    print(get_database_stats())

    print("\nPorts near Helsinki (100nm):")
    for p in get_ports_nearby(60.17, 24.94, 100)[:5]:
        print(f"  {p['name']}, {p['country']} - {p['distance_nm']}nm")

    print("\nSTS Zones:")
    for p in get_sts_zones():
        print(f"  {p['name']}, {p['country']}")
