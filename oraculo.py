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

SIGNOS = "00-Avión,01-Pies,02-Mujer,03-Muerto,04-Tigre,05-Embarazada,06-Elefante,07-Navaja,08-Conejo,09-Hombre,10-Anillo,11-Perro,12-Caballo,13-Gato,14-Boda,15-Ratón,16-Niña,17-Joven,18-Ángel,19-Mariposa,20-Espejo,21-Pájaro,22-Ataúd,23-Mono,24-Sapo,25-Balanza,26-Bandera,27-Juego,28-Gallo,29-Padre,30-Bolo,31-Alacrán,32-Culebra,33-Carpintero,34-Música,35-Virgen,36-Ciejita,37-Suerte,38-Pistola,39-Jabón,40-Cielo,41-Novia,42-Madre,43-Pantera,44-Mesas,45-Iglesia,46-Familia,47-Banco,48-Estrella,49-Sombra,50-Luna Nueva,51-Policía,52-Zorrillo,53-Llanta,54-Licor,55-Olas,56-Árbol,57-Cuchillo,58-Venado,59-Selva,60-Dragón,61-Guerra,62-Lagarto,63-Coco,64-Mueble,65-Pintura,66-Diablo,67-Vaca,68-Ladrón,69-Soldado,70-Oro,71-Zapatos,72-Arco,73-Fuego,74-Edificio,75-Reina,76-Palomas,77-Humo,78-Tienda,79-Flores,80-Café,81-Rieles,82-Escuela,83-Bote,84-Coronas,85-Casa,86-Reloj,87-León,88-Platos,89-Búho,90-Lentes,91-Tortuga,92-Águila,93-Cartero,94-Carro,95-Costurera,96-Dinero,97-Viejito,98-Bailes,99-Aretes"

CALICHE = """Vocabulario hondureño auténtico:
- cipote/cipota: niño/niña | chigüín: niño pequeño | güirro: niño
- maje: tipo, amigo cercano | alero: amigo de confianza
- pisto: dinero | hule: sin dinero | acabado: sin un centavo
- chamba: trabajo | filo/cachuda: hambre
- cheque: todo bien | macizo/de miedo: excelente
- tuani: genial, chévere | a toda máquina: muy bueno
- chunche: cosa cualquiera | chucho: perro callejero
- chele: persona de piel clara
- a wilson: claro que sí | yuca: muy difícil
- chonguengue: fiesta | despelote: relajo divertido
- sapo: chismoso | dundo: tonto | charrula: inútil
- catracho/catracha: hondureño/hondureña | mínimo: banano
- torcido: mala suerte | chepa/chepo: policía
- zarpe: oportunidad | a la gran: expresión de sorpresa"""

EJEMPLOS_PRESAGIO = """
Ejemplos de presagios buenos:
- "Cuando el chucho ladre tres veces sin razón, alguien en tu barrio cambia la suerte esta semana."
- "Si el primer pájaro que ves hoy vuela hacia el sur, el pisto llega antes del viernes."
- "Cuando la vela tiemble sin viento, los números del cielo están hablando — escuchalos."
- "Si soñaste con agua clara esta noche, el zarpe está más cerca de lo que creés, maje."
- "Cuando el vecino riña por nada, señal que la buena racha anda buscando dueño."
"""


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
                        "maxOutputTokens":  1500,
                        "topP":             0.95,
                        "responseMimeType": "application/json",
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

    prompt = f"""Eres el Oráculo de La Diaria Honduras, estilo Zavaleta. Fecha: {fecha_str}.

Tabla de signos: {SIGNOS}

Vocabulario catracho para usar: {CALICHE}

Instrucciones:
1. Elige 4 números distintos entre 01 y 99.
2. Identifica el signo del PRIMER número en la tabla.
3. Escribe UN presagio místico inspirado en ese signo — sin nombrarlo jamás.
   - Que suene a señal del universo o la naturaleza, vago pero creíble.
   - Usá el vocabulario catracho cuando encaje natural.
   - Varía la estructura: puede empezar con "Cuando...", "Si hoy...", "La señal llega cuando...", etc.
   - Máximo 120 caracteres.
4. Escribe una frase de cierre chistosa y catracha, puro despelote, sin relación forzada con los números.
   - Máximo 60 caracteres.

Ejemplos de presagios: {EJEMPLOS_PRESAGIO}

Devolvé SOLO este JSON:
{{"presagio":"max 120 chars, señal mística catracha","numeros":[N1,N2,N3,N4],"frase":"max 60 chars, remate cómico catracho"}}

Solo JSON, nada más."""

    print(f"🔮 Llamando a Gemini para fecha {fecha_str}...")
    respuesta = llamar_gemini(prompt)

    if not respuesta:
        return None

    data = extraer_json(respuesta)

    if not data:
        print(f"❌ No se pudo extraer JSON de la respuesta: {respuesta[:200]}")
        return None

    try:
        assert isinstance(data.get("presagio"), str) and len(data["presagio"]) > 10, "presagio inválido"
        assert isinstance(data.get("numeros"), list) and len(data["numeros"]) == 4, "numeros inválido"
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
                return False

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

    # ✅ Verificar ANTES de llamar a Gemini — evita gastar cuota
    if os.path.exists("oraculo.json"):
        try:
            with open("oraculo.json", "r", encoding="utf-8") as f:
                existente = json.load(f)
            if existente.get("fecha") == fecha_hn:
                print(f"⏭️  Oráculo del {fecha_hn} ya existe, nada que hacer.")
                return False
        except Exception:
            pass  # si el archivo está corrupto, seguimos y regeneramos

    oraculo = generar_oraculo(fecha_hn)

    if not oraculo:
        print("❌ No se pudo generar el oráculo. Usando fallback.")
        oraculo = {
            "presagio": "Cuando el chucho ladre sin razón al amanecer, la suerte anda cerca, maje.",
            "numeros":  [11, 33, 77, 42],
            "frase":    "¡Zaz zaz, Aguilillo!"
        }

    oraculo["fecha"]       = fecha_hn
    oraculo["generado_en"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"🌙 Presagio: {oraculo['presagio']}")
    print(f"🔢 Números:  {oraculo['numeros']}")
    print(f"💬 Frase:    {oraculo['frase']}")

    ok = guardar_oraculo(oraculo)

    if ok:
        msg = (
            "🔮 <b>ORÁCULO DEL DÍA — LOTO HONDURAS</b>\n"
            f"📅 {fecha_hn}\n\n"
            f"🌙 <i>{oraculo['presagio']}</i>\n\n"
            f"🔢 Números: <b>{' · '.join(str(n) for n in oraculo['numeros'])}</b>\n\n"
            f"💬 {oraculo['frase']}"
        )
        enviar_telegram(msg)
        print("📨 Notificación enviada a Telegram")

    print("=" * 60)
    return ok


if __name__ == "__main__":
    main()
