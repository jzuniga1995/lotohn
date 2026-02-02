import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import re

class LotoHnScraper:
    """
    Scraper para loto.hn - Captura TODOS los números incluyendo duplicados
    """
    
    def __init__(self):
        self.base_url = "https://loto.hn"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def obtener_resultados(self, debug=False):
        """
        Obtiene resultados de loto.hn
        """
        url = self.base_url
        
        try:
            print(f"🔗 Conectando a: {url}")
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            print(f"✅ Página obtenida (Código: {response.status_code})\n")
            
            return self._extraer_resultados(response.text, debug)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return {}
    
    def _extraer_resultados(self, html, debug=False):
        """
        Extrae resultados agrupando esferas consecutivas por color
        """
        soup = BeautifulSoup(html, 'html.parser')
        resultados = {}
        
        fecha_actual = self._extraer_fecha(soup)
        print(f"📅 Fecha del sorteo: {fecha_actual}\n")
        
        # Extraer imágenes de logos de juegos
        imagenes_juegos = self._extraer_imagenes_logos(soup)
        if debug and imagenes_juegos:
            print("🖼️  LOGOS ENCONTRADOS:")
            for nombre, url in imagenes_juegos.items():
                print(f"  {nombre}: {url[:80]}...")
            print()
        
        # Buscar todas las esferas
        todas_esferas = soup.find_all('div', class_='esferas')
        print(f"🔍 Total de esferas encontradas: {len(todas_esferas)}\n")
        
        if not todas_esferas:
            print("❌ No se encontraron esferas")
            return {}
        
        # DEBUG: Mostrar todas las esferas individuales si se solicita
        if debug:
            print("🔍 DEBUG - TODAS LAS ESFERAS INDIVIDUALES:")
            for idx, esfera in enumerate(todas_esferas, 1):
                clases = esfera.get('class', [])
                span = esfera.find('span')
                numero = span.get_text().strip() if span else "N/A"
                print(f"  {idx}. Clases: {clases} → Número: '{numero}'")
            print()
        
        print("="*60)
        
        # Agrupar esferas CONSECUTIVAS por color
        grupos = []
        grupo_actual = {'color': None, 'numeros': []}
        
        for esfera in todas_esferas:
            clases = esfera.get('class', [])
            
            # Buscar el color
            color = None
            for clase in clases:
                if 'esfera-' in clase and clase != 'esferas':
                    color = clase.replace('esfera-', '').split('-')[0]
                    break
            
            if not color:
                continue
            
            # Extraer número
            span = esfera.find('span')
            if not span:
                continue
                
            numero = span.get_text().strip()
            numero = ''.join(numero.split())
            
            if not numero:
                continue
            
            # Si el color cambió, cerrar grupo anterior
            if grupo_actual['color'] and color != grupo_actual['color']:
                if len(grupo_actual['numeros']) >= 1:
                    grupos.append(grupo_actual.copy())
                grupo_actual = {'color': color, 'numeros': [numero]}
            else:
                grupo_actual['color'] = color
                # CRÍTICO: append() agrega SIEMPRE, incluso duplicados
                grupo_actual['numeros'].append(numero)
        
        # Agregar último grupo
        if grupo_actual['color'] and len(grupo_actual['numeros']) >= 1:
            grupos.append(grupo_actual)
        
        print(f"📦 Grupos consecutivos detectados: {len(grupos)}\n")
        
        # Mostrar todos los grupos con conteo
        for i, grupo in enumerate(grupos, 1):
            nums = grupo['numeros']
            conteo = len(nums)
            print(f"Grupo {i}: color={grupo['color']}, cantidad={conteo}, números={nums}")
        
        print("\n" + "="*60 + "\n")
        
        # Convertir grupos a juegos
        contador_gris = 0
        contador_amarillo = 0
        
        for grupo in grupos:
            color = grupo['color']
            numeros = grupo['numeros']
            
            if len(numeros) < 1:
                continue
            
            juego_info = None
            
            # GRIS: Primero es Bingo, segundo es Juga Tres
            if color == 'gris':
                contador_gris += 1
                if contador_gris == 1:
                    juego_info = {'key': 'bingo', 'nombre': 'Bingo Con Todo'}
                elif contador_gris == 2:
                    juego_info = {'key': 'jugatres', 'nombre': 'Juga Tres'}
            
            # AMARILLO: Primero es Premia 2, segundo es Super Premio
            elif color == 'amarillo':
                contador_amarillo += 1
                if contador_amarillo == 1:
                    juego_info = {'key': 'premia2', 'nombre': 'Premia 2'}
                elif contador_amarillo == 2:
                    juego_info = {'key': 'superpremio', 'nombre': 'Loto Super Premio'}
            
            # MORADO: Parte de Premia 2
            elif color == 'morado':
                if 'premia2' in resultados:
                    resultados['premia2']['numeros'].extend(numeros)
                    print(f"  💜 Agregando a Premia 2: {' - '.join(numeros)}")
                    continue
                else:
                    juego_info = {'key': 'premia2', 'nombre': 'Premia 2'}
            
            # VERDE: La Diaria
            elif color == 'verde' or color == 'light':
                if 'diaria' not in resultados:
                    juego_info = {'key': 'diaria', 'nombre': 'La Diaria'}
                else:
                    # Agregar números verdes adicionales a La Diaria
                    resultados['diaria']['numeros'].extend(numeros)
                    continue
            
            # MARRÓN/ROJO: Multi-X
            elif color == 'marron' or color == 'rojo':
                juego_info = {'key': 'multix', 'nombre': 'Multi-X'}
            
            # AZUL: Pega 3
            elif color == 'azul':
                juego_info = {'key': 'pega3', 'nombre': 'Pega 3'}
            
            # ROSA: Juga Tres
            elif color == 'rosa':
                juego_info = {'key': 'jugatres', 'nombre': 'Juga Tres'}
            
            if not juego_info:
                print(f"⚠️  Color '{color}' no mapeado: {numeros}")
                continue
            
            juego_key = juego_info['key']
            
            # Si el juego ya existe, combinar números
            if juego_key in resultados:
                resultados[juego_key]['numeros'].extend(numeros)
                continue
            
            # Separar multiplicadores
            numeros_limpios = []
            multiplicador = None
            
            for num in numeros:
                if 'x' in num.lower() and len(num) <= 3:
                    multiplicador = num
                else:
                    numeros_limpios.append(num)
            
            if multiplicador:
                numeros_limpios.append(multiplicador)
            
            resultado = {
                'juego': juego_key,
                'nombre_juego': juego_info['nombre'],
                'logo_url': imagenes_juegos.get(juego_info['nombre'], None),
                'numeros': numeros_limpios if numeros_limpios else numeros,
                'fecha_sorteo': fecha_actual,
                'fecha_consulta': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            resultados[juego_key] = resultado
            numeros_str = ' - '.join(resultado['numeros'])
            print(f"{resultado['nombre_juego']}: {numeros_str}")
        
        # Validar TODOS los resultados al final (después de combinar colores)
        for juego_key, resultado in resultados.items():
            es_valido = self._validar_cantidad_numeros(juego_key, len(resultado['numeros']))
            resultado['valido'] = es_valido
            
            if not es_valido:
                cantidades_esperadas = {
                    'bingo': 7, 'diaria': 3, 'multix': 1, 
                    'pega3': 3, 'premia2': 4, 'superpremio': 6, 'jugatres': 3
                }
                esperada = cantidades_esperadas.get(juego_key, '?')
                resultado['advertencia'] = f"Se esperaban {esperada} números pero se encontraron {len(resultado['numeros'])}"
        
        print("="*60)
        return resultados
    
    def _extraer_imagenes_logos(self, soup):
        """
        Extrae las URLs de las imágenes/logos de cada juego
        """
        imagenes = {}
        
        # Mapeo de palabras clave en URLs o alt text a nombres de juegos
        patrones = {
            'BINGO': 'Bingo Con Todo',
            'DIARIA': 'La Diaria',
            'MULTI': 'Multi-X',
            'PEGA': 'Pega 3',
            'PREMIA': 'Premia 2',
            'SUPER': 'Loto Super Premio',
            'JUGA': 'Juga Tres'
        }
        
        # Buscar todas las imágenes
        imgs = soup.find_all('img')
        
        for img in imgs:
            # Priorizar data-lazy-src, luego data-src, luego src
            src = img.get('data-lazy-src') or img.get('data-src') or img.get('src', '')
            
            # Ignorar placeholders SVG vacíos
            if 'data:image/svg' in src or not src:
                continue
                
            alt = img.get('alt', '')
            title = img.get('title', '')
            
            # Buscar en src, alt o title
            texto_busqueda = (src + ' ' + alt + ' ' + title).upper()
            
            for patron, nombre_juego in patrones.items():
                if patron in texto_busqueda and nombre_juego not in imagenes:
                    # Asegurar que la URL sea completa
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://loto.hn' + src
                    
                    imagenes[nombre_juego] = src
                    break
        
        return imagenes
    
    def _validar_cantidad_numeros(self, juego_key, cantidad):
        """
        Valida que la cantidad de números sea la esperada para cada juego
        """
        cantidades_esperadas = {
            'bingo': 7,        # 7 números
            'diaria': 3,       # 3 números
            'multix': 1,       # Solo multiplicador
            'pega3': 3,        # 3 números
            'premia2': 4,      # 4 números (2 amarillos + 2 morados)
            'superpremio': 6,  # 6 números
            'jugatres': 3      # 3 números
        }
        
        esperada = cantidades_esperadas.get(juego_key)
        
        if not esperada:
            return True  # Si no está definido, aceptar cualquier cantidad
        
        return cantidad == esperada
    
    def _extraer_fecha(self, soup):
        """
        Extrae la fecha del sorteo
        """
        texto_completo = soup.get_text()
        
        # Patrón: "Lunes 05 de Enero, 2026 a las 03:00 PM"
        patron = r'(\w+\s+\d{2}\s+de\s+\w+,\s+\d{4}\s+a\s+las\s+\d{2}:\d{2}\s+[AP]M)'
        match = re.search(patron, texto_completo)
        
        if match:
            return match.group(1)
        
        # Patrón más simple
        patron2 = r'(\d{2}\s+de\s+\w+,\s+\d{4})'
        match2 = re.search(patron2, texto_completo)
        
        if match2:
            return match2.group(1)
        
        return datetime.now().strftime('%d/%m/%Y')
    
    def guardar_json(self, resultados, archivo='resultados_loto_hn.json'):
        """
        Guarda resultados en JSON
        """
        try:
            with open(archivo, 'w', encoding='utf-8') as f:
                json.dump(resultados, f, ensure_ascii=False, indent=2)
            print(f"\n💾 Guardado en: {archivo}")
            return True
        except Exception as e:
            print(f"❌ Error al guardar: {e}")
            return False
    
    def mostrar_resumen(self, resultados):
        """
        Muestra resumen de resultados con validaciones
        """
        print("\n" + "="*60)
        print("📊 RESUMEN DE RESULTADOS")
        print("="*60)
        
        if not resultados:
            print("❌ No se encontraron resultados")
            return
        
        juegos_validos = 0
        juegos_con_advertencia = 0
        
        for key, data in resultados.items():
            nombre = data.get('nombre_juego', key)
            numeros = data.get('numeros', [])
            valido = data.get('valido', True)
            advertencia = data.get('advertencia', None)
            
            if numeros:
                nums_str = ' - '.join(numeros)
                status = "✅" if valido else "⚠️"
                print(f"{status} {nombre}: {nums_str}")
                
                if valido:
                    juegos_validos += 1
                    
                if advertencia:
                    print(f"   ⚠️  {advertencia}")
                    juegos_con_advertencia += 1
            else:
                print(f"❌ {nombre}: Sin resultados")
        
        print("="*60)
        print(f"✨ Total: {len(resultados)} juegos")
        print(f"✅ Válidos: {juegos_validos}")
        
        if juegos_con_advertencia > 0:
            print(f"⚠️  Con advertencias: {juegos_con_advertencia}")



if __name__ == "__main__":
    print("="*60)
    print("🎲 SCRAPER LOTO.HN - 7 JUEGOS 🎲")
    print("="*60)
    print("📌 Estrategia: Identificar por color + orden")
    print("="*60 + "\n")
    
    scraper = LotoHnScraper()
    
    # Debug activado para monitorear en producción
    resultados = scraper.obtener_resultados(debug=True)
    
    scraper.mostrar_resumen(resultados)
    
    if resultados:
        scraper.guardar_json(resultados)
        print("\n✅ Proceso completado exitosamente")
    else:
        print("\n⚠️  No se encontraron resultados")