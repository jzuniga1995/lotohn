import json
import time
import os
import requests
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright


# ============================================
# CONFIGURACIÓN
# ============================================

MAX_REINTENTOS     = 3
ESPERA_REINTENTO   = 5

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ============================================
# HORA HONDURAS — UTC-6 FIJO, NUNCA CAMBIA DST
# ============================================

HN_TZ = timezone(timedelta(hours=-6))

def ahora_hn() -> datetime:
    return datetime.now(HN_TZ)

def fecha_hn_str(fmt='%Y-%m-%d') -> str:
    return ahora_hn().strftime(fmt)

def fecha_hn_ddmm() -> str:
    hn = ahora_hn()
    return f"{str(hn.day).zfill(2)}-{str(hn.month).zfill(2)}"


# ============================================
# FUNCIONES TELEGRAM
# ============================================

def enviar_telegram(mensaje: str, silencioso: bool = False) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Telegram no configurado (faltan variables de entorno)")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_notification": silencioso
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            print(f"⚠️  Telegram HTTP {resp.status_code}: {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"⚠️  Error enviando a Telegram: {e}")
        return False


def alerta_error_scraping(juego_key: str, motivo: str):
    msg = (
        "🚨 <b>SCRAPER — ERROR</b>\n"
        f"🎲 Juego: <code>{juego_key}</code>\n"
        f"❌ Motivo: {motivo}\n"
        f"🕐 {fecha_hn_str('%Y-%m-%d %H:%M:%S')} HN"
    )
    print("   📨 Enviando alerta de error a Telegram...")
    enviar_telegram(msg)


def resumen_tanda_telegram(nombre_tanda: str, resultados: dict):
    bloque_ok, bloque_pendiente = [], []

    for key, data in resultados.items():
        nombre = data.get('nombre_juego', key)
        if data.get('numero_ganador'):
            bloque_ok.append(f"  ✅ <b>{nombre}</b>: {data['numero_ganador']}")
        else:
            bloque_pendiente.append(f"  ⏳ <b>{nombre}</b>")

    lineas = [
        f"📊 <b>LOTO HONDURAS — TANDA {nombre_tanda.upper()}</b>",
        f"🕐 {fecha_hn_str('%Y-%m-%d %H:%M:%S')} HN",
    ]
    if bloque_ok:
        lineas += ["", f"🟢 <b>COMPLETADOS ({len(bloque_ok)})</b>"] + bloque_ok
    if bloque_pendiente:
        lineas += ["", f"⏳ <b>PENDIENTES ({len(bloque_pendiente)})</b>"] + bloque_pendiente

    print("📨 Enviando resumen a Telegram...")
    enviar_telegram("\n".join(lineas), silencioso=True)


# ============================================
# PURGAR CACHÉ CLOUDFLARE
# ============================================

def purgar_cache_cloudflare():
    CF_ZONE_ID = os.environ.get("CF_ZONE_ID", "")
    CF_TOKEN   = os.environ.get("CF_TOKEN", "")
    if not CF_ZONE_ID or not CF_TOKEN:
        print("⚠️  Cloudflare no configurado (faltan CF_ZONE_ID o CF_TOKEN)")
        return
    try:
        resp = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/purge_cache",
            headers={"Authorization": f"Bearer {CF_TOKEN}", "Content-Type": "application/json"},
            json={"purge_everything": True},
            timeout=10
        )
        if resp.ok:
            print("✅ Caché de Cloudflare purgado correctamente")
        else:
            print(f"⚠️  Error purgando caché: {resp.text}")
    except Exception as e:
        print(f"⚠️  Error al purgar caché: {e}")


# ============================================
# TANDAS
# ============================================

