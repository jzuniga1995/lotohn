"""Temporal: Juga 3 y La Diaria no se leen ni de la portada ni de su pagina.
Volcamos la fila mas reciente de su pagina para ver con que clase pintan
el resultado actual (Pega 3 y Premia 2 usan .score-shape-circle)."""
import time
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

SLUGS = ['juga-3-11am', 'la-diaria-10am', 'pega-3-10am']

JS = """() => {
    const et = [...document.querySelectorAll('.bg-slate-500')]
        .find(e => e.textContent.trim().match(/^\\d{2}-\\d{2}$/));
    if (!et) return {error: 'sin etiqueta de fecha'};
    let n = et;
    for (let i = 0; i < 4 && n.parentElement; i++) n = n.parentElement;
    return {
        texto: (n.innerText || '').replace(/\\s+/g, ' ').trim(),
        html: n.outerHTML,
        // cada elemento con su clase y su texto, para ubicar las bolas
        elementos: [...n.querySelectorAll('*')]
            .map(e => ({cls: e.className, txt: (e.innerText || '').replace(/\\s+/g,' ').trim()}))
            .filter(x => typeof x.cls === 'string' && x.cls && x.txt.length <= 30),
    };
}"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_context(user_agent=UA).new_page()
    for slug in SLUGS:
        print("=" * 70)
        print(f"SLUG: {slug}")
        print("=" * 70)
        try:
            page.goto(f"https://loteriasdehonduras.com/loto-hn/{slug}/",
                      wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            print(f"  no cargo: {e}")
            continue
        time.sleep(4)
        r = page.evaluate(JS)
        if r.get('error'):
            print(f"  {r['error']}")
            continue
        print(f"  texto fila: {r['texto'][:120]!r}")
        print(f"  --- elementos (clase -> texto) ---")
        for e in r['elementos']:
            print(f"      {e['cls'][:60]:60} -> {e['txt'][:40]!r}")
        print(f"  --- html ---")
        print("  " + r['html'][:1600].replace('\n', ' '))
    b.close()
