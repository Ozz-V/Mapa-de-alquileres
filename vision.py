"""
vision.py — Solo detecta carteles que digan EXPLICITAMENTE alquiler.
Sin categoría inmobiliaria. Sin interpretaciones.
"""

import re, json, base64
import anthropic

PROMPT = (
    "Analizá esta imagen de Google Street View. "
    "Buscá carteles en rejas, paredes, postes y ventanas.\n\n"
    "UNICA RAZON PARA RESPONDER tiene_cartel true: el cartel contiene EXACTAMENTE alguna de estas palabras:\n"
    "ALQUILO / SE ALQUILA / EN ALQUILER / ALQUILER / ARRIENDO / SE RENTA / DUEÑO ALQUILA\n\n"
    "Si no ves alguna de esas palabras escritas en la imagen — responde tiene_cartel false. Sin excepciones.\n\n"
    "NO registrar bajo ningun concepto:\n"
    "- VENTA / SE VENDE / VENDO / COMPRAMOS / VENDEMOS\n"
    "- Logos, nombres de empresas, publicidad, negocios\n"
    "- Numeros de telefono solos sin cartel de alquiler\n"
    "- Nombres de inmobiliarias sin la palabra alquiler escrita\n\n"
    "Responde SOLO con JSON valido, sin texto extra ni backticks:\n"
    '{\n'
    '  "tiene_cartel": true | false,\n'
    '  "palabras_clave": ["palabras exactas del cartel que viste"],\n'
    '  "texto_cartel": "<todo el texto legible del cartel, o null>",\n'
    '  "telefono": "<numero de telefono si aparece junto al cartel de alquiler, o null>",\n'
    '  "confianza": "alta" | "media" | "baja",\n'
    '  "descripcion": "<1 frase de lo que ves>"\n'
    "}\n\n"
    "Confianza:\n"
    "- alta = la palabra alquiler/alquilo/etc es perfectamente legible\n"
    "- media = se ve pero algo no es claro\n"
    "- baja = crees que podria decir alquiler pero no estas seguro"
)

_ALQUILER_WORDS = ["alquil", "arrend", "se renta", "en renta"]
_VENTA_WORDS    = ["se vende", "en venta", "a la venta", "vendo", "compramos", "vendemos"]


def _has_real_phone(tel: str) -> bool:
    if not tel:
        return False
    digits = re.sub(r"[\s\-\(\)\+]", "", tel)
    return bool(re.search(r"\d{6,}", digits))


def _passes_filter(result: dict) -> bool:
    if not result.get("tiene_cartel"):
        return False

    texto = (result.get("texto_cartel") or "").lower()
    tel   = result.get("telefono") or ""

    # Venta descarta siempre
    if any(v in texto for v in _VENTA_WORDS):
        return False

    # Debe haber una palabra explícita de alquiler en el texto real
    if not any(a in texto for a in _ALQUILER_WORDS):
        return False

    # Debe tener teléfono con dígitos reales
    if not _has_real_phone(tel):
        return False

    return True


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

        # Forzar tipo alquiler_directo (ya no existe categoría inmobiliaria)
        result["tipo"] = "alquiler_directo"

        if not _passes_filter(result):
            return None

        return result

    except Exception as e:
        print(f"    ⚠️  Vision error: {e}")
        return None
