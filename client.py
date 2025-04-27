import socket
import random
from protocol import *
import uuid
CLIENT_USER_ID =  str(uuid.uuid4()).replace("-", "")[:20]

def send_echo(sock_udp):
    header = pack_header(CLIENT_USER_ID, '\xFF' * 20, ECHO)
    sock_udp.sendto(header, ('<broadcast>', UDP_PORT))
    try:
        sock_udp.settimeout(5)
        response, addr = sock_udp.recvfrom(RESPONSE_SIZE)
        status, responder_id = unpack_response(response)
        print(f"[DISCOVERY] Got response from {responder_id} at {addr}")
    except socket.timeout:
        print("[DISCOVERY] No response")

def send_message(sock_udp, target_id, message):
    body_id = 1
    header = pack_header(CLIENT_USER_ID, target_id, MESSAGE, body_id, len(message))
    sock_udp.sendto(header, (target_id, UDP_PORT))

    try:
        sock_udp.settimeout(5)
        response, _ = sock_udp.recvfrom(RESPONSE_SIZE)
        status, _ = unpack_response(response)
        if status != RESPONSE_OK:
            print("[MESSAGE] Target did not acknowledge header")
            return

        body = body_id.to_bytes(8, byteorder='big') + message.encode()
        sock_udp.sendto(body, (target_id, UDP_PORT))

        response, _ = sock_udp.recvfrom(RESPONSE_SIZE)
        status, _ = unpack_response(response)
        if status == RESPONSE_OK:
            print("[MESSAGE] Message sent successfully")
        else:
            print("[MESSAGE] Message not acknowledged")

    except socket.timeout:
        print("[MESSAGE] Timeout waiting for response")

def send_file(sock_udp, target_ip, filepath):
    with open(filepath, "rb") as f:
        file_data = f.read()

    body_id = 1
    header = pack_header(CLIENT_USER_ID, CLIENT_USER_ID, FILE, body_id, len(file_data))
    sock_udp.sendto(header, (target_ip, UDP_PORT))

    try:
        sock_udp.settimeout(5)
        response, _ = sock_udp.recvfrom(RESPONSE_SIZE)
        status, _ = unpack_response(response)
        if status != RESPONSE_OK:
            print("[FILE] Target did not acknowledge header")
            return

        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.connect((target_ip, TCP_PORT))

        tcp_sock.sendall(body_id.to_bytes(8, byteorder='big') + file_data)

        response = tcp_sock.recv(RESPONSE_SIZE)
        status, _ = unpack_response(response)
        if status == RESPONSE_OK:
            print("[FILE] File sent successfully")
        else:
            print("[FILE] File transfer failed")
        tcp_sock.close()

    except socket.timeout:
        print("[FILE] Timeout waiting for response")

def main():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    print("Options:\n1. Discover users\n2. Send message\n3. Send file")
    choice = input("Select option: ").strip()

    if choice == '1':
        send_echo(udp_sock)
    elif choice == '2':
        target_ip = input("Target IP: ")
        message = input("Message: ")
        send_message(udp_sock, target_ip, message)
    elif choice == '3':
        target_ip = input("Target IP: ")
        filepath = input("File path: ")
        send_file(udp_sock, target_ip, filepath)
    else:
        print("Invalid option")

if __name__ == "__main__":
    main()
