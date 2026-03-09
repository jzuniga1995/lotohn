import json
import time
import re
import os
import requests
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright


# ============================================
# CONFIGURACIÓN
# ============================================

MAX_REINTENTOS     = 3
ESPERA_REINTENTO   = 5
PAUSA_ENTRE_JUEGOS = 2

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

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
        f"🕐 {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print(f"   📨 Enviando alerta de error a Telegram...")
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
        f"🕐 {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')} UTC",
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


# Tandas por hora UTC
# 17:xx UTC = 11:00 AM Honduras
# 21:xx UTC = 3:00 PM Honduras
# 03:xx UTC = 9:00 PM Honduras (día siguiente en UTC)

TANDAS = {
    'manana': {
        'juegos': ['juga3_11am', 'premia2_10am', 'pega3_10am', 'la_diaria_10am'],
        'horas_utc': [17]
    },
    'tarde': {
        'juegos': ['juga3_3pm', 'premia2_2pm', 'pega3_2pm', 'la_diaria_2pm'],
        'horas_utc': [21]
    },
    'noche': {
        'juegos': ['juga3_9pm', 'premia2_9pm', 'pega3_9pm', 'la_diaria_9pm'],
        'horas_utc': [3]
    }
}

# Super Premio solo miércoles (2) y sábado (5)
DIAS_SUPER_PREMIO = [2, 5]


def detectar_tanda():
    """Detecta qué tanda correr según la hora UTC actual."""
    hora_utc = datetime.now(timezone.utc).replace(tzinfo=None).hour

    for nombre, config in TANDAS.items():
        if hora_utc in config['horas_utc']:
            juegos = list(config['juegos'])

            # Agregar super_premio solo si es noche y día corresponde
            if nombre == 'noche':
                dia_hn = (datetime.now(timezone.utc) - timedelta(hours=6)).weekday()
                if dia_hn in DIAS_SUPER_PREMIO:
                    juegos.append('super_premio')
                    print(f"🏆 Super Premio incluido (día {dia_hn})")
                else:
                    print(f"⏭️  Super Premio omitido (no es miércoles ni sábado)")

            return nombre, juegos

    # ✅ FIX: hora no programada (ej. 12 UTC = 6am Honduras) → salir sin correr nada
    print(f"⏭️  Hora UTC {hora_utc} no corresponde a ninguna tanda. Nada que hacer.")
    return None, []


# ============================================
# SCRAPER
# ============================================

