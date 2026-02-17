import json
import time
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright


class LotoHondurasScraper:

    def __init__(self):
        self.base_url = "https://loteriasdehonduras.com"

        self.logos_estaticos = {
            'juga3_11am': 'juga3.png',
            'juga3_3pm': 'juga3.png',
            'juga3_9pm': 'juga3.png',
            'premia2_10am': 'premia2.png',
            'premia2_2pm': 'premia2.png',
            'premia2_9pm': 'premia2.png',
            'pega3_10am': 'pega3.png',
            'pega3_2pm': 'pega3.png',
            'pega3_9pm': 'pega3.png',
            'la_diaria_10am': 'la_diaria.png',
            'la_diaria_2pm': 'la_diaria.png',
            'la_diaria_9pm': 'la_diaria.png',
            'super_premio': 'super_premio.png'
        }

        self.juegos = {
            'juga3_11am': '/loto-hn/juga-3-11am',
            'juga3_3pm': '/loto-hn/juga-3-3pm',
            'juga3_9pm': '/loto-hn/juga-3-9pm',
            'premia2_10am': '/loto-hn/premia2-10am',
            'premia2_2pm': '/loto-hn/premia2-2pm',
            'premia2_9pm': '/loto-hn/premia2-9pm',
            'pega3_10am': '/loto-hn/pega-3-10am',
            'pega3_2pm': '/loto-hn/pega-3-2pm',
            'pega3_9pm': '/loto-hn/pega-3-9pm',
            'la_diaria_10am': '/loto-hn/la-diaria-10am',
            'la_diaria_2pm': '/loto-hn/la-diaria-2pm',
            'la_diaria_9pm': '/loto-hn/la-diaria-9pm',
            'super_premio': '/loto-hn/loto-super-premio'
        }

        self.horas_por_juego = {
            'juga3_11am': '11:00 AM',
            'juga3_3pm': '3:00 PM',
            'juga3_9pm': '9:00 PM',
            'premia2_10am': '10:00 AM',
            'premia2_2pm': '2:00 PM',
            'premia2_9pm': '9:00 PM',
            'pega3_10am': '10:00 AM',
            'pega3_2pm': '2:00 PM',
            'pega3_9pm': '9:00 PM',
            'la_diaria_10am': '10:00 AM',
            'la_diaria_2pm': '2:00 PM',
            'la_diaria_9pm': '9:00 PM',
            'super_premio': None
        }

        # Cuántos números tiene cada juego
        self.limite_numeros = {
            'juga3': 1,
            'premia2': 2,
            'pega3': 3,
            'diaria': 3,
            'super': 6
        }

    # ============================================
    # OBTENER TODOS LOS RESULTADOS
    # ============================================

    def obtener_todos_resultados_hoy(self):
        resultados = {}
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')

        print(f"🔍 Fecha: {fecha_hoy}")
        print("=" * 60)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()

            for juego_key in self.juegos.keys():
                print(f"📊 Scrapeando {juego_key}...")
                resultado = self._scrapear_juego(page, juego_key, fecha_hoy)
                resultados[juego_key] = resultado
                time.sleep(1)

            browser.close()

        print("=" * 60)
        print(f"✨ Total: {len(resultados)}")
        return resultados

    # ============================================
    # SCRAPEAR UN JUEGO
    # ============================================

    def _scrapear_juego(self, page, juego_key, fecha):
        url = f"{self.base_url}{self.juegos[juego_key]}?date={fecha}"
        resultado = self._resultado_vacio(juego_key)

        try:
            page.goto(url, wait_until='networkidle', timeout=30000)

            try:
                page.wait_for_selector('[class*="score-shape"]', timeout=10000)
            except:
                print(f"   ⚠️  Timeout esperando resultados")
                return resultado

            # ✅ Intentar obtener resultado de HOY (excluye past-score-ball)
            numeros = self._extraer_numeros(page, juego_key, solo_hoy=True)

            if numeros:
                resultado['numero_ganador'] = numeros[0]
                resultado['numeros_adicionales'] = numeros
                if 'juga3' in juego_key and numeros[0].isdigit():
                    resultado['numeros_individuales'] = list(numeros[0])
                else:
                    resultado['numeros_individuales'] = numeros
                resultado['estado'] = 'completado'
                print(f"   ✅ Números: {numeros}")
            else:
                # ✅ Sin resultado hoy → buscar AYER
                print(f"   🔄 Sin resultado hoy, buscando ayer...")
                fecha_ayer = (datetime.strptime(fecha, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
                url_ayer = f"{self.base_url}{self.juegos[juego_key]}?date={fecha_ayer}"
                page.goto(url_ayer, wait_until='networkidle', timeout=30000)

                try:
                    page.wait_for_selector('[class*="score-shape"]', timeout=10000)
                    # ✅ En página de ayer no filtramos past-score-ball
                    numeros_ayer = self._extraer_numeros(page, juego_key, solo_hoy=False)
                    if numeros_ayer:
                        resultado['numero_ganador'] = numeros_ayer[0]
                        resultado['numeros_adicionales'] = numeros_ayer
                        if 'juga3' in juego_key and numeros_ayer[0].isdigit():
                            resultado['numeros_individuales'] = list(numeros_ayer[0])
                        else:
                            resultado['numeros_individuales'] = numeros_ayer
                        resultado['estado'] = 'anterior'
                        print(f"   📅 Resultado anterior: {numeros_ayer}")
                    else:
                        resultado['estado'] = 'pendiente'
                        print(f"   ⏳ Sin resultado")
                except:
                    resultado['estado'] = 'pendiente'

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

    def _extraer_numeros(self, page, juego_key, solo_hoy=True):
        numeros = []

        try:
            if solo_hoy:
                # Excluir resultados del historial
                selector = '[class*="score-shape"]:not([class*="past-score-ball"])'
            else:
                # En página de ayer todos son past-score-ball, tomamos todos
                selector = '[class*="score-shape"]'

            elementos = page.query_selector_all(selector)

            # Determinar límite de números para este juego
            limite = 3  # default
            for tipo, lim in self.limite_numeros.items():
                if tipo in juego_key:
                    limite = lim
                    break

            for elem in elementos:
                inner_div = elem.query_selector('span > div')
                if inner_div:
                    texto = inner_div.inner_text().strip()
                else:
                    span = elem.query_selector('span')
                    texto = span.inner_text().strip() if span else ''

                if texto:
                    numeros.append(texto)

                # ✅ Parar cuando tengamos los números del sorteo
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

        hoy = datetime.now()
        return f"{str(hoy.day).zfill(2)}-{str(hoy.month).zfill(2)}"

    # ============================================
    # HELPERS
    # ============================================

    def _resultado_vacio(self, juego_key):
        nombre_logo = self.logos_estaticos.get(juego_key, f'{juego_key}.png')
        return {
            'juego': juego_key,
            'nombre_juego': self._obtener_nombre_juego(juego_key),
            'fecha_consulta': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
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
            'juga3_11am': 'Jugá 3 11:00 AM',
            'juga3_3pm': 'Jugá 3 3:00 PM',
            'juga3_9pm': 'Jugá 3 9:00 PM',
            'premia2_10am': 'Premia 2 10:00 AM',
            'premia2_2pm': 'Premia 2 2:00 PM',
            'premia2_9pm': 'Premia 2 9:00 PM',
            'pega3_10am': 'Pega 3 10:00 AM',
            'pega3_2pm': 'Pega 3 2:00 PM',
            'pega3_9pm': 'Pega 3 9:00 PM',
            'la_diaria_10am': 'La Diaria 10:00 AM',
            'la_diaria_2pm': 'La Diaria 2:00 PM',
            'la_diaria_9pm': 'La Diaria 9:00 PM',
            'super_premio': 'Super Premio'
        }
        return nombres.get(juego_key, juego_key)

    # ============================================
    # GUARDAR JSON
    # ============================================

    def guardar_resultados_json(self, resultados, archivo='resultados_loto.json'):
        try:
            salida = {
                'fecha_actualizacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_sorteos': len(resultados),
                'sorteos': resultados
            }
            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(salida, f, ensure_ascii=False, indent=2)
            print(f"💾 Guardado: {archivo}")
            return True
        except Exception as e:
            print(f"❌ Error al guardar: {e}")
            return False

    # ============================================
    # DEBUG
    # ============================================

    def debug_html(self, juego_key):
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        url = f"{self.base_url}{self.juegos[juego_key]}?date={fecha_hoy}"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle', timeout=30000)

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

    todos_resultados = scraper.obtener_todos_resultados_hoy()
    scraper.guardar_resultados_json(todos_resultados, 'resultados_hoy.json')

    print("\n" + "=" * 60)
    print("📊 RESUMEN:")
    print("=" * 60)
    for key, data in todos_resultados.items():
        estado = data.get('estado', '?')
        if data.get('numero_ganador'):
            print(f"✅ [{estado}] {data['nombre_juego']}: {data['numero_ganador']} | {data['fecha_sorteo']} | {data['hora_sorteo']}")
        else:
            print(f"⏳ {data['nombre_juego']}: Pendiente")
    print("=" * 60)
    