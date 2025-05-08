import socket
import threading
import subprocess
import re
import platform
import time
from protocol import (
    pack_header,
    unpack_header,
    pack_response,
    unpack_response,
    BROADCAST_ID,
    UDP_PORT,
    TCP_PORT,
    RESPONSE_OK,
    RESPONSE_BAD_REQUEST,
    RESPONSE_INTERNAL_ERROR,
    MESSAGE,
    ECHO,
    FILE,
    HEADER_SIZE,
)


def get_network_info():
    """Obtiene información de red"""
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


def get_mac_address():
    """Obtiene la dirección MAC del primer adaptador de red activo"""
    try:
        system = platform.system()
        if system == "Darwin":
            output = subprocess.check_output(["ifconfig"], universal_newlines=True)
            interfaces = re.split(r"\n(?=\w)", output)
            for interface in interfaces:
                if "status: active" in interface and "ether " in interface:
                    mac_match = re.search(r"ether (\S+)", interface)
                    if mac_match:
                        mac = mac_match.group(1).replace(":", "").lower()
                        print(f"MAC detectada en macOS: {mac}")
                        return mac
        elif system == "Linux":
            output = subprocess.check_output(["ip", "link"], universal_newlines=True)
            for line in output.splitlines():
                if "link/ether" in line:
                    mac_match = re.search(r"link/ether (\S+)", line)
                    if mac_match:
                        mac = mac_match.group(1).replace(":", "").lower()
                        print(f"MAC detectada en Linux: {mac}")
                        return mac
        elif system == "Windows":
            output = subprocess.check_output(["getmac"], universal_newlines=True)
            if output:
                mac_match = re.search(r"([0-9A-F]{2}[-]){5}([0-9A-F]{2})", output)
                if mac_match:
                    mac = mac_match.group(0).replace("-", "").lower()
                    print(f"MAC detectada en Windows: {mac}")
                    return mac

        import random
        import uuid

        try:
            mac = ":".join(
                [
                    "{:02x}".format((uuid.getnode() >> elements) & 0xFF)
                    for elements in range(0, 8 * 6, 8)
                ][::-1]
            )
            mac = mac.replace(":", "")
            print(f"MAC obtenida mediante uuid: {mac}")
            return mac
        except:
            rand_id = f"user_{random.randint(1000, 9999)}"
            print(f"Generando ID aleatorio: {rand_id}")
            return rand_id

    except Exception as e:
        print(f"Error obteniendo dirección MAC: {e}")
        import random

        rand_id = f"user_{random.randint(1000, 9999)}"
        print(f"Error, generando ID aleatorio: {rand_id}")
        return rand_id


