import json
import re
import sys
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

# Minuto del día (hora HN) en que se juega cada tanda
HORA_EN_MINUTOS = {'11:00 AM': 11 * 60, '3:00 PM': 15 * 60, '9:00 PM': 21 * 60}

# Cuánto le damos a la fuente para publicar un sorteo antes de darlo por atrasado
MARGEN_PUBLICACION_MIN = 30

# Para fechar una tarjeta del feed "En Directo" el margen tiene que ser corto: si
# ya pasó la hora del sorteo y trae números, son los de ese sorteo. Con el margen
# de publicación la fecharíamos como la de ayer justo cuando acaba de salir.
MARGEN_SORTEO_EN_VIVO_MIN = 5

# Juegos que no se sortean todos los días (weekday(): lunes=0 … domingo=6)
DIAS_SORTEO = {'super_premio': {2, 5}}  # Super Premio: miércoles y sábado

# La etiqueta de la tarjeta no trae año. Si la fecha resultante queda más lejos
# que esto de hoy, es que el texto no era una fecha y hay que descartarla.
MAX_DIAS_FECHA = 15

# La fuente pinta el sorteo MÁS RECIENTE con .score-shape-* y los anteriores con
# .past-score-ball ("past" = pasados). Mirando solo los "past" se perdía justo el
# resultado recién salido: al llegar la hora del sorteo su tarjeta cambia de clase
# y se quedaba sin ninguna bola que leer, así que el juego seguía mostrando el de
# ayer hasta que ese resultado pasara a ser "anterior".
#
# El sufijo depende de la FORMA de la bola: -circle para los números de dos
# dígitos (Pega 3, Premia 2) y -square para los compuestos (Jugá 3 con sus tres
# dígitos, La Diaria con "59 Selva"). Por eso se busca por prefijo y no por las
# clases exactas: así también entran las formas que la fuente agregue después.
SELECTOR_TARJETA = 'a[href*="/loto-hn/"]'
SELECTOR_BOLAS = '[class*="score-shape"], .past-score-ball'
SELECTOR_ESPERA = ', '.join(f'{SELECTOR_TARJETA} {s.strip()}'
                            for s in SELECTOR_BOLAS.split(','))


def ultimo_sorteo_esperado(juego_key: str, hora: str, ahora: datetime = None,
                           margen: int = MARGEN_PUBLICACION_MIN) -> date:
    """Fecha del sorteo más reciente de este juego que ya debería estar publicado."""
    ahora = ahora or ahora_hn()
    dia = ahora.date()

    # Antes de la hora del sorteo (+ margen) el último es el del día previo
    if ahora.hour * 60 + ahora.minute < HORA_EN_MINUTOS[hora] + margen:
        dia -= timedelta(days=1)

    dias_validos = DIAS_SORTEO.get(juego_key)
    if dias_validos:
        while dia.weekday() not in dias_validos:
            dia -= timedelta(days=1)
    return dia


# Cuántos valores trae numeros_adicionales de cada familia. Sirve para detectar
# una tarjeta a medio pintar: la portada llegó a mostrar La Diaria como
# ['59', 'Selva', '2X'], sin el "Más 1" que su página sí listaba.
VALORES_ESPERADOS = {'juga3': 1, 'premia2': 2, 'pega_3': 3, 'diaria': 4, 'super_premio': 6}


def valores_esperados(juego_key: str) -> int:
    for prefijo, n in VALORES_ESPERADOS.items():
        if juego_key.startswith(prefijo):
            return n
    return 1


def esta_incompleto(resultado: dict, juego_key: str) -> bool:
    return len(resultado.get('numeros_adicionales') or []) < valores_esperados(juego_key)


def cargar_previos(archivo='resultados_hoy.json') -> dict:
    """key -> numeros_adicionales ya guardados, para no re-guardar lo mismo."""
    try:
        if not os.path.exists(archivo):
            return {}
        with open(archivo, 'r', encoding='utf-8') as f:
            sorteos = json.load(f).get('sorteos', {})
        return {k: v.get('numeros_adicionales') for k, v in sorteos.items()}
    except Exception as e:
        print(f"⚠️  No se pudieron leer los resultados previos: {e}")
        return {}


