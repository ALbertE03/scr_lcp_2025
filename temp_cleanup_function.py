def _cleanup_expected_message_bodies(self):
    """Limpia entradas antiguas del diccionario de cuerpos de mensajes esperados"""
    now = time.time()
    with self._expected_bodies_lock:
        keys_to_remove = []
        for key, data in list(self._expected_message_bodies.items()):
            # Si una entrada tiene más de 30 segundos, la eliminamos
            if now - data["timestamp"] > 30:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            logger.debug(f"Eliminando registro de espera de mensaje antiguo: {key}")
            del self._expected_message_bodies[key]

        if keys_to_remove:
            logger.info(
                f"Limpiados {len(keys_to_remove)} registros de espera de mensajes antiguos"
            )
