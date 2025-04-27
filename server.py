import socket
import threading
from protocol import *
import uuid
SERVER_USER_ID =  str(uuid.uuid4()).replace("-", "")[:20]

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

            body_data, addr2 = sock_udp.recvfrom(8 + body_length)
            recv_body_id = int.from_bytes(body_data[:8], byteorder='big')
            message = body_data[8:].decode()

            print(f"[MESSAGE] Message from {user_from}: {message}")
            sock_udp.sendto(pack_response(RESPONSE_OK, SERVER_USER_ID), addr)

        elif op_code == FILE:
            print(f"[FILE] File header received from {user_from}")
            sock_udp.sendto(pack_response(RESPONSE_OK, SERVER_USER_ID), addr)

            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_sock.bind(('', TCP_PORT))
            tcp_sock.listen(1)
            conn, addr_tcp = tcp_sock.accept()

            print(f"[FILE] TCP connection from {addr_tcp}")

            file_header = conn.recv(8)
            recv_file_id = int.from_bytes(file_header, byteorder='big')
            file_data = b''
            remaining = body_length
            while remaining > 0:
                chunk = conn.recv(min(4096, remaining))
                if not chunk:
                    break
                file_data += chunk
                remaining -= len(chunk)

            with open(f"received_file_{recv_file_id}.bin", "wb") as f:
                f.write(file_data)

            print(f"[FILE] File received and saved as received_file_{recv_file_id}.bin")
            conn.sendall(pack_response(RESPONSE_OK, SERVER_USER_ID))
            conn.close()
            tcp_sock.close()

def main():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(('', UDP_PORT))

    print(f"Server running on UDP port {UDP_PORT} and TCP port {TCP_PORT}...")
    handle_udp(udp_sock)

if __name__ == "__main__":
    main()
