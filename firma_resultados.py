#!/usr/bin/env python3
"""Huella de los resultados publicados, sin los sellos de tiempo.

`resultados_hoy.json` cambia en TODAS las corridas aunque no haya sorteo nuevo:
`fecha_actualizacion` y cada `fecha_consulta` llevan la hora de la corrida. Por
eso el `git diff` del workflow nunca sale vacío y no sirve para decidir si hay
algo nuevo que publicar.

Acá se resume sólo lo que un visitante llega a ver. Si la huella no cambió, el
sorteo es el mismo y no hace falta reconstruir el sitio.
"""

import hashlib
import json
import sys

CAMPOS = ('nombre_juego', 'fecha_sorteo', 'hora_sorteo',
          'numero_ganador', 'numeros_individuales', 'numeros_adicionales')


def firma(archivo='resultados_hoy.json'):
    try:
        with open(archivo, encoding='utf-8') as f:
            sorteos = json.load(f).get('sorteos', {})
    except (OSError, ValueError):
        # Sin archivo o ilegible: huella vacía, que nunca coincide con una real
        return ''

    resumen = {
        clave: {campo: sorteos[clave].get(campo) for campo in CAMPOS}
        for clave in sorted(sorteos)
    }
    crudo = json.dumps(resumen, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(crudo.encode('utf-8')).hexdigest()


if __name__ == '__main__':
    print(firma(sys.argv[1] if len(sys.argv) > 1 else 'resultados_hoy.json'))
