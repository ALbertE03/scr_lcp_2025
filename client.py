import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import uuid
import threading
from datetime import datetime
import sys
import socket
import subprocess
import platform
from network import (
    NetworkManager,
    get_network_info,
    get_mac_address,
)
from chat_manager import ChatManager
from file_transfer import FileTransferManager
import os


def get_local_ip():
    """Obtiene la dirección IP local del dispositivo"""
    try:
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_socket.connect(("8.8.8.8", 80))
        local_ip = temp_socket.getsockname()[0]
        temp_socket.close()
        return local_ip
    except:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            return local_ip
        except:
            return "No se pudo determinar"


class ChatClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat LAN")
        self.root.geometry("1000x700")

        mac_address = get_mac_address()

        mac_bytes = mac_address.encode("utf-8")

        if len(mac_bytes) < 20:
            padding = 20 - len(mac_bytes)
            mac_address = mac_address + "0" * padding
            mac_bytes = mac_address.encode("utf-8")

            while len(mac_bytes) > 20:
                mac_address = mac_address[:-1]
                mac_bytes = mac_address.encode("utf-8")

            while len(mac_bytes) < 20:
                mac_address = mac_address + "0"
                mac_bytes = mac_address.encode("utf-8")

        elif len(mac_bytes) > 20:
            while len(mac_bytes) > 20:
                mac_address = mac_address[:-1]
                mac_bytes = mac_address.encode("utf-8")

        self.client_id = mac_address
        self.log(
            f"ID de cliente configurado: {self.client_id} (longitud en bytes: {len(self.client_id.encode('utf-8'))})"
        )

        # Verificación adicional - debe ser exactamente 20 bytes
        assert (
            len(self.client_id.encode("utf-8")) == 20
        ), "El ID de cliente debe ser exactamente 20 bytes"

        self.network_manager = NetworkManager(self.client_id)
        self.chat_manager = ChatManager(self.client_id)
        self.file_transfer_manager = FileTransferManager(
            self.client_id, self.network_manager
        )

        self.network_manager.set_chat_manager(self.chat_manager)

        self.current_chat = "GLOBAL"

        self.create_widgets()

        self.running = True
        threading.Thread(
            target=self.network_manager.discovery_loop,
            args=(self.chat_manager,),
            daemon=True,
        ).start()
        threading.Thread(
            target=self.network_manager.receive_loop,
            args=(self.chat_manager, self.file_transfer_manager),
            daemon=True,
        ).start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log("Cliente iniciado. Tu ID: " + self.client_id)

        threading.Thread(target=self.show_connection_info, daemon=True).start()

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_panel = ttk.Frame(main_frame, width=250)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)

        self.notebook = ttk.Notebook(left_panel)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        users_tab = ttk.Frame(self.notebook)
        self.notebook.add(users_tab, text="Usuarios")

        ttk.Label(users_tab, text="Usuarios Conectados", style="Header.TLabel").pack(
            pady=5
        )

        self.user_listbox = tk.Listbox(users_tab)
        self.user_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.user_listbox.bind("<<ListboxSelect>>", self.on_user_selected)

        ttk.Button(users_tab, text="Actualizar", command=self.manual_discover).pack(
            pady=5
        )

        chats_tab = ttk.Frame(self.notebook)
        self.notebook.add(chats_tab, text="Chats")

        ttk.Label(chats_tab, text="Conversaciones", style="Header.TLabel").pack(pady=5)

        self.chats_listbox = tk.Listbox(chats_tab)
        self.chats_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.chats_listbox.insert(tk.END, "GLOBAL")
        self.chats_listbox.bind("<<ListboxSelect>>", self.on_chat_selected)

        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.chat_info_label = ttk.Label(
            right_panel, text="Chat Global", style="ChatInfo.TLabel"
        )
        self.chat_info_label.pack(pady=5)

        self.chat_display = scrolledtext.ScrolledText(
            right_panel, state="disabled", wrap=tk.WORD, font=("Arial", 10)
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        input_frame = ttk.Frame(right_panel)
        input_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        self.message_entry = ttk.Entry(input_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.message_entry.bind("<Return>", self.send_message_from_ui)

        ttk.Button(input_frame, text="Enviar", command=self.send_message_from_ui).pack(
            side=tk.LEFT
        )
        ttk.Button(input_frame, text="Archivo", command=self.send_file_dialog).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        style = ttk.Style()
        style.configure("Header.TLabel", font=("Helvetica", 10, "bold"))
        style.configure("ChatInfo.TLabel", font=("Helvetica", 12, "bold"))

    def on_user_selected(self, event):
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            user_display = event.widget.get(index)

            for user_id in self.chat_manager.discovered_users:
                if user_display.startswith(user_id[:10]):
                    self.chat_manager.start_private_chat(user_id)
                    self.current_chat = user_id
                    self.chat_info_label.config(
                        text=f"Chat privado con {user_id[:10]}..."
                    )
                    self.show_chat(user_id)
                    self.update_chats_list()
                    self.log(f"Chat privado iniciado con {user_id}")
                    break

    def on_chat_selected(self, event):
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            chat_display = event.widget.get(index)

            if chat_display == "GLOBAL":
                self.current_chat = "GLOBAL"
                self.chat_info_label.config(text="Chat Global")
                self.show_chat("GLOBAL")
            else:
                for user_id in self.chat_manager.discovered_users:
                    if chat_display.endswith(user_id[:10] + "..."):
                        self.current_chat = user_id
                        self.chat_info_label.config(
                            text=f"Chat privado con {user_id[:10]}..."
                        )
                        self.show_chat(user_id)
                        break

    def show_chat(self, chat_id):
        self.chat_display.config(state="normal")
        self.chat_display.delete(1.0, tk.END)

        if chat_id in self.chat_manager.active_chats:
            for message in self.chat_manager.active_chats[chat_id]:
                self.chat_display.insert(tk.END, message)

        self.chat_display.config(state="disabled")
        self.chat_display.see(tk.END)

    def send_message_from_ui(self, event=None):
        """Envía un mensaje desde la interfaz de usuario"""
        if not self.current_chat:
            messagebox.showwarning("Advertencia", "Por favor selecciona un chat")
            return

        message_text = self.message_entry.get().strip()
        if not message_text:
            return

        def send_task():
            try:
                success = self.network_manager.send_message(
                    self.current_chat, message_text
                )
                if success:
                    self.root.after(
                        0,
                        lambda: [
                            self.chat_manager.add_message_to_chat(
                                self.current_chat, message_text, incoming=False
                            ),
                            self.message_entry.delete(0, tk.END),
                        ],
                    )
                else:
                    self.root.after(
                        0,
                        lambda: messagebox.showerror(
                            "Error", "No se pudo entregar el mensaje"
                        ),
                    )
            except Exception as e:
                error_msg = f"Error inesperado: {str(e)}"
                self.root.after(
                    0, lambda msg=error_msg: messagebox.showerror("Error", msg)
                )
                self.log(error_msg)

        threading.Thread(target=send_task, daemon=True).start()

    def send_file_dialog(self):
        """Diálogo para enviar archivos"""
        if not self.current_chat or (
            self.current_chat != "GLOBAL"
            and self.current_chat not in self.chat_manager.discovered_users
        ):
            messagebox.showwarning("Advertencia", "Por favor selecciona un chat válido")
            return

        filepath = filedialog.askopenfilename()
        if not filepath:
            return

        def send_file_task():
            try:
                success = self.file_transfer_manager.send_file(
                    self.current_chat, filepath
                )
                if success:
                    filename = os.path.basename(filepath)
                    self.root.after(
                        0,
                        lambda: self.chat_manager.add_message_to_chat(
                            self.current_chat,
                            f"Archivo enviado: {filename}",
                            incoming=False,
                        ),
                    )
                else:
                    self.root.after(
                        0,
                        lambda: messagebox.showerror(
                            "Error", "Error en transferencia de archivo"
                        ),
                    )
            except Exception as e:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Error", f"Error enviando archivo: {str(e)}"
                    ),
                )
                self.log(f"Error enviando archivo: {e}")

        threading.Thread(target=send_file_task).start()

    def on_close(self):
        self.log("Cerrando cliente...")
        self.running = False
        self.network_manager.close()
        self.root.destroy()
        sys.exit(0)

    def manual_discover(self):
        """Manualmente inicia el proceso de descubrimiento para buscar usuarios en la red"""
        self.log("Buscando usuarios en la red...")
        try:
            threading.Thread(
                target=self.network_manager.discovery_loop,
                args=(self.chat_manager,),
                daemon=True,
            ).start()
            self.root.after(1000, self.update_users_list)
            messagebox.showinfo(
                "Buscando usuarios",
                "Buscando usuarios en la red. Este proceso puede tardar unos segundos.",
            )
        except Exception as e:
            self.log(f"Error al buscar usuarios: {str(e)}")
            messagebox.showerror("Error", f"Error al buscar usuarios: {str(e)}")

    def update_users_list(self):
        """Actualiza la lista de usuarios conectados en la UI"""
        self.user_listbox.delete(0, tk.END)
        for user_id in self.chat_manager.discovered_users:
            self.user_listbox.insert(
                tk.END,
                f"{user_id[:10]}... ({self.chat_manager.discovered_users[user_id]})",
            )
        self.log(
            f"Lista de usuarios actualizada: {len(self.chat_manager.discovered_users)} usuarios encontrados"
        )

    def update_chats_list(self):
        self.chats_listbox.delete(0, tk.END)
        self.chats_listbox.insert(tk.END, "GLOBAL")

        for user_id in self.chat_manager.chats:
            if user_id != "GLOBAL" and user_id in self.chat_manager.discovered_users:
                self.chats_listbox.insert(tk.END, f"Chat con {user_id[:10]}...")

        self.log(
            f"Lista de chats actualizada: {len(self.chat_manager.chats)} chats activos"
        )

    def show_connection_info(self):
        """Muestra una ventana con información de conexión útil para conectarse con otros usuarios"""
        info_window = tk.Toplevel(self.root)
        info_window.title("Información de Conexión")
        info_window.geometry("400x200")

        local_ip = get_local_ip()
        broadcast_addresses = get_network_info()

        frame = ttk.Frame(info_window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Información para conectarse con otros usuarios",
            font=("Helvetica", 15, "bold"),
        ).pack(pady=(0, 10))

        ttk.Label(
            frame,
            text=f"Tu ID de cliente: {self.client_id}",
            font=("Helvetica", 15),
        ).pack(anchor="w", pady=2)

        ttk.Label(
            frame,
            text=f"Tu dirección IP: {local_ip}",
            font=("Helvetica", 15),
        ).pack(anchor="w", pady=2)

        ttk.Label(
            frame,
            text=f"Puerto UDP: 9990",
            font=("Helvetica", 15),
        ).pack(anchor="w", pady=2)

        ttk.Label(
            frame,
            text="Direcciones de broadcast detectadas:",
            font=("Helvetica", 15),
        ).pack(anchor="w", pady=2)

        broadcast_text = tk.Text(frame, height=5, width=40, font=("Helvetica", 15))
        broadcast_text.pack(fill=tk.X, pady=5)
        for addr in broadcast_addresses:
            broadcast_text.insert(tk.END, f"{addr}\n")
        broadcast_text.config(state="disabled")

    def show_network_details(self):
        """Muestra información detallada de la red"""
        try:
            if platform.system() == "Darwin":
                output = subprocess.check_output(
                    ["ifconfig", "en0"], universal_newlines=True
                )

            details_window = tk.Toplevel(self.root)
            details_window.title("Detalles de red")
            details_window.geometry("600x400")

            text_widget = scrolledtext.ScrolledText(details_window)
            text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text_widget.insert(tk.END, output)
            text_widget.config(state="disabled")

            ttk.Button(
                details_window,
                text="Cerrar",
                command=details_window.destroy,
            ).pack(pady=10)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo obtener información de red: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClientGUI(root)
    root.mainloop()
