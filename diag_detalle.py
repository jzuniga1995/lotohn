"""Temporal: revisa si la página interna de un juego trae el sorteo de hoy
cuando la tarjeta de la portada aparece vacía."""
import re
import time
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

SLUGS = ['juga-3-11am', 'la-diaria-10am', 'premia2-10am', 'pega-3-10am']


def volcar(page, url):
    print("=" * 70)
    print(f"URL: {url}")
    print("=" * 70)
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
    except Exception as e:
        print(f"  ❌ no cargó: {e}")
        return
    time.sleep(4)

    for sel in ['.past-score-ball', 'table', '.bg-slate-500']:
        els = page.query_selector_all(sel)
        print(f"  [{sel}] -> {len(els)} elementos")
        for el in els[:12]:
            txt = re.sub(r'\s+', ' ', el.inner_text() or '').strip()
            if txt:
                print(f"      {txt[:160]!r}")

    # Cualquier fecha dd-mm visible en la página
    cuerpo = re.sub(r'\s+', ' ', page.inner_text('body') or '')
    fechas = sorted(set(re.findall(r'\b\d{2}-\d{2}\b', cuerpo)))
    print(f"  fechas dd-mm en la página: {fechas[:20]}")
    print(f"  primeros 600 chars: {cuerpo[:600]!r}")


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(user_agent=UA).new_page()
    for slug in SLUGS:
        volcar(page, f"https://loteriasdehonduras.com/loto-hn/{slug}/")
    b.close()