TANDAS = {
    'manana': {
        'juegos':   ['juga3_11am', 'premia2_10am', 'pega3_10am', 'la_diaria_10am'],
        'horas_hn': [11]
    },
    'tarde': {
        'juegos':   ['juga3_3pm', 'premia2_2pm', 'pega3_2pm', 'la_diaria_2pm'],
        'horas_hn': [15]
    },
    'noche': {
        'juegos':   ['juga3_9pm', 'premia2_9pm', 'pega3_9pm', 'la_diaria_9pm'],
        'horas_hn': [21]
    }
}

# Super Premio solo miércoles (2) y sábado (5)
DIAS_SUPER_PREMIO = [2, 5]


def detectar_tanda():
    hora_hn = ahora_hn().hour

    for nombre, config in TANDAS.items():
        if hora_hn in config['horas_hn']:
            juegos = list(config['juegos'])

            if nombre == 'noche':
                dia_hn = ahora_hn().weekday()
                if dia_hn in DIAS_SUPER_PREMIO:
                    juegos.append('super_premio')
                    print(f"🏆 Super Premio incluido (día {dia_hn})")
                else:
                    print(f"⏭️  Super Premio omitido (no es miércoles ni sábado)")

            return nombre, juegos

    print(f"⏭️  Hora HN {hora_hn}:xx no corresponde a ninguna tanda. Nada que hacer.")
    return None, []


# ============================================
# SCRAPER — fuente: loto.hn
# ============================================

# Palabras clave en el src de la imagen → tipo de juego interno
GAME_IMG_MAP = {
    'LA DIARIA':   'diaria',
    'SUPERPREMIO': 'super',
    'JUGA TRES':   'juga3',
    'PREMIA2':     'premia2',
    'PEGA3':       'pega3',
}

# tipo → juego_key por tanda
TIPO_A_KEY = {
    'manana': {
        'juga3':   'juga3_11am',
        'premia2': 'premia2_10am',
        'pega3':   'pega3_10am',
        'diaria':  'la_diaria_10am',
    },
    'tarde': {
        'juga3':   'juga3_3pm',
        'premia2': 'premia2_2pm',
        'pega3':   'pega3_2pm',
        'diaria':  'la_diaria_2pm',
    },
    'noche': {
        'juga3':   'juga3_9pm',
        'premia2': 'premia2_9pm',
        'pega3':   'pega3_9pm',
        'diaria':  'la_diaria_9pm',
        'super':   'super_premio',
    },
}


