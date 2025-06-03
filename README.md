# 🚗 Scraper de Licencias de Conducir - Municipalidad de Santiago

Este proyecto automatiza la verificación de disponibilidad de citas para renovación u obtención de licencias de conducir en la Municipalidad de Santiago de Chile.

## 📋 Características

- ✅ Verificación automática de disponibilidad de citas
- 🔄 Monitoreo continuo cada 30 minutos (configurable)
- 📸 Capturas de pantalla automáticas para debugging
- 📝 Logging detallado de todas las operaciones
- 🎨 Interfaz colorida en consola para mejor visualización
- ⚙️ Configuración flexible mediante variables de entorno
- 🌐 Soporte para múltiples navegadores (Chromium, Firefox, WebKit)

## 🛠️ Instalación

### Prerrequisitos

- Python 3.8 o superior
- Windows 10/11 (el script está optimizado para Windows)

### Pasos de instalación

1. **Clonar o descargar el proyecto**
   ```bash
   # Si tienes git instalado
   git clone <url-del-repositorio>
   cd licencia_scraper
   ```

2. **Crear entorno virtual**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Instalar dependencias**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Instalar navegadores de Playwright**
   ```powershell
   playwright install
   ```

## ⚙️ Configuración

El archivo `.env` contiene las configuraciones principales:

```env
# URL del sitio web
TARGET_URL=https://tramites.munistgo.cl/reservahoralicencia/

# Patrón de URL que indica falta de disponibilidad
ERROR_URL_PATTERN=paso-1.aspx?Error=No%20existen%20horas%20disponibles

# Intervalo entre verificaciones (en minutos)
RETRY_INTERVAL_MINUTES=30

# RUT de ejemplo para pruebas
RUT_EJEMPLO=13177777-7

# Modo headless (True/False)
HEADLESS_MODE=False

# Tipo de navegador (chromium/firefox/webkit)
BROWSER_TYPE=chromium
```

### Personalización

- **RUT_EJEMPLO**: Cambia este valor por tu RUT real
- **RETRY_INTERVAL_MINUTES**: Ajusta el intervalo entre verificaciones
- **HEADLESS_MODE**: 
  - `False`: Muestra el navegador (recomendado para debugging)
  - `True`: Ejecuta en segundo plano sin mostrar ventana
- **BROWSER_TYPE**: Elige entre `chromium`, `firefox`, o `webkit`

## 🚀 Uso

### Activar entorno virtual
```powershell
.\venv\Scripts\Activate.ps1
```

### Ejecutar el scraper
```powershell
python licencia_scraper.py
```

### Opciones de ejecución

El programa ofrece dos modos:

1. **Verificación única**: Ejecuta una sola verificación y termina
2. **Monitoreo continuo**: Verifica cada 30 minutos hasta encontrar disponibilidad

## 📊 Funcionamiento del Script

### Paso a Paso

1. **Inicialización del navegador**
   - Configura Playwright con opciones anti-detección
   - Establece user-agent real y configuraciones de viewport
   - Configura timeouts apropiados

2. **Navegación al sitio**
   - Accede a la URL de reserva de licencias
   - Verifica que la página cargue correctamente
   - Toma screenshot para debugging

3. **Llenado del formulario**
   - Busca el campo de RUT usando múltiples selectores
   - Ingresa el RUT configurado
   - Busca y hace clic en el botón de envío

4. **Verificación de disponibilidad**
   - Analiza la URL resultante
   - Busca patrones de texto que indiquen disponibilidad/falta de disponibilidad
   - Examina elementos DOM que sugieran el siguiente paso del proceso

5. **Reporte de resultados**
   - Muestra el estado de la verificación con colores
   - Guarda logs detallados
   - Toma screenshots de los resultados

### Detección de Estados

El script puede detectar:

- ✅ **Citas disponibles**: Cuando encuentra elementos de selección de fecha/hora
- ❌ **Sin disponibilidad**: Cuando detecta mensajes de error o URLs específicas
- ⚠️ **Estado incierto**: Cuando no puede determinar el estado automáticamente

## 📁 Archivos Generados

- `licencia_scraper.log`: Log detallado de todas las operaciones
- `screenshot_step2_*.png`: Screenshot de la página inicial
- `screenshot_result_*.png`: Screenshot del resultado de cada verificación

## 🔧 Explicación del Código

### Estructura Principal

```python
class LicenciaScraper:
    def __init__(self):
        # Carga configuraciones desde .env
        # Inicializa variables de estado
        # Configura sistema de logging
```

### Métodos Principales

- **`initialize_browser()`**: Configura y lanza el navegador con opciones anti-detección
- **`navigate_to_site()`**: Navega al sitio web y verifica la carga
- **`fill_rut_form()`**: Automatiza el llenado del formulario de RUT
- **`check_availability()`**: Analiza la respuesta para determinar disponibilidad
- **`run_single_check()`**: Ejecuta una verificación completa
- **`run_continuous_monitoring()`**: Ejecuta verificaciones periódicas

### Sistema de Logging

```python
def _setup_logging(self):
    # Configura logging tanto a archivo como a consola
    # Formato: timestamp - nivel - mensaje
    # Encoding UTF-8 para caracteres especiales
```

### Manejo de Errores

- Captura y registra todos los errores
- Limpia recursos automáticamente
- Proporciona mensajes informativos al usuario

## 🎨 Características Visuales

- **Colores en consola**: Usa `colorama` para mejor visualización
- **Emojis informativos**: Facilita la identificación rápida del estado
- **Formato consistente**: Pasos numerados y separadores visuales
- **Cuenta regresiva**: Muestra tiempo restante entre verificaciones

## 🔍 Debugging

### Screenshots Automáticos
- Se toman capturas en puntos clave del proceso
- Nombres con timestamp para fácil identificación
- Útiles para diagnosticar problemas

### Logs Detallados
- Registro completo de todas las operaciones
- Niveles de log apropiados (INFO, WARNING, ERROR)
- Timestamps precisos para análisis temporal

### Modo No-Headless
- Ejecuta con `HEADLESS_MODE=False` para ver el navegador
- Permite observar el comportamiento en tiempo real
- Útil para debugging y verificación manual

## ⚠️ Consideraciones Importantes

1. **Uso Responsable**: Este script está diseñado para uso personal y verificación de disponibilidad
2. **Respeto por el Servidor**: El intervalo de 30 minutos evita sobrecargar el servidor
3. **Términos de Servicio**: Asegúrate de cumplir con los términos del sitio web
4. **Datos Personales**: Usa tu RUT real para verificaciones efectivas

## 🐛 Solución de Problemas

### Error: "No se pudo encontrar el campo de RUT"
- Verifica que el sitio web esté accesible
- El sitio puede haber cambiado su estructura HTML
- Revisa los screenshots generados para análisis visual

### Error: "Timeout"
- Verifica tu conexión a internet
- El sitio puede estar experimentando alta carga
- Aumenta los timeouts en el código si es necesario

### Error: "Navegador no se inicia"
- Ejecuta `playwright install` nuevamente
- Verifica que tienes permisos suficientes
- Prueba con un navegador diferente

## 📞 Soporte

Si encuentras problemas:

1. Revisa los logs en `licencia_scraper.log`
2. Examina los screenshots generados
3. Verifica la configuración en `.env`
4. Asegúrate de que todas las dependencias están instaladas

## 📄 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

---

**Nota**: Este script es una herramienta de automatización para verificar disponibilidad de citas. No garantiza la obtención de una cita y debe usarse de manera responsable. 