import json
import os
import re
import time
import requests
from datetime import datetime, timedelta, timezone


# ============================================
# CONFIGURACIÓN
# ============================================

GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL      = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
HISTORIAL_URL   = "https://raw.githubusercontent.com/jzuniga1995/lotohn/main/historial.json"

MAX_REINTENTOS          = 3
ESPERA_ENTRE_REINTENTOS = 15

JUEGOS = {
    'juga3':       'Jugá 3',
    'pega_3':      'Pega 3',
    'premia2':     'Premia 2',
    'la_diaria':   'La Diaria',
    'super_premio':'Súper Premio',
}

# Cuántos sorteos recientes usar por juego
SORTEOS_A_ANALIZAR = 15


# ============================================
# LLAMADA A GEMINI  (mismo patrón que oraculo.py)
# ============================================

def llamar_gemini(prompt: str) -> str | None:
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY no configurada")
        return None

    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            resp = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature":      0.7,
                        "maxOutputTokens":  1024,
                        "topP":             0.95,
                    }
                },
                timeout=60
            )

            if resp.status_code in (429, 503):
                espera = ESPERA_ENTRE_REINTENTOS * intento
                print(f"⏳ HTTP {resp.status_code} (intento {intento}/{MAX_REINTENTOS}), esperando {espera}s...")
                time.sleep(espera)
                continue

            if not resp.ok:
                print(f"❌ Gemini HTTP {resp.status_code}: {resp.text[:300]}")
                return None

            data  = resp.json()
            texto = data["candidates"][0]["content"]["parts"][0]["text"]
            return texto.strip()

        except Exception as e:
            print(f"❌ Error llamando Gemini (intento {intento}): {e}")
            if intento < MAX_REINTENTOS:
                time.sleep(ESPERA_ENTRE_REINTENTOS)

    return None


# ============================================
# EXTRAER JSON ROBUSTO  (mismo patrón que oraculo.py)
# ============================================

def extraer_json(texto: str) -> dict | None:
    try:
        return json.loads(texto)
    except Exception:
        pass

    limpio = re.sub(r"```(?:json)?\s*", "", texto).replace("```", "").strip()
    try:
        return json.loads(limpio)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", limpio)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    return None


# ============================================
# CARGAR HISTORIAL
# ============================================

def cargar_historial() -> dict:
    try:
        resp = requests.get(HISTORIAL_URL, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️  No se pudo cargar historial remoto: {e}")

    # Fallback: leer local
    if os.path.exists("historial.json"):
        with open("historial.json", "r", encoding="utf-8") as f:
            return json.load(f)

    return {}


def extraer_sorteos_juego(historial: dict, slug: str) -> list:
    """
    Extrae los últimos SORTEOS_A_ANALIZAR resultados de un juego dado su slug.
    Busca keys que contengan el slug en cualquier tanda (_11am, _3pm, _9pm).
    """
    resultados = []

    for fecha in sorted(historial.keys(), reverse=True):
        sorteos = historial[fecha]
        for key, nums in sorteos.items():
            if key.startswith(slug) or key == slug:
                if isinstance(nums, list) and nums:
                    resultados.append({
                        "fecha": fecha,
                        "key":   key,
                        "nums":  nums
                    })
        if len(resultados) >= SORTEOS_A_ANALIZAR:
            break

    return resultados[:SORTEOS_A_ANALIZAR]


# ============================================
# ANALIZAR UN JUEGO
# ============================================

def analizar_juego(slug: str, nombre: str, sorteos: list) -> dict | None:
    if not sorteos:
        print(f"   ⚠️  Sin datos para {nombre}")
        return None

    # Formatear historial para el prompt
    lineas = [f"{s['fecha']} ({s['key']}): {' - '.join(s['nums'])}" for s in sorteos]
    historial_texto = "\n".join(lineas)

    prompt = f"""Analiza los últimos {len(sorteos)} sorteos de "{nombre}" (lotería hondureña).

HISTORIAL:
{historial_texto}

Devolvé SOLO este JSON, sin texto extra, sin markdown:
{{"patrones":"patrones detectados max 120 chars","tendencias":"tendencias recientes max 120 chars","sugerencias":["combo1","combo2","combo3"],"advertencia":"aviso sobre el azar max 70 chars"}}"""

    print(f"   🤖 Llamando a Gemini para {nombre}...")
    respuesta = llamar_gemini(prompt)

    if not respuesta:
        return None

    data = extraer_json(respuesta)
    if not data:
        print(f"   ❌ No se pudo extraer JSON (len={len(respuesta)}): {respuesta[:300]}")
        return None

    # Validar estructura mínima
    if not all(k in data for k in ("patrones", "tendencias", "sugerencias", "advertencia")):
        print(f"   ❌ JSON incompleto: {data}")
        return None

    if not isinstance(data["sugerencias"], list) or len(data["sugerencias"]) < 1:
        print(f"   ❌ Sugerencias inválidas")
        return None

    data["sorteos_analizados"] = len(sorteos)
    return data


# ============================================
# GENERAR analisis.json
# ============================================

def generar_analisis() -> dict | None:
    print("📂 Cargando historial...")
    historial = cargar_historial()

    if not historial:
        print("❌ Historial vacío, abortando.")
        return None

    fecha_hn = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d")
    resultado = {
        "fecha":        fecha_hn,
        "generado_en":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "juegos":       {}
    }

    for slug, nombre in JUEGOS.items():
        print(f"\n📊 Analizando {nombre} ({slug})...")
        sorteos = extraer_sorteos_juego(historial, slug)
        print(f"   📈 {len(sorteos)} sorteos encontrados")

        analisis = analizar_juego(slug, nombre, sorteos)

        if analisis:
            resultado["juegos"][slug] = analisis
            print(f"   ✅ {nombre} analizado")
        else:
            resultado["juegos"][slug] = {
                "patrones":    "No se pudo generar el análisis en este momento.",
                "tendencias":  "Intenta de nuevo más tarde.",
                "sugerencias": [],
                "advertencia": "La lotería es un juego de azar.",
                "sorteos_analizados": len(sorteos)
            }
            print(f"   ⚠️  {nombre} usará fallback")

        # Pausa entre llamadas para no saturar la API
        time.sleep(12)

    return resultado


# ============================================
# GUARDAR analisis.json
# ============================================

def guardar_analisis(data: dict, archivo: str = "analisis.json") -> bool:
    try:
        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Guardado: {archivo}")
        return True
    except Exception as e:
        print(f"❌ Error guardando: {e}")
        return False


# ============================================
# MAIN
# ============================================

def main():
    print("🧠 ANALIZADOR DE NÚMEROS — LOTO HONDURAS")
    print("=" * 60)

    fecha_hn = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d")
    print(f"📅 Fecha Honduras: {fecha_hn}")

    analisis = generar_analisis()

    if not analisis:
        print("❌ No se pudo generar el análisis.")
        return False

    ok = guardar_analisis(analisis)

    print("\n" + "=" * 60)
    print("📊 RESUMEN:")
    for slug, data in analisis["juegos"].items():
        n = data.get("sorteos_analizados", 0)
        print(f"  {'✅' if data.get('sugerencias') else '⚠️ '} {JUEGOS.get(slug, slug)}: {n} sorteos analizados")
    print("=" * 60)

    return ok


if __name__ == "__main__":
    main()
