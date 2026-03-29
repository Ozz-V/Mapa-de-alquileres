"""
vision.py — Claude Vision detecta carteles de ALQUILER en fotos de Street View.
Solo registra alquileres. Ignora ventas completamente.
"""

import re, json, base64
import anthropic

PROMPT = """Sos un asistente experto en detectar carteles inmobiliarios de ALQUILER en calles de Paraguay.

Analizá esta imagen de Google Street View con MUCHO DETALLE. Mirá rejas, paredes, postes, ventanas.

═══ QUÉ REGISTRAR ═══

✅ SEÑALES DIRECTAS de alquiler (registrar siempre):
- "SE ALQUILA", "ALQUILO", "EN ALQUILER", "SE RENTA", "ALQUILER", "ARRIENDO"
- "DUEÑO ALQUILA", "ALQUILO DIRECTO", "ALQUILA"
- Cualquier variante escrita a mano o impresa

✅ SEÑALES INDIRECTAS (registrar aunque no diga "alquiler" explícitamente):
- Cartel de inmobiliaria conocida clavado en reja o pared de una propiedad:
  RE/MAX, CENTURY 21, JARILLON, COLDWELL BANKER, ERA, o cualquier logo de agencia
- Nombre de inmobiliaria + número de teléfono en una propiedad
- Código QR de inmobiliaria en una propiedad
- Un cartel genérico de agencia inmobiliaria (aunque no especifique alquiler o venta)

❌ IGNORAR completamente:
- "SE VENDE", "VENDO", "EN VENTA", "A LA VENTA" sin mención de alquiler
- Carteles de negocios comerciales (almacén, farmacia, restaurant, etc.)
- Publicidad que no sea inmobiliaria

═══ RESPUESTA ═══

Respondé SOLO con JSON válido, sin texto extra ni backticks:
{
  "tiene_cartel": true | false,
  "tipo": "alquiler_directo" | "inmobiliaria" | null,
  "palabras_clave": ["palabras", "vistas", "en", "el", "cartel"],
  "texto_cartel": "<todo el texto legible del cartel, o null>",
  "telefono": "<número con código de área si aparece, o null>",
  "inmobiliaria": "<nombre exacto de la inmobiliaria si aparece, o null>",
  "confianza": "alta" | "media" | "baja",
  "descripcion": "<1 frase de lo que ves>"
}

Tipos:
- "alquiler_directo" = dice explícitamente alquiler/alquilo/se renta/se alquila/arriendo
- "inmobiliaria" = cartel de agencia sin especificar, pero claramente inmobiliario

Confianza:
- "alta" = texto perfectamente legible
- "media" = se ve el cartel pero algo no es claro
- "baja" = podría ser un cartel inmobiliario pero no estás seguro

Un papel A4 pegado en la reja también cuenta. Sé minucioso."""


def analyze(image_bytes: bytes, api_key: str) -> dict | None:
    client = anthropic.Anthropic(api_key=api_key)
    try:
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        r = client.messages.create(
            model="claude-sonnet-4-20250514",
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

        # Doble chequeo: descartar si solo menciona venta sin alquiler
        texto    = (result.get("texto_cartel") or "").lower()
        palabras = " ".join(result.get("palabras_clave") or []).lower()
        combined = texto + " " + palabras

        SOLO_VENTA = ["se vende", "en venta", "a la venta", "vendo "]
        ALQUILER   = ["alquil", "arrend", "renta", "inmobiliaria",
                      "remax", "re/max", "century", "jarillon", "coldwell"]

        if any(v in combined for v in SOLO_VENTA):
            if not any(a in combined for a in ALQUILER):
                return None   # Es pura venta, descartar

        return result

    except Exception as e:
        print(f"    ⚠️  Vision error: {e}")
        return None
