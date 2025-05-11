from protocol import *
import socket
import threading
import time
from datetime import datetime, timedelta
import queue
import random
import logging
import os
import sys
from utils.network_utils import *
from utils.system_info import *

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("LCP")


class LCPPeer:
    def __init__(self, user_id):
        self.user_id = user_id.ljust(20)[:20].encode("utf-8")
        self.user_id_str = user_id.ljust(20)[:20]
        logger.info(f"Inicializando peer LCP con ID: {self.user_id_str}")

        (
            self.message_workers_count,
            self.file_workers_count,
            self.max_concurrent_transfers,
        ) = get_optimal_thread_count()

        logger.info(
            f"Configurando {self.message_workers_count} hilos para mensajes (operaciones de red UDP)"
        )
        logger.info(
            f"Configurando {self.file_workers_count} hilos para transferencias (operaciones TCP y archivos)"
        )
        logger.info(
            f"Límite de transferencias concurrentes: {self.max_concurrent_transfers}"
        )

        self.peers = {}
        self._peers_lock = threading.Lock()

        self._udp_socket_lock = threading.Lock()
        self._tcp_socket_lock = threading.Lock()
        self._callback_lock = threading.Lock()

        self._conversation_locks = {}
        self._conversation_locks_lock = threading.Lock()

        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.bind(("0.0.0.0", UDP_PORT))
        logger.info(f"Socket UDP inicializado en 0.0.0.0:{UDP_PORT}")

        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.bind(("0.0.0.0", TCP_PORT))
        self.tcp_socket.listen(5)
        logger.info(f"Socket TCP inicializado en 0.0.0.0:{TCP_PORT}")

        udp_thread = threading.Thread(
            target=self._udp_listener, daemon=True, name="UDP-Listener"
        )
        udp_thread.start()
        logger.info("Hilo UDP-Listener iniciado")

        tcp_thread = threading.Thread(
            target=self._tcp_listener, daemon=True, name="TCP-Listener"
        )
        tcp_thread.start()
        logger.info("Hilo TCP-Listener iniciado")

        discovery_thread = threading.Thread(
            target=self._discovery_service, daemon=True, name="Discovery"
        )
        discovery_thread.start()
        logger.info("Servicio de autodescubrimiento iniciado")

        self.message_callbacks = []
        self.file_callbacks = []
        self.peer_discovery_callbacks = []

        self.file_progress_callbacks = []

        self.message_queue = queue.Queue()

        self.file_send_queue = queue.Queue()

        self.active_file_transfers = 0
        self._transfers_lock = threading.Lock()

        for i in range(self.message_workers_count):
            worker_name = f"Worker-{i+1}"
            threading.Thread(
                target=self._message_worker, daemon=True, name=worker_name
            ).start()
            logger.info(f"Worker de mensajes {worker_name} iniciado")

        for i in range(self.file_workers_count):
            worker_name = f"FileSender-{i+1}"
            threading.Thread(
                target=self._file_send_worker, daemon=True, name=worker_name
            ).start()
            logger.info(f"Worker de envío de archivos {worker_name} iniciado")

    def _build_header(self, user_to, operation, body_id=0, body_length=0):
        """Construye el header"""
        header = bytearray(100)
        header[0:20] = self.user_id
        header[20:40] = (
            BROADCAST_ID * 20
            if user_to is None
            else user_to.ljust(20)[:20].encode("utf-8")
        )
        header[40] = operation
        header[41] = body_id
        header[42:50] = body_length.to_bytes(8, "big")
        return header

    def _parse_header(self, data):
        """Parsea un header LCP de 100 bytes"""
        if len(data) < 100:
            return None

        return {
            "user_from": data[0:20].decode("utf-8").rstrip("\x00"),
            "user_to": data[20:40].decode("utf-8").rstrip("\x00"),
            "operation": data[40],
            "body_id": data[41],
            "body_length": int.from_bytes(data[42:50], "big"),
        }

    def _send_response(self, addr, status, reason=None):
        """Envía una respuesta según el protocolo LCP (25 bytes)

        Args:
            addr: Tuple (IP, puerto) del destinatario
            status: Código de estado (0=OK, 1=Bad Request, 2=Internal Error)
            reason: Razón del error
        """
        response = bytearray(25)
        response[0] = status
        response[1:21] = self.user_id

        status_text = {
            RESPONSE_OK: "OK",
            RESPONSE_BAD_REQUEST: "BAD REQUEST",
            RESPONSE_INTERNAL_ERROR: "INTERNAL ERROR",
        }.get(status, f"UNKNOWN STATUS ({status})")

        if reason and status != RESPONSE_OK:
            logger.warning(
                f"Enviando respuesta {status_text} a {addr[0]}:{addr[1]} - Razón: {reason}"
            )
        else:
            logger.debug(f"Enviando respuesta {status_text} a {addr[0]}:{addr[1]}")

        self.udp_socket.sendto(response, addr)

    def _build_response(self, status, reason=None):
        """Construye respuesta de 25 bytes con código de estado

        Args:
            status: Código de estado (0=OK, 1=Bad Request, 2=Internal Error)
            reason: Razón del error (solo para logs, no se envía en el protocolo)

        Returns:
            bytearray: Respuesta formateada de 25 bytes
        """
        response = bytearray(25)
        response[0] = status
        response[1:21] = self.user_id

        status_text = {
            RESPONSE_OK: "OK",
            RESPONSE_BAD_REQUEST: "BAD REQUEST",
            RESPONSE_INTERNAL_ERROR: "INTERNAL ERROR",
        }.get(status, f"UNKNOWN STATUS ({status})")

        if reason and status != RESPONSE_OK:
            logger.warning(f"Construyendo respuesta {status_text} - Razón: {reason}")

        return response

    def _discovery_service(self):
        """Servicio periódico de autodescubrimiento"""
        while True:
            try:
                self.send_echo()
                time.sleep(5)
            except Exception as e:
                logger.error(e)
            now = datetime.now()
            with self._peers_lock:
                inactive = [
                    user_id
                    for user_id, (_, last_seen) in self.peers.items()
                    if now - last_seen > timedelta(seconds=90)
                ]

                for user_id in inactive:
                    logger.info(
                        f"Peer inactivo eliminado: {user_id} (sin actividad por >90s)"
                    )
                    self.peers.pop(user_id, None)
                    with self._callback_lock:
                        for callback in self.peer_discovery_callbacks:
                            callback(user_id, False)

    def send_echo(self, wait_responses=False):
        """Operación 0: Echo-Reply para descubrimiento de pares

        Args:
            wait_responses: Si es True, espera respuestas durante un breve tiempo
                           y procesa los peers que responden
        """
        header = self._build_header(None, 0)

        with self._udp_socket_lock:

            for i in get_network_info():
                logger.info(f"Enviando ECHO (broadcast) a {i}:{UDP_PORT}")
                self.udp_socket.sendto(header, (i, UDP_PORT))

            self.udp_socket.settimeout(5)
            logger.info(f"Esperando respuestas al ECHO durante 5 segundos...")

            start_time = time.time()

            try:
                while time.time() - start_time < 5:
                    try:
                        resp_data, resp_addr = self.udp_socket.recvfrom(25)

                        if len(resp_data) == 25:
                            status = resp_data[0]
                            user_id = resp_data[1:21].decode("utf-8").rstrip("\x00")

                            if status == 0:
                                logger.info(
                                    f"Recibida respuesta ECHO de {user_id} desde {resp_addr[0]}:{resp_addr[1]}"
                                )

                                with self._peers_lock:
                                    is_new = user_id not in self.peers
                                    self.peers[user_id] = (
                                        resp_addr[0],
                                        datetime.now(),
                                    )

                                    if is_new:
                                        logger.info(
                                            f"Nuevo peer descubierto: {user_id}"
                                        )
                                        for callback in self.peer_discovery_callbacks:
                                            callback(user_id, True)

                    except socket.timeout:
                        break

            except Exception as e:
                logger.error(f"Error procesando respuestas ECHO: {e}")

            finally:
                self.udp_socket.settimeout(None)
                logger.info(
                    f"Finalizada espera de respuestas ECHO. Tiempo total: {time.time() - start_time:.2f}s"
                )

        return

    def _udp_listener(self):
        """Escucha mensajes UDP de control"""
        logger.info("Iniciando escucha de mensajes UDP en puerto %d", UDP_PORT)
        while True:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                logger.info(
                    f"UDP recibido: {len(data)} bytes desde {addr[0]}:{addr[1]}"
                )
                handler_thread = threading.Thread(
                    target=self._handle_udp_message,
                    args=(data, addr),
                    daemon=True,
                    name=f"UDPHandler-{addr[0]}:{addr[1]}",
                )
                handler_thread.start()
                logger.debug(
                    f"Lanzado hilo {handler_thread.name} para procesar mensaje UDP"
                )
            except Exception as e:
                logger.error(f"Error en UDP listener: {e}")

    def _handle_udp_message(self, data, addr):
        """Maneja un mensaje UDP en un hilo separado"""
        try:
            header = self._parse_header(data)
            if not header:
                logger.warning(
                    f"Recibido mensaje UDP malformado desde {addr[0]}:{addr[1]}"
                )
                return

            if header["user_from"] == self.user_id.decode("utf-8").rstrip("\x00"):
                logger.debug(f"Ignorando mensaje propio desde {addr[0]}:{addr[1]}")
                return

            with self._peers_lock:
                is_new = header["user_from"] not in self.peers
                self.peers[header["user_from"]] = (addr[0], datetime.now())
                status_text = "nuevo" if is_new else "existente"
                logger.info(
                    f"Peer {status_text} registrado: {header['user_from']} en {addr[0]}:{addr[1]}"
                )

            if is_new:
                for callback in self.peer_discovery_callbacks:
                    callback(header["user_from"], True)

            operation_type = "desconocida"
            if header["operation"] == 0:
                operation_type = "ECHO"
                self._process_echo(header, addr)
            elif header["operation"] == 1:
                operation_type = "MENSAJE"
                self.message_queue.put(
                    {
                        "type": "message",
                        "header": header,
                        "addr": addr,
                    }
                )
            elif header["operation"] == 2:
                operation_type = "ARCHIVO"
                self.message_queue.put(
                    {
                        "type": "file",
                        "header": header,
                        "addr": addr,
                    }
                )

            logger.info(
                f"Recibido mensaje de tipo {operation_type} (op={header['operation']}) de {header['user_from']}"
            )

            if header["operation"] > 0:
                logger.debug(
                    f"Cola de mensajes: aproximadamente {self.message_queue.qsize()} tareas pendientes"
                )

        except Exception as e:
            logger.error(f"Error procesando mensaje UDP: {e}")

    def _tcp_listener(self):
        """Escucha conexiones TCP para transferencia de archivos"""
        logger.info(f"Iniciando escucha de conexiones TCP en puerto {TCP_PORT}")
        while True:
            try:
                conn, addr = self.tcp_socket.accept()
                logger.info(f"Nueva conexión TCP desde {addr[0]}:{addr[1]}")
                handler_thread = threading.Thread(
                    target=self._handle_file_transfer,
                    args=(conn, addr),
                    daemon=True,
                    name=f"FileHandler-{addr[0]}:{addr[1]}",
                )
                handler_thread.start()
                logger.info(
                    f"Lanzado hilo {handler_thread.name} para manejar transferencia de archivo"
                )
            except Exception as e:
                logger.error(f"Error en TCP listener: {e}", exc_info=True)

    def _process_echo(self, header, addr):
        """Procesa operación 0: Echo-Reply para autodescubrimiento"""
        user_from = header["user_from"]
        worker_name = threading.current_thread().name

        logger.info(
            f"{worker_name} procesando ECHO de {user_from} desde {addr[0]}:{addr[1]}"
        )

        with self._udp_socket_lock:
            logger.debug(f"{worker_name} enviando respuesta a ECHO de {user_from}")
            self._send_response(addr, 0)
            logger.info(f"{worker_name} respuesta a ECHO enviada a {user_from}")

    def _process_message(self, header, addr):
        """Procesa operación 1: Message-Response"""
        user_from = header["user_from"]
        worker_name = threading.current_thread().name

        logger.info(
            f"{worker_name} iniciando procesamiento de mensaje de {user_from} desde {addr[0]}:{addr[1]}"
        )

        with self._conversation_locks_lock:
            if user_from not in self._conversation_locks:
                logger.debug(f"Creando nuevo lock de conversación para {user_from}")
                self._conversation_locks[user_from] = threading.Lock()
            user_lock = self._conversation_locks[user_from]

        with user_lock:
            logger.debug(
                f"{worker_name} adquirió lock de conversación para {user_from}"
            )

            with socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM
            ) as conversation_socket:
                local_port = 0
                conversation_socket.bind(("0.0.0.0", local_port))
                local_addr = conversation_socket.getsockname()
                logger.info(
                    f"{worker_name} creó socket UDP temporal en puerto {local_addr[1]} para conversación"
                )

                if not all(
                    key in header
                    for key in [
                        "user_from",
                        "user_to",
                        "operation",
                        "body_id",
                        "body_length",
                    ]
                ):
                    with self._udp_socket_lock:
                        logger.warning(
                            f"{worker_name} rechazando header de {user_from} por formato incorrecto"
                        )
                        self._send_response(
                            addr, RESPONSE_BAD_REQUEST, "Header incompleto o malformado"
                        )
                    return

                # Verificar que el mensaje está dirigido a nosotros
                expected_recipient = self.user_id_str.rstrip("\x00")
                if (
                    header["user_to"] != expected_recipient
                    and header["user_to"] != "\xff" * 20
                ):
                    with self._udp_socket_lock:
                        logger.warning(
                            f"{worker_name} rechazando mensaje para destinatario incorrecto: {header['user_to']}"
                        )
                        self._send_response(
                            addr,
                            RESPONSE_BAD_REQUEST,
                            f"Destinatario incorrecto: esperaba {expected_recipient}",
                        )
                    return

                with self._udp_socket_lock:
                    logger.debug(
                        f"{worker_name} enviando confirmación de header (phase 1) a {addr[0]}:{addr[1]}"
                    )
                    self._send_response(addr, RESPONSE_OK)
                    logger.info(
                        f"{worker_name} confirmó recepción de header a {user_from}"
                    )

                # Fase 2: Recibir cuerpo del mensaje
                try:
                    logger.info(
                        f"{worker_name} esperando cuerpo del mensaje de {user_from} (timeout: 5s)"
                    )
                    conversation_socket.settimeout(5)
                    body_data, msg_addr = conversation_socket.recvfrom(65507)
                    logger.info(
                        f"{worker_name} recibió {len(body_data)} bytes de datos desde {msg_addr[0]}:{msg_addr[1]}"
                    )

                    # Verificar el origen del mensaje
                    if msg_addr[0] != addr[0]:
                        logger.warning(
                            f"{worker_name} detectó IP diferente en mensaje de datos: esperaba {addr[0]}, recibió {msg_addr[0]}"
                        )
                        with self._udp_socket_lock:
                            self._send_response(
                                addr,
                                RESPONSE_BAD_REQUEST,
                                "Origen del mensaje no coincide con el header",
                            )
                        return

                    # Verificar que el BodyId coincida
                    received_body_id = (
                        int.from_bytes(body_data[:8], "big")
                        if len(body_data) >= 8
                        else -1
                    )
                    expected_body_id = header["body_id"]

                    if received_body_id == expected_body_id:
                        logger.debug(
                            f"{worker_name} verificó BodyId correcto: {received_body_id}"
                        )

                        # Verificar que el tamaño del mensaje coincide con lo indicado en el header
                        expected_length = header["body_length"]
                        actual_length = (
                            len(body_data) - 8
                        )  # Restar los 8 bytes del BodyId

                        if actual_length != expected_length:
                            logger.warning(
                                f"{worker_name} tamaño de mensaje incorrecto: esperaba {expected_length}, recibió {actual_length}"
                            )
                            with self._udp_socket_lock:
                                self._send_response(
                                    addr,
                                    RESPONSE_BAD_REQUEST,
                                    "Tamaño de mensaje incorrecto",
                                )
                            return

                        try:
                            message = body_data[8:].decode("utf-8")
                            logger.info(
                                f"{worker_name} decodificó mensaje de {user_from}: {message[:50]}..."
                            )

                            # Usar lock para callbacks
                            with self._callback_lock:
                                logger.debug(
                                    f"{worker_name} notificando mensaje a {len(self.message_callbacks)} callbacks"
                                )
                                for callback in self.message_callbacks:
                                    callback(user_from, message)

                            # Fase 3: Confirmar recepción
                            with self._udp_socket_lock:
                                logger.debug(
                                    f"{worker_name} enviando confirmación final (phase 3) a {addr[0]}:{addr[1]}"
                                )
                                self._send_response(addr, RESPONSE_OK)
                                logger.info(
                                    f"{worker_name} completó procesamiento de mensaje de {user_from}"
                                )
                        except UnicodeDecodeError:
                            logger.error(
                                f"{worker_name} error decodificando mensaje como UTF-8"
                            )
                            with self._udp_socket_lock:
                                self._send_response(
                                    addr,
                                    RESPONSE_BAD_REQUEST,
                                    "Error de codificación del mensaje",
                                )
                    else:
                        logger.warning(
                            f"{worker_name} error de BodyId: esperaba {expected_body_id}, recibió {received_body_id}"
                        )
                        with self._udp_socket_lock:
                            self._send_response(
                                addr,
                                RESPONSE_BAD_REQUEST,
                                f"BodyId incorrecto: esperaba {expected_body_id}, recibió {received_body_id}",
                            )

                except socket.timeout:
                    logger.error(
                        f"{worker_name} timeout esperando datos de mensaje de {user_from}"
                    )
                    with self._udp_socket_lock:
                        self._send_response(
                            addr,
                            RESPONSE_INTERNAL_ERROR,
                            "Timeout esperando datos del mensaje",
                        )
                except Exception as e:
                    logger.error(
                        f"{worker_name} error procesando mensaje de {user_from}: {e}",
                        exc_info=True,
                    )
                    with self._udp_socket_lock:
                        self._send_response(
                            addr, RESPONSE_INTERNAL_ERROR, f"Error interno: {str(e)}"
                        )
                finally:
                    # Limpiar locks viejos periódicamente
                    if random.random() < 0.1:
                        logger.debug(
                            f"{worker_name} iniciando limpieza de locks de conversación antiguos"
                        )
                        self._cleanup_conversation_locks()

    def _process_file_request(self, header, addr):
        """Procesa operación 2: Send File-Ack"""
        user_from = header["user_from"]
        worker_name = threading.current_thread().name

        logger.info(f"{worker_name} procesando solicitud de archivo de {user_from}")

        # Verificar que el header es válido
        if not all(
            key in header
            for key in ["user_from", "user_to", "operation", "body_id", "body_length"]
        ):
            with self._udp_socket_lock:
                logger.warning(
                    f"{worker_name} rechazando header de archivo de {user_from} por formato incorrecto"
                )
                self._send_response(
                    addr, RESPONSE_BAD_REQUEST, "Header incompleto o malformado"
                )
            return

        # Verificar que el archivo está dirigido a nosotros
        expected_recipient = self.user_id_str.rstrip("\x00")
        if header["user_to"] != expected_recipient:
            with self._udp_socket_lock:
                logger.warning(
                    f"{worker_name} rechazando archivo para destinatario incorrecto: {header['user_to']}"
                )
                self._send_response(
                    addr,
                    RESPONSE_BAD_REQUEST,
                    f"Destinatario incorrecto: esperaba {expected_recipient}",
                )
            return

        file_size = header["body_length"]
        if file_size <= 0 or file_size > (1024 * 1024 * 1024):
            with self._udp_socket_lock:
                logger.warning(
                    f"{worker_name} rechazando archivo de tamaño inválido: {file_size} bytes"
                )
                self._send_response(
                    addr,
                    RESPONSE_BAD_REQUEST,
                    f"Tamaño de archivo inválido: {file_size} bytes",
                )
            return

        # Almacenar el body_id esperado para esta transferencia en un diccionario compartido
        with self._peers_lock:
            expected_file_id = header["body_id"]
            # Si no existe, crear un nuevo diccionario para este peer
            if not hasattr(self, "_expected_file_transfers"):
                self._expected_file_transfers = {}

            # Guardar la información de la transferencia esperada: body_id y tamaño
            peer_ip = addr[0]
            self._expected_file_transfers[peer_ip] = {
                "body_id": expected_file_id,
                "file_size": file_size,
                "user_from": user_from,
                "timestamp": time.time(),
            }
            logger.info(
                f"{worker_name} registrando transferencia esperada de {user_from} con ID {expected_file_id}"
            )

        with self._udp_socket_lock:
            logger.info(
                f"{worker_name} aceptando solicitud de archivo de {user_from}, tamaño: {file_size} bytes, ID: {expected_file_id}"
            )
            self._send_response(addr, RESPONSE_OK)

        logger.info(
            f"{worker_name} esperando conexión TCP de {user_from} para transferencia de archivo con ID {expected_file_id}"
        )

    def _handle_file_transfer(self, conn, addr):
        """Maneja la transferencia de archivo por TCP"""
        worker_name = threading.current_thread().name
        logger.info(
            f"{worker_name} iniciando manejo de transferencia de archivo desde {addr[0]}:{addr[1]}"
        )

        try:
            # Recibir los primeros 8 bytes (File ID) según el protocolo LCP
            file_id_bytes = conn.recv(8)
            if len(file_id_bytes) < 8:
                logger.error(
                    f"{worker_name} recibió identificador de archivo incompleto: {len(file_id_bytes)} bytes"
                )
                conn.send(
                    self._build_response(
                        RESPONSE_BAD_REQUEST, "ID de archivo incompleto"
                    )
                )
                conn.close()
                return

            file_id = int.from_bytes(file_id_bytes, "big")
            logger.info(f"{worker_name} recibió identificador de archivo: {file_id}")

            # Verificar si tenemos una transferencia esperada desde esta IP y con este ID
            expected_transfer_info = None
            peer_id = None

            with self._peers_lock:
                if (
                    hasattr(self, "_expected_file_transfers")
                    and addr[0] in self._expected_file_transfers
                ):
                    expected_transfer_info = self._expected_file_transfers[addr[0]]

                # Buscar el peer_id correspondiente a esta IP
                for user_id, (ip, _) in self.peers.items():
                    if ip == addr[0]:
                        peer_id = user_id
                        break

            # Verificar que es una transferencia válida
            if not expected_transfer_info:
                logger.warning(
                    f"{worker_name} no hay transferencia esperada desde IP {addr[0]}, rechazando conexión"
                )
                conn.send(
                    self._build_response(
                        RESPONSE_BAD_REQUEST, "Transferencia no autorizada"
                    )
                )
                conn.close()
                return

            # Verificar que el ID del archivo coincide con el esperado
            if expected_transfer_info["body_id"] != file_id:
                logger.warning(
                    f"{worker_name} ID de archivo incorrecto: esperado {expected_transfer_info['body_id']}, recibido {file_id}"
                )
                conn.send(
                    self._build_response(
                        RESPONSE_BAD_REQUEST, "ID de archivo incorrecto"
                    )
                )
                conn.close()
                return

            if not peer_id:
                logger.warning(
                    f"{worker_name} no pudo identificar peer con IP {addr[0]}, cerrando conexión"
                )
                conn.send(
                    self._build_response(RESPONSE_BAD_REQUEST, "Peer no identificado")
                )
                conn.close()
                return

            logger.info(
                f"{worker_name} identificó peer como {peer_id} para la transferencia de archivo con ID {file_id}"
            )

            # Crear archivo temporal con el formato lcp_file_<timestamp>_<peer_id>.dat
            timestamp = int(time.time())
            temp_file = f"lcp_file_{timestamp}_{peer_id}.dat"
            expected_size = expected_transfer_info["file_size"]

            try:
                logger.info(
                    f"{worker_name} creando archivo temporal: {temp_file}, tamaño esperado: {expected_size} bytes"
                )

                bytes_recibidos = 0
                with open(temp_file, "wb") as f:
                    logger.info(
                        f"{worker_name} iniciando recepción de datos de archivo"
                    )

                    # Recibir el contenido del archivo según el protocolo LCP
                    while bytes_recibidos < expected_size:
                        # Calcular cuántos bytes quedan por recibir
                        bytes_restantes = expected_size - bytes_recibidos
                        # Usar un tamaño de buffer adecuado (máximo 4096 bytes)
                        chunk_size = min(4096, bytes_restantes)

                        data = conn.recv(chunk_size)
                        if not data:
                            logger.debug(
                                f"{worker_name} fin de transmisión detectado antes de completar"
                            )
                            break

                        f.write(data)
                        bytes_recibidos += len(data)

                        if bytes_recibidos % (1024 * 1024) < 4096:  # Log cada ~1MB
                            progress = (
                                int((bytes_recibidos / expected_size) * 100)
                                if expected_size > 0
                                else 0
                            )
                            logger.info(
                                f"{worker_name} progreso: {bytes_recibidos/1024:.1f} KB ({progress}%) recibidos de {peer_id}"
                            )

            except IOError as e:
                logger.error(f"{worker_name} error de I/O escribiendo archivo: {e}")
                conn.send(
                    self._build_response(
                        RESPONSE_INTERNAL_ERROR, f"Error de I/O: {str(e)}"
                    )
                )
                return

            # Verificar que el archivo se recibió correctamente
            try:
                received_size = os.path.getsize(temp_file)

                # Verificar si el archivo recibido está completo
                if received_size != expected_size:
                    logger.error(
                        f"{worker_name} tamaño de archivo incorrecto: esperado {expected_size}, recibido {received_size}"
                    )
                    conn.send(
                        self._build_response(
                            RESPONSE_BAD_REQUEST,
                            f"Tamaño incorrecto: esperado {expected_size}, recibido {received_size}",
                        )
                    )
                    return

                logger.info(
                    f"{worker_name} transferencia completa: {bytes_recibidos} bytes recibidos en {temp_file}"
                )

                # Limpiar la información de transferencia esperada
                with self._peers_lock:
                    if (
                        hasattr(self, "_expected_file_transfers")
                        and addr[0] in self._expected_file_transfers
                    ):
                        del self._expected_file_transfers[addr[0]]

                # Notificar a los callbacks
                logger.info(
                    f"{worker_name} notificando recepción de archivo a {len(self.file_callbacks)} callbacks"
                )
                for callback in self.file_callbacks:
                    callback(peer_id, temp_file)

                # Enviar confirmación final (25 bytes) según el protocolo
                logger.debug(
                    f"{worker_name} enviando confirmación de recepción exitosa a {peer_id}"
                )
                conn.send(self._build_response(RESPONSE_OK))
                logger.info(
                    f"{worker_name} transferencia de archivo finalizada correctamente"
                )

            except Exception as e:
                logger.error(f"{worker_name} error verificando archivo recibido: {e}")
                conn.send(
                    self._build_response(
                        RESPONSE_INTERNAL_ERROR, f"Error interno: {str(e)}"
                    )
                )

        except ConnectionError as e:
            logger.error(f"{worker_name} error de conexión: {e}")
            try:
                conn.send(
                    self._build_response(
                        RESPONSE_INTERNAL_ERROR, f"Error de conexión: {str(e)}"
                    )
                )
            except:
                pass
        except Exception as e:
            logger.error(
                f"{worker_name} error en transferencia de archivo: {e}", exc_info=True
            )
            try:
                conn.send(
                    self._build_response(RESPONSE_INTERNAL_ERROR, f"Error: {str(e)}")
                )
            except:
                pass
        finally:
            conn.close()
            logger.debug(f"{worker_name} conexión TCP cerrada")

    def _cleanup_conversation_locks(self):
        """Limpia locks de conversaciones antiguas"""
        with self._conversation_locks_lock:
            # Mantener un máximo de 100 locks para evitar crecimiento indefinido
            if len(self._conversation_locks) > 100:
                # Eliminar algunos locks aleatorios
                keys_to_remove = random.sample(
                    list(self._conversation_locks.keys()),
                    len(self._conversation_locks) - 50,
                )
                for key in keys_to_remove:
                    del self._conversation_locks[key]

    def _message_worker(self):
        """Procesa mensajes de la cola"""
        worker_name = threading.current_thread().name
        logger.info(f"Worker {worker_name} iniciado y listo para procesar mensajes")

        while True:
            try:
                task = self.message_queue.get()
                header = task["header"]
                addr = task["addr"]

                logger.info(
                    f"{worker_name} procesando tarea de tipo '{task['type']}' de {header['user_from']} ({addr[0]}:{addr[1]})"
                )

                start_time = time.time()

                if task["type"] == "message":
                    logger.info(
                        f"{worker_name} procesando mensaje de {header['user_from']}"
                    )
                    self._process_message(header, addr)

                elif task["type"] == "file":
                    logger.info(
                        f"{worker_name} procesando solicitud de archivo de {header['user_from']}"
                    )
                    self._process_file_request(header, addr)

                process_time = time.time() - start_time
                logger.info(
                    f"{worker_name} completó procesamiento en {process_time:.3f} segundos"
                )

            except Exception as e:
                logger.error(f"{worker_name} error: {e}")
            finally:
                self.message_queue.task_done()
                logger.debug(
                    f"{worker_name} listo para siguiente tarea. Cola: aprox. {self.message_queue.qsize()} pendientes"
                )

    def _file_send_worker(self):
        """Procesa envíos de archivos de la cola"""
        worker_name = threading.current_thread().name
        logger.info(f"Worker {worker_name} iniciado y listo para enviar archivos")

        while True:
            try:
                task = self.file_send_queue.get()
                user_to = task["user_to"]
                file_path = task["file_path"]

                logger.info(
                    f"{worker_name} procesando envío de archivo '{file_path}' a {user_to}"
                )

                start_time = time.time()

                # Verificar si podemos iniciar una nueva transferencia o debemos esperar
                with self._transfers_lock:
                    if self.active_file_transfers >= self.max_concurrent_transfers:
                        logger.warning(
                            f"{worker_name} alcanzó límite de transferencias concurrentes ({self.max_concurrent_transfers})"
                        )
                        # Volver a poner la tarea en la cola y esperar
                        self.file_send_queue.put(task)
                        time.sleep(1)  # Esperar antes de intentar de nuevo
                        self.file_send_queue.task_done()  # Marcar como completada la tarea actual
                        continue

                    # Incrementar contador de transferencias activas
                    self.active_file_transfers += 1
                    logger.info(
                        f"{worker_name} inicia transferencia ({self.active_file_transfers}/{self.max_concurrent_transfers} activas)"
                    )

                try:
                    # Intentar enviar el archivo
                    success = self._send_file(user_to, file_path)

                    # Notificar el resultado
                    if success:
                        logger.info(
                            f"{worker_name} archivo enviado exitosamente a {user_to}"
                        )
                        # Notificar a los callbacks de progreso que se completó
                        with self._callback_lock:
                            for callback in self.file_progress_callbacks:
                                callback(
                                    user_to, file_path, 100, "completado"
                                )  # 100% completado
                    else:
                        logger.error(
                            f"{worker_name} error enviando archivo a {user_to}"
                        )
                        # Notificar a los callbacks de progreso que falló
                        with self._callback_lock:
                            for callback in self.file_progress_callbacks:
                                callback(
                                    user_to, file_path, -1, "error"
                                )  # -1 indica error

                finally:
                    # Siempre decrementar el contador de transferencias activas
                    with self._transfers_lock:
                        self.active_file_transfers -= 1
                        logger.info(
                            f"{worker_name} finaliza transferencia ({self.active_file_transfers}/{self.max_concurrent_transfers} activas)"
                        )

                process_time = time.time() - start_time
                logger.info(
                    f"{worker_name} completó procesamiento en {process_time:.3f} segundos"
                )

            except Exception as e:
                logger.error(f"{worker_name} error: {e}", exc_info=True)
            finally:
                self.file_send_queue.task_done()
                logger.debug(
                    f"{worker_name} listo para siguiente tarea. Cola: aprox. {self.file_send_queue.qsize()} pendientes"
                )

    def get_resource_stats(self):
        """Devuelve estadísticas sobre recursos actuales y uso del sistema"""
        # Obtener recursos disponibles actualizados
        resources = get_available_resources()

        stats = {
            "mensaje_workers": {
                "total": self.message_workers_count,
                "recomendados": int(
                    resources["cpu_count"]
                    * 3.0
                    * max(
                        0.5,
                        min(
                            1.0,
                            1.0
                            - (resources["system_load"] / resources["cpu_count"] / 2),
                        ),
                    )
                ),
            },
            "archivo_workers": {
                "total": self.file_workers_count,
                "recomendados": int(
                    resources["cpu_count"]
                    * 1.5
                    * max(
                        0.5,
                        min(
                            1.0,
                            1.0
                            - (resources["system_load"] / resources["cpu_count"] / 2),
                        ),
                    )
                ),
            },
            "transferencias": {
                "activas": self.active_file_transfers,
                "max_permitidas": self.max_concurrent_transfers,
                "porcentaje_uso": (
                    round(
                        (self.active_file_transfers / self.max_concurrent_transfers)
                        * 100,
                        1,
                    )
                    if self.max_concurrent_transfers > 0
                    else 0
                ),
            },
            "colas": {
                "mensajes_pendientes": self.message_queue.qsize(),
                "archivos_pendientes": self.file_send_queue.qsize(),
            },
            "peers": {
                "conectados": len(self.peers),
                "lista": list(self.peers.keys()),
            },
            "sistema": resources,
        }

        return stats

    def send_message(self, user_to, message):
        """Envía un mensaje a otro peer"""
        logger.info(f"Intentando enviar mensaje a '{user_to}': {message[:50]}...")

        with self._peers_lock:
            if user_to not in self.peers:
                logger.error(
                    f"No se puede enviar mensaje: peer '{user_to}' no encontrado"
                )
                return False
            peer_addr = (self.peers[user_to][0], 9990)
            logger.info(f"Peer '{user_to}' encontrado en {peer_addr[0]}:{peer_addr[1]}")

        message_id = int(time.time() * 1000) % 256  # BodyId único
        message_bytes = message.encode("utf-8")
        expected_user_id = user_to.encode("utf-8").ljust(20)[:20]

        logger.info(
            f"Enviando mensaje a {user_to} (message_id: {message_id}, tamaño: {len(message_bytes)} bytes)"
        )

        # Obtener o crear lock específico para este usuario
        with self._conversation_locks_lock:
            if user_to not in self._conversation_locks:
                logger.debug(
                    f"Creando nuevo lock de conversación para envío a {user_to}"
                )
                self._conversation_locks[user_to] = threading.Lock()
            user_lock = self._conversation_locks[user_to]

        # Usar el lock específico para conversaciones con este usuario
        with user_lock:
            logger.debug(f"Adquirido lock de conversación para envío a {user_to}")
            try:
                # Fase 1: Enviar header
                header = self._build_header(
                    user_to, MESSAGE, message_id, len(message_bytes)
                )
                logger.info(
                    f"FASE 1: Enviando header LCP a {peer_addr[0]}:{peer_addr[1]}"
                )

                with self._udp_socket_lock:
                    self.udp_socket.sendto(header, peer_addr)
                    logger.debug(f"Header enviado, esperando respuesta (timeout: 5s)")
                    self.udp_socket.settimeout(5)
                    resp_data, resp_addr = self.udp_socket.recvfrom(25)
                    logger.debug(
                        f"Respuesta recibida desde {resp_addr[0]}:{resp_addr[1]} ({len(resp_data)} bytes)"
                    )

                # Verificar identidad
                if resp_addr[0] != peer_addr[0] or resp_data[1:21] != expected_user_id:
                    logger.warning(
                        f"Identidad no verificada en respuesta. Esperada: {user_to}, IP: {peer_addr[0]}"
                    )
                    return False

                if resp_data[0] != 0:  # ResponseStatus != OK
                    logger.error(f"Respuesta negativa recibida: status={resp_data[0]}")
                    return False

                logger.info(f"FASE 1 completada: header aceptado por {user_to}")

                # Fase 2: Enviar cuerpo del mensaje
                body = message_id.to_bytes(8, "big") + message_bytes
                logger.info(
                    f"FASE 2: Enviando cuerpo del mensaje a {peer_addr[0]}:{peer_addr[1]} ({len(body)} bytes)"
                )

                with self._udp_socket_lock:
                    self.udp_socket.sendto(body, peer_addr)
                    logger.debug(
                        f"Cuerpo enviado, esperando confirmación final (timeout: 5s)"
                    )
                    resp_data, resp_addr = self.udp_socket.recvfrom(25)
                    logger.debug(
                        f"Confirmación recibida desde {resp_addr[0]}:{resp_addr[1]}"
                    )

                # Verificar nuevamente identidad
                if resp_addr[0] != peer_addr[0] or resp_data[1:21] != expected_user_id:
                    logger.warning(f"Identidad no verificada en confirmación final")
                    return False

                if resp_data[0] == 0:
                    logger.info(
                        f"FASE 2 completada: mensaje entregado exitosamente a {user_to}"
                    )
                else:
                    logger.error(f"Error en confirmación final: status={resp_data[0]}")

                return resp_data[0] == 0

            except socket.timeout:
                logger.error(f"Timeout esperando respuesta de {user_to}")
                return False
            except Exception as e:
                logger.error(f"Error enviando mensaje a {user_to}: {e}", exc_info=True)
                return False
            finally:
                self.udp_socket.settimeout(None)
                logger.debug(f"Socket UDP restaurado a modo no bloqueante")

    def send_file(self, user_to, file_path):
        """Envía un archivo a otro peer"""
        logger.info(f"Intentando enviar archivo '{file_path}' a '{user_to}'")

        if user_to not in self.peers:
            logger.error(f"No se puede enviar archivo: peer '{user_to}' no encontrado")
            return False

        if not os.path.exists(file_path):
            logger.error(f"No se puede enviar archivo: '{file_path}' no existe")
            return False

        self.file_send_queue.put({"user_to": user_to, "file_path": file_path})
        logger.info(f"Archivo '{file_path}' añadido a la cola de envío")
        return True

    def _send_file(self, user_to, file_path):
        """Realiza el envío de un archivo a otro peer"""
        file_id = int(time.time() * 1000) % 256  # BodyId único
        file_size = os.path.getsize(file_path)
        peer_addr = (self.peers[user_to][0], 9990)
        worker_name = threading.current_thread().name

        # Notificar inicio de transferencia
        with self._callback_lock:
            for callback in self.file_progress_callbacks:
                callback(user_to, file_path, 0, "iniciando")

        logger.info(
            f"{worker_name} enviando archivo a {user_to}: '{file_path}' (file_id: {file_id}, tamaño: {file_size} bytes)"
        )

        try:
            # Fase 1: Enviar header por UDP
            header = self._build_header(user_to, 2, file_id, file_size)
            logger.info(
                f"{worker_name} FASE 1: Enviando header de archivo a {peer_addr[0]}:{peer_addr[1]}"
            )
            with self._udp_socket_lock:
                self.udp_socket.sendto(header, peer_addr)

                # Esperar confirmación de header
                logger.debug(
                    f"{worker_name} Header enviado, esperando confirmación (timeout: 5s)"
                )
                self.udp_socket.settimeout(5)
                resp_data, resp_addr = self.udp_socket.recvfrom(25)

            if resp_data[0] != 0:
                logger.error(
                    f"{worker_name} Confirmación de header rechazada: status={resp_data[0]}"
                )
                return False

            logger.info(
                f"{worker_name} FASE 1 completada: header de archivo aceptado por {user_to}"
            )

            # Fase 2: Enviar archivo por TCP
            logger.info(
                f"{worker_name} FASE 2: Iniciando transferencia TCP con {peer_addr[0]}:{peer_addr[1]}"
            )
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                logger.debug(
                    f"{worker_name} Conectando a {peer_addr[0]}:{peer_addr[1]} para transferencia de archivo"
                )
                s.connect((self.peers[user_to][0], 9990))

                # Enviar identificador de archivo
                logger.debug(
                    f"{worker_name} Enviando identificador de archivo: {file_id}"
                )
                s.send(file_id.to_bytes(8, "big"))

                # Transferir contenido del archivo
                bytes_enviados = 0
                with open(file_path, "rb") as f:
                    logger.info(
                        f"{worker_name} Iniciando transferencia de datos del archivo"
                    )
                    last_progress_update = 0

                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        s.send(chunk)
                        bytes_enviados += len(chunk)

                        # Calcular y reportar progreso en intervalos
                        if file_size > 0:  # Evitar división por cero
                            progress = min(100, int((bytes_enviados * 100) / file_size))

                            # Actualizar progreso cada 5% o cuando alcance 1MB más
                            if (progress - last_progress_update >= 5) or (
                                bytes_enviados % (1024 * 1024) < 4096
                            ):
                                last_progress_update = progress
                                logger.info(
                                    f"{worker_name} Progreso: {bytes_enviados/1024:.1f} KB ({progress}%) enviados a {user_to}"
                                )

                                # Notificar a los callbacks de progreso
                                with self._callback_lock:
                                    for callback in self.file_progress_callbacks:
                                        callback(
                                            user_to, file_path, progress, "progreso"
                                        )

                logger.info(
                    f"{worker_name} Transferencia completa: {bytes_enviados} bytes enviados a {user_to}"
                )

                # Esperar confirmación final
                logger.debug(
                    f"{worker_name} Esperando confirmación final de transferencia"
                )
                resp_data = s.recv(25)

                if resp_data[0] == 0:
                    logger.info(
                        f"{worker_name} FASE 2 completada: archivo entregado exitosamente a {user_to}"
                    )
                    return True
                else:
                    logger.error(
                        f"{worker_name} Error en confirmación final de archivo: status={resp_data[0]}"
                    )
                    return False

        except socket.timeout:
            logger.error(f"{worker_name} Timeout esperando respuesta de {user_to}")
            return False
        except ConnectionError as e:
            logger.error(f"{worker_name} Error de conexión con {user_to}: {e}")
            return False
        except Exception as e:
            logger.error(
                f"{worker_name} Error enviando archivo a {user_to}: {e}", exc_info=True
            )
            return False
        finally:
            self.udp_socket.settimeout(None)
            logger.debug(f"{worker_name} Socket UDP restaurado a modo no bloqueante")

    def register_message_callback(self, callback):
        """Registra una función para recibir mensajes"""
        self.message_callbacks.append(callback)

    def register_file_callback(self, callback):
        """Registra una función para recibir archivos"""
        self.file_callbacks.append(callback)

    def register_peer_discovery_callback(self, callback):
        """Registra una función para notificar cambios en pares"""
        self.peer_discovery_callbacks.append(callback)

    def register_file_progress_callback(self, callback):
        """Registra una función para recibir actualizaciones del progreso de transferencias de archivos.
        El callback debe aceptar (user_id, file_path, progress, status) donde:
        - user_id: ID del usuario remoto
        - file_path: ruta del archivo
        - progress: porcentaje de progreso (0-100) o -1 si hay error
        - status: cadena con el estado ('iniciando', 'progreso', 'completado', 'error')
        """
        self.file_progress_callbacks.append(callback)

    def get_peers(self):
        """Devuelve la lista de pares conocidos"""
        return list(self.peers.keys())

    def close(self):
        """Cierra las conexiones"""
        self.udp_socket.close()
        self.tcp_socket.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 main.py <nombre_usuario>")
        sys.exit(1)

    peer = LCPPeer(sys.argv[1])

    def on_message(user_from, message):
        print(f"\n[MSG de {user_from}]: {message}")

    def on_file(user_from, file_path):
        print(f"\n[ARCHIVO de {user_from}]: Recibido '{file_path}'")

    def on_peer_change(user_id, added):
        action = "Conectado" if added else "Desconectado"
        print(f"\n[PAIR] {action}: {user_id}")
        print("Pares conocidos:", ", ".join(peer.get_peers()) or "Ninguno")

    def on_file_progress(user_id, file_path, progress, status):
        if status == "iniciando":
            print(
                f"\n[ARCHIVO para {user_id}]: Iniciando envío de '{os.path.basename(file_path)}'"
            )
        elif status == "progreso":
            print(
                f"\n[ARCHIVO para {user_id}]: Progreso {progress}% de '{os.path.basename(file_path)}'"
            )
        elif status == "completado":
            print(
                f"\n[ARCHIVO para {user_id}]: Envío completado de '{os.path.basename(file_path)}'"
            )
        elif status == "error":
            print(
                f"\n[ARCHIVO para {user_id}]: ERROR en envío de '{os.path.basename(file_path)}'"
            )

    peer.register_message_callback(on_message)
    peer.register_file_callback(on_file)
    peer.register_peer_discovery_callback(on_peer_change)
    peer.register_file_progress_callback(on_file_progress)

    print(f"\nChat LCP iniciado como '{sys.argv[1]}'")
    print("Pares conocidos:", ", ".join(peer.get_peers()) or "Ninguno")
    print("\nComandos disponibles:")
    print("  msg <usuario> <mensaje> - Enviar mensaje")
    print("  file <usuario> <ruta>   - Enviar archivo")
    print("  list                    - Listar pares")
    print("  stats                   - Mostrar estadísticas de recursos")
    print("  exit                    - Salir")

    try:
        while True:
            try:
                cmd = input("\n> ").strip()
                if not cmd:
                    continue

                if cmd.startswith("msg "):
                    parts = cmd.split(maxsplit=2)
                    if len(parts) == 3:
                        if peer.send_message(parts[1], parts[2]):
                            print("Mensaje enviado")
                        else:
                            print("Error al enviar mensaje")
                    else:
                        print("Formato: msg <usuario> <mensaje>")

                elif cmd.startswith("file "):
                    parts = cmd.split(maxsplit=2)
                    if len(parts) == 3:
                        if peer.send_file(parts[1], parts[2]):
                            print("Archivo enviado")
                        else:
                            print("Error al enviar archivo")
                    else:
                        print("Formato: file <usuario> <ruta_archivo>")

                elif cmd == "list":
                    print("Pares conocidos:")
                    print("\n".join(peer.get_peers()) or "Ninguno")

                elif cmd == "stats":
                    stats = peer.get_resource_stats()
                    print("\n=== Estadísticas del Sistema ===")

                    # Información del sistema
                    print("\n[Sistema]")
                    print(f"Sistema Operativo: {stats['sistema']['platform']}")
                    print(f"CPUs lógicas: {stats['sistema']['cpu_count']}")
                    print(f"Memoria total: {stats['sistema']['memory_gb']:.2f} GB")
                    print(
                        f"Memoria disponible: {stats['sistema']['memory_available_gb']:.2f} GB ({(stats['sistema']['memory_available_gb']/stats['sistema']['memory_gb']*100):.1f}%)"
                    )
                    print(f"Carga del sistema: {stats['sistema']['system_load']:.2f}")

                    # Workers y colas
                    print("\n[Workers]")
                    print(
                        f"Workers para mensajes: {stats['mensaje_workers']['total']} (óptimo según carga actual: {stats['mensaje_workers']['recomendados']})"
                    )
                    print(
                        f"Workers para archivos: {stats['archivo_workers']['total']} (óptimo según carga actual: {stats['archivo_workers']['recomendados']})"
                    )

                    # Transferencias activas
                    print("\n[Transferencias]")
                    print(f"Activas: {stats['transferencias']['activas']}")
                    print(f"Límite: {stats['transferencias']['max_permitidas']}")
                    print(f"Uso: {stats['transferencias']['porcentaje_uso']}%")

                    # Estado de las colas
                    print("\n[Colas]")
                    print(
                        f"Mensajes pendientes: {stats['colas']['mensajes_pendientes']}"
                    )
                    print(
                        f"Archivos pendientes: {stats['colas']['archivos_pendientes']}"
                    )

                    # Peers conectados
                    print("\n[Peers]")
                    print(f"Conectados: {stats['peers']['conectados']}")
                    if stats["peers"]["conectados"] > 0:
                        print("Lista: " + ", ".join(stats["peers"]["lista"]))

                elif cmd == "exit":
                    break

            except KeyboardInterrupt:
                print("\nUsa 'exit' para salir")
                continue

    finally:
        print("\nChat LCP terminado")
