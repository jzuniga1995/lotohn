"""Script temporal de diagnóstico: vuelca la estructura de loteriasdehonduras.com
para poder escribir los selectores del scraper. Se elimina después de usarlo."""

import re
import sys

import requests
from bs4 import BeautifulSoup

URL = "https://loteriasdehonduras.com/"
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

JUEGOS = ['diaria', 'pega', 'premia', 'jug', 'super premio', 'bingo', 'multi', 'gana']


def limpiar(soup):
    for t in soup(['script', 'style', 'noscript', 'svg']):
        t.decompose()
    return soup


def dump_texto(html, etiqueta):
    soup = limpiar(BeautifulSoup(html, 'html.parser'))
    txt = soup.get_text('\n', strip=True)
    txt = re.sub(r'\n{2,}', '\n', txt)
    print(f"\n{'=' * 70}\n=== TEXTO RENDERIZADO [{etiqueta}] (primeros 9000 chars) ===\n{'=' * 70}")
    print(txt[:9000])
    return soup


def dump_bloques(soup, etiqueta):
    """Imprime el HTML de los contenedores que rodean cada nombre de juego."""
    print(f"\n{'=' * 70}\n=== BLOQUES POR JUEGO [{etiqueta}] ===\n{'=' * 70}")
    vistos = set()
    for nodo in soup.find_all(string=True):
        texto = (nodo.strip() or '').lower()
        if not texto or len(texto) > 60:
            continue
        if not any(j in texto for j in JUEGOS):
            continue
        # subir hasta un ancestro con algo de contenido
        cont = nodo.parent
        for _ in range(4):
            if cont is None or cont.parent is None:
                break
            if len(cont.get_text(' ', strip=True)) > 40:
                break
            cont = cont.parent
        if cont is None:
            continue
        html = str(cont)[:1800]
        clave = html[:120]
        if clave in vistos:
            continue
        vistos.add(clave)
        print(f"\n----- match: {texto!r} | tag=<{cont.name}> class={cont.get('class')} -----")
        print(html)
        if len(vistos) >= 25:
            break


def dump_clases(soup, etiqueta):
    """Clases más comunes, para detectar el patrón de tarjetas/bolas."""
    from collections import Counter
    c = Counter()
    for el in soup.find_all(True):
        for cls in (el.get('class') or []):
            c[cls] += 1
    print(f"\n{'=' * 70}\n=== CLASES MÁS COMUNES [{etiqueta}] ===\n{'=' * 70}")
    for cls, n in c.most_common(60):
        print(f"  {n:4d}  {cls}")


def via_requests():
    print(f"\n\n########## FUENTE ESTÁTICA (requests) — {URL} ##########")
    r = requests.get(URL, headers={'User-Agent': UA}, timeout=30)
    print(f"STATUS={r.status_code} LEN={len(r.text)}")
    print(f"CONTENT-TYPE={r.headers.get('content-type')}")
    soup = dump_texto(r.text, 'requests')
    dump_clases(soup, 'requests')
    dump_bloques(soup, 'requests')
    return r.text


def via_playwright():
    print(f"\n\n########## FUENTE RENDERIZADA (playwright) — {URL} ##########")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"playwright no disponible: {e}")
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=UA).new_page()
        page.goto(URL, wait_until='networkidle', timeout=60000)
        page.wait_for_timeout(3000)
        html = page.content()
        print(f"LEN={len(html)}")
        soup = dump_texto(html, 'playwright')
        dump_clases(soup, 'playwright')
        dump_bloques(soup, 'playwright')
        browser.close()


if __name__ == '__main__':
    try:
        via_requests()
    except Exception as e:
        print(f"ERROR requests: {e}")
    if '--solo-requests' not in sys.argv:
        try:
            via_playwright()
        except Exception as e:
            print(f"ERROR playwright: {e}")