def sorteos_atrasados(guardados: dict) -> list:
    """Juegos cuyo último resultado guardado no es el sorteo que ya tocaba, o que
    quedó a medias. Retorna (nombre, motivo)."""
    problemas = []
    for juego in JUEGOS.values():
        guardado = guardados.get(juego['key']) or {}
        esperado = ultimo_sorteo_esperado(juego['key'], juego['hora']).strftime('%Y-%m-%d')
        actual = guardado.get('fecha_historial')
        if actual != esperado:
            problemas.append((juego['nombre'], f"guardado {actual} — se esperaba {esperado}"))
        elif esta_incompleto(guardado, juego['key']):
            problemas.append((juego['nombre'],
                              f"incompleto: {guardado.get('numeros_adicionales')} "
                              f"({valores_esperados(juego['key'])} valores esperados)"))
    return problemas


class LotoHondurasScraper:

    BASE_URL = "https://loteriasdehonduras.com/"

    USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    # ----------------------------------------
    # ENTRADA PRINCIPAL
    # ----------------------------------------

    def obtener_resultados(self, previos: dict = None) -> dict:
        resultados = {}
        descartes = []
        previos = previos or {}

        print(f"🌐 Cargando {self.BASE_URL} ...")
        print("=" * 60)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.USER_AGENT)
                page = context.new_page()

                self._navegar_con_reintentos(page)

                try:
                    page.wait_for_selector(SELECTOR_ESPERA, timeout=30000)
                except Exception as e:
                    print(f"⚠️  Timeout esperando los resultados: {e}")
                    browser.close()
                    return resultados

                self._esperar_tarjetas_estables(page)

                tarjetas = page.query_selector_all(SELECTOR_TARJETA)
                print(f"🃏 Enlaces de sorteo encontrados: {len(tarjetas)}")

                for tarjeta in tarjetas:
                    resultado, motivo = self._procesar_tarjeta(tarjeta, previos)
                    if motivo:
                        descartes.append(motivo)
                    if not resultado:
                        continue
                    key = resultado['juego']
                    # La fuente muestra el mismo juego varias veces (feed "En Directo"
                    # + grilla de resultados). Nos quedamos con el sorteo más nuevo,
                    # no con el que venga primero en el DOM.
                    if key in resultados and not self._es_mas_reciente(resultado, resultados[key]):
                        continue
                    resultados[key] = resultado
                    print(f"   ✅ {resultado['nombre_juego']}: {resultado['numero_ganador']} "
                          f"| {resultado['fecha_historial']} | {resultado['origen']} "
                          f"| todos: {resultado['numeros_adicionales']}")

                # Ojo: esto navega fuera de la portada, así que va después de
                # recorrer las tarjetas (sus handles quedan inválidos al salir)
                descartes += self._completar_desde_paginas(page, resultados)

                browser.close()

        except Exception as e:
            print(f"❌ Error iniciando Playwright/browser: {e}")

        if descartes:
            # Sin esto, una tarjeta rechazada desaparece en silencio y el juego se
            # queda con el resultado de ayer sin que nada lo indique
            print("-" * 60)
            print("🔍 Tarjetas descartadas:")
            for motivo in descartes:
                print(f"   · {motivo}")

        print("=" * 60)
        print(f"✨ Sorteos obtenidos: {len(resultados)}/{len(JUEGOS)}")
        faltantes = KEYS_VIGENTES - set(resultados)
        if faltantes:
            print(f"⚠️  Sin resultado en la fuente: {', '.join(sorted(faltantes))}")
        return resultados

    @staticmethod
    def _es_mas_reciente(nuevo: dict, actual: dict) -> bool:
        if nuevo['fecha_historial'] != actual['fecha_historial']:
            return nuevo['fecha_historial'] > actual['fecha_historial']
        # A igual fecha manda la tarjeta que trae fecha propia sobre la del feed
        return actual['origen'] == 'en_directo' and nuevo['origen'] == 'etiqueta'

    # ----------------------------------------
    # ESPERAR A QUE LA GRILLA TERMINE DE PINTARSE
    # ----------------------------------------

    def _esperar_tarjetas_estables(self, page, intentos: int = 8, pausa: float = 1.0,
                                   selector: str = SELECTOR_ESPERA):
        """La grilla se pinta por partes: esperamos a que deje de crecer para no
        leerla a medias y perder los sorteos que faltaban por renderizar."""
        previo = -1
        for _ in range(intentos):
            actual = len(page.query_selector_all(selector))
            if actual and actual == previo:
                return
            previo = actual
            time.sleep(pausa)

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

    def _procesar_tarjeta(self, tarjeta, previos: dict = None):
        """El enlace <a href="/loto-hn/<slug>/"> envuelve toda la tarjeta del
        sorteo: la etiqueta con la fecha, el nombre y las bolas.

        Retorna (resultado, motivo_descarte). El motivo solo se llena cuando la
        tarjeta era de un juego vigente pero no se pudo usar."""
        previos = previos or {}
        href = tarjeta.get_attribute('href') or ''
        if '/estadisticas/' in href:
            return None, None  # tarjeta de "Números Calientes", no es un resultado

        slug = href.strip('/').split('/')[-1]
        juego = JUEGOS.get(slug)
        if not juego:
            return None, None

        numeros = self._extraer_balls(tarjeta)
        if not numeros:
            return None, f"{slug}: tarjeta sin números (sorteo aún sin publicar)"

        fecha_etiqueta = self._extraer_fecha(tarjeta)
        if fecha_etiqueta:
            fecha_sorteo = fecha_etiqueta - timedelta(days=DESFASE_UTC_DIAS[juego['hora']])
            origen = 'etiqueta'
        else:
            # Tarjeta del feed "En Directo": no trae fecha propia. Es la primera
            # en mostrar el sorteo recién salido — la grilla tarda en refrescarse —
            # así que antes se descartaba y el juego se quedaba con el de ayer.
            # La fechamos con el calendario del juego.
            fecha_sorteo = ultimo_sorteo_esperado(juego['key'], juego['hora'],
                                                  margen=MARGEN_SORTEO_EN_VIVO_MIN)
            origen = 'en_directo'

        ganador, adicionales, individuales, extras = self._formatear_numeros(numeros, juego['key'])
        if not ganador:
            return None, f"{slug}: no se pudo interpretar {numeros}"

        if origen == 'en_directo' and previos.get(juego['key']) == adicionales:
            # El feed sigue mostrando el sorteo anterior: sin fecha propia no
            # podemos distinguirlo del nuevo, así que no lo re-fechamos como de hoy
            return None, f"{slug}: feed En Directo repite el resultado ya guardado"

        return self._armar_resultado(juego, fecha_sorteo, ganador, adicionales,
                                     individuales, extras, origen), None

    @staticmethod
    def _armar_resultado(juego, fecha_sorteo, ganador, adicionales, individuales,
                         extras, origen) -> dict:
        return {
            'origen':               origen,
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
    # RESPALDO: PÁGINA INTERNA DEL JUEGO
    # ----------------------------------------

    # La portada se atrasa de forma despareja: puede tener el sorteo de las 11 de
    # Pega 3 y Premia 2 y dejar vacías las tarjetas de Jugá 3 y La Diaria horas
    # después. La página del juego ya lo lista, así que se usa de respaldo.
    JS_FILAS = """() => {
        const filas = [];
        for (const et of document.querySelectorAll('.bg-slate-500')) {
            const fecha = et.textContent.trim();
            if (!/^\\d{2}-\\d{2}$/.test(fecha)) continue;
            let n = et;
            for (let i = 0; i < 6 && n.parentElement; i++) {
                n = n.parentElement;
                const bolas = n.querySelectorAll('[class*="score-shape"], .past-score-ball');
                // Una sola etiqueta de fecha = seguimos dentro de la misma fila.
                // Sin esto podríamos subir hasta la lista entera y mezclar sorteos.
                if (bolas.length && n.querySelectorAll('.bg-slate-500').length === 1) {
                    filas.push({fecha: fecha, nums: [...bolas]
                        .map(b => b.innerText.replace(/\\s+/g, ' ').trim())
                        .filter(t => t && t !== '-' && t !== '?')});
                    break;
                }
            }
        }
        return filas;
    }"""

    def _completar_desde_paginas(self, page, resultados: dict) -> list:
        # También se reintenta lo que salió a medias: una tarjeta a medio pintar
        # es tan inservible como una ausente si le falta la mitad de los números
        faltantes = [(slug, j) for slug, j in JUEGOS.items()
                     if j['key'] not in resultados
                     or esta_incompleto(resultados[j['key']], j['key'])]
        if not faltantes:
            return []

        notas = []
        print("-" * 60)
        print(f"📄 Buscando en la página de cada juego los {len(faltantes)} "
              f"que faltan o salieron incompletos...")

        for slug, juego in faltantes:
            url = f"{self.BASE_URL}loto-hn/{slug}/"
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_selector(SELECTOR_BOLAS, timeout=20000)
                self._esperar_tarjetas_estables(page, selector=SELECTOR_BOLAS)
                filas = page.evaluate(self.JS_FILAS)
            except Exception as e:
                notas.append(f"{slug}: no se pudo leer su página ({type(e).__name__})")
                continue

            mejor = None
            for fila in filas:
                fecha = self._fecha_desde_texto(fila['fecha'])
                if not fecha or not fila['nums']:
                    continue
                # La fuente fecha en UTC también acá: mismo desfase que la portada
                sorteo = fecha - timedelta(days=DESFASE_UTC_DIAS[juego['hora']])
                if mejor is None or sorteo > mejor[0]:
                    mejor = (sorteo, fila['nums'])

            if not mejor:
                notas.append(f"{slug}: su página no trae ninguna fila utilizable")
                continue

            fecha_sorteo, nums = mejor
            ganador, adicionales, individuales, extras = self._formatear_numeros(nums, juego['key'])
            if not ganador:
                notas.append(f"{slug}: no se pudo interpretar {nums} de su página")
                continue

            nuevo = self._armar_resultado(juego, fecha_sorteo, ganador, adicionales,
                                          individuales, extras, 'pagina_juego')
            actual = resultados.get(juego['key'])
            if actual:
                # La página puede ir más atrasada que la portada, o traer lo mismo
                if nuevo['fecha_historial'] < actual['fecha_historial']:
                    notas.append(f"{slug}: su página está más atrasada que la portada")
                    continue
                if (nuevo['fecha_historial'] == actual['fecha_historial']
                        and len(adicionales) <= len(actual['numeros_adicionales'])):
                    notas.append(f"{slug}: su página tampoco trae los valores que faltan")
                    continue

            resultados[juego['key']] = nuevo
            print(f"   ✅ {juego['nombre']}: {ganador} | {fecha_sorteo:%Y-%m-%d} "
                  f"| pagina_juego | todos: {adicionales}")

        return notas

    # ----------------------------------------
    # FECHA DE LA TARJETA (etiqueta "dd-mm")
    # ----------------------------------------

    def _extraer_fecha(self, tarjeta):
        etiqueta = tarjeta.query_selector('.bg-slate-500')
        texto = etiqueta.inner_text().strip() if etiqueta else (tarjeta.inner_text() or '')
        return self._fecha_desde_texto(texto)

    @staticmethod
    def _fecha_desde_texto(texto: str):
        m = re.search(r'\b(\d{2})-(\d{2})\b', texto or '')
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
        elegida = min(candidatos, key=lambda d: abs((d - hoy).days))
        if abs((elegida - hoy).days) > MAX_DIAS_FECHA:
            # Sin la etiqueta de fecha leemos el texto entero de la tarjeta, donde
            # unos números como "05-10" pasan por fecha. Una fecha lejana delata eso.
            return None
        return elegida

    # ----------------------------------------
    # EXTRAER NÚMEROS DE LAS BOLAS
    # ----------------------------------------

    def _extraer_balls(self, tarjeta) -> list:
        numeros = []
        for ball in tarjeta.query_selector_all(SELECTOR_BOLAS):
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
            # individuales == adicionales: el frontend los usa para pintar
            # número · signo · multiplicador · Más 1
            return numero, adicionales, list(adicionales), extras

        # premia2, pega_3 y super_premio: una bola por número
        return numeros[0], list(numeros), list(numeros), {}

    # ----------------------------------------
    # GUARDAR JSON HOY
    # ----------------------------------------

    def guardar_resultados_json(self, resultados: dict, archivo='resultados_hoy.json'):
        """Retorna el diccionario de sorteos ya fusionado, o None si falló."""
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
            return existente
        except Exception as e:
            print(f"❌ Error al guardar: {e}")
            return None

    # ----------------------------------------
    # GUARDAR HISTORIAL
    # ----------------------------------------

    def guardar_historial_json(self, resultados: dict, archivo='historial.json') -> bool:
        try:
            historial = {}
            if os.path.exists(archivo):
                with open(archivo, 'r', encoding='utf-8') as f:
                    historial = json.load(f)

            hoy = fecha_hn_str('%Y-%m-%d')
            nuevos, corregidos = 0, 0
            for key, data in resultados.items():
                # Cada tarjeta trae su propia fecha, así que un sorteo viejo que
                # siga en pantalla se guarda en su día y no en el de hoy
                fecha_key = data['fecha_historial']
                if fecha_key > hoy:
                    # Una etiqueta mal leída no debe abrir un día en el futuro
                    print(f"   ⏭️  Ignorado {key}: fecha futura {fecha_key}")
                    continue
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
    # Modo aparte que el workflow invoca DESPUÉS del git push. El purgado no
    # puede ir dentro de la corrida del scraper: en ese momento los JSON nuevos
    # solo existen en el runner, así que vaciar el borde mientras el origen
    # todavía sirve los resultados de ayer hace que la primera visita vuelva a
    # cachear justo lo viejo, y ahí se queda hasta que expire el TTL.
    if "--purgar-cache" in sys.argv:
        purgar_cache_cloudflare()
        sys.exit(0)

    scraper = LotoHondurasScraper()

    print("🎲 LOTO HONDURAS SCRAPER — fuente: loteriasdehonduras.com")
    print("=" * 60)
    print(f"⏰ Hora HN: {fecha_hn_str('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    resultados = scraper.obtener_resultados(cargar_previos('resultados_hoy.json'))

    if not resultados:
        alerta_error_scraping("No se obtuvo ningún resultado de loteriasdehonduras.com")
    else:
        guardados = scraper.guardar_resultados_json(resultados, 'resultados_hoy.json')
        scraper.guardar_historial_json(resultados, 'historial.json')

        # Un juego que la fuente no devolvió conserva el resultado anterior: hay
        # que decirlo, porque si no parece que todo se actualizó cuando no fue así
        problemas = sorteos_atrasados(guardados or {})
        if problemas:
            print("-" * 60)
            print(f"🕓 Juegos sin el resultado que ya tocaba ({len(problemas)}):")
            for nombre, motivo in problemas:
                print(f"   · {nombre}: {motivo}")
            alerta_error_scraping(
                f"{len(problemas)} juego(s) sin actualizar: "
                + ", ".join(f"{n} ({m})" for n, m in problemas)
            )

        # El purgado de Cloudflare NO va acá: corre como paso propio del
        # workflow, ya publicados los JSON (ver --purgar-cache arriba).
        resumen_telegram(resultados)

    print("\n" + "=" * 60)
    print("📊 RESUMEN:")
    print("=" * 60)
    for key, data in sorted(resultados.items()):
        print(f"✅ {data['nombre_juego']}: {data['numero_ganador']} "
              f"| {data['fecha_sorteo']} | {data['hora_sorteo']}")
    print("=" * 60)
