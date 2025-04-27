import struct
import socket
import threading
import random


UDP_PORT = 9990
TCP_PORT = 9990

BROADCAST_ID = b'\xFF' * 20


HEADER_FORMAT = "!20s20sBBQ50s"
HEADER_SIZE = 100


RESPONSE_FORMAT = "!B20s4s"
RESPONSE_SIZE = 25


ECHO = 0
MESSAGE = 1
FILE = 2


RESPONSE_OK = 0
RESPONSE_BAD_REQUEST = 1
RESPONSE_INTERNAL_ERROR = 2

SERVER_USER_ID = "ServerNode"

def pack_header(user_from, user_to, op_code, body_id=1, body_length=8):
    reserved = b'\x00' * 50
    return struct.pack(HEADER_FORMAT, user_from.encode(), user_to.encode(), op_code, body_id, body_length, reserved)

def unpack_header(data):
    user_from, user_to, op_code, body_id, body_length, _ = struct.unpack(HEADER_FORMAT, data)
    return user_from.rstrip(b'\x00').decode(), user_to.rstrip(b'\x00').decode(), op_code, body_id, body_length

def pack_response(status, responder_id):
    reserved = b'\x00' * 4
    return struct.pack(RESPONSE_FORMAT, status, responder_id.encode(), reserved)

def unpack_response(data):
    status, responder_id, _ = struct.unpack(RESPONSE_FORMAT, data)
    return status, responder_id.rstrip(b'\x00').decode()

def handle_udp(sock_udp):
    while True:
        data, addr = sock_udp.recvfrom(HEADER_SIZE)
        user_from, user_to, op_code, body_id, body_length = unpack_header(data)

        if op_code == ECHO:
            print(f"[DISCOVERY] Echo received from {user_from}")
            response = pack_response(RESPONSE_OK, SERVER_USER_ID)
            sock_udp.sendto(response, addr)

        elif op_code == MESSAGE:
            print(f"[MESSAGE] Header received from {user_from}")
            sock_udp.sendto(pack_response(RESPONSE_OK, SERVER_USER_ID), addr)

            body_data, _ = sock_udp.recvfrom(body_length + 8)
            recv_body_id = struct.unpack('!Q', body_data[:8])[0]
            message = body_data[8:].decode()

            print(f"[MESSAGE] Message from {user_from}: {message}")
            sock_udp.sendto(pack_response(RESPONSE_OK, SERVER_USER_ID), addr)

        elif op_code == FILE:
            print(f"[FILE] File header received from {user_from}")
            sock_udp.sendto(pack_response(RESPONSE_OK, SERVER_USER_ID), addr)

            # Manejo de archivos aquí

def main():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(('', UDP_PORT))

    print(f"Server running on UDP port {UDP_PORT}...")
    handle_udp(udp_sock)

if __name__ == "__main__":
    main()
