import sys
import asyncio
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from tkinter.scrolledtext import ScrolledText
from datetime import datetime
import queue

from lcp import LCPProtocol
from protocol import LOG_FILE
from utils.logging import setup_logging

# Configurar logging
setup_logging(LOG_FILE)

# Paleta de colores moderna con mejor contraste
COLORS = {
    "primary": "#3f51b5",  # Azul índigo (color principal)
    "primary_dark": "#303f9f",  # Azul índigo oscuro)
    "primary_light": "#c5cae9",  # Azul índigo claro)
    "accent": "#ff4081",  # Rosa (color de acento)
    "accent_dark": "#f50057",  # Rosa oscuro)
    "accent_light": "#ff80ab",  # Rosa claro)
    "success": "#4caf50",  # Verde)
    "warning": "#ff9800",  # Naranja (mejor contraste que ámbar)
    "error": "#f44336",  # Rojo)
    "background": "#f5f5f5",  # Fondo claro)
    "surface": "#ffffff",  # Superficie blanca)
    "on_surface": "#eeeeee",  # Fondo claro para contenedores)
    "text_primary": "#212121",  # Texto primario oscuro (casi negro)
    "text_secondary": "#424242",  # Texto secundario gris oscuro)
    "text_on_primary": "#ffffff",  # Texto sobre fondo primario (blanco)
    "border": "#e0e0e0",  # Borde ligero)
    "message_outgoing": "#3f51b5",  # Burbuja mensaje enviado)
    "message_incoming": "#e0e0e0",  # Burbuja mensaje recibido)
}


class SignalBridge:
    """Puente para emitir señales de eventos asíncronos a la interfaz de Tkinter"""

    def __init__(self, root):
        self.root = root
        self.new_message_callback = None
        self.new_file_callback = None
        self.user_connected_callback = None
        self.user_disconnected_callback = None

    def emit_new_message(self, sender, message):
        if self.new_message_callback:
            self.root.after(0, lambda: self.new_message_callback(sender, message))

    def emit_new_file(self, sender, file_id, file_data):
        if self.new_file_callback:
            self.root.after(
                0, lambda: self.new_file_callback(sender, file_id, file_data)
            )

    def emit_user_connected(self, user_id):
        if self.user_connected_callback:
            self.root.after(0, lambda: self.user_connected_callback(user_id))

    def emit_user_disconnected(self, user_id):
        if self.user_disconnected_callback:
            self.root.after(0, lambda: self.user_disconnected_callback(user_id))


