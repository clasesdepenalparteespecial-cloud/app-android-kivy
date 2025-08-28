import os
import threading
import time
import ssl
import socket
import json
import shutil

# --- Kivy Imports ---
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.utils import platform

# --- Plyer Import ---
from plyer import filechooser

# --- Google API Imports ---
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

# -------------------------------------------------------------------
# LÓGICA DE GOOGLE DRIVE (Adaptada para Android)
# -------------------------------------------------------------------

# Parche de red, seguro para Android
try:
    ssl._create_default_https_context = ssl.create_default_context
except AttributeError:
    pass

# Constantes
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CHUNK_SIZE = 256 * 1024  # 256 KiB

def get_service(cuenta: str, creds_path: str, token_dir: str):
    """
    Obtiene un servicio autenticado de Google Drive.
    En Android, SOLO refresca tokens, NUNCA crea nuevos.
    """
    token_filename = f"token_{cuenta.lower().replace(' ', '_')}.json"
    token_path = os.path.join(token_dir, token_filename)
    creds = None

    if not os.path.exists(token_path):
        raise FileNotFoundError(f"No se encontró el archivo de token: {token_path}")

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print(f"Refrescando token para {cuenta}...")
            creds.refresh(Request())
            # Guardar el token refrescado para la próxima vez
            with open(token_path, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
        else:
            # Si el token no es válido y no se puede refrescar, es un error fatal en Android
            raise ConnectionError(f"Token inválido o expirado para '{cuenta}'. Genéralo de nuevo en PC.")

    return build("drive", "v3", credentials=creds, cache_discovery=False)

def _is_transient(err: Exception) -> bool:
    s = str(err).lower()
    return any(sig in s for sig in (
        "eof occurred", "connection reset", "broken pipe", "timed out", 
        "timeout", "ssl", "tls", "reset by peer", "transport closed",
        "503", "500", "429",
    ))

def _next_chunk_with_retry(request, max_retries: int = 7, base_delay: float = 1.2):
    intento = 0
    while True:
        try:
            return request.next_chunk()
        except (ssl.SSLError, socket.timeout, socket.error, ConnectionResetError, BrokenPipeError, HttpError) as e:
            if intento < max_retries and _is_transient(e):
                sleep_s = base_delay * (2 ** intento)
                print(f"Error transitorio: {e}. Reintentando en {sleep_s:.2f}s...")
                time.sleep(sleep_s)
                intento += 1
                continue
            raise

# -------------------------------------------------------------------
# LÓGICA DE LA APP KIVY
# -------------------------------------------------------------------

KV_STRING = '''
<UploaderInterface>:
    orientation: 'vertical'
    padding: '20dp'
    spacing: '15dp'

    Label:
        id: selected_files_label
        text: 'Sin archivos seleccionados'
        size_hint_y: None
        height: '40dp'
        halign: 'center'

    Button:
        text: 'Seleccionar archivos…'
        size_hint_y: None
        height: '48dp'
        on_release: root.pick_files()

    ProgressBar:
        id: progress_bar
        max: 100
        value: 0
        size_hint_y: None
        height: '20dp'

    Label:
        id: status_label
        text: 'Selecciona una cuenta y archivos para empezar'
        halign: 'center'
        font_size: '16sp'
        text_size: self.width, None

    ScrollView:
        do_scroll_x: False
        GridLayout:
            id: accounts_grid
            cols: 1
            spacing: '10dp'
            size_hint_y: None
            height: self.minimum_height
'''
Builder.load_string(KV_STRING)

class UploaderInterface(BoxLayout):
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_paths = []
        self.app = App.get_running_app()
        # Llamar a la creación de botones en el siguiente frame
        # para asegurar que la app esté completamente inicializada
        Clock.schedule_once(self.create_account_buttons)

    def create_account_buttons(self, dt=None):
        grid = self.ids.accounts_grid
        grid.clear_widgets() # Limpiar por si se llama de nuevo

        if not self.app.config_data or 'cuentas' not in self.app.config_data:
            self.ids.status_label.text = "Error: No se pudo cargar la configuración."
            return

        for cuenta_nombre in self.app.config_data['cuentas'].keys():
            btn = Button(
                text=f'Subir a: {cuenta_nombre}',
                size_hint_y=None,
                height='48dp',
            )
            # Usar una función lambda para capturar el nombre de la cuenta
            btn.bind(on_release=lambda instance, c=cuenta_nombre: self.start_upload(c))
            grid.add_widget(btn)

    def pick_files(self):
        try:
            filechooser.open_file(on_selection=self.handle_selection, multiple=True)
        except Exception as e:
            self.ids.status_label.text = f"Error al abrir selector: {e}"

    def handle_selection(self, selection):
        if selection:
            self.selected_paths = selection
            self.ids.selected_files_label.text = f"{len(selection)} archivo(s) seleccionado(s)"
            self.ids.status_label.text = "Archivos listos. Selecciona una cuenta para subir."

    def start_upload(self, cuenta):
        if not self.selected_paths:
            self.ids.status_label.text = "Error: Primero selecciona archivos."
            return

        self.ids.status_label.text = f"Preparando subida para {cuenta}..."
        
        # Deshabilitar botones
        for button in self.ids.accounts_grid.children:
            button.disabled = True
        
        threading.Thread(
            target=self._upload_thread_target,
            args=(cuenta, self.selected_paths),
            daemon=True
        ).start()

    def _update_ui(self, status_text=None, progress_val=None):
        if status_text is not None:
            self.ids.status_label.text = status_text
        if progress_val is not None:
            self.ids.progress_bar.value = progress_val

    def _upload_thread_target(self, cuenta, rutas):
        try:
            folder_id = self.app.config_data['cuentas'][cuenta].get("carpeta")
            if not folder_id:
                raise ValueError(f"No se encontró 'carpeta' para '{cuenta}'")

            service = get_service(cuenta, self.app.creds_path, self.app.token_dir)
            total = len(rutas)
            
            for i, ruta in enumerate(rutas, start=1):
                nombre = os.path.basename(ruta)
                
                status_msg = f"Subiendo ({i}/{total}): {nombre}"
                Clock.schedule_once(lambda dt, msg=status_msg: self._update_ui(status_text=msg, progress_val=0))
                
                metadata = {"name": nombre, "parents": [folder_id]}
                media = MediaFileUpload(ruta, chunksize=CHUNK_SIZE, resumable=True)
                request = service.files().create(body=metadata, media_body=media, fields="id")
                
                while True:
                    status, done = _next_chunk_with_retry(request)
                    if status:
                        porc = int(status.progress() * 100)
                        Clock.schedule_once(lambda dt, p=porc: self._update_ui(progress_val=p))
                    if done:
                        break
            
            Clock.schedule_once(lambda dt: self._update_ui(status_text='✅ Subida completada', progress_val=100))

        except Exception as e:
            print(f"ERROR DURANTE LA SUBIDA: {type(e).__name__}: {e}")
            error_msg = f"Error: {e}"
            Clock.schedule_once(lambda dt, msg=error_msg: self._update_ui(status_text=msg))
        
        finally:
            # Volver a habilitar los botones
            def enable_buttons(dt):
                for button in self.ids.accounts_grid.children:
                    button.disabled = False
            Clock.schedule_once(enable_buttons)


class MainApp(App):
    def build(self):
        # Estas variables contendrán los datos de configuración
        self.config_data = None
        
        # Rutas de archivos dentro del directorio de datos de la app
        self.config_path = os.path.join(self.user_data_dir, 'config.json')
        self.creds_path = os.path.join(self.user_data_dir, 'credentials.json')
        self.token_dir = os.path.join(self.user_data_dir, 'tokens')
        
        return UploaderInterface()

    def on_start(self):
        """Se ejecuta al iniciar la app. Ideal para permisos y configuración inicial."""
        self.request_android_permissions()
        self.setup_app_files()
        self.load_app_config()

    def request_android_permissions(self):
        if platform == 'android':
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.INTERNET,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE # Aunque no se use, es buena práctica
            ])

    def setup_app_files(self):
        """
        Copia los archivos de configuración desde el paquete de la app al
        directorio de datos del usuario si no existen. Esto solo ocurre en la primera ejecución.
        """
        # Función para copiar si el destino no existe
        def copy_if_not_exists(src, dst):
            if not os.path.exists(dst):
                print(f"Copiando '{src}' a '{dst}'")
                shutil.copy2(src, dst)

        # Copiar archivos individuales
        copy_if_not_exists('config.json', self.config_path)
        copy_if_not_exists('credentials.json', self.creds_path)

        # Copiar el directorio de tokens
        if not os.path.exists(self.token_dir):
            print(f"Copiando directorio 'tokens' a '{self.token_dir}'")
            shutil.copytree('tokens', self.token_dir)
            
    def load_app_config(self):
        """Carga la configuración desde el archivo JSON en el directorio de datos."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)
        except Exception as e:
            print(f"Error fatal: No se pudo cargar el archivo de configuración '{self.config_path}': {e}")
            # En una app real, aquí mostrarías un popup de error
            self.config_data = None


if __name__ == "__main__":
    MainApp().run()