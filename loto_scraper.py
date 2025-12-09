import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import time

class LotoHondurasScraper:
    """
    Scraper para obtener resultados de Loto Honduras
    """
    
    def __init__(self):
        self.base_url = "https://loteriasdehonduras.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Diccionario de juegos disponibles
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
    
    def obtener_resultado(self, juego_key, fecha=None, usar_fecha_hoy=True):
        """
        Obtiene el resultado de un juego específico
        
        Args:
            juego_key: Clave del juego (ej: 'juga3_11am')
            fecha: Fecha en formato 'YYYY-MM-DD' (opcional)
            usar_fecha_hoy: Si es True, busca resultados de hoy por defecto
        
        Returns:
            dict con los resultados o None si hay error
        """
        if juego_key not in self.juegos:
            print(f"Juego '{juego_key}' no encontrado")
            return None
        
        url = self.base_url + self.juegos[juego_key]
        
        # Si se proporciona fecha, agregarla como parámetro
        if fecha:
            url += f"?date={fecha}"
        elif usar_fecha_hoy:
            # Usar la fecha de hoy por defecto
            fecha_hoy = datetime.now().strftime('%Y-%m-%d')
            url += f"?date={fecha_hoy}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Buscar los números ganadores (esto puede variar según la estructura real)
            resultado = self._extraer_numeros(soup, juego_key)
            
            return resultado
            
        except requests.RequestException as e:
            print(f"Error al obtener datos: {e}")
            return None
    
    def _extraer_numeros(self, soup, juego_key):
        """
        Extrae todos los datos disponibles del sorteo
        """
        resultado = {
            'juego': juego_key,
            'nombre_juego': self._obtener_nombre_juego(juego_key),
            'fecha_consulta': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'fecha_sorteo': None,
            'hora_sorteo': None,
            'numero_ganador': None,
            'numeros_individuales': [],
            'numeros_adicionales': [],
            'serie': None,
            'folio': None,
            'estado': None,  # pendiente, completado, cancelado
            'logo_url': None,  # URL del logo del juego
            'extras': {}
        }
        
        # Buscar el número ganador principal en diferentes formatos
        # Intentar múltiples selectores en orden de especificidad
        selectores = [
            ('span', 'score_special3'),  # Específico para algunos juegos
            ('span', 'score_special'),   # Variante sin número
            ('span', 'score'),           # Clase genérica
            ('div', 'score'),            # Por si está en div
        ]
        
        for tag, clase in selectores:
            numero_elem = soup.find(tag, class_=clase)
            if numero_elem:
                numero = numero_elem.get_text().strip()
                if numero and numero.isdigit() and len(numero) <= 4:
                    resultado['numero_ganador'] = numero
                    resultado['numeros_individuales'] = list(numero)
                    print(f"   🔍 Número encontrado con clase '{clase}': {numero}")
                    break
        
        # Si aún no se encontró, buscar en game-scores
        if not resultado['numero_ganador']:
            game_scores = soup.find('div', class_='game-scores')
            if game_scores:
                # Buscar el primer span con clase que contenga 'score'
                primer_score = game_scores.find('span', class_=lambda x: x and 'score' in x)
                if primer_score:
                    numero = primer_score.get_text().strip()
                    if numero and len(numero) <= 4:
                        resultado['numero_ganador'] = numero
                        resultado['numeros_individuales'] = list(numero)
                        print(f"   🔍 Número encontrado en game-scores: {numero}")
        
        # Buscar todos los game-blocks (puede haber múltiples sorteos)
        game_blocks = soup.find_all('div', class_='game-block')
        
        # Intentar encontrar el bloque más reciente (sin clase 'past')
        bloque_actual = None
        for block in game_blocks:
            clases = block.get('class', [])
            if 'past' not in clases:
                bloque_actual = block
                break
        
        # Si no hay bloques actuales, usar el primero
        if not bloque_actual and game_blocks:
            bloque_actual = game_blocks[0]
        
        if bloque_actual:
            # Extraer el logo del juego - intentar múltiples selectores
            logo_img = None
            
            # Intentar diferentes selectores para encontrar el logo
            selectores_logo = [
                ('img', {'class': 'lazy loaded'}),
                ('img', {'class': 'lazy'}),
                ('img', {'class': 'game-logo'}),
                ('img', {'alt': lambda x: x and 'logo' in x.lower()}),
                ('img', {})  # Cualquier img como último recurso
            ]
            
            for tag, attrs in selectores_logo:
                if attrs:
                    logo_img = bloque_actual.find(tag, attrs)
                else:
                    logo_img = bloque_actual.find(tag)
                
                if logo_img and (logo_img.get('src') or logo_img.get('data-src')):
                    break
            
            if logo_img:
                # Intentar obtener src o data-src
                logo_url = logo_img.get('src') or logo_img.get('data-src')
                
                if logo_url:
                    # Si la URL es relativa, convertirla a absoluta
                    if logo_url.startswith('//'):
                        logo_url = 'https:' + logo_url
                    elif logo_url.startswith('/'):
                        logo_url = self.base_url + logo_url
                    elif not logo_url.startswith('http'):
                        logo_url = self.base_url + '/' + logo_url
                    
                    # Intentar descargar la imagen y convertirla a base64
                    try:
                        img_response = requests.get(logo_url, headers=self.headers, timeout=5)
                        if img_response.status_code == 200:
                            import base64
                            img_base64 = base64.b64encode(img_response.content).decode('utf-8')
                            # Detectar tipo de imagen
                            content_type = img_response.headers.get('content-type', 'image/png')
                            resultado['logo_url'] = f"data:{content_type};base64,{img_base64}"
                            print(f"   🖼️  Logo descargado y convertido a base64")
                        else:
                            print(f"   ⚠️  Logo no disponible (HTTP {img_response.status_code})")
                            resultado['logo_url'] = self._obtener_logo_fallback(juego_key)
                    except Exception as e:
                        print(f"   ⚠️  Error al descargar logo: {e}")
                        resultado['logo_url'] = self._obtener_logo_fallback(juego_key)
            
            # Si no se encontró logo, usar el fallback
            if not resultado['logo_url']:
                resultado['logo_url'] = self._obtener_logo_fallback(juego_key)
                print(f"   🖼️  Usando logo fallback (emoji)")
            
            # Extraer fecha del sorteo - buscar en múltiples lugares
            # Opción 1: session-date
            fecha_elem = bloque_actual.find('div', class_='session-date')
            if fecha_elem:
                fecha_texto = fecha_elem.get_text().strip()
                resultado['fecha_sorteo'] = fecha_texto
                try:
                    resultado['extras']['fecha_parseada'] = self._parsear_fecha(fecha_texto)
                except:
                    pass
            
            # Opción 2: Buscar en cualquier elemento que contenga una fecha DD-MM
            if not resultado['fecha_sorteo']:
                import re
                texto_completo = bloque_actual.get_text()
                # Buscar patrón DD-MM (ej: 08-12)
                match = re.search(r'\b(\d{2}-\d{2})\b', texto_completo)
                if match:
                    resultado['fecha_sorteo'] = match.group(1)
            
            # Extraer información adicional del juego
            game_info = bloque_actual.find('div', class_='game-info')
            if game_info:
                info_texto = game_info.get_text().strip()
                resultado['extras']['info_adicional'] = info_texto
                
                # Extraer hora si está en el texto
                hora = self._extraer_hora(info_texto)
                if hora:
                    resultado['hora_sorteo'] = hora
            
            # Buscar el título del juego
            company_title = bloque_actual.find('div', class_='company-title')
            if company_title:
                resultado['extras']['titulo_oficial'] = company_title.get_text().strip()
            
            # Verificar si el sorteo está en modo 'past' (pasado/completado)
            if 'past' in bloque_actual.get('class', []):
                resultado['estado'] = 'completado'
            else:
                resultado['estado'] = 'activo'
        
        # Buscar múltiples números en game-scores (para juegos con varios números)
        game_scores = soup.find('div', class_='game-scores')
        if game_scores:
            # Buscar todos los spans con clases que contengan 'score'
            scores = game_scores.find_all('span', class_=lambda x: x and 'score' in x)
            if scores:
                # Si es el primer score y no hay numero_ganador, usarlo como ganador
                if not resultado['numero_ganador'] and len(scores) > 0:
                    primer_numero = scores[0].get_text().strip()
                    if primer_numero and len(primer_numero) <= 4:
                        resultado['numero_ganador'] = primer_numero
                        resultado['numeros_individuales'] = list(primer_numero)
                        # Los demás van a adicionales
                        if len(scores) > 1:
                            resultado['numeros_adicionales'] = [s.get_text().strip() for s in scores[1:]]
                else:
                    # Todos van a adicionales
                    resultado['numeros_adicionales'] = [s.get_text().strip() for s in scores]
            
            # Buscar modo de bola (ball-mode) si existe
            ball_mode = game_scores.find('div', class_='ball-mode')
            if ball_mode:
                bolas = ball_mode.find_all('span')
                if bolas:
                    resultado['extras']['bolas'] = [b.get_text().strip() for b in bolas]
        
        # Buscar información de premios si existe
        prize_info = soup.find('div', class_=['prize-info', 'premio'])
        if prize_info:
            resultado['extras']['premio'] = prize_info.get_text().strip()
        
        # Extraer serie y folio si existen
        serie_elem = soup.find(class_=['serie', 'serial-number'])
        if serie_elem:
            resultado['serie'] = serie_elem.get_text().strip()
        
        folio_elem = soup.find(class_=['folio', 'ticket-number'])
        if folio_elem:
            resultado['folio'] = folio_elem.get_text().strip()
        
        return resultado
    
    def _obtener_nombre_juego(self, juego_key):
        """Convierte la clave del juego en un nombre legible"""
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
    
    def _obtener_logo_fallback(self, juego_key):
        """Retorna URLs de logos por defecto"""
        # Usar emojis como fallback visual si las URLs del CDN no funcionan
        logos_emoji = {
            'juga3_11am': '🎯',
            'juga3_3pm': '🎯',
            'juga3_9pm': '🎯',
            'premia2_10am': '💎',
            'premia2_2pm': '💎',
            'premia2_9pm': '💎',
            'pega3_10am': '🎲',
            'pega3_2pm': '🎲',
            'pega3_9pm': '🎲',
            'la_diaria_10am': '⭐',
            'la_diaria_2pm': '⭐',
            'la_diaria_9pm': '⭐',
            'super_premio': '🏆'
        }
        
        # Intentar primero con el CDN, si no funciona usar data URL con emoji
        emoji = logos_emoji.get(juego_key, '🎰')
        
        # Crear una data URL con el emoji (siempre funciona)
        return f"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='70' font-size='70'>{emoji}</text></svg>"
    
    def _parsear_fecha(self, fecha_texto):
        """Intenta parsear diferentes formatos de fecha"""
        formatos = [
            '%d-%m-%Y',
            '%d/%m/%Y',
            '%Y-%m-%d',
            '%d de %B de %Y',
            '%d %b %Y'
        ]
        
        for formato in formatos:
            try:
                return datetime.strptime(fecha_texto, formato).strftime('%Y-%m-%d')
            except:
                continue
        
        return fecha_texto
    
    def _extraer_hora(self, texto):
        """Extrae la hora del texto si está presente"""
        import re
        # Buscar patrones como "11:00 AM", "3:00 PM", "21:00"
        patron = r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)'
        match = re.search(patron, texto)
        if match:
            return match.group(1)
        return None
    
    def obtener_todos_resultados_hoy(self):
        """
        Obtiene todos los resultados disponibles del día actual
        """
        resultados = {}
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        
        print(f"🔍 Buscando resultados para: {fecha_hoy}")
        print("="*60)
        
        for juego_key in self.juegos.keys():
            print(f"📊 Obteniendo resultado de {self.juegos[juego_key]}...")
            resultado = self.obtener_resultado(juego_key, fecha=fecha_hoy)
            
            if resultado:
                # Verificar si realmente es de hoy
                if resultado.get('fecha_sorteo'):
                    print(f"   ✅ Encontrado - Fecha: {resultado['fecha_sorteo']}")
                    if resultado.get('numero_ganador'):
                        print(f"   🎯 Número: {resultado['numero_ganador']}")
                else:
                    print(f"   ⚠️  Sin fecha de sorteo")
                
                resultados[juego_key] = resultado
            else:
                print(f"   ❌ No se pudo obtener")
            
            # Pequeña pausa entre requests para ser respetuoso
            time.sleep(1)
        
        print("="*60)
        print(f"✨ Total de juegos obtenidos: {len(resultados)}")
        return resultados
    
    def guardar_resultados_json(self, resultados, archivo='resultados_loto.json'):
        """
        Guarda los resultados en un archivo JSON
        """
        try:
            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(resultados, f, ensure_ascii=False, indent=2)
            print(f"💾 Resultados guardados en {archivo}")
            return True
        except Exception as e:
            print(f"❌ Error al guardar archivo: {e}")
            return False


# Ejemplo de uso
if __name__ == "__main__":
    scraper = LotoHondurasScraper()
    
    print("="*60)
    print("🎲 SCRAPER DE LOTO HONDURAS 🎲")
    print("="*60)
    print()
    
    # Obtener todos los resultados del día
    print("=== 📋 Obteniendo todos los resultados de HOY ===")
    todos_resultados = scraper.obtener_todos_resultados_hoy()
    
    # Guardar en archivo JSON
    scraper.guardar_resultados_json(todos_resultados, 'resultados_hoy.json')
    
    print(f"\n✅ Archivo guardado: resultados_hoy.json")
    
    # Mostrar resumen
    print("\n" + "="*60)
    print("📊 RESUMEN DE RESULTADOS:")
    print("="*60)
    for key, data in todos_resultados.items():
        logo_status = "🖼️" if data.get('logo_url') else "❌"
        if data.get('numero_ganador'):
            print(f"{logo_status} ✅ {data['nombre_juego']}: {data['numero_ganador']} (Fecha: {data['fecha_sorteo']})")
        else:
            print(f"{logo_status} ⏳ {data['nombre_juego']}: Pendiente (Fecha: {data['fecha_sorteo']})")
    print("="*60)