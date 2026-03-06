import json
import os
import re
import time
import requests
from datetime import datetime, timedelta, timezone


# ============================================
# CONFIGURACIÓN
# ============================================

GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL         = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

MAX_REINTENTOS = 3
ESPERA_ENTRE_REINTENTOS = 15  # segundos


# ============================================
# TELEGRAM
# ============================================

def enviar_telegram(mensaje: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id":              TELEGRAM_CHAT_ID,
                "text":                 mensaje,
                "parse_mode":           "HTML",
                "disable_notification": True
            },
            timeout=10
        )
        return resp.ok
    except Exception as e:
        print(f"⚠️  Telegram error: {e}")
        return False


# ============================================
# LLAMADA A GEMINI
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
                        "temperature":      0.9,
                        "maxOutputTokens":  800,
                        "topP":             0.95,
                        "responseMimeType": "application/json",  # fuerza JSON puro sin markdown
                    }
                },
                timeout=45
            )

            if resp.status_code == 429:
                print(f"⏳ Rate limit (intento {intento}/{MAX_REINTENTOS}), esperando {ESPERA_ENTRE_REINTENTOS}s...")
                time.sleep(ESPERA_ENTRE_REINTENTOS)
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
# EXTRAER JSON ROBUSTO
# ============================================

def extraer_json(texto: str) -> dict | None:
    """Extrae el primer objeto JSON válido del texto, aunque venga con basura alrededor."""

    # 1. Intentar parsear directo
    try:
        return json.loads(texto)
    except Exception:
        pass

    # 2. Limpiar bloques markdown ```json ... ```
    limpio = re.sub(r"```(?:json)?\s*", "", texto).replace("```", "").strip()
    try:
        return json.loads(limpio)
    except Exception:
        pass

    # 3. Extraer el primer bloque { ... } completo con regex
    match = re.search(r"\{[\s\S]*\}", limpio)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    return None


# ============================================
# GENERAR ORÁCULO
# ============================================

def generar_oraculo(fecha_str: str) -> dict | None:
    """Genera el oráculo del día vía Gemini. Devuelve dict o None si falla."""

    prompt = f"""Eres el Oráculo Loto Honduras. Generás el contenido diario de cábala para jugadores hondureños.

Hoy es {fecha_str}.

Devolvé ÚNICAMENTE este JSON (sin texto extra, sin markdown):

{{
  "acertijo": "Un acertijo breve y misterioso (máximo 2 oraciones) con referencias a la naturaleza, comida, tradiciones o lugares de Honduras. No des la respuesta. Estilo poético y ambiguo.",
  "numeros": [N1, N2, N3],
  "frase": "Frase corta de cierre, hondureña, con personalidad. Máximo 10 palabras."
}}

Reglas:
- acertijo: string, máximo 150 caracteres, nunca revela la respuesta
- numeros: exactamente 3 enteros distintos entre 1 y 99
- frase: string, máximo 60 caracteres, humor o sabor local hondureño
- Solo JSON, nada más"""

    print(f"🔮 Llamando a Gemini para fecha {fecha_str}...")
    respuesta = llamar_gemini(prompt)

    if not respuesta:
        return None

    data = extraer_json(respuesta)

    if not data:
        print(f"❌ No se pudo extraer JSON de la respuesta: {respuesta[:200]}")
        return None

    try:
        # Validar estructura mínima
        assert isinstance(data.get("acertijo"), str) and len(data["acertijo"]) > 10, "acertijo inválido"
        assert isinstance(data.get("numeros"), list) and len(data["numeros"]) == 3, "numeros inválido"
        assert isinstance(data.get("frase"), str) and len(data["frase"]) > 3, "frase inválida"

        # Normalizar números
        data["numeros"] = [max(1, min(99, int(n))) for n in data["numeros"]]

        return data

    except AssertionError as e:
        print(f"❌ Validación fallida: {e} — datos: {data}")
        return None


# ============================================
# GUARDAR oraculo.json
# ============================================

def guardar_oraculo(data: dict, archivo: str = "oraculo.json") -> bool:
    try:
        if os.path.exists(archivo):
            with open(archivo, "r", encoding="utf-8") as f:
                existente = json.load(f)
            if existente.get("fecha") == data["fecha"]:
                print(f"⏭️  Oráculo del {data['fecha']} ya existe, se conserva.")
                return False  # ← cambia True por False

        with open(archivo, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"💾 Oráculo guardado: {archivo}")
        return True

    except Exception as e:
        print(f"❌ Error guardando oráculo: {e}")
        return False


# ============================================
# MAIN
# ============================================

def main():
    print("🔮 ORÁCULO LOTO HONDURAS")
    print("=" * 60)

    fecha_hn = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d")
    print(f"📅 Fecha Honduras: {fecha_hn}")

    oraculo = generar_oraculo(fecha_hn)

    if not oraculo:
        print("❌ No se pudo generar el oráculo. Usando fallback.")
        oraculo = {
            "acertijo": "Dicen que en Honduras el que espera, desespera... pero el que juega, ¿quién sabe?",
            "numeros":  [11, 33, 77],
            "frase":    "¡Zaz zaz, Aguilillo!"
        }

    oraculo["fecha"]       = fecha_hn
    oraculo["generado_en"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"📜 Acertijo: {oraculo['acertijo']}")
    print(f"🔢 Números:  {oraculo['numeros']}")
    print(f"💬 Frase:    {oraculo['frase']}")

    ok = guardar_oraculo(oraculo)

    if ok:
        msg = (
            "🔮 <b>ORÁCULO DEL DÍA — LOTO HONDURAS</b>\n"
            f"📅 {fecha_hn}\n\n"
            f"📜 <i>{oraculo['acertijo']}</i>\n\n"
            f"🔢 Números: <b>{' · '.join(str(n) for n in oraculo['numeros'])}</b>\n"
            f"💬 {oraculo['frase']}"
        )
        enviar_telegram(msg)
        print("📨 Notificación enviada a Telegram")

    print("=" * 60)
    return ok


if __name__ == "__main__":
    main()