class LotoHondurasScraper:

    def __init__(self):
        self.base_url = "https://loteriasdehonduras.com"

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
            'super_premio':   'super_premio.png'
        }

        self.juegos = {
            'juga3_11am':     '/loto-hn/juga-3-11am',
            'juga3_3pm':      '/loto-hn/juga-3-3pm',
            'juga3_9pm':      '/loto-hn/juga-3-9pm',
            'premia2_10am':   '/loto-hn/premia2-10am',
            'premia2_2pm':    '/loto-hn/premia2-2pm',
            'premia2_9pm':    '/loto-hn/premia2-9pm',
            'pega3_10am':     '/loto-hn/pega-3-10am',
            'pega3_2pm':      '/loto-hn/pega-3-2pm',
            'pega3_9pm':      '/loto-hn/pega-3-9pm',
            'la_diaria_10am': '/loto-hn/la-diaria-10am',
            'la_diaria_2pm':  '/loto-hn/la-diaria-2pm',
            'la_diaria_9pm':  '/loto-hn/la-diaria-9pm',
            'super_premio':   '/loto-hn/loto-super-premio'
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
            'super_premio':   None
        }

        self.limite_numeros = {
            'juga3':   1,
            'premia2': 2,
            'pega3':   3,
            'diaria':  3,
            'super':   6
        }

        self.timeout_especial = {
            'juga3_11am': 60000,
            'juga3_3pm':  60000,
            'juga3_9pm':  60000,
        }

    # ============================================
    # NAVEGACIÓN CON REINTENTOS
    # ============================================

    def _navegar_con_reintentos(self, page, url, juego_key):
        timeout = self.timeout_especial.get(juego_key, 30000)
        ultimo_error = None

        for intento in range(MAX_REINTENTOS):
            try:
                page.goto(url, wait_until='networkidle', timeout=timeout)
                return True
            except Exception as e:
                ultimo_error = e
                if intento < MAX_REINTENTOS - 1:
                    print(f"   🔄 Reintento {intento + 2}/{MAX_REINTENTOS} ({juego_key})...")
                    time.sleep(ESPERA_REINTENTO)

        raise ultimo_error

    # ============================================
    # OBTENER RESULTADOS DE LA TANDA
    # ============================================

    def obtener_resultados_tanda(self, juegos_tanda):
        resultados = {}
        fecha_hoy  = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d')

        print(f"🔍 Fecha UTC: {fecha_hoy}")
        print("=" * 60)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                               '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()

                for juego_key in juegos_tanda:
                    print(f"📊 Scrapeando {juego_key}...")
                    resultado = self._scrapear_juego(page, juego_key, fecha_hoy)
                    resultados[juego_key] = resultado
                    time.sleep(PAUSA_ENTRE_JUEGOS)

                browser.close()

        except Exception as e:
            print(f"❌ Error iniciando Playwright/browser: {e}")

        print("=" * 60)
        print(f"✨ Scrapeados: {len(resultados)}")
        return resultados

    # ============================================
    # SCRAPEAR UN JUEGO — solo busca hoy, sin fallback ayer
    # ============================================

    def _scrapear_juego(self, page, juego_key, fecha):
        url       = f"{self.base_url}{self.juegos[juego_key]}?date={fecha}"
        resultado = self._resultado_vacio(juego_key)

        try:
            self._navegar_con_reintentos(page, url, juego_key)

            try:
                page.wait_for_selector('[class*="score-shape"]', timeout=10000)
            except Exception as e:
                print(f"   ⚠️  Timeout esperando score-shape: {e}")
                return resultado

            numeros = self._extraer_numeros(page, juego_key)

            if numeros:
                resultado['numero_ganador']       = numeros[0]
                resultado['numeros_adicionales']  = numeros
                resultado['numeros_individuales'] = list(numeros[0]) if 'juga3' in juego_key and numeros[0].isdigit() else numeros
                resultado['estado'] = 'completado'
                print(f"   ✅ Números: {numeros}")
            else:
                resultado['estado'] = 'pendiente'
                print(f"   ⏳ Sin resultado aún")

            fecha_sorteo = self._extraer_fecha(page)
            if fecha_sorteo:
                resultado['fecha_sorteo'] = fecha_sorteo
                print(f"   📅 Fecha: {fecha_sorteo}")

            resultado['hora_sorteo'] = self.horas_por_juego.get(juego_key)

        except Exception as e:
            print(f"   ❌ Error: {e}")

        return resultado

    # ============================================
    # EXTRACTORES
    # ============================================

    def _extraer_numeros(self, page, juego_key):
        numeros = []
        es_diaria = 'diaria' in juego_key

        try:
            selector = '[class*="score-shape"]:not([class*="past-score-ball"])'
            elementos = page.query_selector_all(selector)

            limite = 3
            for tipo, lim in self.limite_numeros.items():
                if tipo in juego_key:
                    limite = lim
                    break

            for elem in elementos:
                texto = ''

                inner_div = elem.query_selector('span > div')
                if inner_div:
                    texto = inner_div.inner_text().strip()

                if not texto:
                    span = elem.query_selector('span')
                    if span:
                        texto = span.inner_text().strip()

                if not texto:
                    texto = elem.inner_text().strip()

                texto = texto.strip()
                if not texto or texto in ['-', '?', '']:
                    continue

                if not es_diaria and not texto.replace(' ', '').isdigit():
                    continue

                partes = texto.split(' ', 1)
                if len(partes) == 2 and partes[0].isdigit():
                    numeros.extend(partes)
                else:
                    numeros.append(texto)

                if len(numeros) >= limite:
                    break

        except Exception as e:
            print(f"   ❌ Error extrayendo números: {e}")

        return numeros

    def _extraer_fecha(self, page):
        try:
            texto = page.inner_text('body')
            match = re.search(r'\b(\d{2}-\d{2})\b', texto)
            if match:
                return match.group(1)
        except:
            pass
        hoy = datetime.now(timezone.utc).replace(tzinfo=None)
        return f"{str(hoy.day).zfill(2)}-{str(hoy.month).zfill(2)}"

    # ============================================
    # HELPERS
    # ============================================

    def _resultado_vacio(self, juego_key):
        nombre_logo = self.logos_estaticos.get(juego_key, f'{juego_key}.png')
        return {
            'juego': juego_key,
            'nombre_juego': self._obtener_nombre_juego(juego_key),
            'fecha_consulta': datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S'),
            'fecha_sorteo': None,
            'hora_sorteo': self.horas_por_juego.get(juego_key),
            'numero_ganador': None,
            'numeros_individuales': [],
            'numeros_adicionales': [],
            'serie': None,
            'folio': None,
            'estado': None,
            'logo_url': f'/logos/{nombre_logo}',
            'extras': {}
        }

    def _obtener_nombre_juego(self, juego_key):
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
            'super_premio':   'Super Premio'
        }
        return nombres.get(juego_key, juego_key)

    # ============================================
    # GUARDAR JSON HOY
    # ============================================

    def guardar_resultados_json(self, resultados_tanda, archivo='resultados_hoy.json'):
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
                'fecha_actualizacion': datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S'),
                'total_sorteos': len(existente),
                'sorteos': existente
            }
            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(salida, f, ensure_ascii=False, indent=2)
            print(f"💾 Guardado: {archivo}")
            return True
        except Exception as e:
            print(f"❌ Error al guardar: {e}")
            return False

    # ============================================
    # GUARDAR HISTORIAL
    # ============================================

    def guardar_historial_json(self, resultados_tanda, archivo='historial.json'):
        try:
            historial = {}
            if os.path.exists(archivo):
                with open(archivo, 'r', encoding='utf-8') as f:
                    historial = json.load(f)

            fecha_hn = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=6)).strftime('%Y-%m-%d')

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

    # ============================================
    # DEBUG
    # ============================================

    def debug_html(self, juego_key):
        fecha_hoy = datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d')
        url = f"{self.base_url}{self.juegos[juego_key]}?date={fecha_hoy}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle', timeout=60000)
            try:
                page.wait_for_selector('[class*="score-shape"]', timeout=10000)
            except:
                print("⚠️ No apareció ningún score-shape")

            print("=== ELEMENTOS CON 'score' ===")
            elementos = page.query_selector_all('[class*="score"]')
            for elem in elementos:
                print(f"CLASS: {elem.get_attribute('class')} | TEXT: {elem.inner_text()[:60]}")

            print("\n=== HTML p-card-content ===")
            bloque = page.query_selector('.p-card-content')
            if bloque:
                print(bloque.inner_html()[:2000])
            browser.close()


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    scraper = LotoHondurasScraper()

    print("🎲 LOTO HONDURAS SCRAPER")
    print("=" * 60)

    nombre_tanda, juegos_tanda = detectar_tanda()

    # ✅ FIX: salir limpio si no es hora de ninguna tanda (ej. 6am Honduras = 12 UTC)
    if not juegos_tanda:
        print("✅ Sin tanda que procesar. Finalizando.")
        exit(0)

    print(f"⏰ Hora UTC: {datetime.now(timezone.utc).replace(tzinfo=None).strftime('%H:%M')} | Tanda: {nombre_tanda.upper()}")
    print(f"🎯 Juegos: {juegos_tanda}")
    print("=" * 60)

    resultados_tanda = scraper.obtener_resultados_tanda(juegos_tanda)
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