class LotoHondurasScraper:

    BASE_URL = "https://loto.hn/?pag=body"

    def __init__(self):
        self.logos_estaticos = {
            'juga3_11am':     'juga3.png',
            'juga3_3pm':      'juga3.png',
            'juga3_9pm':      'juga3.png',
            'premia2_10am':   'premia2.png',
            'premia2_2pm':    'premia2.png',
            'premia2_9pm':    'premia2.png',
            'pega3_10am':     'pega3.png',
            'pega3_2pm':      'pega3.png',
            'pega3_9pm':      'pega3.png',
            'la_diaria_10am': 'la_diaria.png',
            'la_diaria_2pm':  'la_diaria.png',
            'la_diaria_9pm':  'la_diaria.png',
            'super_premio':   'super_premio.png',
        }

        self.horas_por_juego = {
            'juga3_11am':     '11:00 AM',
            'juga3_3pm':      '3:00 PM',
            'juga3_9pm':      '9:00 PM',
            'premia2_10am':   '11:00 AM',
            'premia2_2pm':    '3:00 PM',
            'premia2_9pm':    '9:00 PM',
            'pega3_10am':     '11:00 AM',
            'pega3_2pm':      '3:00 PM',
            'pega3_9pm':      '9:00 PM',
            'la_diaria_10am': '11:00 AM',
            'la_diaria_2pm':  '3:00 PM',
            'la_diaria_9pm':  '9:00 PM',
            'super_premio':   None,
        }

    # ----------------------------------------
    # ENTRADA PRINCIPAL
    # ----------------------------------------

    def obtener_resultados_tanda(self, juegos_tanda: list, nombre_tanda: str) -> dict:
        # Inicializar con resultados vacíos
        resultados = {key: self._resultado_vacio(key) for key in juegos_tanda}

        print(f"🌐 Cargando {self.BASE_URL} ...")
        print("=" * 60)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                               '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()

                self._navegar_con_reintentos(page)

                # Esperar a que aparezcan las tarjetas de juegos
                try:
                    page.wait_for_selector('.game-card', timeout=15000)
                except Exception as e:
                    print(f"⚠️  Timeout esperando .game-card: {e}")
                    browser.close()
                    return resultados

                # Pequeña pausa extra para JS dinámico
                time.sleep(2)

                cards = page.query_selector_all('.game-card')
                print(f"🃏 Tarjetas encontradas: {len(cards)}")

                mapa_tanda = TIPO_A_KEY.get(nombre_tanda, {})

                for card in cards:
                    juego_tipo = self._identificar_juego(card)
                    if not juego_tipo:
                        continue

                    juego_key = mapa_tanda.get(juego_tipo)
                    if not juego_key or juego_key not in resultados:
                        continue  # este juego no pertenece a la tanda actual

                    print(f"📊 Procesando {juego_key} (tipo={juego_tipo})...")
                    numeros_raw = self._extraer_balls(card)

                    if not numeros_raw:
                        print(f"   ⏳ Sin números en la tarjeta")
                        continue

                    ganador, adicionales, individuales = self._formatear_numeros(numeros_raw, juego_tipo)

                    if ganador:
                        resultados[juego_key]['numero_ganador']       = ganador
                        resultados[juego_key]['numeros_adicionales']  = adicionales
                        resultados[juego_key]['numeros_individuales'] = individuales
                        resultados[juego_key]['estado']               = 'completado'
                        print(f"   ✅ Ganador: {ganador} | Todos: {adicionales}")
                    else:
                        resultados[juego_key]['estado'] = 'pendiente'
                        print(f"   ⏳ Sin resultado aún")

                    resultados[juego_key]['fecha_sorteo'] = fecha_hn_ddmm()
                    resultados[juego_key]['hora_sorteo']  = self.horas_por_juego.get(juego_key)

                browser.close()

        except Exception as e:
            print(f"❌ Error iniciando Playwright/browser: {e}")

        print("=" * 60)
        completados = sum(1 for r in resultados.values() if r.get('estado') == 'completado')
        print(f"✨ Completados: {completados}/{len(resultados)}")
        return resultados

    # ----------------------------------------
    # NAVEGACIÓN CON REINTENTOS
    # ----------------------------------------

    def _navegar_con_reintentos(self, page):
        ultimo_error = None
        for intento in range(MAX_REINTENTOS):
            try:
                page.goto(self.BASE_URL, wait_until='networkidle', timeout=60000)
                return
            except Exception as e:
                ultimo_error = e
                if intento < MAX_REINTENTOS - 1:
                    print(f"   🔄 Reintento {intento + 2}/{MAX_REINTENTOS}...")
                    time.sleep(ESPERA_REINTENTO)
        raise ultimo_error

    # ----------------------------------------
    # IDENTIFICAR JUEGO POR IMAGEN
    # ----------------------------------------

    def _identificar_juego(self, card) -> str | None:
        img = card.query_selector('img')
        if not img:
            return None
        src = (img.get_attribute('src') or '').upper()
        for keyword, tipo in GAME_IMG_MAP.items():
            if keyword in src:
                return tipo
        return None

    # ----------------------------------------
    # EXTRAER NÚMEROS DE LAS BOLAS
    # ----------------------------------------

    def _extraer_balls(self, card) -> list[str]:
        balls = card.query_selector_all('.ball')
        numeros = []
        for ball in balls:
            clases = ball.get_attribute('class') or ''
            if 'mas1' in clases:
                continue  # bola multiplicadora, no es número
            texto = ball.inner_text().strip()
            if texto and texto not in ['-', '?', '']:
                numeros.append(texto)
        return numeros

    # ----------------------------------------
    # FORMATEAR NÚMEROS SEGÚN EL TIPO DE JUEGO
    # ----------------------------------------

    def _formatear_numeros(self, numeros: list[str], juego_tipo: str):
        """Retorna (numero_ganador, numeros_adicionales, numeros_individuales)."""
        if not numeros:
            return None, [], []

        if juego_tipo == 'juga3':
            # 3 dígitos individuales → unir en un solo string "031"
            ganador = ''.join(numeros)
            return ganador, [ganador], list(numeros)

        elif juego_tipo == 'premia2':
            # 4 dígitos: primeros 2 = número 1, últimos 2 = número 2
            if len(numeros) >= 4:
                n1 = numeros[0] + numeros[1]
                n2 = numeros[2] + numeros[3]
                return n1, [n1, n2], numeros
            elif len(numeros) == 2:
                return numeros[0], numeros, numeros
            ganador = ''.join(numeros)
            return ganador, [ganador], numeros

        elif juego_tipo == 'diaria':
            # 3 números individuales (0-9)
            ganador = ' '.join(numeros)
            return ganador, list(numeros), list(numeros)

        else:
            # pega3 (3 nums de 2 cifras), super (6 nums de 2 cifras)
            return numeros[0], list(numeros), list(numeros)

    # ----------------------------------------
    # HELPERS
    # ----------------------------------------

    def _resultado_vacio(self, juego_key: str) -> dict:
        nombre_logo = self.logos_estaticos.get(juego_key, f'{juego_key}.png')
        return {
            'juego':               juego_key,
            'nombre_juego':        self._obtener_nombre_juego(juego_key),
            'fecha_consulta':      datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'fecha_sorteo':        fecha_hn_ddmm(),
            'hora_sorteo':         self.horas_por_juego.get(juego_key),
            'numero_ganador':      None,
            'numeros_individuales': [],
            'numeros_adicionales': [],
            'serie':               None,
            'folio':               None,
            'estado':              None,
            'logo_url':            f'/logos/{nombre_logo}',
            'extras':              {}
        }

    def _obtener_nombre_juego(self, juego_key: str) -> str:
        nombres = {
            'juga3_11am':     'Jugá 3 11:00 AM',
            'juga3_3pm':      'Jugá 3 3:00 PM',
            'juga3_9pm':      'Jugá 3 9:00 PM',
            'premia2_10am':   'Premia 2 11:00 AM',
            'premia2_2pm':    'Premia 2 3:00 PM',
            'premia2_9pm':    'Premia 2 9:00 PM',
            'pega3_10am':     'Pega 3 11:00 AM',
            'pega3_2pm':      'Pega 3 3:00 PM',
            'pega3_9pm':      'Pega 3 9:00 PM',
            'la_diaria_10am': 'La Diaria 11:00 AM',
            'la_diaria_2pm':  'La Diaria 3:00 PM',
            'la_diaria_9pm':  'La Diaria 9:00 PM',
            'super_premio':   'Super Premio',
        }
        return nombres.get(juego_key, juego_key)

    # ----------------------------------------
    # GUARDAR JSON HOY
    # ----------------------------------------

    def guardar_resultados_json(self, resultados_tanda: dict, archivo='resultados_hoy.json') -> bool:
        try:
            existente = {}
            if os.path.exists(archivo):
                with open(archivo, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existente = data.get('sorteos', {})

            for key, nuevo in resultados_tanda.items():
                anterior = existente.get(key, {})
                if nuevo.get('numero_ganador') is None and anterior.get('numero_ganador') is not None:
                    print(f"   💾 Conservando dato previo de {key}: {anterior.get('numero_ganador')}")
                    existente[key] = anterior
                else:
                    existente[key] = nuevo

            salida = {
                'fecha_actualizacion': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                'total_sorteos':       len(existente),
                'sorteos':             existente
            }
            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(salida, f, ensure_ascii=False, indent=2)
            print(f"💾 Guardado: {archivo}")
            return True
        except Exception as e:
            print(f"❌ Error al guardar: {e}")
            return False

    # ----------------------------------------
    # GUARDAR HISTORIAL
    # ----------------------------------------

    def guardar_historial_json(self, resultados_tanda: dict, archivo='historial.json') -> bool:
        try:
            historial = {}
            if os.path.exists(archivo):
                with open(archivo, 'r', encoding='utf-8') as f:
                    historial = json.load(f)

            fecha_hn = fecha_hn_str('%Y-%m-%d')
            if fecha_hn not in historial:
                historial[fecha_hn] = {}

            for key, data in resultados_tanda.items():
                if data.get('estado') != 'completado':
                    continue
                if historial[fecha_hn].get(key, {}).get('estado') == 'completado':
                    print(f"   📌 Historial: ya existe completado de {key}")
                    continue
                historial[fecha_hn][key] = {
                    'nombre_juego':         data['nombre_juego'],
                    'hora_sorteo':          data['hora_sorteo'],
                    'fecha_sorteo':         data['fecha_sorteo'],
                    'numero_ganador':       data['numero_ganador'],
                    'numeros_adicionales':  data['numeros_adicionales'],
                    'numeros_individuales': data['numeros_individuales'],
                    'logo_url':             data['logo_url'],
                    'estado':               data['estado'],
                }

            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(historial, f, ensure_ascii=False, indent=2)

            total = len(historial.get(fecha_hn, {}))
            print(f"📚 Historial guardado: {archivo} | {fecha_hn}: {total} sorteos")
            return True
        except Exception as e:
            print(f"❌ Error al guardar historial: {e}")
            return False

    # ----------------------------------------
    # DEBUG
    # ----------------------------------------

    def debug_estructura(self):
        """Imprime la estructura de las tarjetas encontradas en loto.hn."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            page.goto(self.BASE_URL, wait_until='networkidle', timeout=60000)
            time.sleep(3)

            cards = page.query_selector_all('.game-card')
            print(f"=== {len(cards)} tarjetas encontradas ===")
            for i, card in enumerate(cards):
                tipo = self._identificar_juego(card)
                balls = self._extraer_balls(card)
                img = card.query_selector('img')
                src = img.get_attribute('src') if img else 'N/A'
                print(f"[{i}] tipo={tipo} | src={src} | balls={balls}")
            browser.close()


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    scraper = LotoHondurasScraper()

    print("🎲 LOTO HONDURAS SCRAPER — fuente: loto.hn")
    print("=" * 60)

    nombre_tanda, juegos_tanda = detectar_tanda()

    if not juegos_tanda:
        print("✅ Sin tanda que procesar. Finalizando.")
        exit(0)

    print(f"⏰ Hora HN: {fecha_hn_str('%H:%M')} | Tanda: {nombre_tanda.upper()}")
    print(f"🎯 Juegos: {juegos_tanda}")
    print("=" * 60)

    resultados_tanda = scraper.obtener_resultados_tanda(juegos_tanda, nombre_tanda)
    scraper.guardar_resultados_json(resultados_tanda, 'resultados_hoy.json')
    scraper.guardar_historial_json(resultados_tanda, 'historial.json')
    purgar_cache_cloudflare()
    resumen_tanda_telegram(nombre_tanda, resultados_tanda)

    print("\n" + "=" * 60)
    print("📊 RESUMEN:")
    print("=" * 60)
    for key, data in resultados_tanda.items():
        estado = data.get('estado', '?')
        if data.get('numero_ganador'):
            print(f"✅ [{estado}] {data['nombre_juego']}: {data['numero_ganador']} | {data['fecha_sorteo']} | {data['hora_sorteo']}")
        else:
            print(f"⏳ {data['nombre_juego']}: Pendiente")
    print("=" * 60)
