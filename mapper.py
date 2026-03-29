"""
mapper.py — Genera un PNG del área escaneada para enviar por Telegram.

Usa la librería `staticmap` (fondo OpenStreetMap, sin costo).
Muestra:
  🔵 Puntos azules  = calles recorridas con Street View
  🔴 Puntos rojos   = carteles de alquiler directo encontrados
  🟠 Puntos naranja = carteles de inmobiliaria encontrados
  🟡 Punto amarillo = centro (Comagro S.A.)
"""

import io
import math

try:
    from staticmap import StaticMap, CircleMarker
    HAS_STATICMAP = True
except ImportError:
    HAS_STATICMAP = False

try:
    import matplotlib
    matplotlib.use("Agg")          # headless, sin display
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


# ── MAPA CON FONDO OSM (staticmap) ─────────────────────────────────────────────

def _map_staticmap(all_points, visited_points, cartel_results,
                   center_lat, center_lon) -> bytes:
    """
    Renderiza con staticmap (fondo de tiles OpenStreetMap).
    Necesita conexión a internet para bajar tiles.
    """
    m = StaticMap(
        1200, 1200,
        url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        headers={"User-Agent": "CartelScanner/1.0 (github.com/Ozz-V/Mapa-de-alquileres)"},
    )

    # ── Calles recorridas (muestrear si hay muchos puntos)
    step = max(1, len(visited_points) // 4000)
    for lat, lon, _ in visited_points[::step]:
        m.add_marker(CircleMarker((lon, lat), "#1E88E5", 4))  # azul

    # ── Puntos NO visitados (pendientes) — gris claro, más pequeños
    visited_set = {f"{lat},{lon}" for lat, lon, _ in visited_points}
    pending = [(lat, lon, hdg) for lat, lon, hdg in all_points
               if f"{lat},{lon}" not in visited_set]
    step_p = max(1, len(pending) // 2000)
    for lat, lon, _ in pending[::step_p]:
        m.add_marker(CircleMarker((lon, lat), "#BDBDBD", 2))  # gris

    # ── Carteles encontrados
    for r in cartel_results:
        color = "#F44336" if r.get("tipo") == "alquiler_directo" else "#FF9800"
        m.add_marker(CircleMarker((r["lon"], r["lat"]), color, 12))

    # ── Centro Comagro
    m.add_marker(CircleMarker((center_lon, center_lat), "#FFD600", 14))

    try:
        image = m.render(zoom=14)
    except Exception:
        image = m.render(zoom=13)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


# ── MAPA FALLBACK CON MATPLOTLIB ────────────────────────────────────────────────

def _map_matplotlib(all_points, visited_points, cartel_results,
                    center_lat, center_lon) -> bytes:
    """
    Fallback: scatter plot con matplotlib (sin internet, sin tiles).
    La distribución de puntos sobre calles dibuja naturalmente la red vial.
    """
    fig, ax = plt.subplots(figsize=(12, 12), facecolor="#0D1117")
    ax.set_facecolor("#0D1117")

    # Todos los puntos del área (fondo gris)
    if all_points:
        lons_all = [p[1] for p in all_points]
        lats_all = [p[0] for p in all_points]
        ax.scatter(lons_all, lats_all, c="#2D3748", s=1, linewidths=0, zorder=1)

    # Puntos visitados (azul)
    if visited_points:
        lons_v = [p[1] for p in visited_points]
        lats_v = [p[0] for p in visited_points]
        ax.scatter(lons_v, lats_v, c="#1E88E5", s=2, alpha=0.7, linewidths=0, zorder=2)

    # Carteles encontrados
    alq = [r for r in cartel_results if r.get("tipo") == "alquiler_directo"]
    inm = [r for r in cartel_results if r.get("tipo") != "alquiler_directo"]

    if alq:
        ax.scatter([r["lon"] for r in alq], [r["lat"] for r in alq],
                   c="#F44336", s=120, zorder=5, marker="*", label=f"Alquiler directo ({len(alq)})")
    if inm:
        ax.scatter([r["lon"] for r in inm], [r["lat"] for r in inm],
                   c="#FF9800", s=120, zorder=5, marker="*", label=f"Inmobiliaria ({len(inm)})")

    # Centro Comagro
    ax.scatter([center_lon], [center_lat], c="#FFD600", s=200, zorder=6,
               marker="D", label="Comagro S.A.")

    # Leyenda y estética
    legend = ax.legend(loc="lower right", facecolor="#1A202C",
                       edgecolor="#4A5568", labelcolor="white", fontsize=11)
    ax.set_title("Mapa de cobertura — Cartel Scanner", color="white",
                 fontsize=15, pad=14, fontweight="bold")
    ax.tick_params(colors="#718096")
    ax.spines["bottom"].set_color("#4A5568")
    ax.spines["left"].set_color("#4A5568")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Stats en el mapa
    total_c = len(cartel_results)
    total_v = len(visited_points)
    info = (f"Visitados: {total_v:,} pts  |  Carteles: {total_c}")
    ax.set_xlabel(info, color="#A0AEC0", fontsize=10)

    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format="PNG", dpi=150, bbox_inches="tight",
                facecolor="#0D1117")
    plt.close()
    buf.seek(0)
    return buf.getvalue()


# ── PUNTO DE ENTRADA PÚBLICO ────────────────────────────────────────────────────

def generate_coverage_map(
    all_points: list,
    visited_points: list,
    cartel_results: list,
    center_lat: float,
    center_lon: float,
) -> bytes:
    """
    Genera un PNG del mapa de cobertura.
    Intenta primero con staticmap (fondo OSM), cae a matplotlib si falla.

    Returns: bytes PNG
    """
    if HAS_STATICMAP:
        try:
            return _map_staticmap(all_points, visited_points, cartel_results,
                                  center_lat, center_lon)
        except Exception as e:
            print(f"  ⚠️  staticmap falló ({e}), usando matplotlib...")

    if HAS_MATPLOTLIB:
        return _map_matplotlib(all_points, visited_points, cartel_results,
                               center_lat, center_lon)

    raise RuntimeError("Ni staticmap ni matplotlib están disponibles.")
