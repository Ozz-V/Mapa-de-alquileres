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

from osm        import get_road_points
from streetview import check_available, fetch_image
from vision     import analyze
from notifier   import send_cartel, send_summary, send_text

# ── CONFIG ─────────────────────────────────────────────────────────────────────
COMAGRO_LAT  = -25.3117193
COMAGRO_LON  = -57.5880857
RADIUS_KM    = 4.0    # Radio de búsqueda
STEP_M       = 40     # Metros entre puntos sobre la calle
MIN_CONFIDENCE = {"alta", "media"}   # Ignorar detecciones "baja"

RESULTS_FILE = "resultados.json"
SEEN_FILE    = "seen.json"

GOOGLE_KEY    = os.environ["GOOGLE_MAPS_API_KEY"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
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
    print(f"   Radio:  {RADIUS_KM}km  |  Paso: {STEP_M}m\n")

    # 1. Obtener puntos sobre calles reales (OSM)
    points = get_road_points(COMAGRO_LAT, COMAGRO_LON, RADIUS_KM, STEP_M)
    print(f"\n  Total puntos: {len(points):,}")

    # Estimación de costo
    est_cost = len(points) * 0.007
    print(f"  Costo máximo estimado: USD ${est_cost:.1f} (cubierto por crédito Google)\n")

    seen    = load_seen()
    results = load_results()

    stats = {"procesados": 0, "fotos": 0, "alquiler_directo": 0, "inmobiliaria": 0, "costo_usd": 0.0}
    pending = [p for p in points if f"{p[0]},{p[1]}" not in seen]
    print(f"  Puntos pendientes: {len(pending):,}  (ya vistos: {len(seen):,})\n")

    if not pending:
        print("  ✅ Todo el área ya fue escaneada.")
        return

    for i, (lat, lon, heading) in enumerate(pending):
        point_key = f"{lat},{lon}"

        # Verificar disponibilidad (gratis)
        if not check_available(lat, lon, GOOGLE_KEY):
            seen.add(point_key)
            stats["procesados"] += 1
            continue

        # Descargar imagen (tiene costo)
        img = fetch_image(lat, lon, heading, GOOGLE_KEY)
        stats["costo_usd"] += 0.007

        if not img:
            seen.add(point_key)
            stats["procesados"] += 1
            continue

        stats["fotos"] += 1

        # Analizar con Claude Vision
        analysis = analyze(img, ANTHROPIC_KEY)

        if (analysis
                and analysis.get("tiene_cartel")
                and analysis.get("confianza") in MIN_CONFIDENCE):

            tipo = analysis.get("tipo") or "?"
            tel  = analysis.get("telefono") or "no legible"
            txt  = analysis.get("texto_cartel") or analysis.get("descripcion") or ""
            emoji = "🏠" if tipo == "alquiler_directo" else "🏢"
            tipo_label = "ALQUILER" if tipo == "alquiler_directo" else "INMOBILIARIA"
            print(f"  {emoji} [{i+1}/{len(pending)}] {tipo_label} — {analysis['confianza']}")
            print(f"     {txt}")
            if analysis.get('inmobiliaria'):
                print(f"     🏢 {analysis['inmobiliaria']}")
            print(f"     📞 {tel}")

            result = {
                "lat":         lat,
                "lon":         lon,
                "heading":     heading,
                "tipo":        tipo,
                "texto":       txt,
                "telefono":    tel,
                "inmobiliaria": analysis.get("inmobiliaria"),
                "confianza":   analysis.get("confianza"),
                "maps_url":    f"https://maps.google.com/?q={lat},{lon}",
                "sv_url":      (f"https://www.google.com/maps/@?api=1"
                                f"&map_action=pano&viewpoint={lat},{lon}"
                                f"&heading={round(heading)}"),
                "fecha":       datetime.now().strftime("%Y-%m-%d"),
            }
            results.append(result)

            if tipo == "alquiler_directo":
                stats["alquiler_directo"] += 1
            else:
                stats["inmobiliaria"] += 1

            send_cartel(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, img, result)
            time.sleep(0.5)

        else:
            if i % 200 == 0:
                print(f"  ... [{i+1}/{len(pending)}] procesados, "
                      f"{stats['fotos']} fotos, "
                      f"{stats['alquiler']+stats['venta']} carteles")

        seen.add(point_key)
        stats["procesados"] += 1

        # Guardar progreso cada 100 puntos
        if stats["procesados"] % 100 == 0:
            save_seen(seen)
            save_results(results)

        time.sleep(0.05)

    save_seen(seen)
    save_results(results)

    print(f"\n{'='*50}")
    print(f"✅ Escaneo completo")
    print(f"   Procesados:  {stats['procesados']:,}")
    print(f"   Fotos:       {stats['fotos']:,}")
    print(f"   Alquiler:    {stats['alquiler']}")
    print(f"   Venta:       {stats['venta']}")
    print(f"   Costo real:  USD ${stats['costo_usd']:.2f}")

    send_summary(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, stats)

    # Resumen de todos los carteles
    if results:
        resumen = "📋 <b>Todos los carteles encontrados:</b>\n\n"
        for r in results:
            resumen += (
                f"• <b>{(r['tipo'] or '?').upper()}</b> ({r['confianza']})\n"
                f"  {r['texto'] or ''}\n"
                f"  📞 {r['telefono'] or 'no legible'}\n"
                f"  <a href='{r['maps_url']}'>Maps</a> | "
                f"<a href='{r['sv_url']}'>Street View</a>\n\n"
            )
        send_text(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, resumen)


if __name__ == "__main__":
    run()
