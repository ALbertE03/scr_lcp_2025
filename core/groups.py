import asyncio
from typing import Set, Dict


class GroupManager:
    """Maneja la funcionalidad de grupos"""

    def __init__(self, protocol):
        """Inicializa el gestor de grupos"""
        self.protocol = protocol
        self.logger = protocol.logger
        # Grupos: group_name -> set of user_ids
        self.groups: Dict[str, Set[str]] = {}
        # Grupos a los que se ha unido el usuario
        self.joined_groups: Set[str] = set()

    async def create_group(self, group_name: str):
        """Crea un nuevo grupo y emite notificación"""
        self.logger.info(f"Intentando crear grupo: {group_name}")
        if group_name in self.groups:
            self.logger.warning(f"El grupo {group_name} ya existe")
            return False

        self.groups[group_name] = set(
            [self.protocol.user_id]
        )  # Creador se une automáticamente
        self.joined_groups.add(group_name)
        self.logger.info(f"Grupo {group_name} creado exitosamente")

        # Notificar a usuarios conocidos sobre el nuevo grupo
        notification = f"SYSTEM:GROUP_CREATED:{group_name}"
        for user_id in self.protocol.known_users:
            await self.protocol.messaging.send_message(user_id, notification)

        return True

    async def invite_to_group(self, group_name: str, user_id: str):
        """Invita a un usuario a unirse a un grupo"""
        if group_name not in self.groups:
            self.logger.error(f"El grupo {group_name} no existe")
            return False

        if user_id not in self.protocol.known_users:
            self.logger.error(f"Usuario {user_id} no encontrado")
            return False

        invitation = f"SYSTEM:GROUP_INVITE:{group_name}"
        return await self.protocol.messaging.send_message(user_id, invitation)

    async def join_group(self, group_name: str):
        """Une al usuario a un grupo"""
        self.logger.info(f"Intentando unirse al grupo: {group_name}")
        if group_name not in self.groups:
            self.logger.error(f"El grupo {group_name} no existe")
            return False

        self.groups[group_name].add(self.protocol.user_id)
        self.joined_groups.add(group_name)
        self.logger.info(f"Unido exitosamente al grupo {group_name}")
        return True

    async def send_group_message(self, group_name: str, message: str):
        """Envía un mensaje a un grupo"""
        self.logger.info(f"Intentando enviar mensaje al grupo {group_name}")
        if group_name not in self.joined_groups:
            self.logger.error(f"No estás unido al grupo {group_name}")
            return False

        if group_name not in self.groups:
            self.logger.error(f"El grupo {group_name} no existe")
            return False

        self.logger.debug(f"Miembros del grupo {group_name}: {self.groups[group_name]}")

        # Enviar mensaje a todos los miembros del grupo
        success = True
        for member in self.groups[group_name]:
            if member != self.protocol.user_id:  # No enviarnos a nosotros mismos
                self.logger.debug(f"Enviando mensaje a miembro {member}")
                if not await self.protocol.messaging.send_message(
                    member, f"[GRUPO {group_name}] {message}"
                ):
                    self.logger.error(f"Error al enviar mensaje a miembro {member}")
                    success = False
                else:
                    self.logger.debug(
                        f"Mensaje enviado exitosamente a miembro {member}"
                    )

        if success:
            self.logger.info(
                f"Mensaje enviado exitosamente a todos los miembros del grupo {group_name}"
            )
        else:
            self.logger.warning(
                f"Mensaje enviado con errores a algunos miembros del grupo {group_name}"
            )

        return success
