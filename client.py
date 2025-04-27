import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import socket
from protocol import *
import uuid
import threading
from datetime import datetime
import time
import os
import sys

class ChatClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Chat LAN")
        self.root.geometry("800x600")
        
        self.client_id = str(uuid.uuid4()).replace("-", "")[:20]
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.bind(('0.0.0.0', UDP_PORT))
        self.udp_socket.settimeout(1) 
        
        self.discovered_users = {}  
        self.active_chats = {}    
        self.current_chat = None
        self.discovery_active = False
        self.last_discovery_time = 0
        
        self.create_widgets()
        
        self.running = True
        threading.Thread(target=self.discovery_loop, daemon=True).start()
        threading.Thread(target=self.receive_loop, daemon=True).start()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log("Client started. Your ID: " + self.client_id)
    
    def log(self, message):

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def create_widgets(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        left_panel = ttk.Frame(main_frame, width=200)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_panel.pack_propagate(False)
        
        ttk.Label(left_panel, text="Online Users", style='Header.TLabel').pack(pady=5)
        
        self.user_listbox = tk.Listbox(left_panel)
        self.user_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.user_listbox.bind('<<ListboxSelect>>', self.on_user_selected)
        
        ttk.Button(left_panel, text="Refresh", command=self.manual_discover).pack(pady=5)
        
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        self.chat_display = scrolledtext.ScrolledText(
            right_panel, state='disabled', wrap=tk.WORD)
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        input_frame = ttk.Frame(right_panel)
        input_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        self.message_entry = ttk.Entry(input_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.message_entry.bind('<Return>', self.send_message_from_ui)
        
        ttk.Button(input_frame, text="Send", command=self.send_message_from_ui).pack(side=tk.LEFT)
        ttk.Button(input_frame, text="Send File", command=self.send_file_dialog).pack(side=tk.LEFT, padx=(5, 0))
        
        style = ttk.Style()
        style.configure('Header.TLabel', font=('Helvetica', 10, 'bold'))
    
    def update_user_list(self):
        current_selection = self.user_listbox.curselection()
        current_user = self.user_listbox.get(current_selection) if current_selection else None
        
        self.user_listbox.delete(0, tk.END)
        
        for user_id in sorted(self.discovered_users.keys()):
            display_text = f"{user_id[:10]}... ({self.discovered_users[user_id]})"
            self.user_listbox.insert(tk.END, display_text)
            
            if current_user and display_text == current_user:
                self.user_listbox.selection_set(tk.END)
    
    def on_user_selected(self, event):
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            user_display = event.widget.get(index)
            
            for user_id in self.discovered_users:
                if user_display.startswith(user_id[:10]):
                    self.current_chat = user_id
                    self.show_chat(user_id)
                    self.log(f"Chat started with {user_id}")
                    break
    
    def show_chat(self, user_id):
        self.chat_display.config(state='normal')
        self.chat_display.delete(1.0, tk.END)
        
        if user_id in self.active_chats:
            for message in self.active_chats[user_id]:
                self.chat_display.insert(tk.END, message)
        
        self.chat_display.config(state='disabled')
        self.chat_display.see(tk.END)
    
    def add_message_to_chat(self, user_id, message, incoming=True):
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{timestamp}] {user_id if incoming else 'You'}: "
        formatted_message = prefix + message + "\n\n"
        
        if user_id not in self.active_chats:
            self.active_chats[user_id] = []
        
        self.active_chats[user_id].append(formatted_message)
        
        if self.current_chat == user_id:
            self.chat_display.config(state='normal')
            self.chat_display.insert(tk.END, formatted_message)
            self.chat_display.config(state='disabled')
            self.chat_display.see(tk.END)
    
    def discovery_loop(self):
        while self.running:
            try:
                now = time.time()
                if now - self.last_discovery_time > 10:  
                    self.manual_discover()
                    self.last_discovery_time = now
                
                time.sleep(1)  
                
            except Exception as e:
                self.log(f"Error in discovery loop: {e}")
                time.sleep(5) 
    
    def manual_discover(self):
        """Inicia el descubrimiento manual de usuarios"""
        if self.discovery_active:
            return
            
        self.discovery_active = True
        try:
            self.log("Starting user discovery...")
            header = pack_header(self.client_id, '\xFF' * 20, ECHO)
            self.udp_socket.sendto(header, ('<broadcast>', UDP_PORT))
            self.log("Discovery request sent")
        except Exception as e:
            self.log(f"Error sending discovery: {e}")
        finally:
            self.discovery_active = False
    
    def receive_loop(self):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                
                if len(data) >= HEADER_SIZE:
                    user_from, user_to, op_code, body_id, body_length = unpack_header(data)
                    
                    if op_code == MESSAGE and (user_to == self.client_id or user_to == '\xFF' * 20):
                        self.log(f"Message received from {user_from}")
                        response = pack_response(RESPONSE_OK, self.client_id)
                        self.udp_socket.sendto(response, addr)
                        
                        try:
                            body_data, _ = self.udp_socket.recvfrom(1024)
                            received_id = int.from_bytes(body_data[:8], byteorder='big')
                            
                            if received_id == body_id:
                                message = body_data[8:].decode('utf-8')
                                self.root.after(0, lambda: self.add_message_to_chat(
                                    user_from, message, incoming=True))
                                
                                if user_from not in self.discovered_users:
                                    self.discovered_users[user_from] = addr[0]
                                    self.root.after(0, self.update_user_list)
                                
                                response = pack_response(RESPONSE_OK, self.client_id)
                                self.udp_socket.sendto(response, addr)
                        except socket.timeout:
                            self.log("Timeout waiting for message body")
                        except Exception as e:
                            self.log(f"Error processing message: {e}")
                    
                    elif op_code == ECHO and user_to == '\xFF' * 20:
                        self.log(f"Discovery request from {user_from}")
                        response = pack_response(RESPONSE_OK, self.client_id)
                        self.udp_socket.sendto(response, addr)
                        
                        if user_from not in self.discovered_users:
                            self.discovered_users[user_from] = addr[0]
                            self.root.after(0, self.update_user_list)
                            self.log(f"New user discovered: {user_from}")
            
            except socket.timeout:
                continue  
            except Exception as e:
                if self.running:
                    self.log(f"Error in receive loop: {e}")
                    time.sleep(1)  
    
    def send_message_from_ui(self, event=None):
        if not self.current_chat:
            messagebox.showwarning("Warning", "Please select a user to chat with")
            return
            
        message = self.message_entry.get().strip()
        if not message:
            return
            
        def send_task():
            try:
                self.log(f"Sending message to {self.current_chat}...")
                body_id = 1 
                header = pack_header(
                    self.client_id, 
                    self.current_chat, 
                    MESSAGE, 
                    body_id, 
                    len(message.encode('utf-8')))
                
                self.udp_socket.sendto(header, (self.discovered_users[self.current_chat], UDP_PORT))

                self.udp_socket.settimeout(5)
                try:
                    response, _ = self.udp_socket.recvfrom(RESPONSE_SIZE)
                    status, _ = unpack_response(response)
                    
                    if status != RESPONSE_OK:
                        self.root.after(0, lambda: messagebox.showerror("Error", "Recipient didn't acknowledge"))
                        return

                    body = body_id.to_bytes(8, byteorder='big') + message.encode('utf-8')
                    self.udp_socket.sendto(body, (self.discovered_users[self.current_chat], UDP_PORT))
                    
                    response, _ = self.udp_socket.recvfrom(RESPONSE_SIZE)
                    status, _ = unpack_response(response)
                    
                    if status == RESPONSE_OK:
                        self.root.after(0, lambda: self.add_message_to_chat(
                            self.current_chat, message, incoming=False))
                        self.root.after(0, lambda: self.message_entry.delete(0, tk.END))
                        self.log("Message sent successfully")
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Error", "Message delivery failed"))
                        self.log("Message delivery failed")
                
                except socket.timeout:
                    self.root.after(0, lambda: messagebox.showerror("Error", "Timeout waiting for response"))
                    self.log("Timeout waiting for message response")
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send: {str(e)}"))
                self.log(f"Error sending message: {e}")
            finally:
                self.udp_socket.settimeout(1)  
    
        threading.Thread(target=send_task).start()
    
    def send_file_dialog(self):
        if not self.current_chat:
            messagebox.showwarning("Warning", "Please select a user to send file to")
            return
            
        filepath = filedialog.askopenfilename()
        if not filepath:
            return
            
        def send_file_task():
            try:
                self.log(f"Preparing to send file to {self.current_chat}...")
                
                with open(filepath, "rb") as f:
                    file_data = f.read()
                
                body_id =1 
                header = pack_header(
                    self.client_id, 
                    self.current_chat, 
                    FILE, 
                    body_id, 
                    len(file_data))
                
                self.udp_socket.sendto(header, (self.discovered_users[self.current_chat], UDP_PORT))

                self.udp_socket.settimeout(5)
                try:
                    response, _ = self.udp_socket.recvfrom(RESPONSE_SIZE)
                    status, _ = unpack_response(response)
                    
                    if status != RESPONSE_OK:
                        self.root.after(0, lambda: messagebox.showerror("Error", "Recipient didn't acknowledge"))
                        return
                    
                    self.log("Starting file transfer...")
                    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    tcp_sock.settimeout(10)  
                    
                    try:
                        tcp_sock.connect((self.discovered_users[self.current_chat], TCP_PORT))
                        tcp_sock.sendall(body_id.to_bytes(8, byteorder='big') + file_data)
                        
                        response = tcp_sock.recv(RESPONSE_SIZE)
                        status, _ = unpack_response(response)
                        
                        if status == RESPONSE_OK:
                            filename = os.path.basename(filepath)
                            self.root.after(0, lambda: self.add_message_to_chat(
                                self.current_chat, f"Sent file: {filename}", incoming=False))
                            self.log("File sent successfully")
                        else:
                            self.root.after(0, lambda: messagebox.showerror("Error", "File transfer failed"))
                            self.log("File transfer failed")
                    
                    except socket.timeout:
                        self.root.after(0, lambda: messagebox.showerror("Error", "File transfer timeout"))
                        self.log("File transfer timeout")
                    finally:
                        tcp_sock.close()
                
                except socket.timeout:
                    self.root.after(0, lambda: messagebox.showerror("Error", "Timeout waiting for file ACK"))
                    self.log("Timeout waiting for file ACK")
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to send file: {str(e)}"))
                self.log(f"Error sending file: {e}")
            finally:
                self.udp_socket.settimeout(1)  
    
        threading.Thread(target=send_file_task).start()
    
    def on_close(self):
        """Maneja el cierre limpio de la aplicación"""
        self.log("Closing client...")
        self.running = False
        try:
            self.udp_socket.close()
        except:
            pass
        self.root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClientGUI(root)
    root.mainloop()