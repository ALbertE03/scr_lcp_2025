import asyncio
import random
from typing import Tuple, Dict, Optional


class FileTransferHandler:
    """Maneja la transferencia de archivos entre usuarios"""

    def __init__(self, protocol):
        """Inicializa el manejador de transferencia de archivos"""
        self.protocol = protocol
        self.logger = self.protocol.logger

    async def send_file(self, user_to: str, file_data: bytes):
        """Envía un archivo a otro usuario"""
        self.logger.info(f"Iniciando envío de archivo a {user_to}")

        if user_to not in self.protocol.known_users:
            self.logger.error(
                f"Usuario destino {user_to} no encontrado en usuarios conocidos"
            )
            return False

        # Generar ID único para el archivo (1 byte: 0-255)
        file_id = random.randint(0, 255)
        body_length = 1 + len(file_data)  # 1 byte para el ID + archivo
        self.logger.debug(
            f"ID de archivo generado: {file_id}, tamaño total: {body_length} bytes"
        )

        # Enviar encabezado por UDP
        self.logger.debug("Enviando encabezado de archivo por UDP...")
        header = self.protocol._pack_header(
            user_to, self.protocol.FILE, file_id, body_length
        )
        await self.protocol._send_udp(header, self.protocol.known_users[user_to])

        # Esperar confirmación del encabezado
        self.logger.debug("Esperando confirmación de encabezado de archivo...")
        confirmation = await self.protocol._receive_udp_with_timeout(
            self.protocol.known_users[user_to], self.protocol.RESPONSE_SIZE
        )
        if not confirmation:
            self.logger.error(
                "No se recibió confirmación del encabezado de archivo (tiempo de espera agotado)"
            )
            return False

        status, responder = self.protocol._unpack_response(confirmation)
        if status != self.protocol.RESPONSE_OK:
            self.logger.error(
                f"Confirmación de encabezado fallida. Estado: {status}, Respondedor: {responder}"
            )
            return False

        self.logger.debug(f"Encabezado de archivo confirmado por {responder}")

        # Establecer conexión TCP para enviar el archivo
        return await self._transfer_file_tcp(user_to, header, file_id, file_data)

    async def _transfer_file_tcp(
        self, user_to: str, header: bytes, file_id: int, file_data: bytes
    ):
        """Realiza la transferencia TCP del archivo"""
        self.logger.debug("Estableciendo conexión TCP...")
        try:
            reader, writer = await asyncio.open_connection(
                self.protocol.known_users[user_to][0], self.protocol.TCP_PORT
            )
            self.logger.info(
                f"Conexión TCP establecida con {self.protocol.known_users[user_to]}"
            )

            # Enviar encabezado nuevamente por TCP (según protocolo)
            self.logger.debug("Enviando encabezado por TCP...")
            writer.write(header)
            await writer.drain()

            # Enviar datos del archivo
            self.logger.debug("Enviando datos del archivo...")
            writer.write(file_id.to_bytes(1, "big"))
            writer.write(file_data)
            await writer.drain()
            self.logger.debug("Datos del archivo enviados")

            # Esperar confirmación
            self.logger.debug("Esperando confirmación de recepción...")
            confirmation_data = await reader.read(self.protocol.RESPONSE_SIZE)
            if len(confirmation_data) < self.protocol.RESPONSE_SIZE:
                self.logger.error(
                    f"Confirmación incompleta, recibido: {len(confirmation_data)} bytes"
                )
                return False

            status, responder = self.protocol._unpack_response(confirmation_data)
            if status != self.protocol.RESPONSE_OK:
                self.logger.error(
                    f"Confirmación fallida. Estado: {status}, Respondedor: {responder}"
                )
                return False

            self.logger.info(
                f"Archivo enviado exitosamente a {user_to}, confirmado por {responder}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error al enviar archivo: {e}", exc_info=True)
            return False
        finally:
            if "writer" in locals():
                writer.close()
                await writer.wait_closed()
                self.logger.debug("Conexión TCP cerrada")
