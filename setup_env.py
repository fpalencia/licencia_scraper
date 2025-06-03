#!/usr/bin/env python3
"""
Script para configurar el archivo .env correctamente
"""

env_content = """TARGET_URL=https://tramites.munistgo.cl/reservahoralicencia/
ERROR_URL_PATTERN=paso-1.aspx?Error=No%20existen%20horas%20disponibles
RETRY_INTERVAL_MINUTES=30
RUT_EJEMPLO=25334838-0
HEADLESS_MODE=False
BROWSER_TYPE=chromium"""

with open('.env', 'w', encoding='utf-8') as f:
    f.write(env_content)

print("✅ Archivo .env creado correctamente")
print("Contenido:")
print(env_content) 