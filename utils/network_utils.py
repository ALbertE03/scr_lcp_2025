"""
Network utilities module for LCP protocol.
Handles network interfaces discovery, broadcast addresses and other network-related operations.
"""

import logging
import platform
import subprocess
import re

logger = logging.getLogger("LCP")


def get_network_info():
    """Obtiene información de red sin dependencias externas"""
    system = platform.system()
    broadcast_addresses = []

    try:
        if system == "Darwin":  # macOS
            output = subprocess.check_output(
                ["ifconfig en0 | grep broadcast | awk '{print $6}'"],
                universal_newlines=True,
                shell=True,
            )
            broadcast_addresses = output.splitlines()
        elif system == "Linux":  # Linux
            try:
                # Método 1: Usar el comando 'ip' (más moderno)
                output = subprocess.check_output(
                    ["ip addr show eth0 | grep brd | awk '{print $4}'"],
                    universal_newlines=True,
                    shell=True,
                )

                for line in output.splitlines():
                    ip_match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", line)
                    if ip_match:
                        ip = ip_match.group(1)
                        prefix_len = int(ip_match.group(2))

                        # Calcular máscara desde prefijo
                        mask_int = (1 << 32) - (1 << (32 - prefix_len))
                        mask = [
                            (mask_int >> 24) & 0xFF,
                            (mask_int >> 16) & 0xFF,
                            (mask_int >> 8) & 0xFF,
                            mask_int & 0xFF,
                        ]

                        # Calcular broadcast
                        ip_parts = list(map(int, ip.split(".")))
                        broadcast_parts = []
                        for i in range(4):
                            broadcast_parts.append(ip_parts[i] | (~mask[i] & 0xFF))

                        broadcast = ".".join(map(str, broadcast_parts))
                        if ip != "127.0.0.1":  # Ignorar localhost
                            broadcast_addresses.append(broadcast)

            except (subprocess.SubprocessError, FileNotFoundError):
                # Método 2: Usar 'ifconfig' (sistemas más antiguos)
                try:
                    output = subprocess.check_output(
                        ["ifconfig"], universal_newlines=True
                    )
                    interfaces = re.split(r"\n(?=\w)", output)

                    for interface in interfaces:
                        # Diferentes formatos posibles en distintas distribuciones
                        if (
                            "inet " in interface
                            and not "inet6 "
                            in interface.split("inet ")[1].split("\n")[0]
                        ):
                            ip_match = re.search(
                                r"inet (\d+\.\d+\.\d+\.\d+)", interface
                            )
                            # Intentar ambos formatos de máscara
                            mask_match = re.search(
                                r"netmask (\d+\.\d+\.\d+\.\d+)", interface
                            ) or re.search(r"Mask:(\d+\.\d+\.\d+\.\d+)", interface)

                            if ip_match and mask_match:
                                ip = ip_match.group(1)
                                mask_str = mask_match.group(1)

                                if ip != "127.0.0.1":  # Ignorar localhost
                                    # Buscar broadcast directo en la salida
                                    bcast_match = re.search(
                                        r"broadcast (\d+\.\d+\.\d+\.\d+)", interface
                                    ) or re.search(
                                        r"Bcast:(\d+\.\d+\.\d+\.\d+)", interface
                                    )

                                    if bcast_match:
                                        broadcast_addresses.append(bcast_match.group(1))
                                    else:
                                        # Calcularlo manualmente
                                        mask = list(map(int, mask_str.split(".")))
                                        ip_parts = list(map(int, ip.split(".")))

                                        broadcast_parts = []
                                        for i in range(4):
                                            broadcast_parts.append(
                                                ip_parts[i] | (~mask[i] & 0xFF)
                                            )

                                        broadcast = ".".join(map(str, broadcast_parts))
                                        broadcast_addresses.append(broadcast)
                except:
                    # Si ningún método funciona
                    logger.warning(
                        "No se pudo detectar direcciones de broadcast, usando fallback"
                    )
                    broadcast_addresses.append("255.255.255.255")

        # Si no se encontró ninguna dirección, usar broadcast general
        if not broadcast_addresses:
            logger.info("Usando dirección de broadcast por defecto (255.255.255.255)")
            broadcast_addresses.append("255.255.255.255")

    except Exception as e:
        logger.error(f"Error obteniendo información de red: {e}")
        broadcast_addresses.append("255.255.255.255")

    # Eliminar duplicados
    broadcast_addresses = list(set(broadcast_addresses))
    logger.info(f"Direcciones de broadcast detectadas: {broadcast_addresses}")
    return broadcast_addresses
