"""
notifier.py — Manda carteles encontrados por Telegram.
"""

import requests


def _post(token: str, method: str, **kwargs):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            timeout=30,
            **kwargs
        )
    except Exception as e:
        print(f"  ⚠️  Telegram error: {e}")


def send_photo(token: str, chat_id: str, image_bytes: bytes, caption: str):
    _post(token, "sendPhoto",
          data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
          files={"photo": ("cartel.jpg", image_bytes, "image/jpeg")})


def send_text(token: str, chat_id: str, text: str):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        _post(token, "sendMessage",
              json={"chat_id": chat_id, "text": chunk,
                    "parse_mode": "HTML", "disable_web_page_preview": True})


def send_map(token: str, chat_id: str, map_bytes: bytes, caption: str):
    """Envía el PNG del mapa de cobertura como documento (sin compresión)."""
    _post(token, "sendDocument",
          data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
          files={"document": ("mapa_cobertura.png", map_bytes, "image/png")})


def send_cartel(token: str, chat_id: str,
                image_bytes: bytes, result: dict):
    """Manda la foto del cartel con toda la info."""
    tipo     = result.get("tipo") or "inmobiliaria"
    texto    = result.get("texto_cartel") or result.get("descripcion") or ""
    tel      = result.get("telefono") or "no legible"
    inmob    = result.get("inmobiliaria") or ""
    dist     = result.get("dist_km", "?")
    lat      = result.get("lat")
    lon      = result.get("lon")
    maps_url = f"https://maps.google.com/?q={lat},{lon}"
    sv_url   = result.get("sv_url", maps_url)

    if tipo == "alquiler_directo":
        emoji  = "🏠"
        titulo = "Cartel de ALQUILER"
    else:
        emoji  = "🏢"
        titulo = f"Inmobiliaria: {inmob}" if inmob else "Cartel inmobiliaria"

    lines = [
        f"{emoji} <b>{titulo}</b>",
        f"📍 {dist} km de Comagro",
    ]
    if texto:
        lines.append(f"📝 {texto}")
    if inmob and tipo != "alquiler_directo":
        lines.append(f"🏢 {inmob}")
    lines.append(f"📞 {tel}")
    lines.append(f"🗺 <a href='{maps_url}'>Google Maps</a> | <a href='{sv_url}'>Street View</a>")

    caption = "\n".join(lines)
    send_photo(token, chat_id, image_bytes, caption)


def send_summary(token: str, chat_id: str, stats: dict):
    """Resumen final del escaneo."""
    total = stats.get("alquiler_directo", 0) + stats.get("inmobiliaria", 0)
    cap_note = ""
    if stats.get("cap_alcanzado"):
        cap_note = f"\n⚠️ Techo USD ${stats.get('costo_usd', 0):.0f} alcanzado"

    text = (
        f"✅ <b>Escaneo completado</b>\n\n"
        f"📍 Puntos procesados:      {stats['procesados']:,}\n"
        f"📸 Fotos analizadas:       {stats['fotos']:,}\n"
        f"🏠 Alquiler directo:       {stats.get('alquiler_directo', 0)}\n"
        f"🏢 Carteles inmobiliaria:  {stats.get('inmobiliaria', 0)}\n"
        f"📊 Total encontrados:      {total}\n"
        f"💰 Costo real:             USD ${stats['costo_usd']:.2f}"
        f"{cap_note}"
    )
    send_text(token, chat_id, text)
