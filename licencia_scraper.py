#!/usr/bin/env python3
"""
Scraper para reserva de licencias de conducir - Municipalidad de Santiago
Este script automatiza el proceso de verificación de disponibilidad de citas
para renovación o obtención de licencias de conducir.
"""

import asyncio
import time
import logging
import re
from datetime import datetime
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from colorama import init, Fore, Style, Back

# Inicializar colorama para colores en Windows
init(autoreset=True)

# Cargar variables de entorno
load_dotenv()

class LicenciaScraper:
    """
    Clase principal para el scraper de licencias de conducir.
    
    Esta clase maneja toda la lógica de automatización web usando Playwright
    para verificar la disponibilidad de citas en el sitio de la Municipalidad de Santiago.
    """
    
    def __init__(self):
        """Inicializa el scraper con configuraciones desde variables de entorno."""
        # URLs y patrones de configuración
        self.target_url = os.getenv('TARGET_URL', 'https://tramites.munistgo.cl/reservahoralicencia/')
        self.error_url_pattern = os.getenv('ERROR_URL_PATTERN', 'paso-1.aspx?Error=No%20existen%20horas%20disponibles')
        
        # Configuraciones de tiempo y comportamiento
        self.retry_interval = int(os.getenv('RETRY_INTERVAL_MINUTES', '30'))
        self.rut_ejemplo = os.getenv('RUT_EJEMPLO', '25334838-0')
        self.headless_mode = os.getenv('HEADLESS_MODE', 'False').lower() == 'true'
        self.browser_type = os.getenv('BROWSER_TYPE', 'chromium')
        
        # Variables de estado
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.attempt_count = 0
        
        # Variables de configuración del usuario
        self.user_rut: Optional[str] = None
        self.operation_type: Optional[str] = None  # 'crear' o 'modificar'
        
        # Configurar logging
        self._setup_logging()
        
    def _setup_logging(self):
        """Configura el sistema de logging para registrar todas las actividades."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('licencia_scraper.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def _validate_rut(self, rut: str) -> bool:
        """
        Valida si el RUT chileno tiene un formato correcto.
        
        Args:
            rut: RUT a validar (ej: 12345678-9)
            
        Returns:
            True si el formato es válido, False en caso contrario.
        """
        import re
        
        # Remover espacios y convertir a mayúsculas
        rut = rut.replace(" ", "").replace(".", "").upper()
        
        # Verificar formato básico: 7-8 dígitos + guión + dígito verificador
        if not re.match(r'^\d{7,8}-[\dK]$', rut):
            return False
            
        # Separar número y dígito verificador
        numero, dv = rut.split('-')
        
        # Calcular dígito verificador
        suma = 0
        multiplicador = 2
        
        for digit in reversed(numero):
            suma += int(digit) * multiplicador
            multiplicador += 1
            if multiplicador > 7:
                multiplicador = 2
                
        resto = suma % 11
        dv_calculado = 11 - resto
        
        if dv_calculado == 11:
            dv_calculado = '0'
        elif dv_calculado == 10:
            dv_calculado = 'K'
        else:
            dv_calculado = str(dv_calculado)
            
        return dv == dv_calculado
    
    def _format_rut(self, rut: str) -> str:
        """
        Formatea el RUT al formato estándar (sin puntos, con guión).
        
        Args:
            rut: RUT a formatear
            
        Returns:
            RUT formateado
        """
        # Remover espacios, puntos y convertir a mayúsculas
        rut = rut.replace(" ", "").replace(".", "").upper()
        
        # Si no tiene guión, agregarlo antes del último carácter
        if '-' not in rut and len(rut) >= 8:
            rut = rut[:-1] + '-' + rut[-1]
            
        return rut
    
    def get_user_input(self):
        """
        Solicita al usuario el RUT y el tipo de operación por terminal.
        """
        self.print_colored(f"\n{'🎯 CONFIGURACIÓN INTERACTIVA 🎯':^60}", 
                          Fore.MAGENTA, Style.BRIGHT)
        
        # Solicitar RUT
        while True:
            self.print_colored("\n📝 Ingrese su RUT (formato: 12345678-9):", Fore.CYAN)
            rut_input = input("RUT: ").strip()
            
            if not rut_input:
                self.print_colored("❌ Debe ingresar un RUT", Fore.RED)
                continue
                
            # Formatear RUT
            formatted_rut = self._format_rut(rut_input)
            
            # Validar RUT
            if self._validate_rut(formatted_rut):
                self.user_rut = formatted_rut
                self.print_colored(f"✅ RUT válido: {self.user_rut}", Fore.GREEN)
                break
            else:
                self.print_colored("❌ RUT inválido. Formato correcto: 12345678-9", Fore.RED)
                self.print_colored("   Ejemplo: 18977386-2", Fore.YELLOW)
        
        # Solicitar tipo de operación
        while True:
            self.print_colored("\n🔧 ¿Qué operación desea realizar?", Fore.CYAN)
            self.print_colored("1. 🆕 Crear nueva cita", Fore.BLUE)
            self.print_colored("2. ✏️  Modificar hora existente", Fore.BLUE)
            
            option = input("\nSeleccione una opción (1 o 2): ").strip()
            
            if option == "1":
                self.operation_type = "crear"
                self.print_colored("✅ Operación seleccionada: Crear nueva cita", Fore.GREEN)
                break
            elif option == "2":
                self.operation_type = "modificar"
                self.print_colored("✅ Operación seleccionada: Modificar hora existente", Fore.GREEN)
                break
            else:
                self.print_colored("❌ Opción inválida. Seleccione 1 o 2", Fore.RED)
        
        # Mostrar resumen de configuración
        self.print_colored(f"\n{'📋 RESUMEN DE CONFIGURACIÓN':^60}", Fore.CYAN, Style.BRIGHT)
        self.print_colored(f"RUT: {self.user_rut}", Fore.WHITE)
        self.print_colored(f"Operación: {self.operation_type.title()}", Fore.WHITE)
        self.print_colored(f"{'-':^60}", Fore.CYAN)
        
    async def _clear_browser_data(self):
        """Limpia todos los datos del navegador para evitar cache de forma agresiva."""
        try:
            if self.page:
                self.print_colored("🧹 Iniciando limpieza agresiva del navegador...", Fore.YELLOW)
                
                # Limpiar localStorage
                await self.page.evaluate("() => { try { localStorage.clear(); } catch(e) {} }")
                
                # Limpiar sessionStorage
                await self.page.evaluate("() => { try { sessionStorage.clear(); } catch(e) {} }")
                
                # Limpiar IndexedDB
                await self.page.evaluate("""
                    async () => {
                        try {
                            if ('indexedDB' in window) {
                                const databases = await indexedDB.databases();
                                await Promise.all(databases.map(db => {
                                    return new Promise((resolve, reject) => {
                                        const deleteReq = indexedDB.deleteDatabase(db.name);
                                        deleteReq.onsuccess = () => resolve();
                                        deleteReq.onerror = () => resolve(); // No fallar si no se puede
                                    });
                                }));
                            }
                        } catch(e) {
                            console.log('Error clearing IndexedDB:', e);
                        }
                    }
                """)
                
                # Limpiar WebSQL (si está disponible)
                await self.page.evaluate("""
                    () => {
                        try {
                            if ('openDatabase' in window) {
                                const db = openDatabase('', '', '', '');
                                if (db) {
                                    db.transaction(tx => {
                                        tx.executeSql('DELETE FROM data', [], () => {}, () => {});
                                    });
                                }
                            }
                        } catch(e) {
                            console.log('Error clearing WebSQL:', e);
                        }
                    }
                """)
                
                # Limpiar Application Cache
                await self.page.evaluate("""
                    () => {
                        try {
                            if ('applicationCache' in window && window.applicationCache) {
                                window.applicationCache.swapCache();
                            }
                        } catch(e) {
                            console.log('Error clearing Application Cache:', e);
                        }
                    }
                """)
                
                # Limpiar cookies del contexto
                await self.context.clear_cookies()
                
                # Limpiar cualquier formulario autollenado
                await self.page.evaluate("""
                    () => {
                        try {
                            // Limpiar todos los campos de input
                            const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"]');
                            inputs.forEach(input => {
                                input.value = '';
                                input.dispatchEvent(new Event('input', { bubbles: true }));
                                input.dispatchEvent(new Event('change', { bubbles: true }));
                            });
                        } catch(e) {
                            console.log('Error clearing form fields:', e);
                        }
                    }
                """)
                
                self.print_colored("✅ Limpieza agresiva del navegador completada", Fore.GREEN)
                
        except Exception as e:
            self.print_colored(f"⚠️ Error al limpiar datos del navegador: {str(e)}", Fore.YELLOW)
            # No es crítico, continuar
        
    def print_colored(self, message: str, color: str = Fore.WHITE, style: str = Style.NORMAL):
        """
        Imprime mensajes con colores para mejor visualización.
        
        Args:
            message: Mensaje a imprimir
            color: Color del texto (usando colorama)
            style: Estilo del texto (normal, bright, etc.)
        """
        print(f"{style}{color}{message}{Style.RESET_ALL}")
        
    def print_step(self, step_number: int, description: str):
        """
        Imprime el paso actual del proceso con formato consistente.
        
        Args:
            step_number: Número del paso
            description: Descripción del paso
        """
        self.print_colored(f"\n{'='*60}", Fore.CYAN)
        self.print_colored(f"PASO {step_number}: {description}", Fore.CYAN, Style.BRIGHT)
        self.print_colored(f"{'='*60}", Fore.CYAN)
        
    async def initialize_browser(self):
        """
        Inicializa el navegador y crea el contexto de navegación.
        
        Este método configura Playwright con las opciones necesarias para
        simular un navegador real y evitar detección de automatización.
        """
        self.print_step(1, "Inicializando navegador")
        
        try:
            # Crear instancia de Playwright
            self.playwright = await async_playwright().start()
            
            # Seleccionar tipo de navegador
            if self.browser_type.lower() == 'firefox':
                browser_launcher = self.playwright.firefox
            elif self.browser_type.lower() == 'webkit':
                browser_launcher = self.playwright.webkit
            else:
                browser_launcher = self.playwright.chromium
                
            self.print_colored(f"🌐 Lanzando navegador: {self.browser_type}", Fore.BLUE)
            
            # Configurar opciones del navegador
            browser_options = {
                'headless': self.headless_mode,
                'args': [
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--incognito',  # Modo incógnito
                    '--disable-save-password-bubble',  # No guardar contraseñas
                    '--disable-autofill',  # Deshabilitar autocompletado
                    '--disable-autofill-keyboard-accessory-view',
                    '--disable-full-form-autofill-ios',
                    '--disable-password-generation',
                    '--disable-password-manager',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-dev-shm-usage',
                    '--disable-gpu-sandbox',
                    '--disable-software-rasterizer',
                    '--disable-background-timer-throttling',
                    '--disable-renderer-backgrounding',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-ipc-flooding-protection',
                    '--disable-hang-monitor',
                    '--disable-client-side-phishing-detection',
                    '--disable-popup-blocking',
                    '--disable-prompt-on-repost',
                    '--disable-domain-reliability',
                    '--disable-component-extensions-with-background-pages'
                ]
            }
            
            # Lanzar navegador
            self.browser = await browser_launcher.launch(**browser_options)
            
            # Crear contexto con configuraciones para evitar cache
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1366, 'height': 768},
                locale='es-CL',
                # Configuraciones para evitar cache y datos guardados
                ignore_https_errors=True,
                java_script_enabled=True,
                # No permitir que se guarde información
                storage_state=None,  # No cargar estado previo
                # Configuraciones adicionales de privacidad
                permissions=[],  # Sin permisos especiales
                extra_http_headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
            
            # Crear nueva página
            self.page = await self.context.new_page()
            
            # Limpiar cualquier dato cacheado
            await self._clear_browser_data()
            
            # Configurar timeouts
            self.page.set_default_timeout(30000)  # 30 segundos
            
            self.print_colored("✅ Navegador inicializado correctamente", Fore.GREEN)
            self.logger.info("Navegador inicializado correctamente")
            
        except Exception as e:
            self.print_colored(f"❌ Error al inicializar navegador: {str(e)}", Fore.RED)
            self.logger.error(f"Error al inicializar navegador: {str(e)}")
            raise
            
    async def navigate_to_site(self):
        """
        Navega al sitio web de reserva de licencias.
        
        Este método carga la página principal y verifica que se haya cargado correctamente.
        """
        self.print_step(2, "Navegando al sitio web")
        
        try:
            self.print_colored(f"🔗 Navegando a: {self.target_url}", Fore.BLUE)
            
            # Limpiar datos antes de navegar
            await self._clear_browser_data()
            
            # Navegar a la URL
            response = await self.page.goto(self.target_url, wait_until='networkidle')
            
            if response and response.status == 200:
                self.print_colored("✅ Página cargada correctamente", Fore.GREEN)
                self.logger.info(f"Navegación exitosa a {self.target_url}")
                
                # Esperar a que la página se cargue completamente
                await self.page.wait_for_load_state('domcontentloaded')
                
                # Verificar y cerrar modales si aparecen
                await self._detect_and_close_modals()
                
                # Tomar screenshot para debug
                await self.page.screenshot(path=f'screenshot_step2_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
                
            else:
                status_code = response.status if response else "Sin respuesta"
                self.print_colored(f"⚠️ Respuesta inesperada del servidor: {status_code}", Fore.YELLOW)
                self.logger.warning(f"Respuesta del servidor: {status_code}")
                
        except Exception as e:
            self.print_colored(f"❌ Error al navegar al sitio: {str(e)}", Fore.RED)
            self.logger.error(f"Error al navegar: {str(e)}")
            raise
            
    async def fill_rut_form(self, rut: str = None):
        """
        Llena el formulario con el RUT y lo envía.
        
        Args:
            rut: RUT a ingresar. Si no se proporciona, usa el RUT de ejemplo.
        """
        self.print_step(3, "Llenando formulario de RUT")
        
        rut_to_use = rut or self.rut_ejemplo
        
        try:
            # Verificar y cerrar modales antes de llenar el formulario
            await self._detect_and_close_modals()
            
            self.print_colored(f"📝 Ingresando RUT: {rut_to_use}", Fore.BLUE)
            
            # Buscar el campo de RUT (puede tener diferentes selectores)
            rut_selectors = [
                'input[name="txtRut"]',
                'input[id="txtRut"]',
                'input[type="text"]',
                '#txtRut'
            ]
            
            rut_input = None
            for selector in rut_selectors:
                try:
                    rut_input = await self.page.wait_for_selector(selector, timeout=5000)
                    if rut_input:
                        self.print_colored(f"✅ Campo RUT encontrado con selector: {selector}", Fore.GREEN)
                        break
                except:
                    continue
                    
            if not rut_input:
                raise Exception("No se pudo encontrar el campo de RUT")
                
            # Limpiar y llenar el campo de forma explícita y agresiva
            self.print_colored(f"🧹 Limpiando campo RUT completamente...", Fore.YELLOW)
            
            # Método 1: Hacer clic y seleccionar todo
            await rut_input.click()
            await self.page.wait_for_timeout(300)
            await rut_input.press('Control+a')  # Seleccionar todo
            await self.page.wait_for_timeout(200)
            await rut_input.press('Delete')     # Borrar contenido
            await self.page.wait_for_timeout(300)
            
            # Método 2: Verificar que esté vacío y forzar limpieza si es necesario
            current_value = await rut_input.input_value()
            self.print_colored(f"📋 Valor actual en campo: '{current_value}'", Fore.CYAN)
            
            if current_value and current_value.strip():
                self.print_colored("⚠️ Campo no se limpió, usando métodos alternativos...", Fore.YELLOW)
                
                # Método alternativo 1: Usar evaluate para limpiar directamente
                await self.page.evaluate("""
                    (selector) => {
                        const element = document.querySelector(selector);
                        if (element) {
                            element.value = '';
                            element.dispatchEvent(new Event('input', { bubbles: true }));
                            element.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }
                """, f'input[name="txtRut"], input[id="txtRut"], #txtRut')
                
                await self.page.wait_for_timeout(300)
                
                # Verificar de nuevo
                current_value = await rut_input.input_value()
                self.print_colored(f"📋 Valor después de limpieza forzada: '{current_value}'", Fore.CYAN)
                
                # Si aún no está vacío, usar método más agresivo
                if current_value and current_value.strip():
                    self.print_colored("🔥 Usando limpieza ultra-agresiva...", Fore.RED)
                    await rut_input.click()
                    await self.page.wait_for_timeout(200)
                    
                    # Seleccionar carácter por carácter y borrar
                    for _ in range(len(current_value) + 5):  # +5 por seguridad
                        await rut_input.press('Backspace')
                        await self.page.wait_for_timeout(50)
                    
                    await self.page.wait_for_timeout(300)
            
            # Verificación final antes de llenar
            final_check = await rut_input.input_value()
            self.print_colored(f"📋 Valor final antes de llenar: '{final_check}'", Fore.CYAN)
            
            # Ahora llenar con el nuevo valor
            self.print_colored(f"✍️ Llenando con nuevo RUT: {rut_to_use}", Fore.GREEN)
            await rut_input.fill(rut_to_use)
            await self.page.wait_for_timeout(500)  # Esperar a que se procese
            
            # Verificar que se llenó correctamente
            filled_value = await rut_input.input_value()
            self.print_colored(f"📋 Valor después de llenar: '{filled_value}'", Fore.CYAN)
            
            if filled_value != rut_to_use:
                self.print_colored(f"⚠️ VALOR INCORRECTO! Esperado: '{rut_to_use}', Actual: '{filled_value}'", Fore.RED)
                
                # Último intento con método typing
                self.print_colored("🔄 Último intento con método typing...", Fore.YELLOW)
                await rut_input.click()
                await rut_input.press('Control+a')
                await rut_input.press('Delete')
                await self.page.wait_for_timeout(300)
                
                # Escribir carácter por carácter
                await rut_input.type(rut_to_use, delay=100)
                await self.page.wait_for_timeout(300)
                
                # Verificación final
                final_value = await rut_input.input_value()
                self.print_colored(f"📋 Valor final después de typing: '{final_value}'", Fore.CYAN)
                
                if final_value != rut_to_use:
                    raise Exception(f"No se pudo ingresar el RUT correctamente. Esperado: '{rut_to_use}', Actual: '{final_value}'")
            
            self.print_colored("✅ RUT ingresado y verificado correctamente", Fore.GREEN)
            
            # Verificar modales antes de enviar
            await self._detect_and_close_modals()
            
            # Buscar y hacer clic en el botón de envío
            submit_selectors = [
                'input[type="submit"]',
                'button[type="submit"]',
                'input[value="ingresar"]',
                '#btnIngresar',
                '.btn-submit'
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    submit_button = await self.page.wait_for_selector(selector, timeout=5000)
                    if submit_button:
                        self.print_colored(f"✅ Botón de envío encontrado: {selector}", Fore.GREEN)
                        break
                except:
                    continue
                    
            if not submit_button:
                raise Exception("No se pudo encontrar el botón de envío")
                
            # Hacer clic en el botón
            self.print_colored("🔄 Enviando formulario...", Fore.BLUE)
            await submit_button.click()
            
            # Esperar a que la página responda
            await self.page.wait_for_load_state('networkidle', timeout=30000)
            
            # Verificar modales después del envío
            await self._detect_and_close_modals()
            
            self.print_colored("✅ Formulario enviado correctamente", Fore.GREEN)
            self.logger.info(f"Formulario enviado con RUT: {rut_to_use}")
            
        except Exception as e:
            self.print_colored(f"❌ Error al llenar formulario: {str(e)}", Fore.RED)
            self.logger.error(f"Error al llenar formulario: {str(e)}")
            raise
            
    async def _check_error_messages(self):
        """
        Verifica si hay mensajes de error en la página actual.
        
        Returns:
            Dict con información del error si se encuentra, None si no hay errores.
        """
        try:
            self.print_colored("🔍 Verificando mensajes de error en la página...", Fore.BLUE)
            
            # Obtener todo el contenido de la página
            page_content = await self.page.content()
            
            # Buscar elementos específicos que contengan errores
            error_selectors = [
                '.error',
                '.alert',
                '.warning',
                '[class*="error"]',
                '[class*="alert"]',
                'div[style*="color:red"]',
                'div[style*="color: red"]',
                'span[style*="color:red"]',
                'span[style*="color: red"]'
            ]
            
            found_errors = []
            
            # Buscar errores por selectores
            for selector in error_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for element in elements:
                        text = await element.text_content()
                        if text and text.strip():
                            found_errors.append(text.strip())
                except:
                    continue
            
            # Buscar patrones de error específicos en el contenido HTML
            error_patterns = [
                r'<b[^>]*>.*?Atención!.*?Error:.*?</b>',
                r'Error:.*?(?=<|$)',
                r'Atención!.*?Error:.*?(?=<|$)',
                r'ud\. ha excedido el tiempo máximo de espera',
                r'tiempo máximo de espera',
                r'no existen horas disponibles',
                r'sin disponibilidad',
                r'agendas llenas',
                r'\*\*Atención!\*\*\s*Error:.*?(?=<|$)',
                r'Atención!\s*Error:.*?Ud\. ha excedido el tiempo máximo de espera',
                r'Buscando especialidades\.\.\.\.'
            ]
            
            for pattern in error_patterns:
                matches = re.findall(pattern, page_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    # Limpiar HTML tags
                    clean_text = re.sub(r'<[^>]+>', '', match).strip()
                    if clean_text and clean_text not in found_errors:
                        found_errors.append(clean_text)
            
            # Mostrar errores encontrados
            if found_errors:
                self.print_colored("🚨 MENSAJES DE ERROR DETECTADOS:", Fore.RED, Style.BRIGHT)
                self.print_colored("=" * 60, Fore.RED)
                
                for i, error in enumerate(found_errors, 1):
                    self.print_colored(f"❌ Error {i}: {error}", Fore.RED)
                    self.logger.error(f"Error detectado: {error}")
                
                self.print_colored("=" * 60, Fore.RED)
                
                # Determinar el tipo de error
                error_text_lower = ' '.join(found_errors).lower()
                
                if 'tiempo máximo de espera' in error_text_lower or 'excedido' in error_text_lower:
                    return {
                        'available': False,
                        'status': 'timeout_error',
                        'message': f'Error de timeout detectado: {found_errors[0]}',
                        'url': self.page.url,
                        'timestamp': datetime.now().isoformat(),
                        'all_errors': found_errors
                    }
                elif 'no existen horas' in error_text_lower or 'sin disponibilidad' in error_text_lower:
                    return {
                        'available': False,
                        'status': 'no_availability_error',
                        'message': f'Sin disponibilidad: {found_errors[0]}',
                        'url': self.page.url,
                        'timestamp': datetime.now().isoformat(),
                        'all_errors': found_errors
                    }
                else:
                    return {
                        'available': None,
                        'status': 'unknown_error',
                        'message': f'Error desconocido: {found_errors[0]}',
                        'url': self.page.url,
                        'timestamp': datetime.now().isoformat(),
                        'all_errors': found_errors
                    }
            else:
                self.print_colored("✅ No se detectaron mensajes de error", Fore.GREEN)
                return None
                
        except Exception as e:
            self.print_colored(f"❌ Error al verificar mensajes de error: {str(e)}", Fore.RED)
            self.logger.error(f"Error al verificar mensajes de error: {str(e)}")
            return None
            
    async def check_availability(self) -> Dict[str, Any]:
        """
        Verifica la disponibilidad de citas analizando la respuesta del servidor.
        
        Returns:
            Dict con información sobre la disponibilidad y estado de la verificación.
        """
        self.print_step(4, "Verificando disponibilidad de citas")
        
        try:
            # Verificar y cerrar modales al inicio
            modal_found = await self._detect_and_close_modals()
            if modal_found:
                # Si había un modal, esperar un poco más para que la página se estabilice
                await self.page.wait_for_timeout(2000)
            
            # Obtener URL actual
            current_url = self.page.url
            self.print_colored(f"🔍 URL actual: {current_url}", Fore.BLUE)
            
            # Tomar screenshot para análisis
            screenshot_path = f'screenshot_result_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
            await self.page.screenshot(path=screenshot_path)
            self.print_colored(f"📸 Screenshot guardado: {screenshot_path}", Fore.BLUE)
            
            # Si estamos en paso-1.aspx o estatus.aspx, buscar el botón específico
            if 'paso-1.aspx' in current_url or 'estatus.aspx' in current_url:
                self.print_colored(f"🔍 Detectado {current_url.split('/')[-1]}, buscando botón de especialidades...", Fore.BLUE)
                
                # Buscar mensajes de error primero
                error_result = await self._check_error_messages()
                if error_result:
                    return error_result
                
                # Si estamos en estatus.aspx, usar el manejador específico
                if 'estatus.aspx' in current_url:
                    estatus_info = await self._handle_estatus_page()
                    if estatus_info and estatus_info.get('errors'):
                        # Si hay errores en estatus, retornar inmediatamente
                        return {
                            'available': False,
                            'status': 'estatus_error',
                            'message': f'Errores en página de estatus: {"; ".join(estatus_info["errors"])}',
                            'url': current_url,
                            'timestamp': datetime.now().isoformat(),
                            'estatus_info': estatus_info
                        }
                
                # Intentar hacer clic en el botón de especialidades con reintentos después de modales
                return await self._click_especialidad_button_with_modal_retry()
            
            # Verificar si hay error de disponibilidad en la URL
            if self.error_url_pattern in current_url:
                self.print_colored("❌ NO HAY CITAS DISPONIBLES", Fore.RED, Style.BRIGHT)
                self.print_colored("🔄 El sistema indica que no existen horas disponibles", Fore.YELLOW)
                
                result = {
                    'available': False,
                    'status': 'no_availability',
                    'message': 'No existen horas disponibles en la especialidad solicitada',
                    'url': current_url,
                    'timestamp': datetime.now().isoformat()
                }
                
                self.logger.info("No hay citas disponibles")
                return result
                
            # Buscar indicadores de disponibilidad en el contenido
            page_content = await self.page.content()
            
            # Palabras clave que indican falta de disponibilidad
            no_availability_keywords = [
                'no existen horas disponibles',
                'sin disponibilidad',
                'no hay citas',
                'agendas llenas',
                'sin cupos',
                'ud. ha excedido el tiempo máximo de espera',
                'tiempo máximo de espera'
            ]
            
            # Palabras clave que indican disponibilidad
            availability_keywords = [
                'seleccione fecha',
                'horarios disponibles',
                'agendar cita',
                'reservar hora'
            ]
            
            content_lower = page_content.lower()
            
            # Verificar falta de disponibilidad
            for keyword in no_availability_keywords:
                if keyword in content_lower:
                    self.print_colored(f"❌ Detectado: '{keyword}' en el contenido", Fore.RED)
                    result = {
                        'available': False,
                        'status': 'no_availability_content',
                        'message': f'Detectado en contenido: {keyword}',
                        'url': current_url,
                        'timestamp': datetime.now().isoformat()
                    }
                    return result
                    
            # Verificar disponibilidad
            for keyword in availability_keywords:
                if keyword in content_lower:
                    self.print_colored(f"✅ ¡CITAS DISPONIBLES! Detectado: '{keyword}'", Fore.GREEN, Style.BRIGHT)
                    result = {
                        'available': True,
                        'status': 'availability_found',
                        'message': f'Disponibilidad detectada: {keyword}',
                        'url': current_url,
                        'timestamp': datetime.now().isoformat()
                    }
                    return result
                    
            # Si no se detecta nada específico, analizar la estructura de la página
            self.print_colored("🔍 Analizando estructura de la página...", Fore.BLUE)
            
            # Buscar elementos que indiquen el siguiente paso del proceso
            next_step_selectors = [
                'select[name*="fecha"]',
                'input[type="date"]',
                '.calendar',
                '#calendario',
                'select[name*="hora"]'
            ]
            
            for selector in next_step_selectors:
                element = await self.page.query_selector(selector)
                if element:
                    self.print_colored(f"✅ ¡POSIBLE DISPONIBILIDAD! Encontrado elemento: {selector}", Fore.GREEN)
                    result = {
                        'available': True,
                        'status': 'possible_availability',
                        'message': f'Elemento de selección encontrado: {selector}',
                        'url': current_url,
                        'timestamp': datetime.now().isoformat()
                    }
                    return result
                    
            # Si llegamos aquí, el estado es incierto
            self.print_colored("⚠️ Estado incierto - requiere revisión manual", Fore.YELLOW)
            result = {
                'available': None,
                'status': 'uncertain',
                'message': 'No se pudo determinar la disponibilidad automáticamente',
                'url': current_url,
                'timestamp': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            self.print_colored(f"❌ Error al verificar disponibilidad: {str(e)}", Fore.RED)
            self.logger.error(f"Error al verificar disponibilidad: {str(e)}")
            
            result = {
                'available': None,
                'status': 'error',
                'message': f'Error durante verificación: {str(e)}',
                'url': self.page.url if self.page else 'unknown',
                'timestamp': datetime.now().isoformat()
            }
            return result

    async def _click_especialidad_button_with_modal_retry(self) -> Dict[str, Any]:
        """
        Hace clic en el botón de especialidades con reintentos infinitos hasta pasar el modal.
        No cierra el navegador durante los reintentos.
        
        Returns:
            Dict con el resultado de la verificación después del clic exitoso.
        """
        retry_count = 0
        
        # Priorizar el botón específico que mencionó el usuario
        primary_button_selector = '#dgGrilla_btIngresar_0'
        
        # Selectores alternativos por si el principal no está disponible
        alternative_selectors = [
            'input[id="dgGrilla_btIngresar_0"]',
            'input[name="dgGrilla$ctl02$btIngresar"]',
            '.BotonIngresar',
            'input.BotonIngresar',
            'th:contains("Modificar") ~ td input[type="submit"]',
            'table input[id*="btIngresar"]'
        ]
        
        self.print_colored(f"\n{'🔄 MODO REINTENTO INFINITO HASTA PASAR MODAL 🔄':^60}", Fore.CYAN, Style.BRIGHT)
        self.print_colored("El navegador se mantendrá abierto hasta lograr pasar el modal", Fore.CYAN)
        self.print_colored("Presiona Ctrl+C para detener si es necesario", Fore.YELLOW)
        
        while True:  # Bucle infinito hasta pasar el modal
            try:
                retry_count += 1
                self.print_colored(f"\n🔄 Intento #{retry_count} para hacer clic en botón de especialidades", Fore.BLUE)
                
                # Buscar tabla y mostrar información (solo en el primer intento)
                if retry_count == 1:
                    self.print_colored("🔍 Verificando tabla de especialidades...", Fore.BLUE)
                    
                    table_info = await self.page.evaluate("""
                        () => {
                            const tables = document.querySelectorAll('table');
                            let tableInfo = [];
                            
                            tables.forEach((table, index) => {
                                const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                                const buttons = Array.from(table.querySelectorAll('input[type="submit"]'));
                                
                                if (headers.length > 0 || buttons.length > 0) {
                                    tableInfo.push({
                                        index: index,
                                        headers: headers,
                                        buttonCount: buttons.length,
                                        buttonIds: buttons.map(btn => btn.id || btn.name || 'sin-id')
                                    });
                                }
                            });
                            
                            return tableInfo;
                        }
                    """)
                    
                    if table_info:
                        self.print_colored("📊 Información de tablas encontradas:", Fore.CYAN)
                        for table in table_info:
                            self.print_colored(f"   Tabla {table['index']}: Headers: {table['headers']}", Fore.CYAN)
                            self.print_colored(f"   Botones ({table['buttonCount']}): {table['buttonIds']}", Fore.CYAN)
                
                # Buscar el botón prioritario primero
                especialidad_button = None
                
                try:
                    especialidad_button = await self.page.wait_for_selector(primary_button_selector, timeout=5000)
                    if especialidad_button:
                        self.print_colored(f"✅ Botón prioritario encontrado: {primary_button_selector}", Fore.GREEN)
                except:
                    # Si no se encuentra el botón prioritario, buscar alternativas
                    self.print_colored(f"⚠️ Botón prioritario {primary_button_selector} no encontrado, buscando alternativas...", Fore.YELLOW)
                    
                    for selector in alternative_selectors:
                        try:
                            especialidad_button = await self.page.wait_for_selector(selector, timeout=3000)
                            if especialidad_button:
                                self.print_colored(f"✅ Botón alternativo encontrado: {selector}", Fore.GREEN)
                                break
                        except:
                            continue
                
                if not especialidad_button:
                    self.print_colored("❌ No se encontró el botón de especialidades, esperando 3 segundos antes de reintentar...", Fore.RED)
                    await self.page.wait_for_timeout(3000)
                    continue  # Continuar el bucle infinito
                
                # Verificar modales antes de hacer clic
                await self._detect_and_close_modals()
                
                self.print_colored("🔄 Haciendo clic en botón de especialidades...", Fore.BLUE)
                await especialidad_button.click()
                
                # Esperar a que la página responda
                await self.page.wait_for_load_state('networkidle', timeout=30000)
                
                # Verificar si aparecieron modales después del clic
                modal_appeared = await self._detect_and_close_modals()
                
                if modal_appeared:
                    self.print_colored(f"🚨 Modal detectado después del clic (Intento #{retry_count}). Reintentando...", Fore.YELLOW)
                    self.print_colored("🔄 Esperando 2 segundos antes del siguiente intento...", Fore.BLUE)
                    await self.page.wait_for_timeout(2000)
                    continue  # Continuar el bucle infinito
                
                # Si no hay modales, verificar la nueva URL y errores
                new_url = self.page.url
                self.print_colored(f"🔍 Nueva URL después del clic: {new_url}", Fore.BLUE)
                
                # Tomar screenshot después del clic exitoso
                screenshot_path = f'screenshot_after_click_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
                await self.page.screenshot(path=screenshot_path)
                self.print_colored(f"📸 Screenshot después del clic: {screenshot_path}", Fore.BLUE)
                
                # Verificar errores después del clic
                error_result = await self._check_error_messages()
                if error_result:
                    # Si hay error después del clic, decidir si reintentar o devolver error
                    error_status = error_result.get('status', '')
                    if error_status in ['timeout_error', 'estatus_error']:
                        self.print_colored(f"⚠️ Error detectado: {error_result.get('message')}", Fore.YELLOW)
                        self.print_colored("🔄 Reintentando debido a error temporal...", Fore.BLUE)
                        await self.page.wait_for_timeout(2000)
                        continue  # Continuar el bucle infinito
                    else:
                        # Error definitivo, retornar
                        return error_result
                
                # Si llegamos aquí, el clic fue exitoso sin modales ni errores temporales
                self.print_colored(f"✅ ¡ÉXITO! Clic exitoso en botón de especialidades después de {retry_count} intentos", Fore.GREEN, Style.BRIGHT)
                
                # Continuar con la verificación normal de disponibilidad
                return await self._continue_availability_check()
                
            except KeyboardInterrupt:
                self.print_colored(f"\n🛑 Reintentos detenidos por el usuario después de {retry_count} intentos", Fore.YELLOW)
                return {
                    'available': None,
                    'status': 'user_interrupted',
                    'message': f'Usuario detuvo los reintentos después de {retry_count} intentos',
                    'url': self.page.url,
                    'timestamp': datetime.now().isoformat()
                }
                
            except Exception as e:
                self.print_colored(f"❌ Error en intento #{retry_count}: {str(e)}", Fore.RED)
                self.print_colored("🔄 Esperando 3 segundos antes de reintentar...", Fore.BLUE)
                await self.page.wait_for_timeout(3000)
                continue  # Continuar el bucle infinito incluso con errores

    async def _continue_availability_check(self) -> Dict[str, Any]:
        """
        Continúa con la verificación de disponibilidad después de un clic exitoso.
        
        Returns:
            Dict con el resultado de la verificación de disponibilidad.
        """
        try:
            current_url = self.page.url
            page_content = await self.page.content()
            
            # Palabras clave que indican falta de disponibilidad
            no_availability_keywords = [
                'no existen horas disponibles',
                'sin disponibilidad',
                'no hay citas',
                'agendas llenas',
                'sin cupos',
                'ud. ha excedido el tiempo máximo de espera',
                'tiempo máximo de espera'
            ]
            
            # Palabras clave que indican disponibilidad
            availability_keywords = [
                'seleccione fecha',
                'horarios disponibles',
                'agendar cita',
                'reservar hora'
            ]
            
            content_lower = page_content.lower()
            
            # Verificar falta de disponibilidad
            for keyword in no_availability_keywords:
                if keyword in content_lower:
                    self.print_colored(f"❌ Detectado: '{keyword}' en el contenido", Fore.RED)
                    return {
                        'available': False,
                        'status': 'no_availability_content',
                        'message': f'Detectado en contenido: {keyword}',
                        'url': current_url,
                        'timestamp': datetime.now().isoformat()
                    }
                    
            # Verificar disponibilidad
            for keyword in availability_keywords:
                if keyword in content_lower:
                    self.print_colored(f"✅ ¡CITAS DISPONIBLES! Detectado: '{keyword}'", Fore.GREEN, Style.BRIGHT)
                    return {
                        'available': True,
                        'status': 'availability_found',
                        'message': f'Disponibilidad detectada: {keyword}',
                        'url': current_url,
                        'timestamp': datetime.now().isoformat()
                    }
            
            # Buscar elementos que indiquen el siguiente paso del proceso
            next_step_selectors = [
                'select[name*="fecha"]',
                'input[type="date"]',
                '.calendar',
                '#calendario',
                'select[name*="hora"]'
            ]
            
            for selector in next_step_selectors:
                element = await self.page.query_selector(selector)
                if element:
                    self.print_colored(f"✅ ¡POSIBLE DISPONIBILIDAD! Encontrado elemento: {selector}", Fore.GREEN)
                    return {
                        'available': True,
                        'status': 'possible_availability',
                        'message': f'Elemento de selección encontrado: {selector}',
                        'url': current_url,
                        'timestamp': datetime.now().isoformat()
                    }
            
            # Estado incierto
            return {
                'available': None,
                'status': 'uncertain',
                'message': 'No se pudo determinar la disponibilidad automáticamente',
                'url': current_url,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'available': None,
                'status': 'error',
                'message': f'Error durante verificación continua: {str(e)}',
                'url': self.page.url if self.page else 'unknown',
                'timestamp': datetime.now().isoformat()
            }

    async def cleanup(self, force_close: bool = True):
        """
        Limpia recursos del navegador.
        
        Args:
            force_close: Si True, cierra todo. Si False, solo limpia referencias.
        """
        try:
            if force_close:
                if self.page:
                    await self.page.close()
                if self.context:
                    await self.context.close()
                if self.browser:
                    await self.browser.close()
                if hasattr(self, 'playwright'):
                    await self.playwright.stop()
                    
                self.print_colored("🧹 Recursos limpiados correctamente", Fore.GREEN)
            else:
                self.print_colored("🔍 Manteniendo navegador abierto para inspección", Fore.CYAN)
                
        except Exception as e:
            self.print_colored(f"⚠️ Error durante limpieza: {str(e)}", Fore.YELLOW)
            
    async def run_single_check(self, rut: str = None, is_continuous: bool = False) -> Dict[str, Any]:
        """
        Ejecuta una verificación completa de disponibilidad.
        
        Args:
            rut: RUT a verificar. Si no se proporciona, usa el RUT del usuario.
            is_continuous: True si se ejecuta en modo monitoreo continuo.
            
        Returns:
            Dict con el resultado de la verificación.
        """
        self.attempt_count += 1
        
        # Usar RUT del usuario si no se proporciona uno específico
        rut_to_use = rut or self.user_rut or self.rut_ejemplo
        
        self.print_colored(f"\n{'🚀 INICIANDO VERIFICACIÓN #{self.attempt_count} 🚀':^60}", 
                          Fore.MAGENTA, Style.BRIGHT)
        self.print_colored(f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", Fore.CYAN)
        self.print_colored(f"RUT: {rut_to_use}", Fore.CYAN)
        self.print_colored(f"Operación: {self.operation_type.title() if self.operation_type else 'No especificada'}", Fore.CYAN)
        if is_continuous:
            self.print_colored("Modo: Monitoreo Continuo", Fore.CYAN)
        
        result = {}  # Inicializar result para el bloque finally
        
        try:
            # Paso 1: Inicializar navegador (solo si no existe o está cerrado)
            if not self.browser or not self.page:
                await self.initialize_browser()
            else:
                self.print_colored("🔄 Reutilizando navegador existente", Fore.GREEN)
            
            # Paso 1.5: Si no es la primera ejecución, recrear contexto para evitar cache
            if self.attempt_count > 1:
                await self.recreate_browser_context()
            
            # Paso 2: Navegar al sitio
            await self.navigate_to_site()
            
            # Paso 3: Llenar formulario
            await self.fill_rut_form(rut_to_use)
            
            # Paso 4: Verificar disponibilidad (con reintentos infinitos para modales)
            result = await self.check_availability()
            
            # Si hay error, manejar según el modo
            if result.get('available') is False and result.get('status') in ['timeout_error', 'estatus_error', 'no_availability_error']:
                if is_continuous:
                    # En modo continuo, solo logear el error y continuar
                    action = await self.handle_error_automatically(result)
                else:
                    # En verificación única, permitir intervención manual
                    action = await self.handle_error_interactively(result)
                
                if action == "exit":
                    return result
                elif action == "retry":
                    # No limpiar aún, el retry se manejará en el nivel superior
                    result['action'] = 'retry'
                    return result
                elif action == "continue":
                    # Continuar como si no hubiera error
                    result['action'] = 'continue'
                    return result
                elif action == "continue_from_current":
                    # Continuar desde el estado actual, re-verificar disponibilidad
                    self.print_colored("🔄 Re-verificando disponibilidad desde estado actual...", Fore.BLUE)
                    result = await self.check_availability()
            
            # Mostrar resultado
            self.print_step(5, "RESULTADO DE LA VERIFICACIÓN")
            
            if result['available'] is True:
                self.print_colored("🎉 ¡CITAS DISPONIBLES ENCONTRADAS!", Fore.GREEN, Style.BRIGHT)
                self.print_colored(f"📋 Detalles: {result['message']}", Fore.GREEN)
                self.print_colored(f"🔗 URL: {result['url']}", Fore.BLUE)
                
            elif result['available'] is False:
                self.print_colored("❌ No hay citas disponibles", Fore.RED)
                self.print_colored(f"📋 Motivo: {result['message']}", Fore.YELLOW)
                
            else:
                self.print_colored("⚠️ Estado incierto", Fore.YELLOW)
                self.print_colored(f"📋 Detalles: {result['message']}", Fore.YELLOW)
                
            return result
            
        except Exception as e:
            error_msg = f"Error durante verificación: {str(e)}"
            self.print_colored(f"❌ {error_msg}", Fore.RED)
            self.logger.error(error_msg)
            
            return {
                'available': None,
                'status': 'error',
                'message': error_msg,
                'timestamp': datetime.now().isoformat()
            }
            
        finally:
            # NUNCA cerrar navegador automáticamente durante reintentos de modales
            # Solo cerrar si el resultado no requiere mantener el navegador abierto
            should_close = not (
                result.get('action') in ['retry', 'continue', 'continue_from_current'] or
                result.get('status') in ['user_interrupted', 'max_retries_exceeded'] or
                is_continuous  # En modo continuo, mantener siempre abierto
            )
            
            if should_close:
                await self.cleanup(force_close=True)
            else:
                self.print_colored("🔍 Manteniendo navegador abierto para continuar operación", Fore.CYAN)

    async def run_continuous_monitoring(self, rut: str = None):
        """
        Ejecuta monitoreo continuo con intervalos configurados.
        
        Args:
            rut: RUT a verificar continuamente. Si no se proporciona, usa el RUT del usuario.
        """
        rut_to_use = rut or self.user_rut or self.rut_ejemplo
        
        self.print_colored(f"\n{'🔄 INICIANDO MONITOREO CONTINUO 🔄':^60}", 
                          Fore.CYAN, Style.BRIGHT)
        self.print_colored(f"Intervalo: {self.retry_interval} minutos", Fore.CYAN)
        self.print_colored(f"RUT: {rut_to_use}", Fore.CYAN)
        self.print_colored(f"Operación: {self.operation_type.title() if self.operation_type else 'No especificada'}", Fore.CYAN)
        self.print_colored("Presiona Ctrl+C para detener", Fore.YELLOW)
        
        try:
            while True:
                result = await self.run_single_check(rut_to_use, is_continuous=True)
                
                # Verificar si el usuario eligió salir (no debería ocurrir en modo continuo)
                if result.get('action') == 'exit':
                    self.print_colored("\n🛑 Saliendo por petición del usuario", Fore.YELLOW)
                    break
                    
                # Verificar si el usuario eligió reintentar sin reiniciar navegador
                if result.get('action') == 'retry_without_restart':
                    self.print_colored("\n♻️ Reintentando sin reiniciar navegador...", Fore.BLUE)
                    # Limpiar datos del navegador actual pero mantener la instancia
                    await self._clear_browser_data()
                    await self.page.goto(self.target_url, wait_until='networkidle')
                    continue  # Reintentar inmediatamente sin esperar
                    
                # Verificar si el usuario eligió reintentar (con reinicio completo)
                if result.get('action') == 'retry':
                    self.print_colored("\n♻️ Reintentando automáticamente...", Fore.BLUE)
                    continue  # Reintentar inmediatamente sin esperar
                
                # Si encontramos disponibilidad, podemos decidir si continuar o parar
                if result.get('available') is True:
                    self.print_colored("\n🎯 ¡CITAS ENCONTRADAS! Revisa el navegador.", 
                                     Fore.GREEN, Style.BRIGHT)
                    # Opcional: break para detener el monitoreo
                    # break
                    
                # Esperar antes del siguiente intento (solo si no es retry)
                if result.get('action') not in ['retry', 'continue', 'retry_without_restart']:
                    wait_seconds = self.retry_interval * 60
                    self.print_colored(f"\n⏰ Esperando {self.retry_interval} minutos hasta el próximo intento...", 
                                     Fore.BLUE)
                    
                    # Mostrar cuenta regresiva
                    for remaining in range(wait_seconds, 0, -60):
                        minutes_left = remaining // 60
                        if minutes_left > 0:
                            print(f"\r⏳ {minutes_left} minutos restantes...", end='', flush=True)
                            await asyncio.sleep(60)
                            
                    print("\r" + " " * 30 + "\r", end='')  # Limpiar línea
                
        except KeyboardInterrupt:
            self.print_colored("\n\n🛑 Monitoreo detenido por el usuario", Fore.YELLOW)
            self.logger.info("Monitoreo detenido por el usuario")
            
        except Exception as e:
            self.print_colored(f"\n❌ Error en monitoreo continuo: {str(e)}", Fore.RED)
            self.logger.error(f"Error en monitoreo continuo: {str(e)}")

    async def recreate_browser_context(self):
        """Recrea el contexto del navegador para eliminar completamente cualquier cache."""
        try:
            self.print_colored("🔄 Recreando contexto del navegador para eliminar cache...", Fore.YELLOW)
            
            # Cerrar página y contexto actuales
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            
            # Crear nuevo contexto completamente limpio
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1366, 'height': 768},
                locale='es-CL',
                # Configuraciones para evitar cache y datos guardados
                ignore_https_errors=True,
                java_script_enabled=True,
                # No permitir que se guarde información
                storage_state=None,  # No cargar estado previo
                # Configuraciones adicionales de privacidad
                permissions=[],  # Sin permisos especiales
                extra_http_headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
            
            # Crear nueva página
            self.page = await self.context.new_page()
            
            # Limpiar datos del nuevo contexto
            await self._clear_browser_data()
            
            # Configurar timeouts
            self.page.set_default_timeout(30000)  # 30 segundos
            
            self.print_colored("✅ Contexto del navegador recreado exitosamente", Fore.GREEN)
            
        except Exception as e:
            self.print_colored(f"❌ Error al recrear contexto: {str(e)}", Fore.RED)
            self.logger.error(f"Error al recrear contexto: {str(e)}")
            raise

    async def _handle_estatus_page(self):
        """
        Maneja específicamente la página estatus.aspx para detectar especialidades disponibles.
        
        Returns:
            Dict con información del estado de la página estatus.
        """
        try:
            self.print_colored("🔍 Analizando página de estatus...", Fore.BLUE)
            
            # Verificar si hay mensaje de "Buscando especialidades"
            is_loading = await self.page.evaluate("""
                () => {
                    const bodyText = document.body.textContent || document.body.innerText || '';
                    return bodyText.toLowerCase().includes('buscando especialidades');
                }
            """)
            
            if is_loading:
                self.print_colored("⏳ Página mostrando 'Buscando especialidades...', esperando...", Fore.YELLOW)
                await self.page.wait_for_timeout(3000)  # Esperar 3 segundos
                
                # Verificar de nuevo después de esperar
                still_loading = await self.page.evaluate("""
                    () => {
                        const bodyText = document.body.textContent || document.body.innerText || '';
                        return bodyText.toLowerCase().includes('buscando especialidades');
                    }
                """)
                
                if still_loading:
                    return {
                        'available': None,
                        'status': 'loading_specialties',
                        'message': 'La página está cargando especialidades',
                        'url': self.page.url,
                        'timestamp': datetime.now().isoformat()
                    }
            
            # Buscar tabla de especialidades
            specialties_info = await self.page.evaluate("""
                () => {
                    const tables = document.querySelectorAll('table');
                    let info = {
                        hasTable: false,
                        hasModifyColumn: false,
                        hasButtons: false,
                        specialties: [],
                        errors: []
                    };
                    
                    // Buscar errores visibles
                    const errorElements = document.querySelectorAll('b, span, div');
                    errorElements.forEach(el => {
                        const text = el.textContent || el.innerText || '';
                        if (text.includes('Error:') || text.includes('Atención!')) {
                            info.errors.push(text.trim());
                        }
                    });
                    
                    // Analizar tablas
                    tables.forEach(table => {
                        const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
                        const hasModify = headers.some(h => h.toLowerCase().includes('modificar'));
                        
                        if (headers.length > 0) {
                            info.hasTable = true;
                            if (hasModify) {
                                info.hasModifyColumn = true;
                            }
                            
                            // Buscar botones en la tabla
                            const buttons = Array.from(table.querySelectorAll('input[type="submit"]'));
                            if (buttons.length > 0) {
                                info.hasButtons = true;
                                buttons.forEach(btn => {
                                    const row = btn.closest('tr');
                                    if (row) {
                                        const cells = Array.from(row.querySelectorAll('td')).map(td => td.textContent.trim());
                                        info.specialties.push({
                                            id: btn.id || btn.name || 'sin-id',
                                            cells: cells
                                        });
                                    }
                                });
                            }
                        }
                    });
                    
                    return info;
                }
            """)
            
            self.print_colored("📋 Información de la página de estatus:", Fore.CYAN)
            self.print_colored(f"   ✅ Tiene tabla: {specialties_info['hasTable']}", Fore.CYAN)
            self.print_colored(f"   ✅ Tiene columna modificar: {specialties_info['hasModifyColumn']}", Fore.CYAN)
            self.print_colored(f"   ✅ Tiene botones: {specialties_info['hasButtons']}", Fore.CYAN)
            self.print_colored(f"   📊 Especialidades encontradas: {len(specialties_info['specialties'])}", Fore.CYAN)
            
            if specialties_info['errors']:
                self.print_colored("🚨 Errores detectados en la página:", Fore.RED)
                for error in specialties_info['errors']:
                    self.print_colored(f"   ❌ {error}", Fore.RED)
            
            if specialties_info['specialties']:
                self.print_colored("📋 Especialidades disponibles:", Fore.GREEN)
                for i, spec in enumerate(specialties_info['specialties']):
                    self.print_colored(f"   {i+1}. ID: {spec['id']} - Datos: {spec['cells']}", Fore.GREEN)
            
            return specialties_info
            
        except Exception as e:
            self.print_colored(f"❌ Error al analizar página de estatus: {str(e)}", Fore.RED)
            return None

    async def _detect_and_close_modals(self) -> bool:
        """
        Detecta y cierra modales/popups automáticamente.
        
        Returns:
            True si se encontró y cerró un modal, False si no había modales.
        """
        try:
            self.print_colored("🔍 Verificando presencia de modales/popups...", Fore.BLUE)
            
            # Detectar diferentes tipos de modales
            modal_selectors = [
                # Modales comunes
                '.modal',
                '.popup',
                '.dialog',
                '.alert',
                '[role="dialog"]',
                '[role="alertdialog"]',
                
                # Modales Bootstrap
                '.modal.show',
                '.modal.fade.show',
                
                # Modales con overlay
                '.modal-backdrop',
                '.overlay',
                
                # Alertas del navegador (pueden aparecer como elementos DOM)
                '.alert-dialog',
                '.swal-modal',
                '.sweetalert-modal',
                
                # Modales específicos del sitio
                'div[style*="z-index"]:not([style*="display: none"])',
                'div[style*="position: fixed"]',
                'div[style*="position: absolute"][style*="top: 0"]'
            ]
            
            modal_found = False
            
            for selector in modal_selectors:
                try:
                    # Buscar modales visibles
                    modals = await self.page.query_selector_all(selector)
                    
                    for modal in modals:
                        # Verificar si el modal está visible
                        is_visible = await modal.evaluate("""
                            (element) => {
                                const style = window.getComputedStyle(element);
                                return style.display !== 'none' && 
                                       style.visibility !== 'hidden' && 
                                       style.opacity !== '0' &&
                                       element.offsetHeight > 0 &&
                                       element.offsetWidth > 0;
                            }
                        """)
                        
                        if is_visible:
                            self.print_colored(f"🚨 Modal detectado con selector: {selector}", Fore.YELLOW)
                            modal_found = True
                            
                            # Intentar cerrar el modal con diferentes métodos
                            closed = await self._close_modal(modal, selector)
                            if closed:
                                self.print_colored("✅ Modal cerrado exitosamente", Fore.GREEN)
                                await self.page.wait_for_timeout(1000)  # Esperar 1 segundo
                            
                except Exception as e:
                    # Continuar con el siguiente selector si hay error
                    continue
            
            if not modal_found:
                self.print_colored("✅ No se detectaron modales", Fore.GREEN)
            
            return modal_found
            
        except Exception as e:
            self.print_colored(f"⚠️ Error al detectar modales: {str(e)}", Fore.YELLOW)
            return False
    
    async def _close_modal(self, modal_element, selector: str) -> bool:
        """
        Intenta cerrar un modal específico usando diferentes métodos.
        
        Args:
            modal_element: Elemento del modal a cerrar
            selector: Selector usado para encontrar el modal
            
        Returns:
            True si se cerró exitosamente, False en caso contrario.
        """
        try:
            # Método 1: Buscar botón de cerrar dentro del modal
            close_selectors = [
                'button[data-dismiss="modal"]',
                '.close',
                '.btn-close',
                '.modal-close',
                'button.close',
                '[aria-label="Close"]',
                '[aria-label="Cerrar"]',
                'button:contains("×")',
                'button:contains("Cerrar")',
                'button:contains("OK")',
                'button:contains("Aceptar")',
                '.fa-times',
                '.fa-close'
            ]
            
            for close_selector in close_selectors:
                try:
                    close_button = await modal_element.query_selector(close_selector)
                    if close_button:
                        self.print_colored(f"🔘 Haciendo clic en botón de cerrar: {close_selector}", Fore.BLUE)
                        await close_button.click()
                        await self.page.wait_for_timeout(500)
                        return True
                except:
                    continue
            
            # Método 2: Presionar Escape
            self.print_colored("⌨️ Intentando cerrar con tecla Escape", Fore.BLUE)
            await self.page.keyboard.press('Escape')
            await self.page.wait_for_timeout(500)
            
            # Verificar si se cerró
            is_still_visible = await modal_element.evaluate("""
                (element) => {
                    const style = window.getComputedStyle(element);
                    return style.display !== 'none' && 
                           style.visibility !== 'hidden' && 
                           style.opacity !== '0';
                }
            """)
            
            if not is_still_visible:
                return True
            
            # Método 3: Hacer clic fuera del modal (en el backdrop)
            self.print_colored("🖱️ Intentando cerrar haciendo clic fuera del modal", Fore.BLUE)
            await self.page.click('body', position={'x': 10, 'y': 10})
            await self.page.wait_for_timeout(500)
            
            # Método 4: Usar JavaScript para ocultar/remover el modal
            self.print_colored("⚡ Usando JavaScript para cerrar modal", Fore.BLUE)
            await modal_element.evaluate("""
                (element) => {
                    // Intentar diferentes métodos para cerrar
                    element.style.display = 'none';
                    element.style.visibility = 'hidden';
                    element.style.opacity = '0';
                    
                    // Si es un modal Bootstrap
                    if (window.bootstrap && element.classList.contains('modal')) {
                        try {
                            const modal = bootstrap.Modal.getInstance(element);
                            if (modal) modal.hide();
                        } catch(e) {}
                    }
                    
                    // Si es jQuery modal
                    if (window.$ && $(element).modal) {
                        try {
                            $(element).modal('hide');
                        } catch(e) {}
                    }
                    
                    // Remover clases de modal activo
                    element.classList.remove('show', 'in', 'active');
                    
                    // Remover backdrop si existe
                    const backdrops = document.querySelectorAll('.modal-backdrop, .fade, .in');
                    backdrops.forEach(backdrop => {
                        backdrop.style.display = 'none';
                        backdrop.remove();
                    });
                }
            """)
            
            return True
            
        except Exception as e:
            self.print_colored(f"❌ Error al cerrar modal: {str(e)}", Fore.RED)
            return False

    async def handle_error_automatically(self, error_info: Dict[str, Any]) -> str:
        """
        Maneja errores automáticamente durante el monitoreo continuo.
        
        Args:
            error_info: Información del error detectado
            
        Returns:
            Acción a realizar ('continue', 'retry', 'retry_without_restart')
        """
        self.print_colored(f"\n{'⚠️ ERROR EN MONITOREO CONTINUO ⚠️':^60}", Fore.YELLOW, Style.BRIGHT)
        self.print_colored("=" * 60, Fore.YELLOW)
        
        # Mostrar información del error
        self.print_colored(f"📋 Tipo de error: {error_info.get('status', 'Desconocido')}", Fore.YELLOW)
        self.print_colored(f"📝 Mensaje: {error_info.get('message', 'Sin mensaje')}", Fore.YELLOW)
        self.print_colored(f"🔗 URL actual: {error_info.get('url', 'Desconocida')}", Fore.YELLOW)
        
        if error_info.get('all_errors'):
            self.print_colored("📄 Errores detectados:", Fore.YELLOW)
            for i, error in enumerate(error_info['all_errors'], 1):
                self.print_colored(f"   {i}. {error}", Fore.RED)
        
        self.print_colored("=" * 60, Fore.YELLOW)
        
        # Primero intentar detectar y cerrar modales
        modal_closed = await self._detect_and_close_modals()
        
        if modal_closed:
            self.print_colored("🔄 Modal cerrado, reintentando desde estado actual...", Fore.BLUE)
            self.logger.info("Modal cerrado, reintentando sin reiniciar navegador")
            return "retry_without_restart"
        
        # Determinar acción automática basada en el tipo de error
        error_status = error_info.get('status', '')
        
        if error_status in ['timeout_error', 'estatus_error']:
            self.print_colored("🔄 Reintentando automáticamente debido a error de timeout/estatus...", Fore.BLUE)
            self.logger.info(f"Reintento automático por error: {error_status}")
            return "retry_without_restart"  # Cambiar para no reiniciar navegador
        elif error_status in ['no_availability_error', 'no_availability_content']:
            self.print_colored("📝 Continuando monitoreo - sin disponibilidad detectada", Fore.BLUE)
            self.logger.info(f"Continuando monitoreo: {error_status}")
            return "continue"
        else:
            # Para errores desconocidos, reintentar sin reiniciar navegador
            self.print_colored("🔄 Reintentando automáticamente por error desconocido...", Fore.BLUE)
            self.logger.info(f"Reintento automático por error desconocido: {error_status}")
            return "retry_without_restart"

    async def handle_error_interactively(self, error_info: Dict[str, Any]) -> str:
        """
        Maneja errores de forma interactiva, manteniendo el navegador abierto.
        
        Args:
            error_info: Información del error detectado
            
        Returns:
            Acción elegida por el usuario ('continue', 'retry', 'manual', 'exit')
        """
        self.print_colored(f"\n{'🚨 ERROR DETECTADO 🚨':^60}", Fore.RED, Style.BRIGHT)
        self.print_colored("=" * 60, Fore.RED)
        
        # Mostrar información del error
        self.print_colored(f"📋 Tipo de error: {error_info.get('status', 'Desconocido')}", Fore.YELLOW)
        self.print_colored(f"📝 Mensaje: {error_info.get('message', 'Sin mensaje')}", Fore.YELLOW)
        self.print_colored(f"🔗 URL actual: {error_info.get('url', 'Desconocida')}", Fore.YELLOW)
        
        if error_info.get('all_errors'):
            self.print_colored("📄 Errores detectados:", Fore.YELLOW)
            for i, error in enumerate(error_info['all_errors'], 1):
                self.print_colored(f"   {i}. {error}", Fore.RED)
        
        self.print_colored("=" * 60, Fore.RED)
        
        # Mantener navegador abierto y preguntar al usuario
        self.print_colored("🔍 NAVEGADOR MANTENIDO ABIERTO para inspección manual", Fore.CYAN, Style.BRIGHT)
        
        while True:
            self.print_colored("\n🤔 ¿Qué desea hacer?", Fore.CYAN, Style.BRIGHT)
            self.print_colored("1. 🔄 Continuar monitoreo (ignorar error)", Fore.BLUE)
            self.print_colored("2. ♻️  Reintentar desde el inicio", Fore.BLUE)
            self.print_colored("3. 🖱️  Pausa para intervención manual", Fore.BLUE)
            self.print_colored("4. ❌ Salir del programa", Fore.BLUE)
            
            choice = input("\nSeleccione una opción (1-4): ").strip()
            
            if choice == "1":
                self.print_colored("✅ Continuando monitoreo...", Fore.GREEN)
                return "continue"
            elif choice == "2":
                self.print_colored("✅ Reintentando desde el inicio...", Fore.GREEN)
                return "retry"
            elif choice == "3":
                return await self._handle_manual_intervention()
            elif choice == "4":
                self.print_colored("✅ Saliendo del programa...", Fore.YELLOW)
                return "exit"
            else:
                self.print_colored("❌ Opción inválida. Seleccione 1, 2, 3 o 4", Fore.RED)
    
    async def _handle_manual_intervention(self) -> str:
        """
        Maneja la intervención manual del usuario.
        
        Returns:
            Acción a realizar después de la intervención manual.
        """
        self.print_colored(f"\n{'🖱️ MODO INTERVENCIÓN MANUAL 🖱️':^60}", Fore.MAGENTA, Style.BRIGHT)
        self.print_colored("=" * 60, Fore.MAGENTA)
        
        self.print_colored("🔧 El navegador está disponible para intervención manual.", Fore.CYAN)
        self.print_colored("🖱️ Puede hacer clic, navegar, llenar formularios, etc.", Fore.CYAN)
        self.print_colored("⏰ Tómese el tiempo necesario para resolver el problema.", Fore.CYAN)
        
        while True:
            self.print_colored("\n🔍 ¿Qué desea hacer después de la intervención manual?", Fore.CYAN)
            self.print_colored("1. ✅ Continuar desde el estado actual", Fore.BLUE)
            self.print_colored("2. 🔄 Reiniciar completamente", Fore.BLUE)
            self.print_colored("3. ⏸️  Mantener pausa (seguir interviniendo)", Fore.BLUE)
            self.print_colored("4. ❌ Salir del programa", Fore.BLUE)
            
            choice = input("\nSeleccione una opción (1-4): ").strip()
            
            if choice == "1":
                self.print_colored("✅ Continuando desde el estado actual...", Fore.GREEN)
                return "continue_from_current"
            elif choice == "2":
                self.print_colored("✅ Reiniciando completamente...", Fore.GREEN)
                return "retry"
            elif choice == "3":
                self.print_colored("⏸️ Manteniendo pausa para más intervención...", Fore.YELLOW)
                input("\nPresione ENTER cuando termine su intervención...")
                continue
            elif choice == "4":
                self.print_colored("✅ Saliendo del programa...", Fore.YELLOW)
                return "exit"
            else:
                self.print_colored("❌ Opción inválida. Seleccione 1, 2, 3 o 4", Fore.RED)


async def main():
    """Función principal del programa."""
    print(f"{Fore.CYAN}{Style.BRIGHT}")
    print("=" * 70)
    print("🚗 SCRAPER DE LICENCIAS DE CONDUCIR - MUNICIPALIDAD DE SANTIAGO 🚗")
    print("=" * 70)
    print(f"{Style.RESET_ALL}")
    
    scraper = LicenciaScraper()
    
    try:
        # Solicitar información al usuario
        scraper.get_user_input()
        
        # Mostrar configuración
        print(f"{Fore.CYAN}📋 CONFIGURACIÓN DEL SISTEMA:")
        print(f"   • URL objetivo: {scraper.target_url}")
        print(f"   • Intervalo de reintento: {scraper.retry_interval} minutos")
        print(f"   • Modo headless: {scraper.headless_mode}")
        print(f"   • Navegador: {scraper.browser_type}")
        print(f"{Style.RESET_ALL}")
        
        # Preguntar al usuario qué quiere hacer
        print(f"\n{Fore.YELLOW}¿Cómo desea ejecutar el monitoreo?")
        print("1. 🔍 Verificación única")
        print("2. 🔄 Monitoreo continuo")
        print(f"{Style.RESET_ALL}")
        
        while True:
            choice = input("\nSeleccione una opción (1 o 2): ").strip()
            
            if choice == "1":
                print(f"{Fore.GREEN}✅ Ejecutando verificación única...{Style.RESET_ALL}")
                result = await scraper.run_single_check()
                print(f"\n{Fore.CYAN}📊 RESULTADO FINAL:")
                print(f"   • Disponible: {result.get('available')}")
                print(f"   • Estado: {result.get('status')}")
                print(f"   • Mensaje: {result.get('message')}")
                print(f"{Style.RESET_ALL}")
                break
                
            elif choice == "2":
                print(f"{Fore.GREEN}✅ Iniciando monitoreo continuo...{Style.RESET_ALL}")
                await scraper.run_continuous_monitoring()
                break
                
            else:
                print(f"{Fore.RED}❌ Opción inválida. Seleccione 1 o 2{Style.RESET_ALL}")
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}🛑 Programa interrumpido por el usuario{Style.RESET_ALL}")
        
    except Exception as e:
        print(f"{Fore.RED}❌ Error general: {str(e)}{Style.RESET_ALL}")
        logging.error(f"Error general: {str(e)}")


if __name__ == "__main__":
    # Ejecutar el programa principal
    asyncio.run(main()) 