"""
vision.py — Gemini Vision detecta carteles de ALQUILER. Usa SDK oficial de Google.
"""

import re, json, base64

PROMPT = (
    "Analizá esta imagen de Google Street View. "
    "Buscá carteles en rejas, paredes, postes y ventanas.\n\n"
    "UNICA RAZON PARA RESPONDER tiene_cartel true: el cartel contiene EXACTAMENTE alguna de estas palabras:\n"
    "ALQUILO / SE ALQUILA / EN ALQUILER / ALQUILER / ARRIENDO / SE RENTA / DUEÑO ALQUILA\n\n"
    "Si no ves alguna de esas palabras escritas — responde tiene_cartel false. Sin excepciones.\n\n"
    "NO registrar:\n"
    "- VENTA / SE VENDE / VENDO / COMPRAMOS / VENDEMOS\n"
    "- Logos, nombres de empresas, publicidad\n"
    "- Numeros de telefono solos sin cartel de alquiler\n"
    "- Nombres de inmobiliarias sin la palabra alquiler escrita\n\n"
    "Responde SOLO con JSON valido, sin texto extra ni backticks:\n"
    '{\n'
    '  "tiene_cartel": true | false,\n'
    '  "palabras_clave": ["palabras exactas vistas"],\n'
    '  "texto_cartel": "<texto legible del cartel o null>",\n'
    '  "telefono": "<numero de telefono junto al cartel o null>",\n'
    '  "confianza": "alta" | "media" | "baja",\n'
    '  "descripcion": "<1 frase de lo que ves>"\n'
    "}"
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
    if any(v in texto for v in _VENTA_WORDS):
        return False
    if not any(a in texto for a in _ALQUILER_WORDS):
        return False
    if not _has_real_phone(tel):
        return False
    return True


def analyze(image_bytes: bytes, api_key: str) -> dict | None:
    try:
        import google.generativeai as genai
        from google.generativeai.types import HarmCategory, HarmBlockThreshold
        import PIL.Image
        import io

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        img = PIL.Image.open(io.BytesIO(image_bytes))

        response = model.generate_content(
            [PROMPT, img],
            generation_config={"temperature": 0, "max_output_tokens": 400},
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            }
        )

        raw = response.text.strip()
        raw = re.sub(r"^```json\s*|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        result["tipo"] = "alquiler_directo"

        if not _passes_filter(result):
            return None

        return result

    except Exception as e:
        print(f"    Vision error: {e}")
        return None
