"""Script temporal de diagnóstico: vuelca las llamadas de red y las tarjetas
de resultados de loteriasdehonduras.com. Se elimina después de usarlo."""

import json
import re

from playwright.sync_api import sync_playwright

URL = "https://loteriasdehonduras.com/"
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


def main():
    capturas = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=UA).new_page()

        def on_response(resp):
            try:
                ct = (resp.headers.get('content-type') or '')
                if 'json' not in ct:
                    return
                capturas.append((resp.url, resp.status, resp.text()[:6000]))
            except Exception as e:
                capturas.append((resp.url, -1, f"ERROR leyendo: {e}"))

        page.on('response', on_response)
        page.goto(URL, wait_until='networkidle', timeout=60000)
        page.wait_for_timeout(4000)

        print("=" * 70)
        print(f"=== RESPUESTAS JSON CAPTURADAS: {len(capturas)} ===")
        print("=" * 70)
        for url, status, body in capturas:
            print(f"\n----- [{status}] {url} -----")
            print(body)

        print("\n" + "=" * 70)
        print("=== TARJETAS .p-card (outerHTML) ===")
        print("=" * 70)
        cards = page.query_selector_all('.p-card')
        print(f"total .p-card = {len(cards)}")
        for i, c in enumerate(cards[:24]):
            html = c.evaluate('el => el.outerHTML')
            texto = re.sub(r'\s+', ' | ', c.inner_text().strip())
            print(f"\n----- CARD[{i}] texto: {texto[:200]}")
            print(html[:2500])

        # Contenedor padre de las tarjetas: revela el grid de resultados
        print("\n" + "=" * 70)
        print("=== PADRES DE LAS TARJETAS ===")
        print("=" * 70)
        vistos = set()
        for c in cards[:24]:
            info = c.evaluate("""el => {
                const p = el.parentElement, g = p && p.parentElement;
                return JSON.stringify({
                    padre: p ? p.className : null,
                    abuelo: g ? g.className : null,
                    hermanos: p ? p.children.length : 0
                });
            }""")
            if info not in vistos:
                vistos.add(info)
                print(info)

        browser.close()


if __name__ == '__main__':
    main()
