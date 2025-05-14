import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, simpledialog, font
import threading
import time
import os
from protocol import *
from main import LCPPeer
import logging
import concurrent.futures
import queue
from utils.system_info import get_optimal_thread_count

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LCP-GUI")


class LCPChat(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("LCP Chat")
        self.geometry("800x600")
        self.minsize(600, 400)

        self.style = ttk.Style()
        self.style.configure("TButton", font=("Arial", 11), padding=6)

        n, _, _ = get_optimal_thread_count()
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=n, thread_name_prefix="GUI-Worker"
        )

        self.update_queue = queue.Queue()

        username = self.get_username()

        self.peer = LCPPeer(username)

        self.peer.register_message_callback(self.on_message)
        self.peer.register_file_callback(self.on_file)
        self.peer.register_peer_discovery_callback(self.on_peer_change)
        self.peer.register_file_progress_callback(self.on_file_progress)

        self.current_chat = None
        self.chat_history = {}
        self.selected_user = tk.StringVar()

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

    def create_widgets(self):
        """Crea los widgets de la interfaz"""
        main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        users_frame = ttk.Frame(main_paned, width=200)
        main_paned.add(users_frame, weight=1)

        chat_frame = ttk.Frame(main_paned)
        main_paned.add(chat_frame, weight=3)

        users_label = ttk.Label(
            users_frame, text="Usuarios Conectados", font=("Arial", 12, "bold")
        )
        users_label.pack(pady=5)

        self.users_list = tk.Listbox(
            users_frame,
            listvariable=self.selected_user,
            selectmode=tk.SINGLE,
            height=20,
            font=("Arial", 11),
        )
        self.users_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.users_list.bind("<<ListboxSelect>>", self.on_user_select)

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

        chat_history_frame = ttk.Frame(chat_frame)
        chat_history_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.chat_display = scrolledtext.ScrolledText(
            chat_history_frame,
            wrap=tk.WORD,
            state="disabled",
            height=20,
            font=("Arial", 11),
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        self.message_input = ttk.Entry(input_frame, font=("Arial", 11))
        self.message_input.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 5))
        self.message_input.bind("<Return>", self.send_message)

        buttons_frame = ttk.Frame(chat_frame)
        buttons_frame.pack(fill=tk.X, pady=5)

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

        broadcast_btn = tk.Button(
            buttons_frame,
            text="Enviar a Todos",
            command=self.send_broadcast,
            bg="#FF9800",
            fg="black",
            font=("Arial", 11),
            padx=15,
            pady=5,
        )
        broadcast_btn.pack(side=tk.LEFT, padx=5)

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
        peers = self.peer.get_peers()

        current_selection = None
        if self.users_list.curselection():
            current_selection = self.users_list.get(self.users_list.curselection()[0])

        self.users_list.delete(0, tk.END)
        for peer_id in peers:
            self.users_list.insert(tk.END, peer_id)

        if current_selection:
            try:
                idx = peers.index(current_selection)
                self.users_list.selection_set(idx)
                self.users_list.see(idx)
            except ValueError:
                self.current_chat = None

        self.status_var.set(f"Conectados: {len(peers)} usuarios")

    def on_user_select(self, event):
        """Maneja la selección de un usuario de la lista"""
        if not self.users_list.curselection():
            return

        selected_idx = self.users_list.curselection()[0]
        selected_user = self.users_list.get(selected_idx)

        self.current_chat = selected_user

        self.display_chat_history(selected_user)

    def display_chat_history(self, user_id):
        """Muestra el historial de chat con un usuario"""
        self.chat_display.configure(state="normal")
        self.chat_display.delete(1.0, tk.END)

        if user_id in self.chat_history:
            for msg in self.chat_history[user_id]:
                self.chat_display.insert(tk.END, f"{msg}\n")

        self.chat_display.configure(state="disabled")

        self.chat_display.see(tk.END)

    def append_to_chat(self, user_id, message):
        """Añade un mensaje al historial y lo muestra si es el chat actual"""
        try:
            timestamp = time.strftime("%H:%M:%S")

            # Formateamos el mensaje de manera distinta según quién lo envía
            if user_id == "Tú":
                formatted_msg = f"[{timestamp}] {user_id}: {message}"
            elif user_id == "Sistema":
                formatted_msg = f"[{timestamp}] 🔔 {user_id}: {message}"
            else:
                # Destacamos los mensajes recibidos
                formatted_msg = f"[{timestamp}] ➤ {user_id}: {message}"
                # También podríamos añadir un color diferente si fuera posible

            if user_id not in self.chat_history:
                self.chat_history[user_id] = []
                logger.info(f"Creado nuevo historial para {user_id}")

            self.chat_history[user_id].append(formatted_msg)

            # Si es el chat actual o un mensaje del sistema, lo mostramos
            if self.current_chat == user_id or user_id == "Sistema":
                self.chat_display.configure(state="normal")
                self.chat_display.insert(tk.END, f"{formatted_msg}\n")
                self.chat_display.configure(state="disabled")
                self.chat_display.see(tk.END)

                # Notificar visualmente que hay un mensaje nuevo
                if user_id != "Tú" and user_id != "Sistema":
                    self.status_var.set(f"✉️ Mensaje nuevo de {user_id}")
            else:
                # Si no es el chat actual, notificar que hay mensajes pendientes
                if user_id != "Sistema":
                    self.status_var.set(f"✉️ Mensaje nuevo sin leer de {user_id}")
                    logger.info(
                        f"Mensaje pendiente de {user_id} (chat actual: {self.current_chat})"
                    )
                    # Aquí podríamos actualizar la UI para mostrar un indicador de mensajes no leídos

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

        message = self.message_input.get().strip()
        if not message:
            return

        current_chat = self.current_chat
        self.message_input.delete(0, tk.END)

        self.status_var.set(f"Enviando mensaje a {current_chat}...")

        self.thread_pool.submit(self._send_message_thread, current_chat, message)

    def _send_message_thread(self, user_to, message):
        """Ejecuta el envío de mensajes en un hilo separado"""
        try:
            success = self.peer.send_message(user_to, message)

            if success:
                self.update_queue.put(lambda: self.append_to_chat("Tú", message))
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
        """Envía un mensaje a todos los usuarios conectados a la vez con una única transmisión"""
        message = self.message_input.get().strip()
        if not message:
            return

        self.message_input.delete(0, tk.END)

        timestamp = time.strftime("%H:%M:%S")
        broadcast_msg = f"[{timestamp}] Tú (Broadcast): {message}"

        if "Broadcast" not in self.chat_history:
            self.chat_history["Broadcast"] = []
        self.chat_history["Broadcast"].append(broadcast_msg)

        if self.current_chat == "Broadcast" or self.current_chat == "Sistema":
            self.chat_display.configure(state="normal")
            self.chat_display.insert(tk.END, f"{broadcast_msg}\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see(tk.END)

        self.status_var.set("Enviando mensaje broadcast...")

        self.append_to_chat("Sistema", f'Enviando a todos: "{message}"')

        self.thread_pool.submit(self._send_broadcast_thread, message)

    def _send_broadcast_thread(self, message):
        """Ejecuta el envío de mensajes broadcast en un hilo separado"""
        try:
            success = self.peer.broadcast_message(message)

            if success:
                self.update_queue.put(
                    lambda: self.status_var.set(
                        "Mensaje broadcast enviado correctamente"
                    )
                )
                self.update_queue.put(
                    lambda: self.append_to_chat(
                        "Sistema", "✓ Mensaje enviado a todos los usuarios"
                    )
                )
            else:
                self.update_queue.put(
                    lambda: self.append_to_chat(
                        "Sistema", "❌ Error enviando mensaje broadcast"
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

        self.status_var.set(f"Preparando envío de archivo a {current_chat}...")

        self.thread_pool.submit(self._send_file_thread, current_chat, filepath)

    def _send_file_thread(self, user_to, filepath):
        """Ejecuta el envío de archivos en un hilo separado"""
        try:
            filename = os.path.basename(filepath)
            self.update_queue.put(
                lambda: self.append_to_chat(
                    "Sistema", f"Iniciando envío de archivo: {filename} a {user_to}"
                )
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

    def on_message(self, user_from, message):
        """Callback para mensajes recibidos"""
        logger.info(f"MENSAJE RECIBIDO de {user_from}: {message[:50]}...")

        # Notificar con efecto visual además de agregar al chat
        try:
            self.status_var.set(f"✉️ Nuevo mensaje de {user_from}")
            # Usar el queue para actualizar la UI desde el hilo principal
            self.update_queue.put(
                lambda u=user_from, m=message: self.append_to_chat(u, m)
            )

            # Si es un mensaje para el chat actual, reproducir un sonido o parpadear (si estuviera implementado)
            if user_from == self.current_chat:
                # Aquí se podría implementar un indicador visual más notorio
                pass

            logger.info(f"Mensaje de {user_from} procesado correctamente")
        except Exception as e:
            logger.error(
                f"Error procesando mensaje recibido de {user_from}: {e}", exc_info=True
            )

    def on_file(self, user_from, file_path):
        """Callback para archivos recibidos"""
        filename = os.path.basename(file_path)
        self.append_to_chat("Sistema", f"Archivo recibido de {user_from}: {filename}")
        self.append_to_chat("Sistema", f"Guardado como: {file_path}")

    def on_peer_change(self, user_id, added):
        """Callback para cambios en la lista de peers"""
        # Normalizar el ID de usuario para mostrar consistentemente
        clean_user_id = user_id.strip() if user_id else user_id
        action = "conectado" if added else "desconectado"
        self.append_to_chat("Sistema", f"Usuario {clean_user_id} se ha {action}")
        self.refresh_users()

    def on_file_progress(self, user_id, file_path, progress, status):
        """Callback para actualizaciones de progreso de transferencias"""
        filename = os.path.basename(file_path)

        if status == "iniciando":
            self.append_to_chat(
                "Sistema", f"Iniciando envío de '{filename}' a {user_id}"
            )
        elif status == "progreso":
            if progress % 20 == 0:
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

    def process_ui_updates(self):
        """Procesa las actualizaciones de la interfaz de usuario desde la cola"""
        processed = 0
        while not self.update_queue.empty() and processed < 10:
            try:
                update_func = self.update_queue.get_nowait()
                update_func()
                processed += 1
            except queue.Empty:
                break
        next_interval = 100 if self.update_queue.qsize() > 5 else 500
        self.after(next_interval, self.process_ui_updates)


if __name__ == "__main__":
    app = LCPChat()
    app.mainloop()
