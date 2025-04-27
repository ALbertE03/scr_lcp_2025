from protocol import pack_response, RESPONSE_OK


class FileTransferManager:
    def __init__(self, client_id, network_manager):
        self.client_id = client_id
        self.network_manager = network_manager

    def handle_file_transfer(self, user_from, user_to, body_id, body_length, addr):
        if user_to == self.client_id:
            print(
                f"Preparando para recibir archivo de {user_from} ({body_length} bytes)"
            )
            response = pack_response(RESPONSE_OK, self.client_id)
            self.network_manager.udp_socket.sendto(response, addr)
            ## falta recivir el archivo
