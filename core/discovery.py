import asyncio


class DiscoveryService:
    """Maneja el descubrimiento y mantención de usuarios en la red"""

    def __init__(self, protocol):
        """Inicializa el servicio de descubrimiento"""
        self.protocol = protocol
        self.logger = self.protocol.logger
        self.discovery_loop_task = None

    async def start(self):
        """Inicia el servicio de descubrimiento"""
        self.discovery_loop_task = asyncio.create_task(self._safe_discovery_loop())

    async def stop(self):
        """Detiene el servicio de descubrimiento"""
        if self.discovery_loop_task:
            self.discovery_loop_task.cancel()

    async def _safe_discovery_loop(self):
        """Wrapper seguro para el loop de descubrimiento"""
        try:
            await self._discovery_loop()
        except Exception as e:
            self.logger.error(f"Error crítico en discovery loop: {e}", exc_info=True)

    async def _discovery_loop(self):
        """Envía periódicamente mensajes de descubrimiento"""
        self.logger.info("Bucle de descubrimiento iniciado")
        initial_delay = 1  # Esperar 1 segundo antes del primer envío

        while self.protocol.running:
            try:
                await asyncio.sleep(initial_delay)
                initial_delay = 0  # Solo esperar al inicio

                self.logger.info("Enviando mensaje de descubrimiento (echo)...")
                await self.send_echo()
                self.logger.info(
                    f"Usuarios conocidos actuales: {len(self.protocol.known_users)}"
                )

                # Esperar 10 segundos pero en chunks para poder salir rápido
                for _ in range(10):
                    if not self.protocol.running:
                        break
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                self.logger.info("Discovery loop cancelado")
                break
            except Exception as e:
                self.logger.error(
                    f"Error en bucle de descubrimiento: {e}", exc_info=True
                )
                await asyncio.sleep(1)

    async def send_echo(self):
        """Envía un mensaje de descubrimiento (echo) a la red"""
        try:
            self.logger.info("Preparando mensaje ECHO de descubrimiento...")
            header = self.protocol._pack_header("broadcast", self.protocol.ECHO)
            self.logger.debug(f"Header ECHO creado")

            # Usar las direcciones de broadcast correctamente
            for addr in self.protocol.BROADCAST_ADDR:
                await self.protocol._send_udp(header, (addr, self.protocol.UDP_PORT))
                self.logger.info(
                    f"Mensaje de descubrimiento (echo) enviado a {addr}:{self.protocol.UDP_PORT}"
                )
        except Exception as e:
            self.logger.error(f"Error al enviar ECHO: {e}", exc_info=True)
            raise
