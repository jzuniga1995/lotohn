import json
import re
import time
import os
import requests
from datetime import date, datetime, timedelta, timezone
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


def alerta_error_scraping(motivo: str):
    msg = (
        "🚨 <b>SCRAPER — ERROR</b>\n"
        f"❌ Motivo: {motivo}\n"
        f"🕐 {fecha_hn_str('%Y-%m-%d %H:%M:%S')} HN"
    )
    print("   📨 Enviando alerta de error a Telegram...")
    enviar_telegram(msg)


def resumen_telegram(resultados: dict):
    hoy = fecha_hn_str('%Y-%m-%d')
    bloque_hoy, bloque_previos = [], []

    for data in resultados.values():
        nombre = data.get('nombre_juego', data.get('juego'))
        linea  = f"  ✅ <b>{nombre}</b>: {data['numero_ganador']}"
        if data.get('fecha_historial') == hoy:
            bloque_hoy.append(linea)
        else:
            bloque_previos.append(f"{linea} <i>({data['fecha_sorteo']})</i>")

    lineas = [
        "📊 <b>LOTO HONDURAS — RESULTADOS</b>",
        f"🕐 {fecha_hn_str('%Y-%m-%d %H:%M:%S')} HN",
    ]
    if bloque_hoy:
        lineas += ["", f"🟢 <b>SORTEOS DE HOY ({len(bloque_hoy)})</b>"] + bloque_hoy
    if bloque_previos:
        lineas += ["", f"🕓 <b>SORTEOS ANTERIORES ({len(bloque_previos)})</b>"] + bloque_previos

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
# CATÁLOGO DE JUEGOS — fuente: loteriasdehonduras.com
# ============================================
#
# El slug es el que usa la fuente en sus enlaces (/loto-hn/<slug>/). La clave
# es la que ya consumen resultados_hoy.json, historial.json y el frontend, así
# que se conserva aunque el slug de la fuente se llame distinto.
#
# Juegos que ya no publica esta fuente y por eso se eliminan:
# Multi X, Bingo con Todo, InstaCash, Apostemos y Ganagol.

JUEGOS = {
    'juga-3-11am':       {'key': 'juga3_11am',   'nombre': 'Jugá 3 11:00 AM',    'hora': '11:00 AM'},
    'juga-3-3pm':        {'key': 'juga3_3pm',    'nombre': 'Jugá 3 3:00 PM',     'hora': '3:00 PM'},
    'juga-3-9pm':        {'key': 'juga3_9pm',    'nombre': 'Jugá 3 9:00 PM',     'hora': '9:00 PM'},
    'premia2-10am':      {'key': 'premia2_11am', 'nombre': 'Premia 2 11:00 AM',  'hora': '11:00 AM'},
    'premia2-2pm':       {'key': 'premia2_3pm',  'nombre': 'Premia 2 3:00 PM',   'hora': '3:00 PM'},
    'premia2-9pm':       {'key': 'premia2_9pm',  'nombre': 'Premia 2 9:00 PM',   'hora': '9:00 PM'},
    'pega-3-10am':       {'key': 'pega_3_11am',  'nombre': 'Pega 3 11:00 AM',    'hora': '11:00 AM'},
    'pega-3-2pm':        {'key': 'pega_3_3pm',   'nombre': 'Pega 3 3:00 PM',     'hora': '3:00 PM'},
    'pega-3-9pm':        {'key': 'pega_3_9pm',   'nombre': 'Pega 3 9:00 PM',     'hora': '9:00 PM'},
    'la-diaria-10am':    {'key': 'diaria_11am',  'nombre': 'La Diaria 11:00 AM', 'hora': '11:00 AM'},
    'la-diaria-2pm':     {'key': 'diaria_3pm',   'nombre': 'La Diaria 3:00 PM',  'hora': '3:00 PM'},
    'la-diaria-9pm':     {'key': 'diaria_9pm',   'nombre': 'La Diaria 9:00 PM',  'hora': '9:00 PM'},
    'loto-super-premio': {'key': 'super_premio', 'nombre': 'Super Premio',       'hora': '9:00 PM'},
}

# Claves válidas: todo lo que no esté aquí se borra de resultados_hoy.json
KEYS_VIGENTES = {j['key'] for j in JUEGOS.values()}

# La fuente fecha cada tarjeta en UTC. Un sorteo de las 9:00 PM HN ocurre a las
# 03:00 UTC del día siguiente, así que su tarjeta aparece con la fecha del día
# siguiente y hay que restarle un día para obtener la fecha real del sorteo.
DESFASE_UTC_DIAS = {'11:00 AM': 0, '3:00 PM': 0, '9:00 PM': 1}


