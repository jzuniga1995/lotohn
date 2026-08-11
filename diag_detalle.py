"""Temporal: la fila más reciente de la página interna no usa .past-score-ball.
Volcamos su HTML para descubrir con qué clase se pinta."""
import re
import time
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

SLUGS = ['juga-3-11am', 'la-diaria-10am', 'pega-3-10am']


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

        # Subimos desde la etiqueta de fecha hasta la fila que la contiene
        for nivel in (1, 2, 3):
            html = page.evaluate("""(nivel) => {
                const et = [...document.querySelectorAll('.bg-slate-500')]
                    .find(e => e.textContent.trim().match(/^\\d{2}-\\d{2}$/));
                if (!et) return 'sin etiqueta';
                let n = et;
                for (let i = 0; i < nivel && n.parentElement; i++) n = n.parentElement;
                return n.outerHTML;
            }""", nivel)
            print(f"\n  --- ancestro nivel {nivel} ({len(html)} chars) ---")
            print("  " + html[:1800].replace('\n', ' '))

        # Todas las clases que aparecen dentro de la primera fila
        clases = page.evaluate("""() => {
            const et = [...document.querySelectorAll('.bg-slate-500')]
                .find(e => e.textContent.trim().match(/^\\d{2}-\\d{2}$/));
            if (!et) return [];
            let fila = et;
            for (let i = 0; i < 3 && fila.parentElement; i++) fila = fila.parentElement;
            return [...new Set([...fila.querySelectorAll('*')]
                .map(e => e.className).filter(c => typeof c === 'string' && c))];
        }""")
        print(f"\n  --- clases dentro de la fila ---")
        for c in clases[:30]:
            print(f"      {c[:150]}")

    b.close()
