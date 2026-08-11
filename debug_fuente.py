"""Script temporal de diagnóstico: vuelca las llamadas de red y las tarjetas
de resultados de loteriasdehonduras.com. Se elimina después de usarlo."""

import re

from playwright.sync_api import sync_playwright

URL = "https://loteriasdehonduras.com/"
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

IGNORAR = ('.js', '.css', '.png', '.jpg', '.jpeg', '.webp', '.svg', '.woff',
           '.woff2', '.ttf', '.ico', '.gif', '.mp4')


def main():
    urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=UA).new_page()

        page.on('request', lambda r: urls.append((r.method, r.url, r.resource_type)))
        page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(8000)

        print("=" * 70)
        print(f"=== PETICIONES ({len(urls)}) — filtradas ===")
        print("=" * 70)
        candidatas = []
        for metodo, u, tipo in urls:
            if any(u.split('?')[0].endswith(ext) for ext in IGNORAR):
                continue
            print(f"  [{tipo:10s}] {metodo} {u}")
            if tipo in ('xhr', 'fetch'):
                candidatas.append(u)

        print("\n" + "=" * 70)
        print("=== CUERPOS DE LAS XHR/FETCH ===")
        print("=" * 70)
        for u in dict.fromkeys(candidatas):
            try:
                r = page.request.get(u)
                ct = r.headers.get('content-type', '')
                print(f"\n----- [{r.status}] {ct} {u} -----")
                print(r.text()[:5000])
            except Exception as e:
                print(f"\n----- ERROR {u}: {e}")

        print("\n" + "=" * 70)
        print("=== TARJETAS .p-card (outerHTML) ===")
        print("=" * 70)
        cards = page.query_selector_all('.p-card')
        print(f"total .p-card = {len(cards)}")
        for i, c in enumerate(cards[:20]):
            texto = re.sub(r'\s+', ' | ', c.inner_text().strip())
            print(f"\n----- CARD[{i}] texto: {texto[:200]}")
            print(c.evaluate('el => el.outerHTML')[:2200])

        browser.close()


if __name__ == '__main__':
    main()
