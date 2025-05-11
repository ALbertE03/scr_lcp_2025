import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, simpledialog, font
import threading
import time
import os
from protocol import *
from main import LCPPeer
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LCP-GUI")


class LCPChat(tk.Tk):
    def __init__(self):
        super().__init__()

        # Configuración de la ventana principal
        self.title("LCP Chat")
        self.geometry("800x600")
        self.minsize(600, 400)

        # Configurar estilo para botones más visibles
        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 11), padding=6)

        # Solicitar nombre de usuario al iniciar
        username = self.get_username()

        # Inicializar el peer LCP
        self.peer = LCPPeer(username)

        # Registrar los callbacks para eventos LCP
        self.peer.register_message_callback(self.on_message)
        self.peer.register_file_callback(self.on_file)
        self.peer.register_peer_discovery_callback(self.on_peer_change)
        self.peer.register_file_progress_callback(self.on_file_progress)

        # Variables para la interfaz
        self.current_chat = None
        self.chat_history = {}  # {user_id: [mensajes]}
        self.selected_user = tk.StringVar()

        # Crear interfaz
        self.create_widgets()

        # Actualizar periódicamente la lista de usuarios
        self.after(1000, self.update_ui)

        # Mostrar mensaje de bienvenida
        self.append_to_chat("Sistema", f"Bienvenido {username}!")
        self.append_to_chat(
            "Sistema", "Esperando descubrir otros usuarios en la red..."
        )

    def get_username(self):
        """Solicita un nombre de usuario al iniciar la aplicación"""
        username = simpledialog.askstring(
            "LCP Chat",
            "Introduce tu nombre de usuario:",
            initialvalue=f"User{int(time.time())%1000}",
        )
        if not username:
            username = f"User{int(time.time())%1000}"
        return username

    def create_widgets(self):
        """Crea los widgets de la interfaz"""
        # Crear frame principal con divisores
        main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Frame para lista de usuarios (izquierda)
        users_frame = ttk.Frame(main_paned, width=200)
        main_paned.add(users_frame, weight=1)

        # Frame para chat (derecha)
        chat_frame = ttk.Frame(main_paned)
        main_paned.add(chat_frame, weight=3)

        # Configurar frame de usuarios
        users_label = ttk.Label(
            users_frame, text="Usuarios Conectados", font=("Arial", 12, "bold")
        )
        users_label.pack(pady=5)

        # Lista de usuarios
        self.users_list = tk.Listbox(
            users_frame,
            listvariable=self.selected_user,
            selectmode=tk.SINGLE,
            height=20,
            font=("Arial", 11),
        )
        self.users_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.users_list.bind("<<ListboxSelect>>", self.on_user_select)

        # Botón de actualizar usuarios - Usar tk Button nativo con colores claros de fácil visualización
        refresh_btn = tk.Button(
            users_frame,
            text="Actualizar",
            command=self.refresh_users,
            font=("Arial", 11),
            bg="#e1e1e1",
            fg="black",
            padx=10,
            pady=5,
        )
        refresh_btn.pack(fill=tk.X, padx=5, pady=5)

        # Configurar frame de chat
        # Frame superior para mostrar mensajes
        chat_history_frame = ttk.Frame(chat_frame)
        chat_history_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Área de texto para mostrar mensajes
        self.chat_display = scrolledtext.ScrolledText(
            chat_history_frame,
            wrap=tk.WORD,
            state="disabled",
            height=20,
            font=("Arial", 11),
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        # Frame inferior para entrada de mensajes
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        # Campo de entrada de texto
        self.message_input = ttk.Entry(input_frame, font=("Arial", 11))
        self.message_input.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))
        self.message_input.bind("<Return>", self.send_message)

        # Frame para botones
        buttons_frame = ttk.Frame(chat_frame)
        buttons_frame.pack(fill=tk.X, pady=5)

        # Botones con colores contrastantes que aseguren visibilidad
        # Botón verde con texto negro
        send_btn = tk.Button(
            buttons_frame,
            text="Enviar",
            command=self.send_message,
            bg="#4CAF50",
            fg="black",
            font=("Arial", 11, "bold"),
            padx=15,
            pady=5,
        )
        send_btn.pack(side=tk.LEFT, padx=5)

        # Botón azul con texto negro
        file_btn = tk.Button(
            buttons_frame,
            text="Enviar Archivo",
            command=self.send_file,
            bg="#2196F3",
            fg="black",
            font=("Arial", 11),
            padx=15,
            pady=5,
        )
        file_btn.pack(side=tk.LEFT, padx=5)

        # Barra de estado
        self.status_var = tk.StringVar()
        self.status_var.set("Listo")
        status_bar = ttk.Label(
            self,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("Arial", 10),
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def update_ui(self):
        """Actualiza periódicamente la interfaz"""
        self.refresh_users()
        self.after(2000, self.update_ui)  # Actualizar cada 2 segundos

    def refresh_users(self):
        """Actualiza la lista de usuarios conectados"""
        peers = self.peer.get_peers()

        # Guardar la selección actual
        current_selection = None
        if self.users_list.curselection():
            current_selection = self.users_list.get(self.users_list.curselection()[0])

        # Actualizar la lista
        self.users_list.delete(0, tk.END)
        for peer_id in peers:
            self.users_list.insert(tk.END, peer_id)

        # Si había una selección, intentar mantenerla
        if current_selection:
            try:
                idx = peers.index(current_selection)
                self.users_list.selection_set(idx)
                self.users_list.see(idx)
            except ValueError:
                # El usuario seleccionado ya no está disponible
                self.current_chat = None

        # Actualizar contador en la barra de estado
        self.status_var.set(f"Conectados: {len(peers)} usuarios")

    def on_user_select(self, event):
        """Maneja la selección de un usuario de la lista"""
        if not self.users_list.curselection():
            return

        selected_idx = self.users_list.curselection()[0]
        selected_user = self.users_list.get(selected_idx)

        # Cambiar el chat activo
        self.current_chat = selected_user

        # Mostrar el historial de este usuario
        self.display_chat_history(selected_user)

    def display_chat_history(self, user_id):
        """Muestra el historial de chat con un usuario"""
        # Limpiar el área de chat
        self.chat_display.configure(state="normal")
        self.chat_display.delete(1.0, tk.END)

        # Mostrar historial si existe
        if user_id in self.chat_history:
            for msg in self.chat_history[user_id]:
                self.chat_display.insert(tk.END, f"{msg}\n")

        self.chat_display.configure(state="disabled")

        # Hacer scroll al final
        self.chat_display.see(tk.END)

    def append_to_chat(self, user_id, message):
        """Añade un mensaje al historial y lo muestra si es el chat actual"""
        # Formatear mensaje
        timestamp = time.strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {user_id}: {message}"

        # Guardar en historial
        if user_id not in self.chat_history:
            self.chat_history[user_id] = []

        # Añadir al historial
        self.chat_history[user_id].append(formatted_msg)

        # Si es el chat actual, mostrar
        if self.current_chat == user_id or user_id == "Sistema":
            self.chat_display.configure(state="normal")
            self.chat_display.insert(tk.END, f"{formatted_msg}\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see(tk.END)

    def send_message(self, event=None):
        """Envía un mensaje al usuario seleccionado"""
        if not self.current_chat:
            self.append_to_chat(
                "Sistema", "Por favor, selecciona un usuario para enviar mensajes."
            )
            return

        message = self.message_input.get().strip()
        if not message:
            return

        # Enviar el mensaje
        success = self.peer.send_message(self.current_chat, message)

        if success:
            # Añadir a nuestro propio historial
            self.append_to_chat("Tú", message)
            self.message_input.delete(0, tk.END)
        else:
            self.append_to_chat(
                "Sistema", f"Error enviando mensaje a {self.current_chat}."
            )

    def send_file(self):
        """Envía un archivo al usuario seleccionado"""
        if not self.current_chat:
            self.append_to_chat(
                "Sistema", "Por favor, selecciona un usuario para enviar archivos."
            )
            return

        # Abrir diálogo para seleccionar archivo
        filepath = filedialog.askopenfilename(title="Selecciona un archivo para enviar")
        if not filepath:
            return

        # Intentar enviar el archivo
        success = self.peer.send_file(self.current_chat, filepath)

        if success:
            filename = os.path.basename(filepath)
            self.append_to_chat(
                "Sistema",
                f"Iniciando envío de archivo: {filename} a {self.current_chat}",
            )
        else:
            self.append_to_chat(
                "Sistema", f"Error enviando archivo a {self.current_chat}."
            )

    # Callbacks para eventos LCP
    def on_message(self, user_from, message):
        """Callback para mensajes recibidos"""
        # Mostrar en la interfaz
        self.append_to_chat(user_from, message)

    def on_file(self, user_from, file_path):
        """Callback para archivos recibidos"""
        # Notificar sobre recepción de archivo
        filename = os.path.basename(file_path)
        self.append_to_chat("Sistema", f"Archivo recibido de {user_from}: {filename}")
        self.append_to_chat("Sistema", f"Guardado como: {file_path}")

    def on_peer_change(self, user_id, added):
        """Callback para cambios en la lista de peers"""
        action = "conectado" if added else "desconectado"
        self.append_to_chat("Sistema", f"Usuario {user_id} se ha {action}")
        self.refresh_users()

    def on_file_progress(self, user_id, file_path, progress, status):
        """Callback para actualizaciones de progreso de transferencias"""
        filename = os.path.basename(file_path)

        if status == "iniciando":
            self.append_to_chat(
                "Sistema", f"Iniciando envío de '{filename}' a {user_id}"
            )
        elif status == "progreso":
            if progress % 20 == 0:  # Actualizar cada 20%
                self.status_var.set(
                    f"Enviando '{filename}' a {user_id}: {progress}% completado"
                )
        elif status == "completado":
            self.append_to_chat(
                "Sistema", f"Archivo '{filename}' enviado correctamente a {user_id}"
            )
            self.status_var.set("Listo")
        elif status == "error":
            self.append_to_chat(
                "Sistema", f"Error enviando archivo '{filename}' a {user_id}"
            )
            self.status_var.set("Error en la transferencia")


if __name__ == "__main__":
    app = LCPChat()
    app.mainloop()
