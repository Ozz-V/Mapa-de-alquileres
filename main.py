"""
main.py — Orquestador del Street View Cartel Scanner
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
RADIUS_KM    = 2.0
STEP_M       = 80
MAX_COST_USD = 100.0
MIN_CONFIDENCE = {"alta"}

RESULTS_FILE = "resultados.json"
SEEN_FILE    = "seen.json"

GOOGLE_KEY       = os.environ["GOOGLE_MAPS_API_KEY"]
GEMINI_KEY       = os.environ["GEMINI_API_KEY"]
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

# ── MAPAS ──────────────────────────────────────────────────────────────────────

def _build_map_bytes(all_points, seen, results):
    visited_pts = [
        (lat, lon, hdg)
        for lat, lon, hdg in all_points
        if f"{lat},{lon}" in seen
    ]
    return generate_coverage_map(
        all_points     = all_points,
        visited_points = visited_pts,
        cartel_results = results,
        center_lat     = COMAGRO_LAT,
        center_lon     = COMAGRO_LON,
    ), len(visited_pts)


def send_progress_map(all_points, seen, results, stats):
    try:
        map_bytes, total_v = _build_map_bytes(all_points, seen, results)
        pct     = int(total_v / len(all_points) * 100) if all_points else 0
        total_c = stats["alquiler_directo"] + stats["inmobiliaria"]
        caption = (
            "Progreso: " + str(pct) + "% ("
            + str(total_v) + "/" + str(len(all_points)) + " puntos)\n"
            "Carteles encontrados: " + str(total_c) + "\n"
            "Costo: USD $" + str(round(stats["costo_usd"], 2))
        )
        send_map(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, map_bytes, caption)
        print("  Mapa de progreso enviado (" + str(pct) + "%)")
    except Exception as e:
        print("  Mapa progreso error: " + str(e))


def send_final_map(all_points, seen, results, stats):
    try:
        map_bytes, total_v = _build_map_bytes(all_points, seen, results)
        total_c = stats["alquiler_directo"] + stats["inmobiliaria"]
        caption = (
            "Mapa final - Escaneo completo\n"
            "Radio: " + str(RADIUS_KM) + " km\n"
            "Puntos recorridos: " + str(total_v) + "\n"
            "Carteles encontrados: " + str(total_c) + "\n"
            "Costo: USD $" + str(round(stats["costo_usd"], 2))
        )
        send_map(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, map_bytes, caption)
        print("  Mapa final enviado")
    except Exception as e:
        print("  Mapa final error: " + str(e))

# ── MAIN ───────────────────────────────────────────────────────────────────────

def run():
    print("\nCartel Scanner - " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("  Centro: Comagro S.A. (" + str(COMAGRO_LAT) + ", " + str(COMAGRO_LON) + ")")
    print("  Radio: " + str(RADIUS_KM) + "km  |  Paso: " + str(STEP_M) + "m")
    print("  Techo de costo: USD $" + str(MAX_COST_USD) + "\n")

    all_points = get_road_points(COMAGRO_LAT, COMAGRO_LON, RADIUS_KM, STEP_M)
    print("\n  Total puntos: " + str(len(all_points)))

    est_cost = len(all_points) * 0.007
    print("  Costo maximo estimado: USD $" + str(round(est_cost, 1)))
    if est_cost > MAX_COST_USD:
        accessible = int(MAX_COST_USD / 0.007)
        print("  Supera el techo - se procesaran hasta " + str(accessible) + " fotos")
    else:
        print("  Dentro del techo de USD $" + str(MAX_COST_USD))
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
    print("  Puntos pendientes: " + str(len(pending)) + "  (ya vistos: " + str(len(seen)) + ")\n")

    if not pending:
        print("  Todo el area ya fue escaneada.")
        send_final_map(all_points, seen, results, stats)
        return

    # Mandar mapa inicial mostrando lo que falta recorrer
    if seen:
        send_progress_map(all_points, seen, results, stats)

    for i, (lat, lon, heading) in enumerate(pending):
        point_key = f"{lat},{lon}"

        # Techo de costo
        if stats["costo_usd"] >= MAX_COST_USD:
            if not stats["cap_alcanzado"]:
                stats["cap_alcanzado"] = True
                print("\n  Techo USD $" + str(MAX_COST_USD) + " alcanzado.\n")
            seen.add(point_key)
            stats["procesados"] += 1
            if stats["procesados"] % 500 == 0:
                save_seen(seen)
            continue

        if not check_available(lat, lon, GOOGLE_KEY):
            seen.add(point_key)
            stats["procesados"] += 1
            continue

        img = fetch_image(lat, lon, heading, GOOGLE_KEY)
        stats["costo_usd"] += 0.007

        if not img:
            seen.add(point_key)
            stats["procesados"] += 1
            continue

        stats["fotos"] += 1

        analysis = analyze(img, GEMINI_KEY)

        if (analysis
                and analysis.get("tiene_cartel")
                and analysis.get("confianza") in MIN_CONFIDENCE):

            tipo     = "alquiler_directo"
            tel      = analysis.get("telefono") or "no legible"
            txt      = analysis.get("texto_cartel") or analysis.get("descripcion") or ""
            dist_km  = round(haversine_km(COMAGRO_LAT, COMAGRO_LON, lat, lon), 2)

            print("  ALQUILER [" + str(i+1) + "/" + str(len(pending)) + "] - " + analysis["confianza"])
            print("     " + txt)
            print("     Tel: " + tel)
            print("     " + str(dist_km) + " km de Comagro")

            result = {
                "lat":          lat,
                "lon":          lon,
                "heading":      heading,
                "tipo":         tipo,
                "texto_cartel": txt,
                "telefono":     tel,
                "inmobiliaria": None,
                "confianza":    analysis.get("confianza"),
                "dist_km":      dist_km,
                "maps_url":     "https://maps.google.com/?q=" + str(lat) + "," + str(lon),
                "sv_url":       ("https://www.google.com/maps/@?api=1"
                                 "&map_action=pano&viewpoint=" + str(lat) + "," + str(lon)
                                 + "&heading=" + str(round(heading))),
                "fecha":        datetime.now().strftime("%Y-%m-%d"),
            }
            results.append(result)
            stats["alquiler_directo"] += 1

            send_cartel(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, img, result)
            time.sleep(0.5)

        else:
            total_c = stats["alquiler_directo"] + stats["inmobiliaria"]
            if i % 200 == 0:
                print("  ... [" + str(i+1) + "/" + str(len(pending)) + "] "
                      + str(stats["fotos"]) + " fotos, "
                      + str(total_c) + " carteles, "
                      + "USD $" + str(round(stats["costo_usd"], 2)))

        seen.add(point_key)
        stats["procesados"] += 1

        if stats["procesados"] % 100 == 0:
            save_seen(seen)
            save_results(results)

        # Mapa de progreso cada 500 puntos
        if stats["procesados"] % 500 == 0:
            send_progress_map(all_points, seen, results, stats)

        time.sleep(4.1)  # Gemini free tier: max 15 req/min = 1 cada 4s

    save_seen(seen)
    save_results(results)

    total_c = stats["alquiler_directo"] + stats["inmobiliaria"]
    print("\n" + "="*50)
    print("Escaneo completo")
    print("  Procesados:  " + str(stats["procesados"]))
    print("  Fotos:       " + str(stats["fotos"]))
    print("  Carteles:    " + str(total_c))
    print("  Costo real:  USD $" + str(round(stats["costo_usd"], 2)))

    send_summary(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, stats)

    if results:
        resumen = "<b>Todos los carteles encontrados:</b>\n\n"
        for r in results:
            resumen += (
                "ALQUILER (" + str(r["confianza"]) + ") - " + str(r.get("dist_km", "?")) + " km\n"
                + str(r.get("texto_cartel") or "") + "\n"
                "Tel: " + str(r["telefono"] or "no legible") + "\n"
                "<a href='" + r["maps_url"] + "'>Maps</a> | "
                "<a href='" + r["sv_url"] + "'>Street View</a>\n\n"
            )
        send_text(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, resumen)

    send_final_map(all_points, seen, results, stats)


if __name__ == "__main__":
    run()
