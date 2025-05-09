import struct
import uuid


UDP_PORT = 9990
TCP_PORT = 9990

# ID de broadcast
BROADCAST_ID = b"\xff" * 20

# Formatos para estructuras de datos
HEADER_FORMAT = "!20s20sBBQ50s"
HEADER_SIZE = 100

RESPONSE_FORMAT = "!B20s4s"
RESPONSE_SIZE = 25

# Códigos de operación
ECHO = 0
MESSAGE = 1
FILE = 2

# Códigos de respuesta
RESPONSE_OK = 0
RESPONSE_BAD_REQUEST = 1
RESPONSE_INTERNAL_ERROR = 2

SERVER_USER_ID = str(uuid.uuid4()).replace("-", "")[:20]
LOG_FILE = "Logs/lcp.log"


def pack_header(user_from, user_to, op_code, body_id=0, body_length=0):

    if isinstance(user_from, str):
        user_from = user_from.encode("utf-8").ljust(20, b"\0")[:20]
    elif len(user_from) != 20:
        user_from = user_from.ljust(20, b"\0")[:20]

    if isinstance(user_to, str):
        user_to = user_to.encode("utf-8").ljust(20, b"\0")[:20]
    elif len(user_to) != 20:
        user_to = user_to.ljust(20, b"\0")[:20]

    reserved = b"\x00" * 50
    return struct.pack(
        HEADER_FORMAT, user_from, user_to, op_code, body_id, body_length, reserved
    )


def unpack_header(data):
    user_from, user_to, op_code, body_id, body_length, _ = struct.unpack(
        HEADER_FORMAT, data
    )
    return (
        user_from.rstrip(b"\x00").decode(),
        user_to.rstrip(b"\x00").decode(),
        op_code,
        body_id,
        body_length,
    )


def pack_response(status, responder_id):

    if isinstance(responder_id, str):
        responder_id = responder_id.encode("utf-8").ljust(20, b"\0")[:20]
    elif len(responder_id) != 20:
        responder_id = responder_id.ljust(20, b"\0")[:20]

    reserved = b"\x00" * 4
    return struct.pack(RESPONSE_FORMAT, status, responder_id, reserved)


def unpack_response(data):
    status, responder_id, _ = struct.unpack(RESPONSE_FORMAT, data)
    return status, responder_id.rstrip(b"\x00").decode()
