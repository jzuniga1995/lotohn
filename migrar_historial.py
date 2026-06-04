"""
Migra historial.json del formato viejo (objeto con 8 campos) al formato nuevo
(solo array de números). Sobreescribe el mismo archivo.

Uso:
    python3 migrar_historial.py
"""

import json
import os

ARCHIVO = 'historial.json'


def migrar(entrada: dict) -> dict:
    nuevo = {}
    for fecha, sorteos in entrada.items():
        nuevo[fecha] = {}
        for key, data in sorteos.items():
            # Ya está en formato nuevo (lista) → conservar tal cual
            if isinstance(data, list):
                nuevo[fecha][key] = data
                continue

            # Formato viejo (dict) → extraer solo los números
            nums = data.get('numeros_adicionales') or []

            # Fallback: si numeros_adicionales está vacío, usar numero_ganador
            if not nums and data.get('numero_ganador'):
                nums = [data['numero_ganador']]

            nuevo[fecha][key] = nums

    return nuevo


def main():
    if not os.path.exists(ARCHIVO):
        print(f"❌ No se encontró {ARCHIVO}")
        return

    with open(ARCHIVO, 'r', encoding='utf-8') as f:
        historial = json.load(f)

    total_fechas  = len(historial)
    total_sorteos = sum(len(s) for s in historial.values())

    print(f"📂 Leyendo {ARCHIVO}: {total_fechas} fechas, {total_sorteos} sorteos")

    migrado = migrar(historial)

    # Guardar compacto (sin indentación ni espacios extra)
    with open(ARCHIVO, 'w', encoding='utf-8') as f:
        json.dump(migrado, f, ensure_ascii=False, separators=(',', ':'))

    size_kb = os.path.getsize(ARCHIVO) / 1024
    print(f"✅ Migración completa → {ARCHIVO} ({size_kb:.1f} KB)")
    print(f"   {total_fechas} fechas | {total_sorteos} sorteos")


if __name__ == '__main__':
    main()
