"""
vision.py — Claude Vision detecta carteles de ALQUILER en fotos de Street View.

Reglas duras:
  ✅ PASA  — dice explícitamente alquiler/alquilo/se alquila/arriendo/se renta
  ✅ PASA  — dice "inmobiliaria" + tiene número de teléfono (sin mencionar venta)
  ✅ PASA  — combo de las dos anteriores
  ❌ DESCARTA — menciona venta/vendo/en venta/se vende (sin importar el resto)
  ❌ DESCARTA — solo nombre de agencia o logo sin número ni palabra "alquiler"
"""

import re, json, base64
import anthropic

PROMPT = """Analizá esta imagen de Google Street View buscando carteles inmobiliarios de ALQUILER en Paraguay.
Mirá rejas, paredes, postes, ventanas. Sé muy literal — solo registrá lo que dice explícitamente el cartel.

═══ CUÁNDO REGISTRAR (tiene_cartel: true) ═══

✅ CASO 1 — Dice explícitamente alquiler:
   Palabras exactas: ALQUILO · SE ALQUILA · EN ALQUILER · ALQUILER · ARRIENDO · SE RENTA · DUEÑO ALQUILA
   → tipo: "alquiler_directo"

✅ CASO 2 — Dice la palabra INMOBILIARIA y tiene número de teléfono visible:
   La palabra "inmobiliaria" debe estar escrita en el cartel + debe haber un número de teléfono
   → tipo: "inmobiliaria"

═══ CUÁNDO IGNORAR (tiene_cartel: false) ═══

❌ Dice VENTA / EN VENTA / SE VENDE / VENDO → descartar SIEMPRE, aunque combine con otras cosas
❌ Solo un logo o nombre de agencia (RE/MAX, Century 21, etc.) sin la palabra "inmobiliaria" escrita ni número
❌ Carteles de negocios (almacén, farmacia, pizzería, "Pilar", nombres propios, etc.)
❌ Publicidad que no sea específicamente inmobiliaria de alquiler
❌ No hay ningún cartel visible

═══ RESPUESTA ═══

Respondé SOLO con JSON válido, sin texto extra ni backticks:
{
  "tiene_cartel": true | false,
  "tipo": "alquiler_directo" | "inmobiliaria" | null,
  "palabras_clave": ["palabras", "exactas", "vistas"],
  "texto_cartel": "<todo el texto legible, o null>",
  "telefono": "<número si aparece, o null>",
  "inmobiliaria": "<nombre de la agencia si aparece escrito, o null>",
  "confianza": "alta" | "media" | "baja",
  "descripcion": "<1 frase de lo que ves>"
}

Confianza:
- "alta" = texto perfectamente legible
- "media" = se ve pero algo no es claro
- "baja" = dudás si es un cartel inmobiliario de alquiler"""


import re as _re

_ALQUILER_WORDS = ["alquil", "arrend", "se renta", "en renta"]
_VENTA_WORDS    = ["se vende", "en venta", "a la venta", "vendo", "en vta"]


def _has_real_phone(tel: str) -> bool:
    """Requiere al menos 6 dígitos consecutivos — descarta frases como 'no legible'."""
    if not tel:
        return False
    digits = _re.sub(r"[\s\-\(\)\+]", "", tel)
    return bool(_re.search(r"\d{6,}", digits))


def _passes_filter(result: dict) -> bool:
    if not result.get("tiene_cartel"):
        return False

    tipo         = result.get("tipo") or ""
    # SOLO el texto literal del cartel — NO palabras_clave (son interpretación del modelo)
    texto_cartel = (result.get("texto_cartel") or "").lower()
    tel          = result.get("telefono") or ""

    # Venta en el texto real descarta siempre
    if any(v in texto_cartel for v in _VENTA_WORDS):
        return False

    # alquiler_directo: palabra de alquiler en texto real + teléfono con dígitos reales
    if tipo == "alquiler_directo":
        tiene_alquiler = any(a in texto_cartel for a in _ALQUILER_WORDS)
        return tiene_alquiler and _has_real_phone(tel)

    # inmobiliaria: la palabra "inmobiliaria" debe estar ESCRITA en el cartel + teléfono real
    if tipo == "inmobiliaria":
        tiene_palabra = "inmobiliaria" in texto_cartel
        return tiene_palabra and _has_real_phone(tel)

    return False


def analyze(image_bytes: bytes, api_key: str) -> dict | None:
    client = anthropic.Anthropic(api_key=api_key)
    try:
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        r = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       b64,
                        }
                    },
                    {"type": "text", "text": PROMPT}
                ]
            }]
        )
        raw = r.content[0].text.strip()
        raw = re.sub(r"^```json\s*|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)

        if not _passes_filter(result):
            return None

        return result

    except Exception as e:
        print(f"    ⚠️  Vision error: {e}")
        return None
