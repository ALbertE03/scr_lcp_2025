import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import socket
from protocol import *
import uuid
import threading

class LCPClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat")
        
        self.client_id = str(uuid.uuid4()).replace("-", "")[:20]
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.discovered_users = {}  
        
        self.create_widgets()
        
        self.running = True
        self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
        self.receive_thread.start()
    
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(main_frame, text=f"Your ID: {self.client_id}").grid(row=0, column=0, sticky=tk.W)
        
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, pady=10, sticky=(tk.W, tk.E))
        
        discovery_tab = ttk.Frame(notebook)
        self.create_discovery_tab(discovery_tab)
        notebook.add(discovery_tab, text="Discovery")
        
        message_tab = ttk.Frame(notebook)
        self.create_message_tab(message_tab)
        notebook.add(message_tab, text="Messages")
        
        file_tab = ttk.Frame(notebook)
        self.create_file_tab(file_tab)
        notebook.add(file_tab, text="Files")
        
        ttk.Label(main_frame, text="Activity Log:").grid(row=2, column=0, sticky=tk.W)
        self.log_area = scrolledtext.ScrolledText(main_frame, width=60, height=10, state='disabled')
        self.log_area.grid(row=3, column=0, pady=5)
    
    def create_discovery_tab(self, parent):
        ttk.Label(parent, text="Discover users in the network:").grid(row=0, column=0, pady=5, sticky=tk.W)
        
        ttk.Button(parent, text="Discover Users", command=self.discover_users).grid(row=1, column=0, pady=5)
        
        ttk.Label(parent, text="Discovered Users:").grid(row=2, column=0, sticky=tk.W)
        self.user_listbox = tk.Listbox(parent, height=5)
        self.user_listbox.grid(row=3, column=0, sticky=(tk.W, tk.E))
        
        refresh_frame = ttk.Frame(parent)
        refresh_frame.grid(row=4, column=0, pady=5)
        ttk.Button(refresh_frame, text="Refresh", command=self.refresh_user_list).grid(row=0, column=0, padx=5)
        ttk.Button(refresh_frame, text="Clear", command=self.clear_user_list).grid(row=0, column=1, padx=5)
    
    def create_message_tab(self, parent):
        ttk.Label(parent, text="Send a message:").grid(row=0, column=0, pady=5, sticky=tk.W)
        
        ttk.Label(parent, text="To:").grid(row=1, column=0, sticky=tk.W)
        self.message_recipient = ttk.Combobox(parent, values=list(self.discovered_users.keys()))
        self.message_recipient.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)
        
        ttk.Label(parent, text="Message:").grid(row=2, column=0, sticky=tk.W)
        self.message_entry = tk.Text(parent, height=5, width=40)
        self.message_entry.grid(row=3, column=0, columnspan=2, pady=5)
        
        ttk.Button(parent, text="Send Message", command=self.send_message).grid(row=4, column=0, columnspan=2, pady=5)
    
    def create_file_tab(self, parent):
        ttk.Label(parent, text="Send a file:").grid(row=0, column=0, pady=5, sticky=tk.W)
        
        ttk.Label(parent, text="To:").grid(row=1, column=0, sticky=tk.W)
        self.file_recipient = ttk.Combobox(parent, values=list(self.discovered_users.keys()))
        self.file_recipient.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5)
        
        ttk.Label(parent, text="File:").grid(row=2, column=0, sticky=tk.W)
        self.file_path = tk.StringVar()
        ttk.Entry(parent, textvariable=self.file_path, state='readonly').grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(parent, text="Browse...", command=self.browse_file).grid(row=3, column=1, sticky=tk.E, pady=5)
        
        ttk.Button(parent, text="Send File", command=self.send_file).grid(row=4, column=0, columnspan=2, pady=5)
    
    def log_message(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.configure(state='disabled')
        self.log_area.see(tk.END)
    
    def discover_users(self):
        def discovery_task():
            self.log_message("[DISCOVERY] Discovering users...")
            header = pack_header(self.client_id, '\xFF' * 20, ECHO)
            self.udp_socket.sendto(header, ('<broadcast>', UDP_PORT))
            
            try:
                self.udp_socket.settimeout(3)
                while True:
                    response, addr = self.udp_socket.recvfrom(RESPONSE_SIZE)
                    status, responder_id = unpack_response(response)
                    if status == RESPONSE_OK:
                        self.discovered_users[responder_id] = addr[0]
                        self.log_message(f"[DISCOVERY] Found user: {responder_id} at {addr[0]}")
                        self.refresh_user_list()
            except socket.timeout:
                self.log_message("[DISCOVERY] Discovery completed")
                self.udp_socket.settimeout(None)
        
        threading.Thread(target=discovery_task).start()
    
    def refresh_user_list(self):
        self.user_listbox.delete(0, tk.END)
        for user_id in self.discovered_users:
            self.user_listbox.insert(tk.END, f"{user_id} ({self.discovered_users[user_id]})")
        
        users = list(self.discovered_users.keys())
        self.message_recipient['values'] = users
        self.file_recipient['values'] = users
    
    def clear_user_list(self):
        self.discovered_users.clear()
        self.user_listbox.delete(0, tk.END)
        self.message_recipient.set('')
        self.file_recipient.set('')
    
    def send_message(self):
        recipient_id = self.message_recipient.get()
        message = self.message_entry.get("1.0", tk.END).strip()
        
        if not recipient_id:
            messagebox.showerror("Error", "Please select a recipient")
            return
        if not message:
            messagebox.showerror("Error", "Message cannot be empty")
            return
        
        def send_task():
            try:
                self.log_message(f"[MESSAGE] Sending message to {recipient_id}...")
                body_id = 1  
                header = pack_header(
                    self.client_id, 
                    recipient_id, 
                    MESSAGE, 
                    body_id, 
                    len(message.encode('utf-8')))
                
                self.udp_socket.sendto(header, (self.discovered_users[recipient_id], UDP_PORT))
                
                self.udp_socket.settimeout(5)
                response, _ = self.udp_socket.recvfrom(RESPONSE_SIZE)
                status, _ = unpack_response(response)
                
                if status != RESPONSE_OK:
                    self.log_message("[MESSAGE] Recipient didn't acknowledge header")
                    return
                
                body = body_id.to_bytes(8, byteorder='big') + message.encode('utf-8')
                self.udp_socket.sendto(body, (self.discovered_users[recipient_id], UDP_PORT))
                
                response, _ = self.udp_socket.recvfrom(RESPONSE_SIZE)
                status, _ = unpack_response(response)
                
                if status == RESPONSE_OK:
                    self.log_message("[MESSAGE] Message sent successfully")
                else:
                    self.log_message("[MESSAGE] Message delivery failed")
                
            except socket.timeout:
                self.log_message("[MESSAGE] Timeout waiting for response")
            except Exception as e:
                self.log_message(f"[MESSAGE] Error: {str(e)}")
            finally:
                self.udp_socket.settimeout(None)
        
        threading.Thread(target=send_task).start()
    
    def browse_file(self):
        filename = filedialog.askopenfilename()
        if filename:
            self.file_path.set(filename)
    
    def send_file(self):
        recipient_id = self.file_recipient.get()
        filepath = self.file_path.get()
        
        if not recipient_id:
            messagebox.showerror("Error", "Please select a recipient")
            return
        if not filepath:
            messagebox.showerror("Error", "Please select a file")
            return
        
        def send_task():
            try:
                self.log_message(f"[FILE] Preparing to send file to {recipient_id}...")
                
                with open(filepath, "rb") as f:
                    file_data = f.read()
                
                body_id = 1  
                header = pack_header(
                    self.client_id, 
                    recipient_id, 
                    FILE, 
                    body_id, 
                    len(file_data))
                
                self.udp_socket.sendto(header, (self.discovered_users[recipient_id], UDP_PORT))
                
                self.udp_socket.settimeout(5)
                response, _ = self.udp_socket.recvfrom(RESPONSE_SIZE)
                status, _ = unpack_response(response)
                
                if status != RESPONSE_OK:
                    self.log_message("[FILE] Recipient didn't acknowledge header")
                    return
                
                self.log_message("[FILE] Starting file transfer...")
                tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tcp_sock.connect((self.discovered_users[recipient_id], TCP_PORT))
                
                tcp_sock.sendall(body_id.to_bytes(8, byteorder='big') + file_data)
                
                response = tcp_sock.recv(RESPONSE_SIZE)
                status, _ = unpack_response(response)
                
                if status == RESPONSE_OK:
                    self.log_message("[FILE] File sent successfully")
                else:
                    self.log_message("[FILE] File transfer failed")
                
                tcp_sock.close()
                
            except socket.timeout:
                self.log_message("[FILE] Timeout waiting for response")
            except Exception as e:
                self.log_message(f"[FILE] Error: {str(e)}")
            finally:
                self.udp_socket.settimeout(None)
        
        threading.Thread(target=send_task).start()
    
    def receive_messages(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                
                if len(data) >= HEADER_SIZE:
                    user_from, user_to, op_code, body_id, body_length = unpack_header(data)
                
                    if op_code == MESSAGE and (user_to == self.client_id or user_to == '\xFF' * 20):
                        response = pack_response(RESPONSE_OK, self.client_id)
                        self.udp_socket.sendto(response, addr)
                        
                        self.udp_socket.settimeout(5)
                        body_data, _ = self.udp_socket.recvfrom(1024)
                        received_id = int.from_bytes(body_data[:8], byteorder='big')
                        
                        if received_id == body_id:
                            message = body_data[8:].decode('utf-8')
                            self.log_message(f"\n[MESSAGE] From {user_from}: {message}")
                            
                            response = pack_response(RESPONSE_OK, self.client_id)
                            self.udp_socket.sendto(response, addr)
            
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.log_message(f"[ERROR] Receiving: {str(e)}")
    
    def on_close(self):
        self.running = False
        self.udp_socket.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = LCPClientGUI(root)
    root.mainloop()