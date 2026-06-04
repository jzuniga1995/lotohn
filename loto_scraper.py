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
        'horas_hn': [11]
    },
    'tarde': {
        'horas_hn': [15]
    },
    'noche': {
        'horas_hn': [21]
    }
}

DIAS_SUPER_PREMIO = [2, 5]  # miércoles y sábado


def detectar_tanda():
    hora_hn = ahora_hn().hour

    for nombre, config in TANDAS.items():
        if hora_hn in config['horas_hn']:
            return nombre

    print(f"⏭️  Hora HN {hora_hn}:xx no corresponde a ninguna tanda. Nada que hacer.")
    return None


# ============================================
# SCRAPER — fuente: loto.hn
# ============================================

# Juegos sin tanda (resultado único, sin sufijo de hora)
JUEGOS_SIN_TANDA = {'super_premio', 'instacash', 'apostemos', 'bingo_con_todo', 'multi_x', 'ganagol'}

# Sufijo de hora por tanda
SUFIJO_TANDA = {
    'manana': '_11am',
    'tarde':  '_3pm',
    'noche':  '_9pm',
}

# Hora legible por tanda
HORA_TANDA = {
    'manana': '11:00 AM',
    'tarde':  '3:00 PM',
    'noche':  '9:00 PM',
}

# Nombres legibles por slug
NOMBRES_JUEGO = {
    'diaria':         'La Diaria',
    'super_premio':   'Super Premio',
    'juga3':          'Jugá 3',
    'premia2':        'Premia 2',
    'pega_3':         'Pega 3',
    'instacash':      'InstaCash',
    'apostemos':      'Apostemos',
    'bingo_con_todo': 'Bingo con Todo',
    'multi_x':        'Multi X',
    'ganagol':        'Ganagol',
}


