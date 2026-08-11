"""Temporal: la fila más reciente de la página interna no usa .past-score-ball.
Subimos hasta el contenedor que ya incluye los números para ver cómo se pintan."""
import time
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

SLUGS = ['juga-3-11am', 'la-diaria-10am', 'pega-3-10am', 'premia2-10am']

JS = """(nivel) => {
    const et = [...document.querySelectorAll('.bg-slate-500')]
        .find(e => e.textContent.trim().match(/^\\d{2}-\\d{2}$/));
    if (!et) return {html: 'sin etiqueta', text: '', clases: []};
    let n = et;
    for (let i = 0; i < nivel && n.parentElement; i++) n = n.parentElement;
    return {
        html: n.outerHTML,
        text: (n.innerText || '').replace(/\\s+/g, ' ').trim(),
        clases: [...new Set([...n.querySelectorAll('*')]
            .map(e => e.className).filter(c => typeof c === 'string' && c))],
    };
}"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(user_agent=UA).new_page()

    for slug in SLUGS:
        url = f"https://loteriasdehonduras.com/loto-hn/{slug}/"
        print("=" * 70)
        print(f"URL: {url}")
        print("=" * 70)
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            print(f"  ❌ no cargó: {e}")
            continue
        time.sleep(4)

        for nivel in (4, 5):
            r = page.evaluate(JS, nivel)
            print(f"\n  --- nivel {nivel} | texto: {r['text'][:120]!r}")
            print(f"  HTML ({len(r['html'])} chars):")
            print("  " + r['html'][:2200].replace('\n', ' '))
            print(f"  clases: {r['clases'][:22]}")

    b.close()
