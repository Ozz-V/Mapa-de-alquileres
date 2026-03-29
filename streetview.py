"""
streetview.py — Google Street View Static API
Verifica disponibilidad (gratis) antes de pagar por la imagen.
"""

import requests

SV_BASE  = "https://maps.googleapis.com/maps/api/streetview"
META_URL = SV_BASE + "/metadata"
IMG_URL  = SV_BASE

IMG_SIZE = "640x480"
IMG_FOV  = 90     # Campo visual. 90° = visión normal, 120° = más contexto
IMG_PITCH = 5     # Ligera inclinación hacia arriba para ver carteles en paredes/rejas


def check_available(lat: float, lon: float, api_key: str) -> bool:
    """Consulta metadata — GRATIS, no descuenta del crédito."""
    try:
        r = requests.get(META_URL, params={
            "location": f"{lat},{lon}",
            "radius":   20,
            "key":      api_key,
        }, timeout=10)
        return r.ok and r.json().get("status") == "OK"
    except Exception:
        return False


def fetch_image(lat: float, lon: float, heading: float, api_key: str) -> bytes | None:
    """
    Descarga la imagen. Esto SÍ consume crédito (~$0.007 por imagen).
    heading: dirección de la cámara en grados (0=Norte, 90=Este, etc.)
    """
    try:
        r = requests.get(IMG_URL, params={
            "size":     IMG_SIZE,
            "location": f"{lat},{lon}",
            "heading":  round(heading),
            "fov":      IMG_FOV,
            "pitch":    IMG_PITCH,
            "radius":   20,
            "source":   "outdoor",   # evita fotos de interior
            "key":      api_key,
        }, timeout=20)
        if r.ok and r.headers.get("content-type", "").startswith("image"):
            return r.content
    except Exception:
        pass
    return None
