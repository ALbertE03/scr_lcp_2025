import socket
import threading
from protocol import (
    pack_header,
    unpack_header,
    pack_response,
    unpack_response,
    BROADCAST_ID,
    UDP_PORT,
    RESPONSE_OK,
    MESSAGE,
    ECHO,
    FILE,
    HEADER_SIZE,
)


class NetworkManager:
    def __init__(self, client_id):
        self.client_id = client_id
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.bind(("", UDP_PORT))
        self.running = True

    def discovery_loop(self, chat_manager):
        while self.running:
            try:
                header = pack_header(
                    self.client_id.encode("utf-8"), BROADCAST_ID, ECHO, 0, 0
                )
                self.udp_socket.sendto(header, ("255.255.255.255", UDP_PORT))
                threading.Event().wait(10)
            except Exception as e:
                print(f"Error en el descubrimiento: {e}")

    def receive_loop(self, chat_manager, file_transfer_manager):
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                if len(data) >= HEADER_SIZE:
                    user_from, user_to, op_code, body_id, body_length = unpack_header(
                        data
                    )
                    if op_code == ECHO:
                        response = pack_response(RESPONSE_OK, self.client_id)
                        self.udp_socket.sendto(response, addr)
                        chat_manager.add_user(user_from, addr[0])
                    elif op_code == MESSAGE:
                        chat_manager.handle_message(
                            user_from,
                            user_to,
                            body_id,
                            body_length,
                            addr,
                            self.udp_socket,
                        )
                    elif op_code == FILE:
                        file_transfer_manager.handle_file_transfer(
                            user_from, user_to, body_id, body_length, addr
                        )
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error en el bucle de recepción: {e}")

    def close(self):
        self.running = False
        self.udp_socket.close()

    def send_message(self, user_to, message_text):
        """Envía un mensaje a un usuario específico o al broadcast"""
        try:

            if user_to == "GLOBAL":
                target_id = BROADCAST_ID
                target_address = ("255.255.255.255", UDP_PORT)
            else:

                target_id = user_to.encode("utf-8")
                if user_to not in self.chat_manager.discovered_users:
                    print(f"Usuario desconocido: {user_to}")
                    return False

                target_address = (self.chat_manager.discovered_users[user_to], UDP_PORT)

            body_id = 0
            body_length = len(message_text.encode("utf-8"))

            header = pack_header(
                self.client_id.encode("utf-8"),
                target_id,
                MESSAGE,
                body_id,
                body_length,
            )

            self.udp_socket.sendto(header, target_address)
            self.udp_socket.sendto(message_text.encode("utf-8"), target_address)

            return True
        except Exception as e:
            print(f"Error enviando mensaje: {e}")
            return False
