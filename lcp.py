import asyncio
import uuid
import socket
import struct
import select
from typing import Tuple, Dict, Set, Optional, List
import time

# Importar módulos del proyecto
from protocol import (
    TCP_PORT,
    UDP_PORT,
    BROADCAST_ID,
    HEADER_FORMAT,
    HEADER_SIZE,
    RESPONSE_FORMAT,
    RESPONSE_OK,
    RESPONSE_SIZE,
    FILE,
    MESSAGE,
    ECHO,
    LOG_FILE,
)
from utils.logging import get_module_logger
from utils.network import get_broadcast_addresses

# Importar los módulos de core
from core.messaging import MessageHandler
from core.discovery import DiscoveryService
from core.files import FileTransferHandler
from core.groups import GroupManager

# Importar los módulos de storage
from storage.history import HistoryManager


class LCPProtocol:
    """
    Implementación del protocolo LCP (Local Chat Protocol)
    """

    def __init__(self, username: str):
        """Inicializa el protocolo LCP"""
        self.username = username
        self.user_id = self._generate_user_id(username)

        # Constantes de protocolo importadas para acceso en módulos
        self.TCP_PORT = TCP_PORT
        self.UDP_PORT = UDP_PORT
        self.BROADCAST_ID = BROADCAST_ID
        self.HEADER_SIZE = HEADER_SIZE
        self.RESPONSE_SIZE = RESPONSE_SIZE
        self.RESPONSE_OK = RESPONSE_OK
        self.MESSAGE = MESSAGE
        self.FILE = FILE
        self.ECHO = ECHO

        # Direcciones de broadcast
        self.BROADCAST_ADDR = get_broadcast_addresses()

        # Estado
        self.known_users: Dict[str, Tuple[str, int]] = {}  # user_id -> (ip, port)
        self.running = False

        # Sockets y tareas
        self.udp_socket = None
        self.tcp_server = None
        self.udp_listener_task = None

        # Bloqueo para el socket UDP
        self.udp_lock = asyncio.Lock()

        # Configurar logger
        self.logger = get_module_logger(f"LCP-{username}")

        # Callbacks
        self.message_callbacks = []
        self.file_callbacks = []

        # Inicializar componentes
        self.messaging = MessageHandler(self)
        self.discovery = DiscoveryService(self)
        self.files = FileTransferHandler(self)
        self.groups = GroupManager(self)
        self.storage = HistoryManager(self)

    def _generate_user_id(self, username: str) -> str:
        """Genera un ID de usuario válido según el protocolo"""
        user_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, username)).replace("-", "")[:20]
        return user_uuid.ljust(20, "\0")[:20]

    def _pack_header(
        self, user_to: str, op_code: int, body_id: int = 0, body_length: int = 0
    ) -> bytes:
        """Empaqueta el encabezado según el protocolo"""
        user_from = self.user_id.encode("utf-8").ljust(20, b"\0")[:20]

        if user_to.lower() == "broadcast":
            # Asegurarse de que BROADCAST_ID sea bytes y no string
            user_to = (
                BROADCAST_ID.encode("utf-8")
                if isinstance(BROADCAST_ID, str)
                else BROADCAST_ID
            )
        else:
            user_to = user_to.encode("utf-8").ljust(20, b"\0")[:20]

        reserved = b"\x00" * 50
        return struct.pack(
            HEADER_FORMAT, user_from, user_to, op_code, body_id, body_length, reserved
        )

    def _unpack_header(self, data: bytes) -> Tuple[str, str, int, int, int]:
        """Desempaqueta el encabezado según el protocolo"""
        user_from, user_to, op_code, body_id, body_length, _ = struct.unpack(
            HEADER_FORMAT, data
        )
        # Manejo más robusto de la decodificación
        try:
            user_from_str = user_from.rstrip(b"\x00").decode("utf-8", errors="replace")
            user_to_str = user_to.rstrip(b"\x00").decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            self.logger.warning(
                "Problema decodificando encabezado, usando valores seguros"
            )
            user_from_str = user_from.rstrip(b"\x00").decode(
                "latin1"
            )  # Fallback seguro
            user_to_str = user_to.rstrip(b"\x00").decode("latin1")  # Fallback seguro

        return (
            user_from_str,
            user_to_str,
            op_code,
            body_id,
            body_length,
        )

    def _pack_response(self, status: int, responder_id: Optional[str] = None) -> bytes:
        """Empaqueta una respuesta según el protocolo"""
        if responder_id is None:
            responder_id = self.user_id
        responder_id = responder_id.encode("utf-8").ljust(20, b"\0")[:20]
        reserved = b"\x00" * 4
        return struct.pack(RESPONSE_FORMAT, status, responder_id, reserved)

    def _unpack_response(self, data: bytes) -> Tuple[int, str]:
        """Desempaqueta una respuesta según el protocolo"""
        status, responder_id, _ = struct.unpack(RESPONSE_FORMAT, data)
        return status, responder_id.rstrip(b"\x00").decode()

    async def start(self):
        """Inicia el protocolo: configura sockets y servicios"""
        self.running = True

        # Configurar socket UDP
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.bind(("0.0.0.0", UDP_PORT))
        self.logger.info(f"Socket UDP configurado en puerto {UDP_PORT}")

        # Configurar servidor TCP
        self.tcp_server = await asyncio.start_server(
            self._handle_tcp_connection, "0.0.0.0", TCP_PORT
        )
        self.logger.info(f"Servidor TCP configurado en puerto {TCP_PORT}")

        self.logger.info(
            f"Iniciado LCP para usuario {self.username} (ID: {self.user_id})"
        )
        self.logger.info(f"Escuchando en UDP/{UDP_PORT} y TCP/{TCP_PORT}")

        # Cargar historial
        await self.storage.load_history_from_file()

        # Iniciar tareas en segundo plano
        self.udp_listener_task = asyncio.create_task(self._safe_udp_listener())

        # Iniciar descubrimiento
        await self.discovery.start()

    async def stop(self):
        """Detiene el protocolo y libera recursos"""
        if not self.running:
            return

        self.logger.info("Iniciando proceso de detención...")
        self.running = False

        # Guardar historial antes de detener
        await self.storage.save_history_to_file()

        # Detener descubrimiento
        await self.discovery.stop()

        # Cancelar tareas
        if self.udp_listener_task:
            self.udp_listener_task.cancel()

        # Cerrar sockets
        if self.udp_socket:
            self.udp_socket.close()
            self.logger.info("Socket UDP cerrado")
        if self.tcp_server:
            self.tcp_server.close()
            await self.tcp_server.wait_closed()
            self.logger.info("Servidor TCP cerrado")

        self.logger.info("Protocolo LCP detenido completamente")

    async def _safe_udp_listener(self):
        """Wrapper seguro para el listener UDP"""
        try:
            await self._udp_listener()
        except Exception as e:
            self.logger.error(f"Error crítico en UDP listener: {e}", exc_info=True)
            await self.stop()

    async def _udp_listener(self):
        """Escucha mensajes UDP entrantes"""
        self.logger.info("Escuchador UDP iniciado")

        # Configurar socket en modo no bloqueante
        self.udp_socket.setblocking(False)

        while self.running:
            try:
                self.logger.debug("Esperando mensajes UDP...")
                # Usar select para no bloquear
                ready, _, _ = select.select([self.udp_socket], [], [], 0.1)
                if ready:
                    data, addr = self.udp_socket.recvfrom(1024)
                    self.logger.debug(
                        f"Mensaje UDP recibido de {addr}, tamaño: {len(data)} bytes"
                    )
                    await self._handle_udp_message(data, addr)
                else:
                    # Dar tiempo para otras tareas
                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                self.logger.info("UDP listener cancelado")
                break
            except Exception as e:
                self.logger.error(f"Error en UDP listener: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _handle_tcp_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Maneja conexiones TCP entrantes para transferencia de archivos"""
        addr = writer.get_extra_info("peername")
        self.logger.info(f"Nueva conexión TCP establecida desde {addr}")

        try:
            # Leer los primeros 100 bytes (deberían ser el header)
            self.logger.debug("Leyendo cabecera TCP...")
            header_data = await reader.read(HEADER_SIZE)
            if len(header_data) < HEADER_SIZE:
                self.logger.error(
                    f"Cabecera TCP incompleta, recibido: {len(header_data)} bytes"
                )
                return

            user_from, user_to, op_code, body_id, body_length = self._unpack_header(
                header_data
            )
            self.logger.debug(
                f"Header TCP recibido - De: {user_from}, Para: {user_to}, "
                f"Operación: {op_code}, Body ID: {body_id}, Tamaño: {body_length}"
            )

            if op_code == FILE:
                self.logger.info("Operación de archivo detectada")
                # Leer el primer byte (ID del archivo)
                file_id_data = await reader.read(1)
                if len(file_id_data) < 1:
                    self.logger.error(
                        f"ID de archivo incompleto, recibido: {len(file_id_data)} bytes"
                    )
                    return

                file_id = int.from_bytes(file_id_data, "big")
                remaining_bytes = body_length - 1
                self.logger.debug(
                    f"Recibiendo archivo ID: {file_id}, tamaño restante: {remaining_bytes} bytes"
                )

                # Leer el resto del archivo
                file_data = await reader.read(remaining_bytes)
                if len(file_data) < remaining_bytes:
                    self.logger.error(
                        f"Datos de archivo incompletos, recibido: {len(file_data)} bytes"
                    )
                    return

                self.logger.info(
                    f"Archivo recibido completo - ID: {file_id}, Tamaño: {len(file_data)} bytes"
                )

                # Notificar a los callbacks
                for callback in self.file_callbacks:
                    await callback(user_from, file_id, file_data)

                # Enviar confirmación
                response = self._pack_response(RESPONSE_OK)
                writer.write(response)
                await writer.drain()
                self.logger.debug("Confirmación de archivo enviada")

        except Exception as e:
            self.logger.error(f"Error en conexión TCP: {e}", exc_info=True)
        finally:
            writer.close()
            await writer.wait_closed()
            self.logger.info(f"Conexión TCP con {addr} cerrada")

    async def _handle_udp_message(self, data: bytes, addr: Tuple[str, int]):
        """Procesa un mensaje UDP recibido"""
        try:
            self.logger.debug(f"Procesando mensaje UDP de {addr}")

            if len(data) < HEADER_SIZE:
                self.logger.warning(f"Mensaje UDP demasiado corto: {len(data)} bytes")
                return

            user_from, user_to, op_code, body_id, body_length = self._unpack_header(
                data
            )
            self.logger.debug(
                f"Header UDP - De: {user_from}, Para: {user_to}, "
                f"Operación: {op_code}, Body ID: {body_id}, Tamaño: {body_length}"
            )

            # Actualizar lista de usuarios conocidos
            if user_from != self.user_id:
                self.known_users[user_from] = addr
                self.logger.info(f"Usuario descubierto: {user_from} en {addr}")

            if op_code == ECHO:
                self.logger.debug(f"Mensaje ECHO recibido de {user_from}")
                # Responder al echo
                if user_to == BROADCAST_ID or user_to == self.user_id:
                    self.logger.debug("Respondiendo a ECHO...")
                    response = self._pack_response(RESPONSE_OK)
                    await self._send_udp(response, addr)
                    self.logger.debug("Respuesta ECHO enviada")

            elif op_code == MESSAGE:
                self.logger.debug(f"Mensaje recibido de {user_from}")
                # Verificar si el mensaje es para nosotros o broadcast
                if user_to == "broadcast" or user_to == self.user_id:
                    self.logger.debug(
                        "Mensaje destinado a nosotros, confirmando recepción..."
                    )
                    # Confirmar recepción del encabezado
                    response = self._pack_response(RESPONSE_OK)
                    await self._send_udp(response, addr)
                    self.logger.debug("Confirmación de encabezado enviada")

                    # Esperar el cuerpo del mensaje
                    self.logger.debug(
                        f"Esperando cuerpo del mensaje ({body_length} bytes)..."
                    )
                    body_data = await self._receive_udp_with_timeout(addr, body_length)
                    if body_data and len(body_data) == body_length:
                        message_id = int.from_bytes(body_data[:1], "big")
                        message_content = body_data[1:].decode("utf-8")
                        self.logger.info(
                            f"Mensaje completo recibido - ID: {message_id}, Contenido: {message_content}"
                        )

                        # Notificar a los callbacks
                        for callback in self.message_callbacks:
                            await callback(user_from, message_content)

                        # Guardar mensaje en historial
                        await self.storage.save_message_to_history(
                            user_from, False, message_content
                        )

                        # Confirmar recepción del mensaje
                        final_response = self._pack_response(RESPONSE_OK)
                        await self._send_udp(final_response, addr)
                        self.logger.debug("Confirmación final de mensaje enviada")
                    else:
                        self.logger.error(
                            f"No se recibió el cuerpo del mensaje correctamente. Recibido: {len(body_data) if body_data else 0} bytes"
                        )

        except Exception as e:
            self.logger.error(f"Error al procesar mensaje UDP: {e}", exc_info=True)

    async def _send_udp(self, data: bytes, addr: Tuple[str, int]):
        """Envía datos por UDP con protección de concurrencia"""
        self.logger.debug(f"Enviando datos UDP a {addr}, tamaño: {len(data)} bytes")

        async with self.udp_lock:  # Proteger el acceso al socket
            loop = asyncio.get_event_loop()
            try:
                await loop.sock_sendto(self.udp_socket, data, addr)
                self.logger.debug("Datos UDP enviados exitosamente")
            except Exception as e:
                self.logger.error(f"Error al enviar por UDP: {e}", exc_info=True)
                raise

    async def _receive_udp_with_timeout(
        self, expected_addr: Tuple[str, int], expected_length: int, timeout: int = 5
    ) -> Optional[bytes]:
        """Espera un mensaje UDP específico con timeout"""
        self.logger.debug(
            f"Esperando mensaje UDP de {expected_addr}, tamaño esperado: {expected_length} bytes"
        )
        loop = asyncio.get_event_loop()
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Comprobar si hay datos disponibles sin bloquear
                data, addr = await loop.sock_recvfrom(
                    self.udp_socket, expected_length + 1024
                )
                self.logger.debug(
                    f"Datos UDP recibidos durante espera: {len(data)} bytes de {addr}"
                )

                if addr == expected_addr and len(data) == expected_length:
                    self.logger.debug("Mensaje esperado recibido correctamente")
                    return data
                else:
                    self.logger.debug("Mensaje recibido no coincide con lo esperado")
            except BlockingIOError:
                await asyncio.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Error al recibir UDP: {e}", exc_info=True)
                return None

        self.logger.warning(
            f"Tiempo de espera agotado para mensaje UDP de {expected_addr}"
        )
        return None

    # Métodos públicos que redirigen a los componentes correspondientes

    # Métodos de mensajería
    async def send_message(self, user_to: str, message: str):
        return await self.messaging.send_message(user_to, message)

    # Métodos de archivos
    async def send_file(self, user_to: str, file_data: bytes):
        return await self.files.send_file(user_to, file_data)

    # Métodos de grupos
    async def create_group(self, group_name: str):
        return await self.groups.create_group(group_name)

    async def invite_to_group(self, group_name: str, user_id: str):
        return await self.groups.invite_to_group(group_name, user_id)

    async def join_group(self, group_name: str):
        return await self.groups.join_group(group_name)

    async def send_group_message(self, group_name: str, message: str):
        return await self.groups.send_group_message(group_name, message)

    # Métodos de callbacks
    def add_message_callback(self, callback):
        """Añade un callback para recibir mensajes"""
        self.logger.debug(f"Añadiendo callback de mensaje: {callback.__name__}")
        self.message_callbacks.append(callback)

    def add_file_callback(self, callback):
        """Añade un callback para recibir archivos"""
        self.logger.debug(f"Añadiendo callback de archivo: {callback.__name__}")
        self.file_callbacks.append(callback)