class ChatTab(ttk.Frame):
    """Frame para conversaciones individuales o grupales"""

    def __init__(self, parent, contact_name, is_group=False):
        super().__init__(parent)
        self.contact_name = contact_name
        self.is_group = is_group
        self.setup_ui()

    def setup_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Área de mensajes
        self.chat_area = ScrolledText(self, wrap=tk.WORD, state="disabled")
        self.chat_area.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.chat_area.tag_config(
            "outgoing",
            foreground=COLORS["text_on_primary"],
            background=COLORS["message_outgoing"],
            lmargin1=20,
            lmargin2=20,
            rmargin=20,
            spacing1=5,
            spacing3=5,
            relief="raised",
            borderwidth=2,
        )
        self.chat_area.tag_config(
            "incoming",
            foreground=COLORS["text_primary"],
            background=COLORS["message_incoming"],
            lmargin1=20,
            lmargin2=20,
            rmargin=20,
            spacing1=5,
            spacing3=5,
            relief="raised",
            borderwidth=2,
        )

        # Contenedor para campo de entrada y botones
        input_frame = ttk.Frame(self)
        input_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        # Campo de entrada
        self.message_input = ttk.Entry(input_frame)
        self.message_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)

        # Botón de enviar
        self.send_button = ttk.Button(input_frame, text="Enviar")
        self.send_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Botón de archivo
        self.file_button = ttk.Button(input_frame, text="Archivo")
        self.file_button.pack(side=tk.LEFT, padx=5, pady=5)

    def add_message(self, sender, message, is_outgoing=False):
        """Añade un mensaje al área de chat"""
        self.chat_area.config(state="normal")
        timestamp = datetime.now().strftime("%H:%M")

        if is_outgoing:
            tag = "outgoing"
            sender_name = "Tú"
            align = "right"
        else:
            tag = "incoming"
            sender_name = sender
            align = "left"

        self.chat_area.insert(tk.END, f"{sender_name} ({timestamp}):\n", tag)
        self.chat_area.insert(tk.END, f"{message}\n\n", tag)
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)

    def add_file_notification(self, sender, file_id, file_size, is_outgoing=False):
        """Añade notificación de archivo recibido"""
        self.chat_area.config(state="normal")
        timestamp = datetime.now().strftime("%H:%M")
        file_size_str = self._format_file_size(file_size)

        if is_outgoing:
            tag = "outgoing"
            sender_name = "Tú"
        else:
            tag = "incoming"
            sender_name = sender

        self.chat_area.insert(tk.END, f"{sender_name} ({timestamp}):\n", tag)
        self.chat_area.insert(tk.END, "📎 Archivo recibido\n", tag)
        self.chat_area.insert(tk.END, f"ID: {file_id}\n", tag)
        self.chat_area.insert(tk.END, f"Tamaño: {file_size_str}\n\n", tag)
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)

    def _format_file_size(self, size_bytes):
        """Formatea el tamaño de archivo a un formato más legible"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class CreateGroupDialog(simpledialog.Dialog):
    """Diálogo para crear grupos"""

    def __init__(self, parent, users):
        self.users = users
        self.selected_users = []
        super().__init__(parent, "Crear Grupo")

    def body(self, master):
        ttk.Label(master, text="Nombre del grupo:").grid(row=0, sticky=tk.W)
        self.group_name = ttk.Entry(master)
        self.group_name.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(master, text="Seleccionar miembros:").grid(
            row=1, columnspan=2, sticky=tk.W
        )

        self.user_list = tk.Listbox(master, selectmode=tk.MULTIPLE)
        self.user_list.grid(row=2, columnspan=2, sticky="nsew", padx=5, pady=5)

        for user_id in self.users:
            self.user_list.insert(tk.END, user_id)

        # Configurar scrollbar
        scrollbar = ttk.Scrollbar(
            master, orient="vertical", command=self.user_list.yview
        )
        scrollbar.grid(row=2, column=2, sticky="ns")
        self.user_list.config(yscrollcommand=scrollbar.set)

        # Configurar expansión
        master.grid_rowconfigure(2, weight=1)
        master.grid_columnconfigure(1, weight=1)

        return self.group_name

    def apply(self):
        self.group_name_value = self.group_name.get()
        self.selected_users = [self.users[i] for i in self.user_list.curselection()]


class AsyncIOHandler:
    def __init__(self):
        self.loop = None
        self.queue = queue.Queue()
        self.running = False

    def run_forever(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.running = True

        while self.running:
            try:
                # Obtener y ejecutar tareas de la cola
                while not self.queue.empty():
                    task = self.queue.get_nowait()
                    asyncio.ensure_future(task())

                # Ejecutar un paso del bucle
                self.loop.run_until_complete(asyncio.sleep(0.01))
            except Exception as e:
                print(f"Error en AsyncIOHandler: {e}")

    def stop(self):
        self.running = False
        if self.loop:
            self.loop.stop()


class LCPClient(tk.Tk):
    """Ventana principal del cliente LCP"""

    def __init__(self):
        super().__init__()
        self.lcp = None
        self.signal_bridge = SignalBridge(self)
        self.tabs = {}  # name -> tab
        self.groups = set()

        # Crear manejador de asyncio
        self.async_handler = AsyncIOHandler()
        self.async_queue = self.async_handler.queue

        self.setup_ui()
        self.setup_signals()

        # Protocolo para manejar cierre de ventana
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        """Maneja el cierre de la ventana principal"""
        if self.lcp and self.lcp.running:
            messagebox.showinfo(
                "Cerrando", "Desconectando de la red antes de cerrar..."
            )
            # Usa after para permitir que el mensaje se muestre
            self.after(100, self._cleanup_and_close)
        else:
            self._cleanup_and_close()

    def _cleanup_and_close(self):
        """Limpia los recursos y cierra la aplicación"""
        try:
            # Detener el manejador de asyncio
            if hasattr(self, "async_handler"):
                self.async_handler.stop()

            # Destruir la ventana principal
            self.destroy()
        except Exception as e:
            print(f"Error al cerrar la aplicación: {e}")
            sys.exit(1)

    def setup_ui(self):
        """Configura la interfaz de usuario"""
        self.title("LCP Chat")
        self.geometry("1200x700")
        self.configure(bg=COLORS["background"])

        # Configurar estilo
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Configurar estilos personalizados
        self.style.configure("TFrame", background=COLORS["background"])
        self.style.configure(
            "TLabel", background=COLORS["background"], foreground=COLORS["text_primary"]
        )
        self.style.configure("TButton", padding=6)
        self.style.configure(
            "Primary.TButton",
            background=COLORS["primary"],
            foreground=COLORS["text_on_primary"],
        )
        self.style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground=COLORS["text_on_primary"],
        )
        self.style.configure(
            "Warning.TButton",
            background=COLORS["warning"],
            foreground=COLORS["text_primary"],
        )
        self.style.configure(
            "Error.TButton",
            background=COLORS["error"],
            foreground=COLORS["text_on_primary"],
        )

        # Widget principal
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Panel izquierdo (contactos y grupos)
        left_panel = ttk.Frame(main_frame, width=300, style="TFrame")
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)

        # Información de usuario
        user_info = ttk.Frame(left_panel, style="TFrame")
        user_info.pack(fill=tk.X, pady=(0, 10))

        self.username_label = ttk.Label(
            user_info, text="No conectado", font=("Helvetica", 10, "bold")
        )
        self.username_label.pack(side=tk.LEFT, padx=5, pady=5)

        self.connect_button = ttk.Button(
            user_info, text="Conectar", style="Primary.TButton"
        )
        self.connect_button.pack(side=tk.RIGHT, padx=5, pady=5)

        # Sección de contactos
        contacts_label = ttk.Label(
            left_panel,
            text="Contactos",
            font=("Helvetica", 12, "bold"),
            foreground=COLORS["primary"],
        )
        contacts_label.pack(fill=tk.X, padx=5, pady=5)

        self.contacts_list = tk.Listbox(left_panel)
        self.contacts_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Botones de acción
        action_frame = ttk.Frame(left_panel)
        action_frame.pack(fill=tk.X, pady=5)

        self.broadcast_button = ttk.Button(
            action_frame, text="Broadcast", style="Accent.TButton"
        )
        self.broadcast_button.pack(side=tk.LEFT, expand=True, padx=5)

        self.create_group_button = ttk.Button(
            action_frame, text="Nuevo Grupo", style="Warning.TButton"
        )
        self.create_group_button.pack(side=tk.LEFT, expand=True, padx=5)

        # Sección de grupos
        groups_label = ttk.Label(
            left_panel,
            text="Grupos",
            font=("Helvetica", 12, "bold"),
            foreground=COLORS["primary"],
        )
        groups_label.pack(fill=tk.X, padx=5, pady=5)

        self.groups_list = tk.Listbox(left_panel)
        self.groups_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Panel derecho (pestañas de chat)
        self.tab_control = ttk.Notebook(main_frame)
        self.tab_control.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Barra de estado
        self.status_bar = ttk.Label(
            self,
            text="Desconectado",
            background=COLORS["primary"],
            foreground=COLORS["text_on_primary"],
            anchor=tk.CENTER,
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Configurar menú contextual
        self.contacts_menu = tk.Menu(self, tearoff=0)
        self.contacts_menu.add_command(label="Enviar Mensaje")
        self.contacts_menu.add_command(label="Enviar Archivo")
        self.contacts_menu.add_command(label="Invitar a Grupo")

        self.groups_menu = tk.Menu(self, tearoff=0)
        self.groups_menu.add_command(label="Abrir Chat")
        self.groups_menu.add_command(label="Invitar Usuario")

        self.contacts_list.bind("<Button-3>", self.show_contact_menu)
        self.groups_list.bind("<Button-3>", self.show_group_menu)

    def setup_signals(self):
        """Conecta señales y eventos"""
        self.connect_button.config(command=self.connect_to_network)
        self.broadcast_button.config(command=self.open_broadcast_tab)
        self.create_group_button.config(command=self.create_group_dialog)

        self.contacts_list.bind("<Double-1>", self.open_contact_chat)
        self.groups_list.bind("<Double-1>", self.open_group_chat)

        # Configurar callbacks del signal bridge
        self.signal_bridge.new_message_callback = self.handle_new_message
        self.signal_bridge.new_file_callback = self.handle_new_file
        self.signal_bridge.user_connected_callback = self.add_contact
        self.signal_bridge.user_disconnected_callback = self.remove_contact

    async def start(self):
        """Inicia el cliente LCP"""
        self.connect_to_network()

    def connect_to_network(self):
        """Conecta al usuario a la red LCP"""
        username = simpledialog.askstring("Conectar", "Introduce tu nombre de usuario:")
        if not username:
            return

        self.connect_button.config(state=tk.DISABLED, text="Conectando...")

        # En lugar de crear_task directamente, usa el bucle de asyncio en el hilo secundario
        self.async_queue.put(lambda: self._start_protocol(username))

    async def _start_protocol(self, username):
        """Inicia el protocolo LCP en segundo plano"""
        try:
            self.lcp = LCPProtocol(username)

            # Configurar callbacks
            self.lcp.add_message_callback(self._handle_message_callback)
            self.lcp.add_file_callback(self._handle_file_callback)
            self.lcp.add_user_connected_callback(
                self._handle_user_connected_callback
            )  # Añadir este

            await self.lcp.start()

            # Actualizar UI
            self.username_label.config(text=f"Conectado como: {username}")
            self.connect_button.config(
                state=tk.NORMAL,
                text="Desconectar",
                style="Error.TButton",
                command=self.disconnect_from_network,
            )
            self.status_bar.config(text=f"Conectado a la red LCP como {username}")

            # Iniciar tab de broadcast
            self.open_broadcast_tab()

            # Esperar un momento para descubrir usuarios
            await asyncio.sleep(2)

        except Exception as e:
            messagebox.showerror("Error de Conexión", f"No se pudo conectar: {str(e)}")
            self.connect_button.config(state=tk.NORMAL, text="Conectar")

    async def disconnect_from_network(self):
        """Desconecta de la red LCP"""
        if self.lcp and self.lcp.running:
            self.connect_button.config(state=tk.DISABLED, text="Desconectando...")

            await self.lcp.stop()

            # Limpiar UI
            self.username_label.config(text="No conectado")
            self.contacts_list.delete(0, tk.END)
            self.groups_list.delete(0, tk.END)

            # Cerrar todas las pestañas
            for tab_id in list(self.tabs.keys()):
                self.tab_control.forget(self.tabs[tab_id])
                del self.tabs[tab_id]

            # Resetear botón
            self.connect_button.config(
                state=tk.NORMAL,
                text="Conectar",
                style="Primary.TButton",
                command=self.connect_to_network,
            )
            self.status_bar.config(text="Desconectado de la red LCP")

    def open_broadcast_tab(self):
        """Abre pestaña de broadcast"""
        if "broadcast" not in self.tabs:
            broadcast_tab = ChatTab(self.tab_control, "broadcast", is_group=True)
            broadcast_tab.send_button.config(
                command=lambda: self.send_message(broadcast_tab)
            )
            broadcast_tab.file_button.config(
                command=lambda: self.send_file(broadcast_tab)
            )
            broadcast_tab.message_input.bind(
                "<Return>", lambda e: self.send_message(broadcast_tab)
            )

            self.tab_control.add(broadcast_tab, text="Broadcast")
            self.tabs["broadcast"] = broadcast_tab

        # Seleccionar la pestaña
        self.tab_control.select(self.tabs["broadcast"])

    def open_contact_chat(self, event=None):
        """Abre chat con un contacto"""
        selection = self.contacts_list.curselection()
        if not selection:
            return

        contact_name = self.contacts_list.get(selection[0])
        if contact_name not in self.tabs:
            contact_tab = ChatTab(self.tab_control, contact_name)
            contact_tab.send_button.config(
                command=lambda: self.send_message(contact_tab)
            )
            contact_tab.file_button.config(command=lambda: self.send_file(contact_tab))
            contact_tab.message_input.bind(
                "<Return>", lambda e: self.send_message(contact_tab)
            )

            self.tab_control.add(contact_tab, text=contact_name)
            self.tabs[contact_name] = contact_tab

            # Cargar historial
            if self.lcp:
                history = self.lcp.storage.get_message_history(contact_name)
                if contact_name in history and history[contact_name]:
                    for msg in history[contact_name]:
                        contact_tab.add_message(
                            "Tú" if msg["is_outgoing"] else contact_name,
                            msg["message"],
                            is_outgoing=msg["is_outgoing"],
                        )

        # Seleccionar la pestaña
        self.tab_control.select(self.tabs[contact_name])

    def open_group_chat(self, event=None):
        """Abre chat con un grupo"""
        selection = self.groups_list.curselection()
        if not selection:
            return

        group_name = self.groups_list.get(selection[0])
        if group_name not in self.tabs:
            group_tab = ChatTab(self.tab_control, group_name, is_group=True)
            group_tab.send_button.config(
                command=lambda: self.send_group_message(group_tab)
            )
            group_tab.message_input.bind(
                "<Return>", lambda e: self.send_group_message(group_tab)
            )

            self.tab_control.add(group_tab, text=f"🔊 {group_name}")
            self.tabs[group_name] = group_tab

        # Seleccionar la pestaña
        self.tab_control.select(self.tabs[group_name])

    def create_group_dialog(self):
        """Muestra diálogo para crear un grupo"""
        if not self.lcp or not self.lcp.running:
            messagebox.showwarning("Error", "Debes estar conectado para crear grupos")
            return

        known_users = list(self.lcp.known_users.keys())
        if not known_users:
            messagebox.showinfo(
                "Sin contactos", "No hay contactos disponibles para crear un grupo"
            )
            return

        dialog = CreateGroupDialog(self, known_users)

        if dialog.group_name_value:
            group_name = dialog.group_name_value
            members = dialog.selected_users

            if not group_name:
                messagebox.showwarning(
                    "Error", "El nombre del grupo no puede estar vacío"
                )
                return

            asyncio.create_task(self._create_group(group_name, members))

    async def _create_group(self, group_name, members):
        """Crea un grupo en segundo plano"""
        try:
            if await self.lcp.create_group(group_name):
                # Añadir a lista de grupos
                self.groups.add(group_name)
                self.groups_list.insert(tk.END, group_name)

                # Invitar a miembros
                for member in members:
                    await self.lcp.invite_to_group(group_name, member)

                # Abrir pestaña del grupo
                self.open_group_chat()

                messagebox.showinfo(
                    "Grupo Creado",
                    f"El grupo {group_name} ha sido creado correctamente",
                )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo crear el grupo: {str(e)}")

    def send_message(self, tab):
        """Envía un mensaje al contacto actual"""
        if not self.lcp or not self.lcp.running:
            return

        message = tab.message_input.get().strip()
        if not message:
            return

        # Limpiar campo
        tab.message_input.delete(0, tk.END)

        # Mostrar mensaje en la interfaz como "pendiente"
        tab.add_message("Tú", message, is_outgoing=True)

        # Enviar a través del protocolo
        asyncio.create_task(self._send_message_task(tab.contact_name, message))

    async def _send_message_task(self, contact_name, message):
        """Tarea para enviar el mensaje sin bloquear la UI"""
        try:
            await self.lcp.send_message(contact_name, message)
        except Exception as e:
            print(f"Error al enviar mensaje: {e}")

    def send_group_message(self, tab):
        """Envía un mensaje al grupo actual"""
        if not self.lcp or not self.lcp.running:
            return

        message = tab.message_input.get().strip()
        if not message:
            return

        # Limpiar campo
        tab.message_input.delete(0, tk.END)

        # Mostrar mensaje en la interfaz
        tab.add_message("Tú", message, is_outgoing=True)

        # Enviar a través del protocolo
        if tab.contact_name == "broadcast":
            asyncio.create_task(self._send_message_task("broadcast", message))
        else:
            asyncio.create_task(
                self._send_group_message_task(tab.contact_name, message)
            )

    async def _send_group_message_task(self, group_name, message):
        """Tarea para enviar mensaje de grupo"""
        try:
            await self.lcp.send_group_message(group_name, message)
        except Exception as e:
            print(f"Error al enviar mensaje de grupo: {e}")

    def send_file(self, tab):
        """Envía un archivo al contacto actual"""
        if not self.lcp or not self.lcp.running:
            return

        if tab.contact_name == "broadcast":
            messagebox.showwarning(
                "No soportado", "No se pueden enviar archivos por broadcast"
            )
            return

        # Abrir diálogo para seleccionar archivo
        file_path = filedialog.askopenfilename(title="Seleccionar Archivo")

        if not file_path:
            return

        try:
            with open(file_path, "rb") as f:
                file_data = f.read()

            # Mostrar indicador en la interfaz
            file_name = file_path.split("/")[-1]
            tab.add_message("Tú", f"Enviando archivo: {file_name}", is_outgoing=True)

            # Enviar archivo
            asyncio.create_task(self._send_file_task(tab.contact_name, file_data))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar el archivo: {str(e)}")

    async def _send_file_task(self, contact_name, file_data):
        """Tarea para enviar archivo"""
        try:
            await self.lcp.send_file(contact_name, file_data)
        except Exception as e:
            print(f"Error al enviar archivo: {e}")

    def add_contact(self, user_id):
        """Añade un contacto a la lista"""
        # Verificar que no esté ya en la lista
        if user_id in self.contacts_list.get(0, tk.END):
            return

        self.contacts_list.insert(tk.END, user_id)

    def remove_contact(self, user_id):
        """Elimina un contacto de la lista"""
        items = self.contacts_list.get(0, tk.END)
        if user_id in items:
            index = items.index(user_id)
            self.contacts_list.delete(index)

    def handle_new_message(self, sender, message):
        """Maneja un mensaje nuevo recibido"""
        if sender not in self.tabs:
            # Crear pestaña para el remitente si no existe
            contact_tab = ChatTab(self.tab_control, sender)
            contact_tab.send_button.config(
                command=lambda: self.send_message(contact_tab)
            )
            contact_tab.file_button.config(command=lambda: self.send_file(contact_tab))
            contact_tab.message_input.bind(
                "<Return>", lambda e: self.send_message(contact_tab)
            )

            self.tab_control.add(contact_tab, text=sender)
            self.tabs[sender] = contact_tab

        # Verificar si es un mensaje de sistema para grupos
        if message.startswith("SYSTEM:GROUP_"):
            parts = message.split(":")
            if len(parts) >= 3 and parts[1] == "GROUP_CREATED":
                group_name = parts[2]
                self.groups.add(group_name)
                self.groups_list.insert(tk.END, group_name)
                return
            elif len(parts) >= 3 and parts[1] == "GROUP_INVITE":
                group_name = parts[2]
                self.handle_group_invite(sender, group_name)
                return

        # Si es mensaje de grupo, identificar
        if message.startswith("[GRUPO "):
            group_end = message.find("]")
            if group_end > 7:
                group_name = message[7:group_end]
                # Crear pestaña de grupo si no existe
                if group_name not in self.tabs:
                    self.groups.add(group_name)
                    self.groups_list.insert(tk.END, group_name)
                    group_tab = ChatTab(self.tab_control, group_name, is_group=True)
                    group_tab.send_button.config(
                        command=lambda: self.send_group_message(group_tab)
                    )
                    group_tab.message_input.bind(
                        "<Return>", lambda e: self.send_group_message(group_tab)
                    )

                    self.tab_control.add(group_tab, text=f"🔊 {group_name}")
                    self.tabs[group_name] = group_tab

                # Añadir mensaje a la pestaña de grupo
                self.tabs[group_name].add_message(sender, message[group_end + 2 :])
                return

        # Añadir mensaje a la pestaña correspondiente
        self.tabs[sender].add_message(sender, message)

    def handle_group_invite(self, sender, group_name):
        """Maneja una invitación a un grupo"""
        reply = messagebox.askyesno(
            "Invitación a Grupo",
            f"{sender} te ha invitado al grupo '{group_name}'. ¿Deseas unirte?",
        )

        if reply:
            asyncio.create_task(self._join_group(group_name))

    async def _join_group(self, group_name):
        """Une al usuario a un grupo"""
        try:
            if await self.lcp.join_group(group_name):
                # Añadir a lista de grupos si no existe
                if group_name not in self.groups:
                    self.groups.add(group_name)
                    self.groups_list.insert(tk.END, group_name)

                # Abrir pestaña del grupo
                self.open_group_chat()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo unir al grupo: {str(e)}")

    def handle_new_file(self, sender, file_id, file_data):
        """Maneja un archivo nuevo recibido"""
        if sender not in self.tabs:
            # Crear pestaña para el remitente si no existe
            contact_tab = ChatTab(self.tab_control, sender)
            contact_tab.send_button.config(
                command=lambda: self.send_message(contact_tab)
            )
            contact_tab.file_button.config(command=lambda: self.send_file(contact_tab))
            contact_tab.message_input.bind(
                "<Return>", lambda e: self.send_message(contact_tab)
            )

            self.tab_control.add(contact_tab, text=sender)
            self.tabs[sender] = contact_tab

        # Añadir notificación de archivo
        self.tabs[sender].add_file_notification(sender, file_id, len(file_data))

        # Preguntar si guardar archivo
        reply = messagebox.askyesno(
            "Archivo Recibido",
            f"Has recibido un archivo de {sender} ({len(file_data)} bytes). ¿Deseas guardarlo?",
        )

        if reply:
            # Abrir diálogo para guardar
            file_path = filedialog.asksaveasfilename(
                title="Guardar Archivo", initialfile=f"archivo_{file_id}"
            )

            if file_path:
                try:
                    with open(file_path, "wb") as f:
                        f.write(file_data)
                    messagebox.showinfo(
                        "Archivo Guardado",
                        f"El archivo se guardó correctamente en {file_path}",
                    )
                except Exception as e:
                    messagebox.showerror(
                        "Error", f"No se pudo guardar el archivo: {str(e)}"
                    )

    def show_contact_menu(self, event):
        """Muestra menú contextual para contactos"""
        if not self.contacts_list.size():
            return

        try:
            index = self.contacts_list.nearest(event.y)
            contact_name = self.contacts_list.get(index)

            # Configurar menú
            self.contacts_menu.entryconfig(0, command=lambda: self.open_contact_chat())
            self.contacts_menu.entryconfig(
                1, command=lambda: self._send_file_to_contact(contact_name)
            )
            self.contacts_menu.entryconfig(
                2, command=lambda: self.show_invite_dialog(contact_name)
            )

            self.contacts_menu.post(event.x_root, event.y_root)
        except:
            pass

    def show_group_menu(self, event):
        """Muestra menú contextual para grupos"""
        if not self.groups_list.size():
            return

        try:
            index = self.groups_list.nearest(event.y)
            group_name = self.groups_list.get(index)

            # Configurar menú
            self.groups_menu.entryconfig(0, command=lambda: self.open_group_chat())
            self.groups_menu.entryconfig(
                1, command=lambda: self.show_group_invite_dialog(group_name)
            )

            self.groups_menu.post(event.x_root, event.y_root)
        except:
            pass

    def _send_file_to_contact(self, contact_name):
        """Envía archivo a un contacto desde el menú contextual"""
        # Abrir chat y simular clic en botón de archivo
        self.open_contact_chat()
        if contact_name in self.tabs:
            self.send_file(self.tabs[contact_name])

    def show_invite_dialog(self, contact_name):
        """Muestra diálogo para invitar usuario a un grupo"""
        if not self.lcp or not self.lcp.running:
            messagebox.showwarning(
                "Error", "Debes estar conectado para invitar usuarios"
            )
            return

        if not self.groups:
            messagebox.showinfo("Sin grupos", "No tienes grupos creados")
            return

        # Crear diálogo personalizado
        dialog = tk.Toplevel(self)
        dialog.title(f"Invitar a {contact_name}")
        dialog.resizable(False, False)

        ttk.Label(
            dialog, text=f"Selecciona el grupo al que invitar a {contact_name}:"
        ).pack(padx=10, pady=5)

        group_combo = ttk.Combobox(dialog, values=list(self.groups))
        group_combo.pack(padx=10, pady=5, fill=tk.X)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(padx=10, pady=10, fill=tk.X)

        ok_button = ttk.Button(
            button_frame,
            text="Aceptar",
            command=lambda: self._invite_from_dialog(dialog, group_combo, contact_name),
        )
        ok_button.pack(side=tk.RIGHT, padx=5)

        cancel_button = ttk.Button(
            button_frame, text="Cancelar", command=dialog.destroy
        )
        cancel_button.pack(side=tk.RIGHT, padx=5)

    def show_group_invite_dialog(self, group_name):
        """Muestra diálogo para invitar usuarios a un grupo específico"""
        if not self.lcp or not self.lcp.running:
            messagebox.showwarning(
                "Error", "Debes estar conectado para invitar usuarios"
            )
            return

        known_users = list(self.lcp.known_users.keys())
        if not known_users:
            messagebox.showinfo(
                "Sin contactos", "No hay contactos disponibles para invitar"
            )
            return

        # Crear diálogo personalizado
        dialog = tk.Toplevel(self)
        dialog.title(f"Invitar a {group_name}")
        dialog.resizable(False, False)

        ttk.Label(
            dialog, text=f"Selecciona el usuario a invitar al grupo {group_name}:"
        ).pack(padx=10, pady=5)

        user_combo = ttk.Combobox(dialog, values=known_users)
        user_combo.pack(padx=10, pady=5, fill=tk.X)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(padx=10, pady=10, fill=tk.X)

        ok_button = ttk.Button(
            button_frame,
            text="Aceptar",
            command=lambda: self._invite_user_from_dialog(
                dialog, group_name, user_combo
            ),
        )
        ok_button.pack(side=tk.RIGHT, padx=5)

        cancel_button = ttk.Button(
            button_frame, text="Cancelar", command=dialog.destroy
        )
        cancel_button.pack(side=tk.RIGHT, padx=5)

    def _invite_from_dialog(self, dialog, group_combo, contact_name):
        """Procesa la invitación desde el diálogo"""
        selected_group = group_combo.get()
        if not selected_group:
            messagebox.showwarning("Error", "Debes seleccionar un grupo")
            return

        dialog.destroy()
        asyncio.create_task(self._invite_to_group(selected_group, contact_name))

    def _invite_user_from_dialog(self, dialog, group_name, user_combo):
        """Procesa la invitación de usuario desde el diálogo"""
        selected_user = user_combo.get()
        if not selected_user:
            messagebox.showwarning("Error", "Debes seleccionar un usuario")
            return

        dialog.destroy()
        asyncio.create_task(self._invite_to_group(group_name, selected_user))

    async def _invite_to_group(self, group_name, user_id):
        """Invita a un usuario a un grupo"""
        try:
            if await self.lcp.invite_to_group(group_name, user_id):
                messagebox.showinfo(
                    "Invitación Enviada",
                    f"{user_id} ha sido invitado al grupo {group_name}",
                )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar la invitación: {str(e)}")

    # Métodos de callback para el protocolo LCP
    async def _handle_message_callback(self, sender, message):
        """Callback para mensajes recibidos"""
        self.signal_bridge.emit_new_message(sender, message)

    async def _handle_file_callback(self, sender, file_id, file_data):
        """Callback para archivos recibidos"""
        self.signal_bridge.emit_new_file(sender, file_id, file_data)


def main():
    # Iniciar cliente
    window = LCPClient()
    import threading

    # Ejecutar el bucle de asyncio en un hilo separado
    asyncio_thread = threading.Thread(
        target=window.async_handler.run_forever, daemon=True
    )
    asyncio_thread.start()

    # Dar tiempo a la ventana para inicializarse
    window.after(100, lambda: window.async_queue.put(lambda: window.start()))

    # Iniciar el bucle principal de Tkinter en el hilo principal
    window.mainloop()


if __name__ == "__main__":
    main()
