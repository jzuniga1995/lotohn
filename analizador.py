import json
import os
import random
from collections import Counter
from datetime import datetime, timedelta, timezone


HISTORIAL_URL = "https://raw.githubusercontent.com/jzuniga1995/lotohn/main/historial.json"

JUEGOS = {
    'juga3':        'Jugá 3',
    'pega_3':       'Pega 3',
    'premia2':      'Premia 2',
    'la_diaria':    'La Diaria',
    'super_premio': 'Súper Premio',
}

SORTEOS_A_ANALIZAR = 30


def cargar_historial() -> dict:
    try:
        import requests
        resp = requests.get(HISTORIAL_URL, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️  No se pudo cargar historial remoto: {e}")

    if os.path.exists("historial.json"):
        with open("historial.json", "r", encoding="utf-8") as f:
            return json.load(f)

    return {}


def extraer_sorteos_juego(historial: dict, slug: str) -> list:
    resultados = []
    for fecha in sorted(historial.keys(), reverse=True):
        for key, nums in historial[fecha].items():
            if (key.startswith(slug) or key == slug) and isinstance(nums, list) and nums:
                resultados.append({"fecha": fecha, "key": key, "nums": nums})
        if len(resultados) >= SORTEOS_A_ANALIZAR:
            break
    return resultados[:SORTEOS_A_ANALIZAR]


def extraer_numeros(sorteos: list, slug: str) -> list:
    """Extrae solo los valores numéricos según el juego."""
    nums = []
    for s in sorteos:
        for n in s['nums']:
            # la_diaria: ignorar signo y multiplicador (no son dígitos puros)
            if slug == 'la_diaria':
                try:
                    int(n)
                    nums.append(n.zfill(2))
                except ValueError:
                    pass
            else:
                nums.append(n)
    return nums


def analizar_juego(slug: str, nombre: str, sorteos: list) -> dict:
    if not sorteos:
        return _fallback(slug, 0)

    todos = extraer_numeros(sorteos, slug)
    recientes = extraer_numeros(sorteos[:7], slug)

    freq_total   = Counter(todos)
    freq_reciente = Counter(recientes)

    mas_frecuentes  = [n for n, _ in freq_total.most_common(8)]
    menos_frecuentes = [n for n, _ in freq_total.most_common()[:-9:-1]]
    top_recientes   = [n for n, _ in freq_reciente.most_common(5)]

    patrones  = _describir_patrones(freq_total, mas_frecuentes)
    tendencias = _describir_tendencias(top_recientes, mas_frecuentes)
    sugerencias = _generar_sugerencias(slug, mas_frecuentes, freq_total)
    advertencia = "La lotería es un juego de azar. Juega con responsabilidad."

    return {
        "patrones":           patrones,
        "tendencias":         tendencias,
        "sugerencias":        sugerencias,
        "advertencia":        advertencia,
        "sorteos_analizados": len(sorteos),
    }


def _describir_patrones(freq: Counter, top: list) -> str:
    top3 = top[:3]
    conteos = [f"{n}({freq[n]}v)" for n in top3]
    return f"Más frecuentes: {', '.join(conteos)} en {sum(freq.values())} sorteos analizados."


def _describir_tendencias(recientes: list, historicos: list) -> str:
    coinciden = [n for n in recientes if n in historicos[:5]]
    if coinciden:
        return f"Los números {', '.join(coinciden[:3])} son frecuentes tanto en el historial como en sorteos recientes."
    return f"Últimos sorteos muestran números distintos al patrón histórico: {', '.join(recientes[:3])}."


def _generar_sugerencias(slug: str, top: list, freq: Counter) -> list:
    pool = top[:10] if len(top) >= 10 else top

    if slug == 'juga3':
        # 1 número de 3 dígitos
        candidatos = list(freq.most_common(10))
        return [n for n, _ in candidatos[:3]]

    if slug == 'pega_3':
        # 3 números de 2 dígitos separados por guión
        sugs = []
        usados = list(pool)
        random.seed(42)
        for i in range(3):
            sample = random.sample(usados, min(3, len(usados)))
            sugs.append('-'.join(sorted(sample)))
        return sugs

    if slug == 'premia2':
        # 2 números de 2 dígitos separados por guión
        sugs = []
        random.seed(7)
        for i in range(3):
            sample = random.sample(pool, min(2, len(pool)))
            sugs.append('-'.join(sorted(sample)))
        return sugs

    if slug == 'la_diaria':
        # 1 número de 2 dígitos
        return [n for n, _ in freq.most_common(3)]

    if slug == 'super_premio':
        # 6 números del 01 al 33
        validos = [n for n in pool if 1 <= int(n) <= 33]
        # completar con números del rango si faltan
        todos_rango = [f"{i:02d}" for i in range(1, 34)]
        extra = [n for n in todos_rango if n not in validos]
        random.seed(13)
        random.shuffle(extra)
        combinado = (validos + extra)[:18]
        sugs = []
        for i in range(3):
            chunk = sorted(combinado[i*6:(i+1)*6], key=lambda x: int(x))
            sugs.append('-'.join(chunk))
        return sugs

    return pool[:3]


def _fallback(slug: str, n: int) -> dict:
    return {
        "patrones":           "No hay suficientes datos para analizar.",
        "tendencias":         "Intenta de nuevo cuando haya más historial disponible.",
        "sugerencias":        [],
        "advertencia":        "La lotería es un juego de azar.",
        "sorteos_analizados": n,
    }


def generar_analisis() -> dict | None:
    print("📂 Cargando historial...")
    historial = cargar_historial()

    if not historial:
        print("❌ Historial vacío, abortando.")
        return None

    fecha_hn = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d")
    resultado = {
        "fecha":       fecha_hn,
        "generado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "juegos":      {}
    }

    for slug, nombre in JUEGOS.items():
        print(f"\n📊 Analizando {nombre} ({slug})...")
        sorteos = extraer_sorteos_juego(historial, slug)
        print(f"   📈 {len(sorteos)} sorteos encontrados")
        analisis = analizar_juego(slug, nombre, sorteos)
        resultado["juegos"][slug] = analisis
        print(f"   ✅ {nombre} analizado")

    return resultado


def main():
    print("🧠 ANALIZADOR DE NÚMEROS — LOTO HONDURAS")
    print("=" * 60)

    fecha_hn = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d")
    print(f"📅 Fecha Honduras: {fecha_hn}")

    analisis = generar_analisis()

    if not analisis:
        print("❌ No se pudo generar el análisis.")
        return False

    with open("analisis.json", "w", encoding="utf-8") as f:
        json.dump(analisis, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Guardado: analisis.json")

    print("\n" + "=" * 60)
    print("📊 RESUMEN:")
    for slug, data in analisis["juegos"].items():
        n = data.get("sorteos_analizados", 0)
        ok = "✅" if data.get("sugerencias") else "⚠️ "
        print(f"  {ok} {JUEGOS.get(slug, slug)}: {n} sorteos — {data['sugerencias']}")
    print("=" * 60)

    return True


if __name__ == "__main__":
    main()
