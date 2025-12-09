# 🎯 Scraper Loto Honduras

Scraper automático de resultados de Loto Honduras.

## 📊 Sorteos monitoreados

- Jugá 3 (11:00 AM, 3:00 PM, 9:00 PM)
- Pega 3 (11:00 AM, 3:00 PM, 9:00 PM)
- Premia 2 (11:00 AM, 3:00 PM, 9:00 PM)
- La Diaria (3:00 PM, 9:00 PM)
- Super Premio (9:00 PM)

## ⏰ Ejecución automática

El scraper se ejecuta automáticamente **3 veces al día**:
- 11:05 AM (Honduras)
- 3:05 PM (Honduras)
- 9:05 PM (Honduras)

*5 minutos después de cada sorteo principal*

## 📁 Archivos generados

- `resultados_hoy.json` - Resultados actualizados en formato JSON

## 🔗 Uso

Los resultados se pueden consumir desde:
```
https://raw.githubusercontent.com/TU_USUARIO/scraper-loto-honduras/main/resultados_hoy.json
```

## 🛠️ Instalación local

```bash
pip install -r requirements.txt
python loto_scraper.py
```

## 📝 Licencia

MIT