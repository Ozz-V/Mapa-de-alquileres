"""
main.py — Orquestador del Street View Cartel Scanner
=====================================================
Recorre calles alrededor de Comagro S.A. usando OpenStreetMap + Google Street View,
detecta carteles de alquiler/venta con Claude Vision, y notifica por Telegram.

Variables de entorno requeridas:
  GOOGLE_MAPS_API_KEY
  ANTHROPIC_API_KEY
  TELEGRAM_TOKEN
  TELEGRAM_CHAT_ID
"""

import os, json, time
from pathlib import Path
from datetime import datetime

from osm        import get_road_points, haversine_km
from streetview import check_available, fetch_image
from vision     import analyze
from notifier   import send_cartel, send_summary, send_text, send_map
from mapper     import generate_coverage_map

# ── CONFIG ─────────────────────────────────────────────────────────────────────
COMAGRO_LAT  = -25.3117193
COMAGRO_LON  = -57.5880857
RADIUS_KM    = 4.0    # Radio de búsqueda
STEP_M       = 40     # Metros entre puntos sobre la calle
MAX_COST_USD = 100.0  # Techo de gasto en Street View (nunca superar)

MIN_CONFIDENCE = {"alta", "media"}   # Ignorar detecciones "baja"

RESULTS_FILE = "resultados.json"
SEEN_FILE    = "seen.json"

GOOGLE_KEY       = os.environ["GOOGLE_MAPS_API_KEY"]
ANTHROPIC_KEY    = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── ESTADO ─────────────────────────────────────────────────────────────────────

def load_seen() -> set:
    if Path(SEEN_FILE).exists():
        return set(json.loads(Path(SEEN_FILE).read_text()))
    return set()

def save_seen(seen: set):
    Path(SEEN_FILE).write_text(json.dumps(list(seen)))

def load_results() -> list:
    if Path(RESULTS_FILE).exists():
        return json.loads(Path(RESULTS_FILE).read_text(encoding="utf-8"))
    return []

def save_results(results: list):
    Path(RESULTS_FILE).write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# ── MAIN ───────────────────────────────────────────────────────────────────────

