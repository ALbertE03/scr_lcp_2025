import json
import os
import time
from typing import Dict, List


class HistoryManager:
    """Gestiona el historial de mensajes"""

    def __init__(self, protocol):
        """Inicializa el gestor de historial"""
        self.protocol = protocol
        self.logger = protocol.logger
        self.message_history: Dict[str, List[Dict[str, any]]] = {}

    async def save_message_to_history(
        self, user_id: str, is_outgoing: bool, message: str
    ):
        """Guarda un mensaje en el historial"""
        if user_id not in self.message_history:
            self.message_history[user_id] = []

        # Mantener solo los últimos 10 mensajes
        if len(self.message_history[user_id]) >= 10:
            self.message_history[user_id].pop(0)

        self.message_history[user_id].append(
            {"timestamp": time.time(), "is_outgoing": is_outgoing, "message": message}
        )
        self.logger.debug(f"Mensaje guardado en historial de {user_id}")

    async def save_history_to_file(self):
        """Guarda el historial de mensajes en un archivo"""
        try:
            filename = f"history_{self.protocol.username}.json"
            # Convertir timestamp a string para serialización
            serializable_history = {}
            for user_id, messages in self.message_history.items():
                serializable_history[user_id] = []
                for msg in messages:
                    msg_copy = msg.copy()
                    msg_copy["timestamp"] = str(msg_copy["timestamp"])
                    serializable_history[user_id].append(msg_copy)

            with open(filename, "w") as f:
                json.dump(serializable_history, f)
            self.logger.info(f"Historial guardado en {filename}")
            return True
        except Exception as e:
            self.logger.error(f"Error al guardar historial: {e}")
            return False

    async def load_history_from_file(self):
        """Carga el historial de mensajes desde un archivo"""
        try:
            filename = f"history_{self.protocol.username}.json"
            if not os.path.exists(filename):
                self.logger.info(f"No existe archivo de historial {filename}")
                return False

            with open(filename, "r") as f:
                serialized_history = json.load(f)

            # Convertir string a timestamp
            for user_id, messages in serialized_history.items():
                if user_id not in self.message_history:
                    self.message_history[user_id] = []
                for msg in messages:
                    msg["timestamp"] = float(msg["timestamp"])
                    self.message_history[user_id].append(msg)

            self.logger.info(f"Historial cargado desde {filename}")
            return True
        except Exception as e:
            self.logger.error(f"Error al cargar historial: {e}")
            return False

    def get_message_history(
        self, user_id: str = None
    ) -> Dict[str, List[Dict[str, any]]]:
        """Recupera el historial de mensajes con un usuario o con todos"""
        if user_id:
            return {user_id: self.message_history.get(user_id, [])}
        return self.message_history