class LotoHondurasScraper:

    BASE_URL = "https://loteriasdehonduras.com/"

    USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    # ----------------------------------------
    # ENTRADA PRINCIPAL
    # ----------------------------------------

    def obtener_resultados(self) -> dict:
        resultados = {}

        print(f"🌐 Cargando {self.BASE_URL} ...")
        print("=" * 60)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.USER_AGENT)
                page = context.new_page()

                self._navegar_con_reintentos(page)

                try:
                    page.wait_for_selector('a[href*="/loto-hn/"] .past-score-ball', timeout=30000)
                except Exception as e:
                    print(f"⚠️  Timeout esperando los resultados: {e}")
                    browser.close()
                    return resultados

                time.sleep(2)

                tarjetas = page.query_selector_all('a[href*="/loto-hn/"]')
                print(f"🃏 Enlaces de sorteo encontrados: {len(tarjetas)}")

                for tarjeta in tarjetas:
                    resultado = self._procesar_tarjeta(tarjeta)
                    if not resultado:
                        continue
                    key = resultado['juego']
                    if key in resultados:
                        continue  # la fuente repite el sorteo en el feed "En Directo"
                    resultados[key] = resultado
                    print(f"   ✅ {resultado['nombre_juego']}: {resultado['numero_ganador']} "
                          f"| {resultado['fecha_historial']} | todos: {resultado['numeros_adicionales']}")

                browser.close()

        except Exception as e:
            print(f"❌ Error iniciando Playwright/browser: {e}")

        print("=" * 60)
        print(f"✨ Sorteos obtenidos: {len(resultados)}/{len(JUEGOS)}")
        faltantes = KEYS_VIGENTES - set(resultados)
        if faltantes:
            print(f"⚠️  Sin resultado en la fuente: {', '.join(sorted(faltantes))}")
        return resultados

    # ----------------------------------------
    # NAVEGACIÓN CON REINTENTOS
    # ----------------------------------------

    def _navegar_con_reintentos(self, page):
        ultimo_error = None
        for intento in range(MAX_REINTENTOS):
            try:
                # 'networkidle' no sirve: la publicidad del sitio mantiene la red ocupada
                page.goto(self.BASE_URL, wait_until='domcontentloaded', timeout=60000)
                return
            except Exception as e:
                ultimo_error = e
                if intento < MAX_REINTENTOS - 1:
                    print(f"   🔄 Reintento {intento + 2}/{MAX_REINTENTOS}...")
                    time.sleep(ESPERA_REINTENTO)
        raise ultimo_error

    # ----------------------------------------
    # PROCESAR UNA TARJETA DE RESULTADO
    # ----------------------------------------

    def _procesar_tarjeta(self, tarjeta):
        """El enlace <a href="/loto-hn/<slug>/"> envuelve toda la tarjeta del
        sorteo: la etiqueta con la fecha, el nombre y las bolas."""
        href = tarjeta.get_attribute('href') or ''
        if '/estadisticas/' in href:
            return None  # tarjeta de "Números Calientes", no es un resultado

        slug = href.strip('/').split('/')[-1]
        juego = JUEGOS.get(slug)
        if not juego:
            return None

        fecha_etiqueta = self._extraer_fecha(tarjeta)
        if not fecha_etiqueta:
            return None  # sin fecha propia: es el feed "En Directo", ya viene en la grilla

        numeros = self._extraer_balls(tarjeta)
        if not numeros:
            return None

        fecha_sorteo = fecha_etiqueta - timedelta(days=DESFASE_UTC_DIAS[juego['hora']])
        ganador, adicionales, individuales, extras = self._formatear_numeros(numeros, juego['key'])
        if not ganador:
            return None

        return {
            'juego':                juego['key'],
            'nombre_juego':         juego['nombre'],
            'fecha_consulta':       datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'fecha_sorteo':         fecha_sorteo.strftime('%d-%m'),
            'fecha_historial':      fecha_sorteo.strftime('%Y-%m-%d'),
            'hora_sorteo':          juego['hora'],
            'numero_ganador':       ganador,
            'numeros_individuales': individuales,
            'numeros_adicionales':  adicionales,
            'serie':                None,
            'folio':                None,
            'estado':               'completado',
            'logo_url':             f"/logos/{juego['key']}.png",
            'extras':               extras
        }

    # ----------------------------------------
    # FECHA DE LA TARJETA (etiqueta "dd-mm")
    # ----------------------------------------

    def _extraer_fecha(self, tarjeta):
        etiqueta = tarjeta.query_selector('.bg-slate-500')
        texto = etiqueta.inner_text().strip() if etiqueta else (tarjeta.inner_text() or '')
        m = re.search(r'\b(\d{2})-(\d{2})\b', texto)
        if not m:
            return None

        dia, mes = int(m.group(1)), int(m.group(2))
        hoy = ahora_hn().date()

        # La etiqueta no trae año: se elige el que deje la fecha más cerca de hoy,
        # para que el cambio de año no mande los resultados a un año equivocado.
        candidatos = []
        for anio in (hoy.year - 1, hoy.year, hoy.year + 1):
            try:
                candidatos.append(date(anio, mes, dia))
            except ValueError:
                continue  # 29-02 en año no bisiesto
        if not candidatos:
            return None
        return min(candidatos, key=lambda d: abs((d - hoy).days))

    # ----------------------------------------
    # EXTRAER NÚMEROS DE LAS BOLAS
    # ----------------------------------------

    def _extraer_balls(self, tarjeta) -> list:
        numeros = []
        for ball in tarjeta.query_selector_all('.past-score-ball'):
            texto = re.sub(r'\s+', ' ', ball.inner_text()).strip()
            if texto and texto not in ['-', '?']:
                numeros.append(texto)
        return numeros

    # ----------------------------------------
    # FORMATEAR NÚMEROS SEGÚN EL TIPO DE JUEGO
    # ----------------------------------------

    def _formatear_numeros(self, numeros: list, juego_key: str):
        """Retorna (numero_ganador, numeros_adicionales, numeros_individuales, extras)."""
        if not numeros:
            return None, [], [], {}

        if juego_key.startswith('juga3'):
            # una sola bola con los 3 dígitos: "457"
            ganador = numeros[0]
            return ganador, [ganador], list(ganador), {}

        if juego_key.startswith('diaria'):
            # bolas: "87 León" (número + figura), multiplicador ("JG"/"2X") y adicional
            numero, _, figura = numeros[0].partition(' ')
            resto = numeros[1:]
            adicionales = [numero] + ([figura] if figura else []) + resto
            extras = {
                'figura':        figura or None,
                'multiplicador': resto[0] if len(resto) > 0 else None,
                'adicional':     resto[1] if len(resto) > 1 else None,
            }
            return numero, adicionales, [numero], extras

        # premia2, pega_3 y super_premio: una bola por número
        return numeros[0], list(numeros), list(numeros), {}

    # ----------------------------------------
    # GUARDAR JSON HOY
    # ----------------------------------------

    def guardar_resultados_json(self, resultados: dict, archivo='resultados_hoy.json') -> bool:
        try:
            existente = {}
            if os.path.exists(archivo):
                with open(archivo, 'r', encoding='utf-8') as f:
                    existente = json.load(f).get('sorteos', {})

            # Se descartan los juegos que la fuente ya no publica
            eliminados = [k for k in existente if k not in KEYS_VIGENTES]
            for k in eliminados:
                del existente[k]
            if eliminados:
                print(f"   🗑️  Juegos eliminados (ya no existen en la fuente): {', '.join(eliminados)}")

            for key, nuevo in resultados.items():
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

    def guardar_historial_json(self, resultados: dict, archivo='historial.json') -> bool:
        try:
            historial = {}
            if os.path.exists(archivo):
                with open(archivo, 'r', encoding='utf-8') as f:
                    historial = json.load(f)

            nuevos, corregidos = 0, 0
            for key, data in resultados.items():
                # Cada tarjeta trae su propia fecha, así que un sorteo viejo que
                # siga en pantalla se guarda en su día y no en el de hoy
                fecha_key = data['fecha_historial']
                if fecha_key not in historial:
                    historial[fecha_key] = {}
                anterior = historial[fecha_key].get(key)
                # Solo guardamos los números — la key ya codifica juego + tanda
                nums = data['numeros_adicionales']
                if anterior == nums:
                    continue
                if anterior is None:
                    nuevos += 1
                else:
                    # La fuente manda: si lo guardado no coincide, estaba mal
                    print(f"   ♻️  Corregido {fecha_key}/{key}: {anterior} → {nums}")
                    corregidos += 1
                historial[fecha_key][key] = nums

            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(historial, f, ensure_ascii=False, separators=(',', ':'))

            fecha_hn = fecha_hn_str('%Y-%m-%d')
            print(f"📚 Historial guardado: {archivo} | {nuevos} nuevos | {corregidos} corregidos "
                  f"| {fecha_hn}: {len(historial.get(fecha_hn, {}))} sorteos")
            return True
        except Exception as e:
            print(f"❌ Error al guardar historial: {e}")
            return False


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    scraper = LotoHondurasScraper()

    print("🎲 LOTO HONDURAS SCRAPER — fuente: loteriasdehonduras.com")
    print("=" * 60)
    print(f"⏰ Hora HN: {fecha_hn_str('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    resultados = scraper.obtener_resultados()

    if not resultados:
        alerta_error_scraping("No se obtuvo ningún resultado de loteriasdehonduras.com")
    else:
        scraper.guardar_resultados_json(resultados, 'resultados_hoy.json')
        scraper.guardar_historial_json(resultados, 'historial.json')
        purgar_cache_cloudflare()
        resumen_telegram(resultados)

    print("\n" + "=" * 60)
    print("📊 RESUMEN:")
    print("=" * 60)
    for key, data in sorted(resultados.items()):
        print(f"✅ {data['nombre_juego']}: {data['numero_ganador']} "
              f"| {data['fecha_sorteo']} | {data['hora_sorteo']}")
    print("=" * 60)