class NetworkManager:
    def __init__(self, client_id=None):
        if client_id is None:
            self.client_id = get_mac_address()
            self.client_id = self.client_id[:20]
            print(f"Usando dirección MAC como ID: {self.client_id}")
        else:
            self.client_id = client_id[:20]

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.settimeout(5.0)

        self.broadcast_addresses = get_network_info()
        print(f"Direcciones de broadcast disponibles: {self.broadcast_addresses}")

        try:
            self.udp_socket.bind(("0.0.0.0", UDP_PORT))
        except Exception as e:
            print(f"Error al vincular el socket UDP: {e}")
            self.udp_socket.bind(("127.0.0.1", UDP_PORT))

        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.tcp_socket.bind(("0.0.0.0", TCP_PORT))
            self.tcp_socket.listen(5)
        except Exception as e:
            print(f"Error al vincular el socket TCP: {e}")

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
                        print(f"Intentando enviar ECHO a {broadcast_addr}:{UDP_PORT}")
                        self.udp_socket.sendto(header, (broadcast_addr, UDP_PORT))
                        success = True
                        print(f"ECHO enviado exitosamente a {broadcast_addr}")
                    except Exception as e:
                        print(f"Error enviando a {broadcast_addr}: {e}")

                if not success:
                    try:
                        self.udp_socket.sendto(header, ("127.0.0.1", UDP_PORT))
                        print("ECHO enviado a localhost")
                    except Exception as e:
                        print(f"Error enviando a localhost: {e}")

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

                if len(data) == 25:
                    try:
                        try:
                            status, sender_id = unpack_response(data)
                            print(
                                f"Respuesta recibida: status={status}, from={sender_id}"
                            )
                        except Exception as e:
                            response = pack_response(
                                RESPONSE_BAD_REQUEST, self.client_id
                            )
                            self.udp_socket.sendto(response, addr)
                            print(f"Error al unpackear respuesta: {e}")
                            continue
                        if status == RESPONSE_OK:
                            sender_id_str = sender_id.strip("\x00")
                            chat_manager.add_user(sender_id_str, addr[0])
                            print(
                                f"Usuario añadido desde respuesta: {sender_id_str} en {addr[0]}"
                            )
                        continue
                    except Exception as e:
                        response = pack_response(
                            RESPONSE_INTERNAL_ERROR, self.client_id
                        )
                        self.udp_socket.sendto(response, addr)
                        print(f"Error al procesar respuesta: {e}")

                if len(data) == HEADER_SIZE:
                    user_from, user_to, op_code, body_id, body_length = unpack_header(
                        data
                    )
                    print(
                        f"Header recibido: from={user_from}, to={user_to}, op={op_code}"
                    )

                    user_from = user_from.rstrip("\x00")
                    user_to = user_to.rstrip("\x00")
                    broadcast_id = BROADCAST_ID.decode("utf-8").rstrip("\x00")

                    is_for_us = user_to == self.client_id or user_to == broadcast_id

                    if op_code == ECHO:
                        print(f"ECHO recibido de {user_from}")
                        response = pack_response(RESPONSE_OK, self.client_id)
                        self.udp_socket.sendto(response, addr)
                        chat_manager.add_user(user_from, addr[0])
                        print(
                            f"Usuario descubierto y guardado: {user_from} en {addr[0]}"
                        )

                    elif op_code == MESSAGE and is_for_us:
                        response = pack_response(RESPONSE_OK, self.client_id)
                        self.udp_socket.sendto(response, addr)

                        # Fase 2: Esperar el cuerpo del mensaje
                        chat_manager.handle_message(
                            user_from,
                            user_to,
                            body_id,
                            body_length,
                            addr,
                            self.udp_socket,
                        )
                    elif op_code == FILE and is_for_us:
                        # Responder al header de archivo con OK para iniciar transferencia TCP
                        response = pack_response(RESPONSE_OK, self.client_id)
                        self.udp_socket.sendto(response, addr)

                        # Delegar la transferencia del archivo al gestor correspondiente
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
        self.tcp_socket.close()

    def send_message(self, user_to, message_text):
        """Envía un mensaje a un usuario específico o al broadcast"""
        try:
            if not self.chat_manager:
                print("Error: chat_manager no configurado")
                return False

            message_bytes = message_text.encode("utf-8")
            body_id = int(time.time() % 256)
            body_length = len(message_bytes)

            if user_to == "GLOBAL":
                target_id = BROADCAST_ID
                success = False

                for broadcast_addr in self.broadcast_addresses:
                    try:
                        target_address = (broadcast_addr, UDP_PORT)

                        header = pack_header(
                            self.client_id.encode("utf-8"),
                            target_id,
                            MESSAGE,
                            body_id,
                            body_length,
                        )
                        print(f"Enviando header de mensaje global a {target_address}")
                        self.udp_socket.sendto(header, target_address)

                        try:
                            self.udp_socket.settimeout(5.0)
                            data, resp_addr = self.udp_socket.recvfrom(25)
                            status, resp_id = unpack_response(data)

                            if status == RESPONSE_OK:
                                message_with_id = (
                                    body_id.to_bytes(8, byteorder="big") + message_bytes
                                )
                                self.udp_socket.sendto(message_with_id, target_address)
                                success = True
                                print(
                                    f"Mensaje enviado correctamente a {broadcast_addr}"
                                )
                        except socket.timeout:
                            print(f"Timeout esperando respuesta de {broadcast_addr}")
                    except Exception as e:
                        print(f"Error enviando a {broadcast_addr}: {e}")

                return success
            else:
                # Mensaje a usuario específico
                target_id = user_to.encode("utf-8")
                if user_to not in self.chat_manager.discovered_users:
                    print(f"Usuario desconocido: {user_to}")
                    return False

                target_address = (
                    self.chat_manager.discovered_users[user_to],
                    UDP_PORT,
                )

                # Fase 1: Enviar header según protocolo LCP
                header = pack_header(
                    self.client_id.encode("utf-8"),
                    target_id,
                    MESSAGE,
                    body_id,
                    body_length,
                )

                print(f"Enviando header de mensaje a {target_address}")
                self.udp_socket.sendto(header, target_address)

                # Según protocolo: esperar respuesta antes de enviar cuerpo
                try:
                    self.udp_socket.settimeout(5.0)  # Timeout según protocolo
                    data, resp_addr = self.udp_socket.recvfrom(25)
                    status, resp_id = unpack_response(data)

                    if status == RESPONSE_OK:
                        # Fase 2: Enviar cuerpo del mensaje con los 8 bytes de ID primero
                        message_with_id = (
                            body_id.to_bytes(8, byteorder="big") + message_bytes
                        )
                        self.udp_socket.sendto(message_with_id, target_address)
                        return True
                    else:
                        print(f"Error de respuesta: status={status}")
                        return False
                except socket.timeout:
                    print(f"Timeout esperando respuesta de {user_to}")
                    return False

        except Exception as e:
            print(f"Error enviando mensaje: {e}")
            return False
