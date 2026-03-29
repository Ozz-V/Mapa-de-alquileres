# 🗺️ Cartel Scanner — Detector de alquileres y ventas en Street View

Recorre las calles alrededor de **Comagro S.A.** usando Google Street View,
detecta carteles de alquiler y venta con IA (Claude Vision), y manda
cada hallazgo con foto + ubicación exacta por Telegram.

## Cómo funciona

```
OpenStreetMap → puntos cada 40m sobre calles reales (gratis)
        ↓
Street View Metadata → ¿hay imagen aquí? (gratis)
        ↓
Street View Static API → descarga la foto (~$0.007)
        ↓
Claude Vision → ¿hay cartel de alquiler o venta?
        ↓
✅ Si sí → foto + ubicación + teléfono por Telegram
        ↓
Guarda progreso → retoma si se interrumpe
```

## Setup

### 1. Clonar el repo
```bash
git clone https://github.com/TU_USUARIO/cartel-scanner
cd cartel-scanner
```

### 2. Google Maps API Key
1. Ir a [console.cloud.google.com](https://console.cloud.google.com)
2. Crear proyecto nuevo
3. Habilitar **Street View Static API**
4. Crear credencial → **API Key**
5. (Opcional pero recomendado) Restringir la key a Street View Static API

> **Crédito gratis:** Google da **$200/mes** automáticamente.
> El escaneo completo cuesta ~$43 → **$0 de tu bolsillo**.

### 3. Secrets en GitHub
Settings → Secrets and variables → Actions → New repository secret

| Secret | Descripción |
|--------|-------------|
| `GOOGLE_MAPS_API_KEY` | Key de Google Maps Platform |
| `ANTHROPIC_API_KEY` | Ya lo tenés del rental bot |
| `TELEGRAM_TOKEN` | Ya lo tenés del rental bot |
| `TELEGRAM_CHAT_ID` | Ya lo tenés del rental bot |

### 4. Correr
GitHub → **Actions** → **🗺️ Cartel Scanner** → **Run workflow**

La primera corrida descarga las calles de OSM y las cachea.
Las corridas siguientes usan el caché y solo escanean puntos nuevos.

---

## Archivos del repo

| Archivo | Qué hace |
|---------|----------|
| `main.py` | Orquestador principal |
| `osm.py` | Descarga red de calles de OpenStreetMap |
| `streetview.py` | Consulta Google Street View |
| `vision.py` | Analiza imágenes con Claude Vision |
| `notifier.py` | Manda resultados por Telegram |
| `resultados.json` | Todos los carteles encontrados (generado) |
| `seen.json` | Puntos ya procesados (generado) |
| `osm_points.json` | Caché de la red de calles (generado) |

---

## Parámetros ajustables en `main.py`

```python
RADIUS_KM = 3.0   # Radio en km alrededor de Comagro
STEP_M    = 40    # Metros entre puntos (más chico = más detalle = más costo)
```

### Estimación de costos (con $200 crédito Google = todo gratis)

| Radio | Paso | Puntos OSM | Costo estimado | Con crédito |
|-------|------|-----------|----------------|-------------|
| 1.5km | 40m  | ~2.200    | ~$15           | **$0** |
| 3.0km | 40m  | ~6.200    | ~$43           | **$0** |
| 3.0km | 25m  | ~16.000   | ~$112          | **$0** |
| 5.0km | 40m  | ~17.000   | ~$119          | **$0** |

---

## Resultados

Cada cartel encontrado se guarda en `resultados.json`:
```json
{
  "lat": -25.3089,
  "lon": -57.5901,
  "tipo": "alquiler",
  "texto": "SE ALQUILA - 3 DORM - 0981 123456",
  "telefono": "0981 123456",
  "confianza": "alta",
  "maps_url": "https://maps.google.com/?q=-25.3089,-57.5901",
  "sv_url": "https://www.google.com/maps/@?api=1&map_action=pano&...",
  "fecha": "2026-03-29"
}
```

Y recibís esto en Telegram:
```
🏠 Cartel de ALQUILER
📍 1.2 km de Comagro
📝 SE ALQUILA - 3 DORM - 0981 123456
📞 0981 123456
🔗 Ver en Google Maps
```

---

## Resumen de costos

- **OpenStreetMap**: gratis, sin límite
- **Street View Metadata**: gratis, no consume crédito
- **Street View Static**: $7 por 1000 imágenes → ~$43 para 3km
- **Claude Vision**: incluido en tu plan Anthropic
- **GitHub Actions**: gratis (plan free da 2000 min/mes)
- **Crédito Google**: $200/mes automático → **costo neto $0**
