import json
import os
import requests
from datetime import datetime, timedelta, timezone


# ============================================
# CONFIGURACIÓN
# ============================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")


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

    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature":     1.0,
                    "maxOutputTokens": 400,
                    "topP":            0.95,
                }
            },
            timeout=30
        )

        if not resp.ok:
            print(f"❌ Gemini HTTP {resp.status_code}: {resp.text}")
            return None

        data   = resp.json()
        texto  = data["candidates"][0]["content"]["parts"][0]["text"]
        return texto.strip()

    except Exception as e:
        print(f"❌ Error llamando Gemini: {e}")
        return None


# ============================================
# GENERAR ORÁCULO
# ============================================

def generar_oraculo(fecha_str: str) -> dict | None:
    """Genera el oráculo del día vía Gemini. Devuelve dict o None si falla."""

    prompt = f"""Eres el Oráculo Loto Honduras. Tu trabajo es generar el contenido diario de cábala para jugadores de lotería hondureños.

Hoy es {fecha_str}.

Genera un JSON con exactamente esta estructura y sin ningún texto adicional, sin bloques de código markdown, solo el JSON puro:

{{
  "acertijo": "Un acertijo breve y misterioso (máximo 2 oraciones) con referencias a la naturaleza, comida, tradiciones o lugares de Honduras. No des la respuesta. Estilo poético y ambiguo, como los acertijos de Zavaleta.",
  "numeros": [3 números enteros entre 1 y 99, distintos entre sí],
  "frase": "Una frase corta de cierre, hondureña, con personalidad. Puede tener humor local. Máximo 10 palabras."
}}

Reglas importantes:
- El acertijo NUNCA debe dar la respuesta explícita
- Los números deben sentirse relacionados con el acertijo (aunque sea simbólicamente)
- La frase de cierre debe sonar auténtica, no genérica
- Todo en español hondureño natural
- Solo devuelve el JSON, nada más"""

    print(f"🔮 Llamando a Gemini para fecha {fecha_str}...")
    respuesta = llamar_gemini(prompt)

    if not respuesta:
        return None

    # Limpiar posibles bloques markdown que Gemini a veces agrega
    respuesta = respuesta.strip()
    if respuesta.startswith("```"):
        respuesta = respuesta.split("```")[1]
        if respuesta.startswith("json"):
            respuesta = respuesta[4:]
    respuesta = respuesta.strip()

    try:
        data = json.loads(respuesta)

        # Validar estructura mínima
        assert isinstance(data.get("acertijo"), str) and len(data["acertijo"]) > 10
        assert isinstance(data.get("numeros"), list) and len(data["numeros"]) == 3
        assert isinstance(data.get("frase"), str) and len(data["frase"]) > 3

        # Normalizar números a enteros entre 1 y 99
        data["numeros"] = [max(1, min(99, int(n))) for n in data["numeros"]]

        return data

    except Exception as e:
        print(f"❌ Error parseando respuesta de Gemini: {e}")
        print(f"   Respuesta recibida: {respuesta}")
        return None


# ============================================
# GUARDAR oraculo.json
# ============================================

def guardar_oraculo(data: dict, archivo: str = "oraculo.json") -> bool:
    try:
        # Si ya existe un oráculo del mismo día, no sobreescribir
        if os.path.exists(archivo):
            with open(archivo, "r", encoding="utf-8") as f:
                existente = json.load(f)
            if existente.get("fecha") == data["fecha"]:
                print(f"⏭️  Oráculo del {data['fecha']} ya existe, se conserva.")
                return True

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

    # Fecha Honduras (UTC-6)
    fecha_hn  = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d")
    print(f"📅 Fecha Honduras: {fecha_hn}")

    # Generar contenido
    oraculo = generar_oraculo(fecha_hn)

    if not oraculo:
        print("❌ No se pudo generar el oráculo. Usando fallback.")
        # Fallback manual para que el componente nunca quede vacío
        oraculo = {
            "acertijo": "Dicen que en Honduras el que espera, desespera... pero el que juega, ¿quién sabe?",
            "numeros":  [11, 33, 77],
            "frase":    "¡Zaz zaz, Aguilillo!"
        }

    # Agregar metadatos
    oraculo["fecha"]        = fecha_hn
    oraculo["generado_en"]  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"📜 Acertijo: {oraculo['acertijo']}")
    print(f"🔢 Números: {oraculo['numeros']}")
    print(f"💬 Frase: {oraculo['frase']}")

    # Guardar
    ok = guardar_oraculo(oraculo)

    # Notificar Telegram
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

    