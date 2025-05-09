import asyncio
import random
from typing import Dict, Tuple, Optional, List


class MessageHandler:
    """Maneja la lógica de envío y recepción de mensajes"""

    def __init__(self, protocol):
        """Inicializa el manejador de mensajes"""
        self.protocol = protocol
        self.logger = self.protocol.logger

    async def send_message(self, user_to: str, message: str):
        """Envía un mensaje a otro usuario o a todos (broadcast)"""
        self.logger.info(f"Iniciando envío de mensaje a {user_to}")

        # Validar el destino
        if user_to != "broadcast" and user_to not in self.protocol.known_users:
            self.logger.error(
                f"Usuario destino {user_to} no encontrado en usuarios conocidos"
            )
            return False

        message_id = random.randint(0, 255)
        message_bytes = message.encode("utf-8")

        # Empaquetar cuerpo del mensaje
        body_data = message_id.to_bytes(1, "big") + message_bytes
        body_length = len(body_data)

        self.logger.debug(
            f"ID de mensaje generado: {message_id}, tamaño total: {body_length} bytes"
        )

        # Preparar el encabezado
        header = self.protocol._pack_header(
            user_to, self.protocol.MESSAGE, message_id, body_length
        )

        # Manejar caso de broadcast
        if user_to == "broadcast":
            result = await self._send_broadcast_message(header, body_data)
        else:
            result = await self._send_direct_message(user_to, header, body_data)

        # Si es un mensaje directo y se envió correctamente, guardar en historial
        if user_to != "broadcast" and result:
            await self.protocol.storage.save_message_to_history(user_to, True, message)

        return result

    async def _send_broadcast_message(self, header, body_data):
        """Envía un mensaje a todas las direcciones de broadcast"""
        self.logger.debug("Enviando mensaje broadcast")

        # Lanzar envíos en paralelo para mayor eficiencia
        tasks = []
        for addr in self.protocol.BROADCAST_ADDR:
            dest_addr = (addr, self.protocol.UDP_PORT)
            # Crear tarea para enviar a cada dirección
            task = asyncio.create_task(
                self._send_broadcast_to_addr(dest_addr, header, body_data)
            )
            tasks.append(task)

        # Esperar a que terminen todos los envíos
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verificar resultados
        success_count = sum(1 for result in results if result is True)

        if success_count > 0:
            self.logger.info(
                f"Mensaje broadcast enviado a {success_count}/{len(self.protocol.BROADCAST_ADDR)} direcciones"
            )
            return True
        else:
            self.logger.error(
                "No se pudo enviar el mensaje broadcast a ninguna dirección"
            )
            return False

    async def _send_broadcast_to_addr(self, dest_addr, header, body_data):
        """Envía un mensaje broadcast a una dirección específica"""
        try:
            # Enviar encabezado
            await self.protocol._send_udp(header, dest_addr)
            # Pequeña pausa para evitar congestión
            await asyncio.sleep(0.1)
            # Enviar cuerpo
            await self.protocol._send_udp(body_data, dest_addr)
            return True
        except Exception as e:
            self.logger.error(f"Error enviando broadcast a {dest_addr}: {e}")
            return False

    async def _send_direct_message(self, user_to, header, body_data):
        """Envía un mensaje directo a un usuario específico con confirmación"""
        self.logger.debug(f"Enviando mensaje directo a {user_to}")
        dest_addr = self.protocol.known_users[user_to]

        # Enviar encabezado con reintentos
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                # Enviar encabezado
                await self.protocol._send_udp(header, dest_addr)

                # Esperar confirmación del encabezado
                confirmation = await self.protocol._receive_udp_with_timeout(
                    dest_addr, self.protocol.RESPONSE_SIZE, timeout=2
                )
                if not confirmation:
                    if attempt < max_retries:
                        self.logger.warning(
                            f"No se recibió confirmación, reintento {attempt}/{max_retries}"
                        )
                        continue
                    self.logger.error(
                        "No se recibió confirmación después de varios intentos"
                    )
                    return False

                # Verificar confirmación
                status, responder = self.protocol._unpack_response(confirmation)
                if status != self.protocol.RESPONSE_OK:
                    self.logger.error(
                        f"Confirmación de encabezado fallida. Estado: {status}"
                    )
                    return False

                self.logger.debug(f"Encabezado confirmado por {responder}")

                # Enviar cuerpo del mensaje
                await self.protocol._send_udp(body_data, dest_addr)

                # Esperar confirmación final
                final_confirmation = await self.protocol._receive_udp_with_timeout(
                    dest_addr, self.protocol.RESPONSE_SIZE, timeout=3
                )
                if not final_confirmation:
                    self.logger.error("No se recibió confirmación final del mensaje")
                    return False

                status, responder = self.protocol._unpack_response(final_confirmation)
                if status != self.protocol.RESPONSE_OK:
                    self.logger.error(f"Confirmación final fallida. Estado: {status}")
                    return False

                # Mensaje enviado exitosamente
                self.logger.info(f"Mensaje enviado exitosamente a {user_to}")
                return True

            except Exception as e:
                self.logger.error(f"Error en intento {attempt}: {e}")
                if attempt == max_retries:
                    return False
                await asyncio.sleep(0.5)  # Esperar antes de reintentar

        return False
