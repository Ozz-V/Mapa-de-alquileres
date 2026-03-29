"""
osm.py — Descarga la red de calles desde OpenStreetMap (gratis)
y genera puntos cada STEP_M metros solo sobre calles reales.

Usa la API Overpass — no requiere key ni registro.
"""

import math, time, json, requests
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
CACHE_FILE   = "osm_points.json"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = (math.sin((lat2-lat1)/2)**2
         + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2) -> float:
    """Rumbo en grados de (lat1,lon1) a (lat2,lon2)."""
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2)
    y = (math.cos(lat1)*math.sin(lat2)
         - math.sin(lat1)*math.cos(lat2)*math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def interpolate_segment(lat1, lon1, lat2, lon2, step_m: int) -> list:
    """
    Devuelve puntos cada step_m metros entre dos coordenadas,
    junto con el rumbo de la calle (para orientar la cámara).
    """
    total_km = haversine_km(lat1, lon1, lat2, lon2)
    total_m  = total_km * 1000
    if total_m < step_m:
        return []

    brng   = bearing(lat1, lon1, lat2, lon2)
    steps  = int(total_m / step_m)
    points = []

    for i in range(steps):
        frac   = (i * step_m) / total_m
        lat    = lat1 + frac * (lat2 - lat1)
        lon    = lon1 + frac * (lon2 - lon1)
        points.append((round(lat, 7), round(lon, 7), round(brng, 1)))

    return points


def fetch_roads(center_lat: float, center_lon: float, radius_km: float) -> list:
    """
    Descarga calles de OSM dentro del radio.
    Retorna lista de segmentos: [(lat1,lon1,lat2,lon2), ...]
    """
    r_deg = radius_km / 111.32  # grados aproximados
    bbox  = (
        center_lat - r_deg, center_lon - r_deg,
        center_lat + r_deg, center_lon + r_deg,
    )

    query = f"""
    [out:json][timeout:60];
    (
      way["highway"~"^(residential|primary|secondary|tertiary|unclassified|living_street|service|trunk|motorway_link|primary_link|secondary_link|tertiary_link)$"]
         ({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out geom;
    """

    print("  📡 Descargando calles de OpenStreetMap...")
    for attempt in range(3):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, timeout=90)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f"  ⚠️  Reintentando OSM ({e})")
            time.sleep(5)

    segments = []
    for element in data.get("elements", []):
        if element.get("type") != "way":
            continue
        geom = element.get("geometry", [])
        for i in range(len(geom) - 1):
            a, b = geom[i], geom[i+1]
            segments.append((a["lat"], a["lon"], b["lat"], b["lon"]))

    print(f"  ✅ {len(segments)} segmentos de calle descargados")
    return segments


def get_road_points(center_lat: float, center_lon: float,
                    radius_km: float, step_m: int) -> list:
    """
    Devuelve lista de (lat, lon, heading) sobre calles reales,
    filtrando los que caen fuera del radio.
    Cachea en osm_points.json para no repetir la descarga.
    """
    cache_key = f"{center_lat}_{center_lon}_{radius_km}_{step_m}"

    if Path(CACHE_FILE).exists():
        cached = json.loads(Path(CACHE_FILE).read_text())
        if cached.get("key") == cache_key:
            pts = cached["points"]
            print(f"  📦 Usando caché OSM: {len(pts):,} puntos")
            return pts

    segments = fetch_roads(center_lat, center_lon, radius_km)

    all_points = []
    seen       = set()

    for lat1, lon1, lat2, lon2 in segments:
        for lat, lon, hdg in interpolate_segment(lat1, lon1, lat2, lon2, step_m):
            dist = haversine_km(center_lat, center_lon, lat, lon)
            if dist > radius_km:
                continue
            key = f"{lat},{lon}"
            if key in seen:
                continue
            seen.add(key)
            all_points.append((lat, lon, hdg))

    all_points.sort(key=lambda p: haversine_km(center_lat, center_lon, p[0], p[1]))

    Path(CACHE_FILE).write_text(
        json.dumps({"key": cache_key, "points": all_points})
    )
    print(f"  ✅ {len(all_points):,} puntos únicos sobre calles")
    return all_points
