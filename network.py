import socket
import threading
import subprocess
import re
import platform
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


def get_network_info():
    """Obtiene información de red sin dependencias externas"""
    system = platform.system()
    broadcast_addresses = []

    try:
        if system == "Darwin":
            output = subprocess.check_output(["ifconfig"], universal_newlines=True)
            interfaces = re.split(r"\n(?=\w)", output)

            for interface in interfaces:
                if (
                    "status: active" in interface
                    and "inet " in interface
                    and "netmask" in interface
                ):
                    ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", interface)
                    mask_match = re.search(r"netmask (0x[0-9a-f]+)", interface)

                    if ip_match and mask_match:
                        ip = ip_match.group(1)
                        hex_mask = mask_match.group(1)
                        int_mask = int(hex_mask, 16)

                        mask = [
                            (int_mask >> 24) & 0xFF,
                            (int_mask >> 16) & 0xFF,
                            (int_mask >> 8) & 0xFF,
                            int_mask & 0xFF,
                        ]
                        mask_str = ".".join(map(str, mask))

                        ip_parts = list(map(int, ip.split(".")))
                        mask_parts = mask
                        broadcast_parts = []

                        for i in range(4):
                            broadcast_parts.append(
                                ip_parts[i] | (~mask_parts[i] & 0xFF)
                            )

                        broadcast = ".".join(map(str, broadcast_parts))
                        broadcast_addresses.append(broadcast)
    except Exception as e:
        print(f"Error obteniendo información de red: {e}")

    return broadcast_addresses


class NetworkManager:
    def __init__(self, client_id):
        self.client_id = client_id
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.settimeout(0.5)

        self.broadcast_addresses = get_network_info()
        print(f"Direcciones de broadcast disponibles: {self.broadcast_addresses}")

        try:
            self.udp_socket.bind(("0.0.0.0", UDP_PORT))
        except Exception as e:
            print(f"Error al vincular el socket: {e}")
            self.udp_socket.bind(("127.0.0.1", UDP_PORT))

        self.running = True
        self.chat_manager = None

    def set_chat_manager(self, chat_manager):
        """Asigna el chat manager para poder acceder a los usuarios descubiertos"""
        self.chat_manager = chat_manager

    def discovery_loop(self, chat_manager):
        if not self.chat_manager:
            self.set_chat_manager(chat_manager)

        while self.running:
            try:
                header = pack_header(
                    self.client_id.encode("utf-8"), BROADCAST_ID, ECHO, 0, 0
                )
                print(f"Enviando discovery broadcast desde {self.client_id}")

                success = False
                for broadcast_addr in self.broadcast_addresses:
                    try:
                        self.udp_socket.sendto(header, (broadcast_addr, UDP_PORT))
                        success = True
                        print(f"Broadcast enviado a {broadcast_addr}")
                    except Exception as e:
                        print(f"Error enviando a {broadcast_addr}: {e}")

                if not success:
                    self.udp_socket.sendto(header, ("127.0.0.1", UDP_PORT))
                    print("Broadcast enviado a localhost (127.0.0.1)")

                threading.Event().wait(10)
            except Exception as e:
                print(f"Error en el descubrimiento: {e}")
                threading.Event().wait(2)

    def receive_loop(self, chat_manager, file_transfer_manager):
        if not self.chat_manager:
            self.set_chat_manager(chat_manager)

        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                print(f"Datos recibidos de {addr}, longitud: {len(data)}")

                if len(data) >= HEADER_SIZE:
                    user_from, user_to, op_code, body_id, body_length = unpack_header(
                        data
                    )
                    print(
                        f"Header recibido: from={user_from}, to={user_to}, op={op_code}"
                    )

                    is_for_us = (
                        user_to == self.client_id
                        or user_to == BROADCAST_ID.decode("utf-8").rstrip("\x00")
                    )

                    if op_code == ECHO:
                        response = pack_response(RESPONSE_OK, self.client_id)
                        self.udp_socket.sendto(response, addr)
                        chat_manager.add_user(user_from, addr[0])
                        print(
                            f"Usuario descubierto y guardado: {user_from} en {addr[0]}"
                        )
                    elif op_code == MESSAGE and is_for_us:
                        chat_manager.handle_message(
                            user_from,
                            user_to,
                            body_id,
                            body_length,
                            addr,
                            self.udp_socket,
                        )
                    elif op_code == FILE and is_for_us:
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
            if not self.chat_manager:
                print("Error: chat_manager no configurado")
                return False

            if user_to == "GLOBAL":
                target_id = BROADCAST_ID

                success = False
                for broadcast_addr in self.broadcast_addresses:
                    try:
                        target_address = (broadcast_addr, UDP_PORT)
                        body_id = 0
                        body_length = len(message_text.encode("utf-8"))

                        header = pack_header(
                            self.client_id.encode("utf-8"),
                            target_id,
                            MESSAGE,
                            body_id,
                            body_length,
                        )

                        print(
                            f"Enviando mensaje global a {target_address}, header size: {len(header)}"
                        )
                        self.udp_socket.sendto(header, target_address)
                        self.udp_socket.sendto(
                            message_text.encode("utf-8"), target_address
                        )
                        success = True
                    except Exception as e:
                        print(f"Error enviando a {broadcast_addr}: {e}")

                return success
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

                print(
                    f"Enviando mensaje a {target_address}, header size: {len(header)}"
                )
                self.udp_socket.sendto(header, target_address)
                self.udp_socket.sendto(message_text.encode("utf-8"), target_address)
                return True

        except Exception as e:
            print(f"Error enviando mensaje: {e}")
            return False