class LotoHondurasScraper:

    BASE_URL = "https://loto.hn/?pag=body"

    # ----------------------------------------
    # ENTRADA PRINCIPAL
    # ----------------------------------------

    def obtener_resultados_tanda(self, nombre_tanda: str) -> dict:
        resultados = {}

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

                try:
                    page.wait_for_selector('.game-card', timeout=15000)
                except Exception as e:
                    print(f"⚠️  Timeout esperando .game-card: {e}")
                    browser.close()
                    return resultados

                time.sleep(2)

                cards = page.query_selector_all('.game-card')
                print(f"🃏 Tarjetas encontradas: {len(cards)}")

                for card in cards:
                    juego_key, nombre_juego = self._identificar_juego(card, nombre_tanda)
                    if not juego_key:
                        continue

                    # Super Premio solo miércoles y sábado
                    if juego_key == 'super_premio':
                        if ahora_hn().weekday() not in DIAS_SUPER_PREMIO:
                            print(f"⏭️  Super Premio omitido (no es miércoles ni sábado)")
                            continue
                        print(f"🏆 Super Premio incluido")

                    print(f"📊 Procesando {juego_key}...")
                    numeros_raw = self._extraer_balls(card)
                    resultado   = self._resultado_vacio(juego_key, nombre_juego, nombre_tanda)

                    if numeros_raw:
                        ganador, adicionales, individuales = self._formatear_numeros(numeros_raw, juego_key)
                        if ganador:
                            resultado['numero_ganador']       = ganador
                            resultado['numeros_adicionales']  = adicionales
                            resultado['numeros_individuales'] = individuales
                            resultado['estado']               = 'completado'
                            print(f"   ✅ Ganador: {ganador} | Todos: {adicionales}")
                        else:
                            resultado['estado'] = 'pendiente'
                            print(f"   ⏳ Sin resultado aún")
                    else:
                        resultado['estado'] = 'pendiente'
                        print(f"   ⏳ Sin números en la tarjeta")

                    resultados[juego_key] = resultado

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
    # IDENTIFICAR JUEGO — dinámico por href "CONOCE MÁS"
    # ----------------------------------------

    def _identificar_juego(self, card, nombre_tanda: str):
        """
        Lee el href del botón 'CONOCE MÁS' para extraer ?pag=<slug>.
        Juegos con tanda reciben sufijo (_11am / _3pm / _9pm).
        Juegos sin tanda usan el slug directo.
        Retorna (juego_key, nombre_juego) o (None, None).
        """
        slug = None
        for enlace in card.query_selector_all('a'):
            href = (enlace.get_attribute('href') or '')
            if 'pag=' in href:
                slug = href.split('pag=')[-1].strip().rstrip('/').replace('-', '_').lower()
                break

        if not slug:
            return None, None

        nombre_base = NOMBRES_JUEGO.get(slug, slug.replace('_', ' ').title())

        if slug in JUEGOS_SIN_TANDA:
            return slug, nombre_base

        sufijo       = SUFIJO_TANDA.get(nombre_tanda, '')
        hora         = HORA_TANDA.get(nombre_tanda, '')
        juego_key    = f"{slug}{sufijo}"
        nombre_juego = f"{nombre_base} {hora}".strip()
        return juego_key, nombre_juego

    # ----------------------------------------
    # EXTRAER NÚMEROS DE LAS BOLAS
    # ----------------------------------------

    def _extraer_balls(self, card) -> list:
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

    def _formatear_numeros(self, numeros: list, juego_key: str):
        """Retorna (numero_ganador, numeros_adicionales, numeros_individuales)."""
        if not numeros:
            return None, [], []

        if 'juga3' in juego_key:
            # 3 dígitos → unir "031"
            ganador = ''.join(numeros)
            return ganador, [ganador], list(numeros)

        elif 'premia2' in juego_key:
            # 4 dígitos agrupados en pares: "65" y "31"
            if len(numeros) >= 4:
                n1 = numeros[0] + numeros[1]
                n2 = numeros[2] + numeros[3]
                return n1, [n1, n2], numeros
            elif len(numeros) == 2:
                return numeros[0], numeros, numeros
            ganador = ''.join(numeros)
            return ganador, [ganador], numeros

        elif 'diaria' in juego_key:
            # 3 números individuales 0-9
            ganador = ' '.join(numeros)
            return ganador, list(numeros), list(numeros)

        else:
            # pega_3, super_premio, bingo_con_todo, multi_x, etc.
            return numeros[0], list(numeros), list(numeros)

    # ----------------------------------------
    # HELPERS
    # ----------------------------------------

    def _resultado_vacio(self, juego_key: str, nombre_juego: str, nombre_tanda: str) -> dict:
        hora = HORA_TANDA.get(nombre_tanda) if juego_key not in JUEGOS_SIN_TANDA else None
        return {
            'juego':                juego_key,
            'nombre_juego':         nombre_juego,
            'fecha_consulta':       datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'fecha_sorteo':         fecha_hn_ddmm(),
            'hora_sorteo':          hora,
            'numero_ganador':       None,
            'numeros_individuales': [],
            'numeros_adicionales':  [],
            'serie':                None,
            'folio':                None,
            'estado':               None,
            'logo_url':             f'/logos/{juego_key}.png',
            'extras':               {}
        }

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
                if key in historial[fecha_hn]:
                    print(f"   📌 Historial: ya existe {key}")
                    continue
                # Solo guardamos los números — la key ya codifica juego + tanda
                historial[fecha_hn][key] = data['numeros_adicionales']

            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(historial, f, ensure_ascii=False, separators=(',', ':'))

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
        """Imprime todos los juegos detectados en loto.hn con sus números."""
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
                key, nombre = self._identificar_juego(card, 'manana')
                balls = self._extraer_balls(card)
                print(f"[{i}] key={key} | nombre={nombre} | balls={balls}")
            browser.close()


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    scraper = LotoHondurasScraper()

    print("🎲 LOTO HONDURAS SCRAPER — fuente: loto.hn")
    print("=" * 60)

    nombre_tanda = detectar_tanda()

    if not nombre_tanda:
        print("✅ Sin tanda que procesar. Finalizando.")
        exit(0)

    print(f"⏰ Hora HN: {fecha_hn_str('%H:%M')} | Tanda: {nombre_tanda.upper()}")
    print("=" * 60)

    resultados_tanda = scraper.obtener_resultados_tanda(nombre_tanda)
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
