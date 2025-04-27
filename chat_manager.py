from protocol import pack_response, RESPONSE_OK, BROADCAST_ID


class ChatManager:
    def __init__(self, client_id):
        self.client_id = client_id
        self.discovered_users = {}
        self.chats = {}
        self.active_chats = {"GLOBAL": []}

    def add_user(self, user_id, address):
        if user_id not in self.discovered_users:
            self.discovered_users[user_id] = address
            print(f"Usuario descubierto: {user_id} en {address}")

    def handle_message(
        self, user_from, user_to, body_id, body_length, addr, udp_socket
    ):
        if user_to == self.client_id or user_to == BROADCAST_ID.decode("utf-8"):
            udp_socket.sendto(pack_response(RESPONSE_OK, self.client_id), addr)
            print(f"Mensaje recibido de {user_from}: {body_length} bytes")
            # Registro del mensaje en el historial
            self.add_message_to_chat(user_from, f"{body_length} bytes recibidos")

    def get_chat(self, user_id):
        return self.chats.get(user_id, [])

    def add_message_to_chat(self, user_id, message, incoming=True):
        if user_id not in self.chats:
            self.chats[user_id] = []
        self.chats[user_id].append(("incoming" if incoming else "outgoing", message))

    def start_private_chat(self, user_id):
        """Inicia un chat privado con un usuario específico"""
        if user_id not in self.chats:
            self.chats[user_id] = []
        if user_id not in self.active_chats:
            self.active_chats[user_id] = []
            self.active_chats[user_id].append(f"Inicio de chat con {user_id}...\n")
