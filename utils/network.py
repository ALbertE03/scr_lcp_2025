import platform
import subprocess
import re
import socket
import logging


def get_broadcast_addresses():
    """Obtiene direcciones de broadcast disponibles"""
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
        logging.error(f"Error obteniendo información de red: {e}")

    return broadcast_addresses
