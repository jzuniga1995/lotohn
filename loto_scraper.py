import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import time

class LotoHondurasScraper:
    """
    Scraper SIMPLIFICADO - NO descarga logos
    Solo genera JSON con rutas relativas
    """
    
    def __init__(self):
        self.base_url = "https://loteriasdehonduras.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # Mapeo de juegos a nombres de archivo de logo
        # (los logos deben estar en /public/logos/ del frontend)
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
    
    def obtener_resultado(self, juego_key, fecha=None, usar_fecha_hoy=True):
        """
        Obtiene el resultado de un juego específico
        """
        if juego_key not in self.juegos:
            return None
        
        url = self.base_url + self.juegos[juego_key]
        
        if fecha:
            url += f"?date={fecha}"
        elif usar_fecha_hoy:
            fecha_hoy = datetime.now().strftime('%Y-%m-%d')
            url += f"?date={fecha_hoy}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            resultado = self._extraer_numeros(soup, juego_key)
            
            return resultado
            
        except requests.RequestException as e:
            print(f"Error: {e}")
            return None
    
    def _extraer_numeros(self, soup, juego_key):
        """
        Extrae todos los datos del sorteo
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
            'estado': None,
            'logo_url': None,  # ← Ruta relativa al logo
            'extras': {}
        }
        
        # ✅ ASIGNAR RUTA DEL LOGO (sin descargar nada)
        nombre_archivo = self.logos_estaticos.get(juego_key, f'{juego_key}.png')
        resultado['logo_url'] = f'/logos/{nombre_archivo}'
        print(f"   📁 Logo: {resultado['logo_url']}")
        
        # Buscar número ganador
        selectores = [
            ('span', 'score_special3'),
            ('span', 'score_special'),
            ('span', 'score'),
            ('div', 'score'),
        ]
        
        for tag, clase in selectores:
            numero_elem = soup.find(tag, class_=clase)
            if numero_elem:
                numero = numero_elem.get_text().strip()
                if numero and numero.isdigit() and len(numero) <= 4:
                    resultado['numero_ganador'] = numero
                    resultado['numeros_individuales'] = list(numero)
                    print(f"   🔍 Número: {numero}")
                    break
        
        if not resultado['numero_ganador']:
            game_scores = soup.find('div', class_='game-scores')
            if game_scores:
                primer_score = game_scores.find('span', class_=lambda x: x and 'score' in x)
                if primer_score:
                    numero = primer_score.get_text().strip()
                    if numero and len(numero) <= 4:
                        resultado['numero_ganador'] = numero
                        resultado['numeros_individuales'] = list(numero)
                        print(f"   🔍 Número: {numero}")
        
        game_blocks = soup.find_all('div', class_='game-block')
        
        bloque_actual = None
        for block in game_blocks:
            if 'past' not in block.get('class', []):
                bloque_actual = block
                break
        
        if not bloque_actual and game_blocks:
            bloque_actual = game_blocks[0]
        
        if bloque_actual:
            # Fecha sorteo
            fecha_elem = bloque_actual.find('div', class_='session-date')
            if fecha_elem:
                resultado['fecha_sorteo'] = fecha_elem.get_text().strip()
            
            if not resultado['fecha_sorteo']:
                import re
                texto = bloque_actual.get_text()
                match = re.search(r'\b(\d{2}-\d{2})\b', texto)
                if match:
                    resultado['fecha_sorteo'] = match.group(1)
            
            # Info adicional
            game_info = bloque_actual.find('div', class_='game-info')
            if game_info:
                info_texto = game_info.get_text().strip()
                resultado['extras']['info_adicional'] = info_texto
                
                hora = self._extraer_hora(info_texto)
                if hora:
                    resultado['hora_sorteo'] = hora
            
            # Estado
            if 'past' in bloque_actual.get('class', []):
                resultado['estado'] = 'completado'
            else:
                resultado['estado'] = 'activo'
        
        # Números adicionales
        game_scores = soup.find('div', class_='game-scores')
        if game_scores:
            scores = game_scores.find_all('span', class_=lambda x: x and 'score' in x)
            if scores:
                if not resultado['numero_ganador'] and len(scores) > 0:
                    primer_numero = scores[0].get_text().strip()
                    if primer_numero and len(primer_numero) <= 4:
                        resultado['numero_ganador'] = primer_numero
                        resultado['numeros_individuales'] = list(primer_numero)
                        if len(scores) > 1:
                            resultado['numeros_adicionales'] = [s.get_text().strip() for s in scores[1:]]
                else:
                    resultado['numeros_adicionales'] = [s.get_text().strip() for s in scores]
        
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
    
    def _extraer_hora(self, texto):
        """Extrae la hora del texto si está presente"""
        import re
        match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)', texto)
        return match.group(1) if match else None
    
    def obtener_todos_resultados_hoy(self):
        """
        Obtiene todos los resultados disponibles del día actual
        """
        resultados = {}
        fecha_hoy = datetime.now().strftime('%Y-%m-%d')
        
        print(f"🔍 Fecha: {fecha_hoy}")
        print("="*60)
        
        for juego_key in self.juegos.keys():
            print(f"📊 {self.juegos[juego_key]}...")
            resultado = self.obtener_resultado(juego_key, fecha=fecha_hoy)
            
            if resultado:
                resultados[juego_key] = resultado
            
            time.sleep(1)
        
        print("="*60)
        print(f"✨ Total: {len(resultados)}")
        return resultados
    
    def guardar_resultados_json(self, resultados, archivo='resultados_loto.json'):
        """
        Guarda los resultados en un archivo JSON
        """
        try:
            # Agregar metadatos
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
            print(f"❌ Error: {e}")
            return False


if __name__ == "__main__":
    scraper = LotoHondurasScraper()
    
    print("🎲 LOTO HONDURAS SCRAPER (SIN DESCARGA DE LOGOS)")
    print("="*60)
    
    # Obtener resultados del día
    todos_resultados = scraper.obtener_todos_resultados_hoy()
    scraper.guardar_resultados_json(todos_resultados, 'resultados_hoy.json')
    
    print("\n" + "="*60)
    print("📊 RESUMEN:")
    print("="*60)
    for key, data in todos_resultados.items():
        if data.get('numero_ganador'):
            print(f"✅ {data['nombre_juego']}: {data['numero_ganador']} | Logo: {data['logo_url']}")
        else:
            print(f"⏳ {data['nombre_juego']}: Pendiente | Logo: {data['logo_url']}")
    print("="*60)
    