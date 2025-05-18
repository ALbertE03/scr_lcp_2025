import customtkinter as ctk
from tkinter import filedialog, simpledialog
import time
import os
import logging
import concurrent.futures
import queue
from utils import get_optimal_thread_count
from main import Peer


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LCP-GUI")


class LCPChat(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("LCP Chat 2025")
        self.geometry("1000x700")
        self.minsize(800, 600)

        # Configuración de colores
        self.bg_color = ("#f0f0f0", "#2b2b2b")
        self.text_color = ("#000000", "#ffffff")
        self.button_color = ("#4a90e2", "#1f6aa5")
        self.success_color = ("#4CAF50", "#2E7D32")
        self.warning_color = ("#FF9800", "#F57C00")
        self.error_color = ("#F44336", "#D32F2F")
        self.progress_color = ("#4a90e2", "#1f6aa5")

        self.sent_file_notifications = set()

        n, _, _ = get_optimal_thread_count()
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=n, thread_name_prefix="GUI-Worker"
        )

        self.update_queue = queue.Queue()

        username = self.get_username()

        self.peer = Peer(username)

        self.peer.register_message_callback(self.on_message)
        self.peer.register_file_callback(self.on_file)
        self.peer.register_peer_discovery_callback(self.on_peer_change)
        self.peer.register_file_progress_callback(self.on_file_progress)

        self.current_chat = None
        self.chat_history = {}
        self.selected_user = ctk.StringVar()

        self.file_progress_bars = {}
        self.progress_window = None

        self.create_widgets()

        self.after(1000, self.update_ui)
        self.after(100, self.process_ui_updates)

        self.append_to_chat("Sistema", f"Bienvenido {username}!")
        self.append_to_chat(
            "Sistema", "Esperando descubrir otros usuarios en la red..."
        )

    def __del__(self):
        """Destructor para liberar recursos"""
        if hasattr(self, "thread_pool"):
            self.thread_pool.shutdown(wait=False)

        if hasattr(self, "progress_window") and self.progress_window is not None:
            try:
                self.progress_window.destroy()
            except:
                pass

    def get_username(self):
        """Solicita un nombre de usuario al iniciar la aplicación"""
        username = simpledialog.askstring(
            "LCP Chat",
            "Introduce tu nombre de usuario:",
            initialvalue="Albert",
        )
        if not username:
            username = f"User{int(time.time())%1000}"
        return username

    def create_progress_window(self):
        """Crea la ventana única para mostrar todas las transferencias de archivos"""
        # Si la ventana ya existe, no crear una nueva
        if self.progress_window is not None:
            if self.progress_window.winfo_exists():
                return

        # Crear ventana de progreso principal (oculta inicialmente)
        self.progress_window = ctk.CTkToplevel(self)
        self.progress_window.withdraw()  # Ocultar mientras se configura

        self.progress_window.title("Transferencias de Archivos")
        self.progress_window.geometry("550x400")
        self.progress_window.resizable(True, True)
        self.progress_window.transient(self)
        self.progress_window.protocol("WM_DELETE_WINDOW", self.hide_progress_window)

        # Frame para el título y herramientas
        header_frame = ctk.CTkFrame(self.progress_window)
        header_frame.pack(fill="x", padx=10, pady=(10, 0))

        # Título con ícono
        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=5)

        icon_label = ctk.CTkLabel(title_frame, text="📁", font=("Arial", 20))
        icon_label.pack(side="left", padx=(5, 5))

        title_label = ctk.CTkLabel(
            title_frame,
            text="Transferencias de Archivos",
            font=("Arial", 16, "bold"),
        )
        title_label.pack(side="left", pady=5)

        # Botones de herramientas
        button_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=5)

        # Etiqueta de estado
        self.transfer_status = ctk.CTkLabel(
            button_frame,
            text="Sin transferencias activas",
            font=("Arial", 11),
            text_color=("gray60", "gray70"),
        )
        self.transfer_status.pack(side="left", padx=10)

        # Botón para limpiar completadas
        clear_button = ctk.CTkButton(
            button_frame,
            text="Limpiar Completadas",
            command=self.clear_completed_transfers,
            font=("Arial", 11),
            height=28,
            width=30,
            fg_color=("#3498db", "#2980b9"),
        )
        clear_button.pack(side="right", padx=10)

        # Separador
        separator = ctk.CTkFrame(
            self.progress_window, height=1, fg_color=("gray80", "gray30")
        )
        separator.pack(fill="x", padx=10, pady=(0, 5))

        # Frame contenedor para las barras de progreso (con scroll)
        self.transfers_container = ctk.CTkScrollableFrame(self.progress_window)
        self.transfers_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Actualizar todos los componentes antes de mostrar
        self.progress_window.update_idletasks()

        # Mostrar la ventana
        self.progress_window.deiconify()
        self.progress_window.focus_force()
        self.progress_window.attributes("-topmost", True)

    def hide_progress_window(self):
        """Oculta la ventana de progreso en lugar de destruirla"""
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.withdraw()

    def show_progress_window(self):
        """Muestra la ventana de progreso si existe"""
        if self.progress_window is None or not self.progress_window.winfo_exists():
            self.create_progress_window()
        else:
            self.progress_window.deiconify()
            self.progress_window.focus_force()
            self.progress_window.attributes("-topmost", True)

    def create_progress_bar(self, user_id, filename):
        """Crea una barra de progreso visual para un archivo en transferencia"""

        self.show_progress_window()

        file_key = f"{user_id}_{filename}"

        if file_key in self.file_progress_bars:
            logger.debug(f"Eliminando barra de progreso existente para {file_key}")
            progress_data = self.file_progress_bars[file_key]
            if "frame" in progress_data and progress_data["frame"] is not None:
                progress_data["frame"].destroy()
            del self.file_progress_bars[file_key]

        transfer_frame = ctk.CTkFrame(
            self.transfers_container,
            corner_radius=6,
            border_width=1,
            border_color=("gray85", "gray25"),
            fg_color=("gray95", "gray15"),
        )
        transfer_frame.pack(fill="x", pady=5, padx=5)

        header_frame = ctk.CTkFrame(transfer_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(8, 0), padx=5)

        icon_label = ctk.CTkLabel(header_frame, text="📄", font=("Arial", 18))
        icon_label.pack(side="left", padx=5)

        short_filename = filename
        if len(filename) > 30:
            short_filename = filename[:27] + "..."

        file_label = ctk.CTkLabel(
            header_frame,
            text=f"{short_filename} → {user_id}",
            font=("Arial", 12),
            anchor="w",
        )
        file_label.pack(side="left", fill="x", expand=True, padx=5)

        close_button = ctk.CTkButton(
            header_frame,
            text="×",
            width=22,
            height=22,
            font=("Arial", 14, "bold"),
            fg_color=("gray75", "gray40"),
            hover_color=("gray65", "gray30"),
            command=lambda: self.remove_progress_bar(user_id, filename),
        )
        close_button.pack(side="right", padx=(0, 5))

        percent_label = ctk.CTkLabel(
            header_frame,
            text="0%",
            font=("Arial", 12, "bold"),
        )
        percent_label.pack(side="right", padx=(0, 8))

        bar_container = ctk.CTkFrame(transfer_frame, fg_color="transparent")
        bar_container.pack(fill="x", pady=(5, 8), padx=10)

        progress_bar = ctk.CTkProgressBar(
            bar_container,
            orientation="horizontal",
            mode="determinate",
            height=15,
            fg_color=("#E0E0E0", "#3a3a3a"),
            progress_color=("#4a90e2", "#1f6aa5"),
            corner_radius=2,
        )
        progress_bar.pack(fill="x")
        progress_bar.set(0)

        # Guardar referencias
        self.file_progress_bars[file_key] = {
            "frame": transfer_frame,
            "bar": progress_bar,
            "label": percent_label,
            "file_label": file_label,
            "icon": icon_label,
            "close_button": close_button,
            "_last_value": 0,
        }

        # Actualizar la ventana
        self.progress_window.update_idletasks()

    def update_progress_bar(self, user_id, filename, progress):
        """Actualiza la barra de progreso sin parpadeos"""
        file_key = f"{user_id}_{filename}"

        if file_key in self.file_progress_bars:
            progress_data = self.file_progress_bars[file_key]
            self.show_progress_window()
            if abs(progress_data["_last_value"] - progress) >= 5 or progress in [
                0,
                25,
                50,
                75,
                100,
            ]:
                try:
                    # Actualizar barra de progreso
                    progress_data["bar"].set(progress / 100)
                    progress_data["label"].configure(text=f"{progress}%")
                    progress_data["_last_value"] = progress

                    if progress < 25:
                        progress_bar_color = ("#4a90e2", "#1f6aa5")
                    elif progress < 50:
                        progress_bar_color = ("#3498db", "#2980b9")
                    elif progress < 75:
                        progress_bar_color = ("#2ecc71", "#27ae60")
                    elif progress < 100:
                        progress_bar_color = ("#f39c12", "#d35400")
                    else:
                        progress_bar_color = ("#2ecc71", "#27ae60")

                    progress_data["bar"].configure(progress_color=progress_bar_color)

                    if progress < 100:
                        progress_data["file_label"].configure(
                            text=f"{filename} → {user_id}"
                        )
                        progress_data["icon"].configure(text="🔄")
                    else:
                        progress_data["file_label"].configure(
                            text=f"{filename} → {user_id} (Completado)"
                        )
                        progress_data["icon"].configure(text="✅")
                        self.after(
                            3000, lambda: self.remove_progress_bar(user_id, filename)
                        )

                except Exception as e:
                    logger.debug(f"Error al actualizar barra: {e}")

            if self.progress_window and self.progress_window.winfo_exists():
                self.progress_window.update_idletasks()

    def remove_progress_bar(self, user_id, filename):
        """Elimina una barra de progreso específica"""
        file_key = f"{user_id}_{filename}"

        if file_key in self.file_progress_bars:
            progress_data = self.file_progress_bars[file_key]
            if "frame" in progress_data and progress_data["frame"] is not None:
                try:
                    progress_data["frame"].destroy()
                except Exception:
                    pass
            del self.file_progress_bars[file_key]

            if not self.file_progress_bars:

                self.after(1000, self.hide_progress_window)
            else:

                active_transfers = sum(
                    1
                    for k, v in self.file_progress_bars.items()
                    if v.get("_last_value", 0) < 100
                )
                if active_transfers > 0:
                    self.transfer_status.configure(
                        text=f"{active_transfers} transferencias activas"
                    )
                else:
                    self.transfer_status.configure(
                        text="Todas las transferencias completadas"
                    )

    def clear_completed_transfers(self):
        """Limpia las barras de progreso de transferencias completadas"""
        completed_keys = []

        # Identificar transferencias completadas
        for file_key, progress_data in self.file_progress_bars.items():
            if progress_data.get("_last_value", 0) >= 100:
                completed_keys.append(file_key)

        # Eliminar las barras de progreso completadas
        for file_key in completed_keys:
            parts = file_key.split("_", 1)
            if len(parts) == 2:
                user_id, filename = parts
                self.remove_progress_bar(user_id, filename)

        # Al limpiar las transferencias, también limpiamos las notificaciones
        if hasattr(self, "sent_file_notifications"):
            self.sent_file_notifications.clear()

        # Actualizar estado
        if self.file_progress_bars:
            active_count = len(self.file_progress_bars)
            self.transfer_status.configure(
                text=f"{active_count} transferencias activas"
            )
        else:
            self.transfer_status.configure(text="Sin transferencias activas")
            self.after(500, self.hide_progress_window)

    def create_widgets(self):
        """Crea los widgets de la interfaz"""
        # Configurar grid principal
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Frame lateral para usuarios
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(1, weight=1)

        # Título usuarios
        self.sidebar_label = ctk.CTkLabel(
            self.sidebar_frame, text="Usuarios Conectados", font=("Arial", 14, "bold")
        )
        self.sidebar_label.grid(row=0, column=0, padx=20, pady=10)

        # Lista de usuarios
        self.users_list = ctk.CTkScrollableFrame(self.sidebar_frame)
        self.users_list.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # Botón actualizar
        self.refresh_button = ctk.CTkButton(
            self.sidebar_frame,
            text="Actualizar",
            command=self.refresh_users,
            font=("Arial", 12),
        )
        self.refresh_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        # Frame principal del chat
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Área de chat
        self.chat_display = ctk.CTkTextbox(
            self.main_frame, wrap="word", state="disabled", font=("Arial", 14)
        )
        self.chat_display.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        # Frame de entrada de mensaje
        self.input_frame = ctk.CTkFrame(self.main_frame, height=50)
        self.input_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        # Entrada de mensaje
        self.message_input = ctk.CTkEntry(
            self.input_frame,
            placeholder_text="Escribe tu mensaje aquí...",
            font=("Arial", 14),
        )
        self.message_input.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.message_input.bind("<Return>", self.send_message)

        # Botón enviar
        self.send_button = ctk.CTkButton(
            self.input_frame,
            text="Enviar",
            command=self.send_message,
            width=80,
            font=("Arial", 12),
        )
        self.send_button.grid(row=0, column=1, padx=(0, 5))

        # Frame de botones adicionales
        self.buttons_frame = ctk.CTkFrame(self.main_frame)
        self.buttons_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")

        # Botón broadcast
        self.broadcast_button = ctk.CTkButton(
            self.buttons_frame,
            text="Enviar a Todos",
            command=self.send_broadcast,
            fg_color=self.warning_color,
            font=("Arial", 12),
        )
        self.broadcast_button.pack(side="left", padx=5, pady=5, fill="x", expand=True)

        # Botón archivo
        self.file_button = ctk.CTkButton(
            self.buttons_frame,
            text="Enviar Archivo",
            command=self.send_file,
            font=("Arial", 12),
        )
        self.file_button.pack(side="left", padx=5, pady=5, fill="x", expand=True)

        # Barra de estado
        self.status_var = ctk.StringVar()
        self.status_var.set("Conectando...")
        self.status_bar = ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            anchor="w",
            font=("Arial", 11),
            corner_radius=0,
        )
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

    def update_ui(self):
        """Actualiza periódicamente la interfaz"""
        current_peers = set(self.peer.get_peers())
        if hasattr(self, "_last_peers"):
            if current_peers != self._last_peers:
                self.refresh_users()
        else:
            self.refresh_users()

        self._last_peers = current_peers
        self.after(5000, self.update_ui)

    def refresh_users(self):
        """Actualiza la lista de usuarios conectados"""
        all_peers = self.peer.get_peers()
        peers = [peer_id for peer_id in all_peers if peer_id.strip() != ""]

        if len(all_peers) != len(peers):
            logger.info(
                f"Se filtraron {len(all_peers) - len(peers)} peers con nombres vacíos"
            )

        # Limpiar lista actual
        for widget in self.users_list.winfo_children():
            widget.destroy()

        # Agregar usuarios
        for i, peer_id in enumerate(peers):
            user_btn = ctk.CTkButton(
                self.users_list,
                text=peer_id,
                command=lambda p=peer_id: self.select_user(p),
                anchor="w",
                font=("Arial", 12),
                fg_color="transparent",
                hover_color=("#e1e1e1", "#3a3a3a"),
            )
            user_btn.pack(fill="x", pady=2)

        self.status_var.set(f"Conectados: {len(peers)} usuarios")

    def select_user(self, user_id):
        """Selecciona un usuario para chatear"""
        self.current_chat = user_id
        self.display_chat_history(user_id)

    def display_chat_history(self, user_id):
        """Muestra el historial de chat con un usuario"""
        try:
            self.chat_display.configure(state="normal")
            self.chat_display.delete("1.0", "end")

            if user_id in self.chat_history:
                history_text = "\n".join(self.chat_history[user_id]) + "\n"
                self.chat_display.insert("end", history_text)

            self.chat_display.configure(state="disabled")
            self.chat_display.see("end")

            self.status_var.set(f"Chat con: {user_id}")
            if user_id != "Sistema" and user_id != "Broadcast" and user_id != "Tú":
                logger.info(f"Mensajes de {user_id} marcados como leídos")
        except Exception as e:
            logger.error(f"Error al mostrar historial de chat: {e}", exc_info=True)

    def append_to_chat(self, user_id, message, chat_id=None):
        """Añade un mensaje al historial y lo muestra si es el chat actual"""
        try:
            timestamp = time.strftime("%H:%M:%S")
            if user_id == "Tú":
                formatted_msg = f"[{timestamp}] {user_id}: {message}"
            elif user_id == "Sistema":
                formatted_msg = f"[{timestamp}] 🔔 {user_id}: {message}"
            else:
                formatted_msg = f"[{timestamp}] ➤ {user_id}: {message}"

            if chat_id:
                if chat_id not in self.chat_history:
                    self.chat_history[chat_id] = []
                    logger.info(f"Creado nuevo historial para {chat_id}")
                self.chat_history[chat_id].append(formatted_msg)

                if self.current_chat == chat_id:
                    self.chat_display.configure(state="normal")
                    self.chat_display.insert("end", f"{formatted_msg}\n")
                    self.chat_display.configure(state="disabled")
                    self.chat_display.see("end")

            if user_id not in self.chat_history:
                self.chat_history[user_id] = []
                logger.info(f"Creado nuevo historial para {user_id}")

            self.chat_history[user_id].append(formatted_msg)

            if self.current_chat == user_id or user_id == "Sistema":
                self.chat_display.configure(state="normal")
                self.chat_display.insert("end", f"{formatted_msg}\n")
                self.chat_display.configure(state="disabled")
                self.chat_display.see("end")

                if user_id != "Tú" and user_id != "Sistema":
                    self.status_var.set(f"✉️ Mensaje nuevo de {user_id}")
            else:
                if user_id != "Sistema" and user_id != "Tú":
                    self.status_var.set(f"✉️ Mensaje nuevo sin leer de {user_id}")
                    logger.info(
                        f"Mensaje pendiente de {user_id} (chat actual: {self.current_chat})"
                    )

            logger.debug(
                f"Mensaje añadido al historial de {user_id}: {message[:30]}..."
            )
        except Exception as e:
            logger.error(f"Error añadiendo mensaje al chat: {e}", exc_info=True)

    def send_message(self, event=None):
        """Envía un mensaje al usuario seleccionado"""
        if not self.current_chat:
            self.append_to_chat(
                "Sistema", "Por favor, selecciona un usuario para enviar mensajes."
            )
            return

        if self.current_chat.strip() == "":
            self.append_to_chat(
                "Sistema",
                "Error: No se puede enviar mensaje a un usuario con nombre vacío.",
            )
            return

        message = self.message_input.get().strip()
        if not message:
            return

        current_chat = self.current_chat
        self.message_input.delete(0, "end")

        self.status_var.set(f"Enviando mensaje a {current_chat}...")

        self.thread_pool.submit(self._send_message_thread, current_chat, message)

    def _send_message_thread(self, user_to, message):
        """Ejecuta el envío de mensajes en un hilo separado"""
        try:
            success = self.peer.send_message(user_to, message)

            if success:
                self.update_queue.put(
                    lambda: self.append_to_chat("Tú", message, user_to)
                )
                self.update_queue.put(
                    lambda: self.status_var.set("Mensaje enviado correctamente")
                )
            else:
                self.update_queue.put(
                    lambda: self.append_to_chat(
                        "Sistema", f"Error enviando mensaje a {user_to}."
                    )
                )
                self.update_queue.put(
                    lambda: self.status_var.set("Error al enviar mensaje")
                )

        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
            self.update_queue.put(
                lambda: self.append_to_chat(
                    "Sistema", f"Error enviando mensaje: {str(e)}"
                )
            )
            self.update_queue.put(
                lambda: self.status_var.set("Error al enviar mensaje")
            )

    def send_broadcast(self):
        """Envía un mensaje a todos los usuarios conectados"""
        message = self.message_input.get().strip()
        if not message:
            return

        self.message_input.delete(0, "end")

        timestamp = time.strftime("%H:%M:%S")
        broadcast_msg = f"[{timestamp}] Tú (Broadcast): {message}"

        if "Broadcast" not in self.chat_history:
            self.chat_history["Broadcast"] = []
        self.chat_history["Broadcast"].append(broadcast_msg)

        peers = self.peer.get_peers()
        for peer_id in peers:
            if peer_id not in self.chat_history:
                self.chat_history[peer_id] = []
            self.chat_history[peer_id].append(broadcast_msg)

        if self.current_chat == "Broadcast" or self.current_chat == "Sistema":
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", f"{broadcast_msg}\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see("end")
        elif self.current_chat in peers:
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", f"{broadcast_msg}\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see("end")

        self.status_var.set("Enviando mensaje broadcast...")
        self.append_to_chat("Sistema", f'Enviando a todos: "{message}"')

        self.thread_pool.submit(self._send_broadcast_thread, message)

    def _send_broadcast_thread(self, message):
        """Ejecuta el envío de mensajes broadcast en un hilo separado"""
        try:
            success = self.peer.broadcast_message(message, max_retries=3)

            if success:
                self.update_queue.put(
                    lambda: self.status_var.set(
                        "Mensaje broadcast enviado correctamente"
                    )
                )
                self.update_queue.put(
                    lambda: self.append_to_chat(
                        "Sistema",
                        "✅ Mensaje enviado a todos los usuarios correctamente",
                    )
                )
            else:
                self.update_queue.put(
                    lambda: self.append_to_chat(
                        "Sistema",
                        "❌ Error enviando mensaje broadcast después de varios intentos",
                    )
                )
                self.update_queue.put(
                    lambda: self.status_var.set("Error al enviar mensaje broadcast")
                )

        except Exception as e:
            logger.error(f"Error enviando mensaje broadcast: {e}")
            self.update_queue.put(
                lambda: self.append_to_chat(
                    "Sistema", f"❌ Error enviando mensaje broadcast: {str(e)}"
                )
            )
            self.update_queue.put(
                lambda: self.status_var.set("Error al enviar mensaje broadcast")
            )

    def send_file(self):
        """Envía un archivo al usuario seleccionado"""
        if not self.current_chat:
            self.append_to_chat(
                "Sistema", "Por favor, selecciona un usuario para enviar archivos."
            )
            return

        filepath = filedialog.askopenfilename(title="Selecciona un archivo para enviar")
        if not filepath:
            return

        current_chat = self.current_chat
        filename = os.path.basename(filepath)

        peers = self.peer.get_peers()
        if current_chat not in peers:
            self.append_to_chat(
                "Sistema",
                f"Error: No se puede enviar archivo a {current_chat}, peer no encontrado.",
            )
            return

        self.status_var.set(f"Preparando envío de archivo a {current_chat}...")
        self.thread_pool.submit(self._send_file_thread, current_chat, filepath)

    def _send_file_thread(self, user_to, filepath):
        """Ejecuta el envío de archivos en un hilo separado"""
        try:
            filename = os.path.basename(filepath)

            clean_user_to = user_to.strip() if isinstance(user_to, str) else user_to

            notification_id = f"start_{clean_user_to}_{filename}"

            if notification_id not in self.sent_file_notifications:
                self.update_queue.put(
                    lambda: self.append_to_chat(
                        "Sistema",
                        f"Iniciando envío de archivo: {filename} a {clean_user_to}",
                    )
                )

                self.sent_file_notifications.add(notification_id)

            file_msg = f"Enviando archivo: {filename}"
            self.update_queue.put(
                lambda: self.append_to_chat("Tú", file_msg, clean_user_to)
            )

            success = self.peer.send_file(user_to, filepath)

            if not success:
                self.update_queue.put(
                    lambda: self.append_to_chat(
                        "Sistema", f"Error al iniciar el envío de archivo a {user_to}."
                    )
                )
                self.update_queue.put(
                    lambda: self.status_var.set("Error al enviar archivo")
                )
                self.update_queue.put(
                    lambda: self.remove_progress_bar(user_to, filename)
                )

        except Exception as e:
            logger.error(f"Error enviando archivo: {e}")
            self.update_queue.put(
                lambda: self.append_to_chat(
                    "Sistema", f"Error al enviar archivo: {str(e)}"
                )
            )
            self.update_queue.put(
                lambda: self.status_var.set("Error al enviar archivo")
            )
            self.update_queue.put(lambda: self.remove_progress_bar(user_to, filename))

    def on_message(self, user_from, message):
        """Callback para mensajes recibidos"""
        logger.info(f"MENSAJE RECIBIDO de {user_from}: {message[:50]}...")
        try:
            self.status_var.set(f"✉️ Nuevo mensaje de {user_from}")
            self.update_queue.put(
                lambda u=user_from, m=message: self.append_to_chat(u, m)
            )

            logger.info(f"Mensaje de {user_from} procesado correctamente")
        except Exception as e:
            logger.error(
                f"Error procesando mensaje recibido de {user_from}: {e}", exc_info=True
            )

    def on_file(self, user_from, file_path):
        """Callback para archivos recibidos"""
        try:
            # Limpiar el ID para evitar duplicados por espacios
            clean_user_from = (
                user_from.strip() if isinstance(user_from, str) else user_from
            )
            filename = os.path.basename(file_path)

            self.status_var.set(f"✉️ Archivo recibido de {clean_user_from}: {filename}")

            file_key = f"{clean_user_from}_{filename}"

            def create_completed_bar():
                self.show_progress_window()
                self.create_progress_bar(clean_user_from, filename)
                self.update_progress_bar(clean_user_from, filename, 100)

            self.update_queue.put(create_completed_bar)

            # Generamos un ID único para este mensaje de archivo recibido
            notification_id = f"received_{clean_user_from}_{filename}"

            # Solo notificar si no se ha notificado antes
            if notification_id not in self.sent_file_notifications:
                self.append_to_chat(
                    "Sistema", f"Archivo recibido de {clean_user_from}: {filename}"
                )
                self.append_to_chat("Sistema", f"Guardado como: {file_path}")
                file_msg = f"Archivo recibido: {filename}"
                self.append_to_chat(clean_user_from, file_msg)

                # Marcar como notificado
                self.sent_file_notifications.add(notification_id)

        except Exception as e:
            logger.error(f"Error procesando archivo recibido: {e}", exc_info=True)

    def on_peer_change(self, user_id, added):
        """Callback para cambios en la lista de peers"""
        if user_id:
            clean_user_id = user_id.strip()
            if clean_user_id == "":
                return
        else:
            return

        action = "conectado" if added else "desconectado"
        self.append_to_chat("Sistema", f"Usuario '{clean_user_id}' se ha {action}")
        self.update_queue.put(self.refresh_users)

    def on_file_progress(self, user_id, file_path, progress, status):
        """Callback para actualizaciones de progreso de transferencias"""
        try:
            clean_user_id = user_id.strip() if isinstance(user_id, str) else user_id
            filename = os.path.basename(file_path)
            file_key = f"{clean_user_id}_{filename}"

            if status == "iniciando":
                # No mostramos el mensaje de inicio aquí para evitar duplicaciones,
                # ya se muestra en _send_file_thread

                if file_key not in self.file_progress_bars:
                    self.update_queue.put(
                        lambda: self.create_progress_bar(clean_user_id, filename)
                    )

                    def update_status():
                        active_count = len(self.file_progress_bars)
                        if hasattr(self, "transfer_status"):
                            self.transfer_status.configure(
                                text=f"{active_count} transferencias activas"
                            )

                    self.update_queue.put(update_status)
                else:
                    self.update_queue.put(
                        lambda: self.update_progress_bar(clean_user_id, filename, 0)
                    )

            elif status == "progreso":
                if file_key not in self.file_progress_bars:

                    def create_and_update():
                        self.create_progress_bar(clean_user_id, filename)
                        self.update_progress_bar(clean_user_id, filename, progress)

                    self.update_queue.put(create_and_update)
                else:
                    self.update_queue.put(
                        lambda p=progress: self.update_progress_bar(
                            clean_user_id, filename, p
                        )
                    )

                self.status_var.set(
                    f"Enviando '{filename}' a {clean_user_id}: {progress}% completado"
                )

            elif status == "completado":
                if file_key not in self.file_progress_bars:

                    def create_and_complete():
                        self.create_progress_bar(clean_user_id, filename)
                        self.update_progress_bar(clean_user_id, filename, 100)

                    self.update_queue.put(create_and_complete)
                else:
                    self.update_queue.put(
                        lambda: self.update_progress_bar(clean_user_id, filename, 100)
                    )

                # Generamos un ID único para este mensaje de completado
                notification_id = f"complete_{clean_user_id}_{filename}"
                msg_text = (
                    f"Archivo '{filename}' enviado correctamente a {clean_user_id}"
                )

                # Verificamos si ya se envió este mensaje antes
                if notification_id not in self.sent_file_notifications:
                    self.append_to_chat("Sistema", msg_text)
                    # Marcamos como enviado para no repetirlo
                    self.sent_file_notifications.add(notification_id)

                    # Limpiamos notificaciones antiguas si hay muchas (más de 50)
                    if len(self.sent_file_notifications) > 50:
                        self.sent_file_notifications.clear()

                self.status_var.set("Listo")

            elif status == "error":
                self.append_to_chat(
                    "Sistema", f"Error enviando archivo '{filename}' a {clean_user_id}"
                )
                self.status_var.set("Error en la transferencia")
                if file_key in self.file_progress_bars:
                    self.update_queue.put(
                        lambda: self.remove_progress_bar(clean_user_id, filename)
                    )

        except Exception as e:
            logger.error(f"Error en callback de progreso: {e}", exc_info=True)

    def process_ui_updates(self):
        """Procesa las actualizaciones de la interfaz de usuario desde la cola"""
        processed = 0
        while not self.update_queue.empty() and processed < 10:
            try:
                update_func = self.update_queue.get_nowait()
                try:
                    update_func()
                except Exception as e:
                    logger.error(
                        f"Error al procesar actualización de UI: {e}", exc_info=True
                    )
                processed += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error inesperado en cola de UI: {e}", exc_info=True)

        pending = self.update_queue.qsize()
        next_interval = 50 if pending > 10 else (100 if pending > 0 else 500)
        self.after(next_interval, self.process_ui_updates)


if __name__ == "__main__":
    app = LCPChat()
    app.mainloop()
