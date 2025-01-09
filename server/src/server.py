# server/src/server.py

import sys
import os

# Add the project root directory to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import socket
import struct
import threading
import time
import argparse
from shared.protocol import (
    create_offer_message,
    parse_request_message,
    create_payload_message,
    PAYLOAD_TYPE,
    REQUEST_TYPE,
)
from shared.utils import get_local_ip, setup_logger, load_config
from colorama import Fore, Style
from concurrent.futures import ThreadPoolExecutor

CONFIG = load_config()
SERVER_CONFIG = CONFIG["server"]

# Constants
OFFER_INTERVAL = SERVER_CONFIG["OFFER_INTERVAL"]  # seconds between offer broadcasts
OFFER_PORT = SERVER_CONFIG["OFFER_PORT"]  # UDP port for offer messages
SEGMENT_SIZE = SERVER_CONFIG["SEGMENT_SIZE"]  # segment size for UDP payload messages
BUFFER_SIZE = SERVER_CONFIG["BUFFER_SIZE"]  # Buffer size for receiving data
NETWORK_DELAY = SERVER_CONFIG["NETWORK_DELAY"]  # Delay between sending UDP segments

# Initialize Logger
logger = setup_logger('server', 'server.log')


def handle_tcp_client(conn, addr, file_size):
    """
    Handles a TCP client by sending the requested amount of data and closing the connection.

    Args:
        conn (socket.socket): The TCP connection socket.
        addr (tuple): The client's address.
        file_size (int): The number of bytes to send.
    """
    try:
        logger.info(f"[TCP] Handling client {addr} for {file_size} bytes.")
        bytes_sent = 0
        buffer_size = 4096  # 4KB per send
        dummy_data = b'a' * buffer_size  # Dummy data to send

        start_time = time.time()

        while bytes_sent < file_size:
            remaining = file_size - bytes_sent
            chunk_size = buffer_size if remaining >= buffer_size else remaining
            conn.sendall(dummy_data[:chunk_size])
            bytes_sent += chunk_size

        end_time = time.time()
        total_time = end_time - start_time
        speed = (bytes_sent * 8) / total_time  # bits per second

        logger.info(f"[TCP] Sent {bytes_sent} bytes to {addr} in {total_time:.2f} seconds at {speed:.2f} bps.")
    except Exception as e:
        logger.error(f"[TCP] Error with client {addr}: {e}")
    finally:
        conn.close()
        logger.info(f"[TCP] Connection with {addr} closed.")


def handle_udp_request(data, addr, udp_socket):
    """
    Handles a UDP client request by sending data in payload messages.

    Args:
        data (bytes): The received UDP request message.
        addr (tuple): The client's address.
        udp_socket (socket.socket): The UDP socket to send data through.
    """
    try:
        logger.info(f"[UDP] Received data from {addr}.")
        # Parse request message
        file_size = parse_request_message(data)
        if file_size is None:
            logger.warning(f"[UDP] Invalid request from {addr}.")
            return

        logger.info(f"[UDP] Handling UDP request from {addr} for {file_size} bytes.")

        # Calculate number of segments
        total_segments = (file_size + SEGMENT_SIZE - 1) // SEGMENT_SIZE

        # Pre-generate a dummy payload
        dummy_payload = b'a' * SEGMENT_SIZE

        # Send payload messages
        for segment in range(1, total_segments + 1):
            payload = create_payload_message(total_segments, segment, dummy_payload)
            udp_socket.sendto(payload, addr)
            logger.debug(f"[UDP] Sent segment {segment}/{total_segments} to {addr}.")
            time.sleep(NETWORK_DELAY)  # Slight delay to prevent network congestion

        logger.info(f"[UDP] Sent {total_segments} segments to {addr}.")
    except Exception as e:
        logger.error(f"[UDP] Error handling UDP request from {addr}: {e}")


# Define maximum number of worker threads
MAX_WORKERS = 50


def tcp_server(tcp_port):
    """
    Starts the TCP server to listen for incoming connections.

    Args:
        tcp_port (int): The TCP port number to listen on.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', tcp_port))
        s.listen()
        logger.info(f"[TCP] TCP server listening on port {tcp_port}.")
        print(Fore.BLUE + f"[TCP] TCP server listening on port {tcp_port}" + Style.RESET_ALL)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            while True:
                try:
                    conn, addr = s.accept()
                    logger.info(f"[TCP] Accepted connection from {addr}.")
                    # Receive file size from client
                    data = b''
                    while not data.endswith(b'\n'):
                        packet = conn.recv(1024)
                        if not packet:
                            break
                        data += packet
                    if not data:
                        logger.warning(f"[TCP] No data received from {addr}. Closing connection.")
                        conn.close()
                        continue
                    file_size_str = data.strip().decode()
                    file_size = int(file_size_str)
                    logger.info(f"[TCP] Client {addr} requested {file_size} bytes.")
                    # Submit the handling task to the thread pool
                    executor.submit(handle_tcp_client, conn, addr, file_size)
                except Exception as e:
                    logger.error(f"[TCP] Error accepting connections: {e}")


def udp_server(udp_port):
    """
    Starts the UDP server to listen for incoming requests.

    Args:
        udp_port (int): The UDP port number to listen on.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(('', udp_port))
        logger.info(f"[UDP] UDP server listening on port {udp_port}.")
        print(Fore.MAGENTA + f"[UDP] UDP server listening on port {udp_port}" + Style.RESET_ALL)
        while True:
            try:
                data, addr = s.recvfrom(BUFFER_SIZE)
                logger.info(f"[UDP] Received request from {addr}.")
                threading.Thread(target=handle_udp_request, args=(data, addr, s), daemon=True).start()
            except Exception as e:
                logger.error(f"[UDP] Error receiving data: {e}")


def offer_broadcaster(tcp_port, udp_port):
    """
    Broadcasts offer messages via UDP every second to announce server availability.

    Args:
        tcp_port (int): The TCP port number to include in the offer message.
        udp_port (int): The UDP port number to include in the offer message.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        offer_message = create_offer_message(tcp_port, udp_port)
        while True:
            try:
                # Broadcast to the local network on OFFER_PORT
                s.sendto(offer_message, ('<broadcast>', OFFER_PORT))
                logger.info(f"[Offer] Broadcasted offer message (TCP:{tcp_port}, UDP:{udp_port}).")
                time.sleep(OFFER_INTERVAL)
            except Exception as e:
                logger.error(f"[Offer] Error broadcasting offer: {e}")
                time.sleep(OFFER_INTERVAL)


def main():
    """
    The main function to start the server application.
    """
    parser = argparse.ArgumentParser(description="Network Speed Test Server")
    parser.add_argument('--tcp_port', type=int, default=5001, help='TCP port to listen on')
    parser.add_argument('--udp_port', type=int, default=5002, help='UDP port to listen on')
    args = parser.parse_args()

    # Start offer broadcaster thread
    threading.Thread(target=offer_broadcaster, args=(args.tcp_port, args.udp_port), daemon=True).start()

    # Start TCP and UDP server threads
    threading.Thread(target=tcp_server, args=(args.tcp_port,), daemon=True).start()
    threading.Thread(target=udp_server, args=(args.udp_port,), daemon=True).start()

    # Log and print server start information
    local_ip = get_local_ip()
    logger.info(f"Server started, listening on IP address {local_ip}")
    print(Fore.GREEN + f"Server started, listening on IP address {local_ip}" + Style.RESET_ALL)

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
        print(Fore.RED + "\nServer shutting down." + Style.RESET_ALL)


if __name__ == "__main__":
    main()