def run():
    print(f"\n🗺️  Cartel Scanner — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   Centro: Comagro S.A. ({COMAGRO_LAT}, {COMAGRO_LON})")
    print(f"   Radio:  {RADIUS_KM}km  |  Paso: {STEP_M}m")
    print(f"   Techo de costo: USD ${MAX_COST_USD:.0f}\n")

    # 1. Obtener puntos sobre calles reales (OSM)
    all_points = get_road_points(COMAGRO_LAT, COMAGRO_LON, RADIUS_KM, STEP_M)
    print(f"\n  Total puntos: {len(all_points):,}")

    # Estimación de costo (worst-case: todos tienen Street View)
    est_cost = len(all_points) * 0.007
    print(f"  Costo máximo estimado: USD ${est_cost:.1f}")
    if est_cost > MAX_COST_USD:
        accessible = int(MAX_COST_USD / 0.007)
        print(f"  ⚠️  Supera el techo — se procesarán hasta {accessible:,} fotos y luego se omite la descarga.")
    else:
        print(f"  ✅ Dentro del techo de USD ${MAX_COST_USD:.0f}")
    print()

    seen    = load_seen()
    results = load_results()

    stats = {
        "procesados": 0,
        "fotos": 0,
        "alquiler_directo": 0,
        "inmobiliaria": 0,
        "costo_usd": 0.0,
        "cap_alcanzado": False,
    }
    pending = [p for p in all_points if f"{p[0]},{p[1]}" not in seen]
    print(f"  Puntos pendientes: {len(pending):,}  (ya vistos: {len(seen):,})\n")

    if not pending:
        print("  ✅ Todo el área ya fue escaneada.")
        _send_final_map(all_points, seen, results, stats)
        return

    visited_this_run = []  # Para incluir en el mapa

    for i, (lat, lon, heading) in enumerate(pending):
        point_key = f"{lat},{lon}"

        # ── TECHO DE COSTO ──────────────────────────────────────────────────
        # Si ya se alcanzó el cap, marcar como visto sin descargar imagen
        if stats["costo_usd"] >= MAX_COST_USD:
            if not stats["cap_alcanzado"]:
                stats["cap_alcanzado"] = True
                print(f"\n  🛑 Techo USD ${MAX_COST_USD:.0f} alcanzado — "
                      f"completando área sin descargar más fotos.\n")
            seen.add(point_key)
            visited_this_run.append((lat, lon, heading))
            stats["procesados"] += 1
            if stats["procesados"] % 500 == 0:
                save_seen(seen)
            continue

        # Verificar disponibilidad (gratis)
        if not check_available(lat, lon, GOOGLE_KEY):
            seen.add(point_key)
            visited_this_run.append((lat, lon, heading))
            stats["procesados"] += 1
            continue

        # Descargar imagen (tiene costo ~$0.007)
        img = fetch_image(lat, lon, heading, GOOGLE_KEY)
        stats["costo_usd"] += 0.007

        if not img:
            seen.add(point_key)
            visited_this_run.append((lat, lon, heading))
            stats["procesados"] += 1
            continue

        stats["fotos"] += 1

        # Analizar con Claude Vision
        analysis = analyze(img, ANTHROPIC_KEY)

        if (analysis
                and analysis.get("tiene_cartel")
                and analysis.get("confianza") in MIN_CONFIDENCE):

            tipo  = analysis.get("tipo") or "inmobiliaria"
            tel   = analysis.get("telefono") or "no legible"
            txt   = analysis.get("texto_cartel") or analysis.get("descripcion") or ""
            emoji = "🏠" if tipo == "alquiler_directo" else "🏢"
            tipo_label = "ALQUILER" if tipo == "alquiler_directo" else "INMOBILIARIA"
            dist_km = round(haversine_km(COMAGRO_LAT, COMAGRO_LON, lat, lon), 2)

            print(f"  {emoji} [{i+1}/{len(pending)}] {tipo_label} — {analysis['confianza']}")
            print(f"     {txt}")
            if analysis.get("inmobiliaria"):
                print(f"     🏢 {analysis['inmobiliaria']}")
            print(f"     📞 {tel}")
            print(f"     📍 {dist_km} km de Comagro")

            result = {
                "lat":          lat,
                "lon":          lon,
                "heading":      heading,
                "tipo":         tipo,
                "texto_cartel": txt,           # ← clave consistente con notifier.py
                "telefono":     tel,
                "inmobiliaria": analysis.get("inmobiliaria"),
                "confianza":    analysis.get("confianza"),
                "dist_km":      dist_km,       # ← requerido por notifier.py
                "maps_url":     f"https://maps.google.com/?q={lat},{lon}",
                "sv_url":       (f"https://www.google.com/maps/@?api=1"
                                 f"&map_action=pano&viewpoint={lat},{lon}"
                                 f"&heading={round(heading)}"),
                "fecha":        datetime.now().strftime("%Y-%m-%d"),
            }
            results.append(result)

            if tipo == "alquiler_directo":
                stats["alquiler_directo"] += 1
            else:
                stats["inmobiliaria"] += 1

            send_cartel(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, img, result)
            time.sleep(0.5)

        else:
            total_carteles = stats["alquiler_directo"] + stats["inmobiliaria"]
            if i % 200 == 0:
                print(f"  ... [{i+1}/{len(pending)}] procesados, "
                      f"{stats['fotos']} fotos, "
                      f"{total_carteles} carteles, "
                      f"USD ${stats['costo_usd']:.2f}")

        seen.add(point_key)
        visited_this_run.append((lat, lon, heading))
        stats["procesados"] += 1

        # Guardar progreso cada 100 puntos
        if stats["procesados"] % 100 == 0:
            save_seen(seen)
            save_results(results)

        time.sleep(0.05)

    save_seen(seen)
    save_results(results)

    total_carteles = stats["alquiler_directo"] + stats["inmobiliaria"]
    print(f"\n{'='*50}")
    print(f"✅ Escaneo completo")
    print(f"   Procesados:    {stats['procesados']:,}")
    print(f"   Fotos:         {stats['fotos']:,}")
    print(f"   Alquiler dir.: {stats['alquiler_directo']}")
    print(f"   Inmobiliaria:  {stats['inmobiliaria']}")
    print(f"   Total:         {total_carteles}")
    print(f"   Costo real:    USD ${stats['costo_usd']:.2f}")
    if stats["cap_alcanzado"]:
        print(f"   ⚠️  Techo USD ${MAX_COST_USD:.0f} alcanzado — resto del área completado sin fotos")

    send_summary(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, stats)

    # Resumen de todos los carteles
    if results:
        resumen = "📋 <b>Todos los carteles encontrados:</b>\n\n"
        for r in results:
            resumen += (
                f"• <b>{(r['tipo'] or '?').upper()}</b> ({r['confianza']})"
                f" — {r.get('dist_km', '?')} km\n"
                f"  {r.get('texto_cartel') or ''}\n"
                f"  📞 {r['telefono'] or 'no legible'}\n"
                f"  <a href='{r['maps_url']}'>Maps</a> | "
                f"<a href='{r['sv_url']}'>Street View</a>\n\n"
            )
        send_text(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, resumen)

    # Enviar mapa de cobertura
    _send_final_map(all_points, seen, results, stats)


def _send_final_map(all_points, seen, results, stats):
    """Genera y envía el mapa de cobertura por Telegram."""
    print("\n  🗺️  Generando mapa de cobertura...")
    try:
        # Puntos visitados = todos los que están en el set seen
        visited_pts = [
            (lat, lon, hdg)
            for lat, lon, hdg in all_points
            if f"{lat},{lon}" in seen
        ]
        map_bytes = generate_coverage_map(
            all_points    = all_points,
            visited_points = visited_pts,
            cartel_results = results,
            center_lat    = COMAGRO_LAT,
            center_lon    = COMAGRO_LON,
        )
        total_carteles = stats["alquiler_directo"] + stats["inmobiliaria"]
        caption = (
            f"🗺️ <b>Mapa de cobertura</b>\n"
            f"📍 Radio: {RADIUS_KM} km | Paso: {STEP_M} m\n"
            f"🔵 Calles recorridas: {len(visited_pts):,} puntos\n"
            f"🔴 Carteles encontrados: {total_carteles}\n"
            f"💰 Costo: USD ${stats['costo_usd']:.2f}"
        )
        send_map(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, map_bytes, caption)
        print("  ✅ Mapa enviado por Telegram")
    except Exception as e:
        print(f"  ⚠️  No se pudo generar el mapa: {e}")


if __name__ == "__main__":
    run()
