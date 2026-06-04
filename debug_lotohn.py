"""
Script de diagnóstico para loto.hn
Corre esto localmente y pega el output para ajustar los selectores del scraper principal.

Uso:
    python3 debug_lotohn.py
"""

from playwright.sync_api import sync_playwright
import time

URL = "https://loto.hn/?pag=body"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        print(f"Cargando {URL} ...")
        page.goto(URL, wait_until='networkidle', timeout=60000)
        time.sleep(3)

        print(f"Título: {page.title()}")
        print("=" * 70)

        # Imprimir HTML completo (para análisis)
        body_html = page.content()
        with open("debug_lotohn_output.html", "w", encoding="utf-8") as f:
            f.write(body_html)
        print("HTML completo guardado en: debug_lotohn_output.html")
        print("=" * 70)

        # Intentar detectar elementos con números
        selectores_prueba = [
            '[class*="result"]',
            '[class*="numero"]',
            '[class*="number"]',
            '[class*="ganador"]',
            '[class*="winner"]',
            '[class*="sorteo"]',
            '[class*="premio"]',
            '[class*="ball"]',
            'table td',
            '.resultado',
            '.numero',
        ]

        for sel in selectores_prueba:
            elementos = page.query_selector_all(sel)
            if elementos:
                print(f"\nSelector '{sel}' → {len(elementos)} elementos:")
                for i, elem in enumerate(elementos[:5]):
                    try:
                        clase = elem.get_attribute('class') or ''
                        texto = elem.inner_text().strip()[:80]
                        print(f"  [{i}] class='{clase}' | texto='{texto}'")
                    except:
                        pass

        print("\n" + "=" * 70)
        print("HTML del body (primeros 8000 chars):")
        body = page.query_selector('body')
        if body:
            print(body.inner_html()[:8000])

        browser.close()

if __name__ == "__main__":
    main()
