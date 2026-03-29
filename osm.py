"""
osm.py — Descarga la red de calles desde OpenStreetMap (gratis)
y genera puntos cada STEP_M metros solo sobre calles reales.

Usa la API Overpass con múltiples mirrors de respaldo.
"""

import math, time, json, requests
from pathlib import Path

# Mirrors en orden de prioridad — si uno falla pasa al siguiente
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

CACHE_FILE = "osm_points.json"


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = (math.sin((lat2-lat1)/2)**2
         + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2)
    return 2 * R * math.asin(math.sqrt(a))


def bearing(lat1, lon1, lat2, lon2) -> float:
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2)
    y = (math.cos(lat1)*math.sin(lat2)
         - math.sin(lat1)*math.cos(lat2)*math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def interpolate_segment(lat1, lon1, lat2, lon2, step_m: int) -> list:
    total_km = haversine_km(lat1, lon1, lat2, lon2)
    total_m  = total_km * 1000
    if total_m < step_m:
        return []

    brng   = bearing(lat1, lon1, lat2, lon2)
    steps  = int(total_m / step_m)
    points = []

    for i in range(steps):
        frac = (i * step_m) / total_m
        lat  = lat1 + frac * (lat2 - lat1)
        lon  = lon1 + frac * (lon2 - lon1)
        points.append((round(lat, 7), round(lon, 7), round(brng, 1)))

    return points


def fetch_roads(center_lat: float, center_lon: float, radius_km: float) -> list:
    r_deg = radius_km / 111.32
    bbox  = (
        center_lat - r_deg, center_lon - r_deg,
        center_lat + r_deg, center_lon + r_deg,
    )

    query = f"""
    [out:json][timeout:90];
    (
      way["highway"~"^(residential|primary|secondary|tertiary|unclassified|living_street|service|trunk|motorway_link|primary_link|secondary_link|tertiary_link)$"]
         ({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]});
    );
    out geom;
    """

    print("  📡 Descargando calles de OpenStreetMap...")

    # Intentar cada mirror hasta que uno responda
    last_error = None
    for mirror in OVERPASS_MIRRORS:
        for attempt in range(3):
            try:
                print(f"     → {mirror.split('/')[2]} (intento {attempt+1})")
                r = requests.post(
                    mirror,
                    data={"data": query},
                    timeout=120,
                    headers={"User-Agent": "CartelScanner/1.0"},
                )
                r.raise_for_status()
                data = r.json()

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

            except Exception as e:
                last_error = e
                print(f"  ⚠️  Error ({e}) — reintentando en 10s...")
                time.sleep(10)

    raise RuntimeError(f"Todos los mirrors de Overpass fallaron. Último error: {last_error}")


def get_road_points(center_lat: float, center_lon: float,
                    radius_km: float, step_m: int) -> list:
    cache_key = f"{center_lat}_{center_lon}_{radius_km}_{step_m}"

    if Path(CACHE_FILE).exists():
        try:
            cached = json.loads(Path(CACHE_FILE).read_text())
            if cached.get("key") == cache_key:
                pts = cached["points"]
                print(f"  📦 Usando caché OSM: {len(pts):,} puntos (sin descargar nada)")
                return pts
        except Exception:
            pass  # Caché corrupto, re-descargar

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
