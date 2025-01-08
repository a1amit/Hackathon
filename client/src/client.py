# client/src/client.py

import sys
import os
import socket
import struct
import threading
import time

# Add the project root directory to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from shared.protocol import (
    create_request_message,
    parse_offer_message,
    parse_payload_message,
    REQUEST_TYPE,
    PAYLOAD_TYPE,
)
from shared.utils import setup_logger
from colorama import Fore, Style

# Constants
OFFER_PORT = 13117  # UDP port to listen for offer messages
BUFFER_SIZE = 65507  # Maximum UDP datagram size

# Initialize Logger
logger = setup_logger('client', 'client.log')

# State Flag and Lock
is_transfer_active = False
transfer_lock = threading.Lock()


def listen_for_offers(stop_event, offer_queue):
    """
    Listens for offer messages on the UDP broadcast port and adds them to the offer queue.

    Args:
        stop_event (threading.Event): Event to signal stopping the listener.
        offer_queue (list): List to store received offers.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('', OFFER_PORT))
        s.settimeout(1)  # Set timeout to allow periodic checks for stop_event
        print(Fore.GREEN + "Client started, listening for offer requests..." + Style.RESET_ALL)
        while not stop_event.is_set():
            try:
                data, addr = s.recvfrom(BUFFER_SIZE)
                offer = parse_offer_message(data)
                with transfer_lock:
                    if offer and not is_transfer_active:
                        udp_port, tcp_port = offer
                        server_ip = addr[0]
                        offer_queue.append((server_ip, udp_port, tcp_port))
                        print(Fore.CYAN + f"Received offer from {server_ip}" + Style.RESET_ALL)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error listening for offers: {e}")
                continue


def get_user_parameters():
    """
    Prompts the user to input file size, number of TCP connections, and number of UDP connections.

    Returns:
        tuple: A tuple containing file_size (int), tcp_connections (int), udp_connections (int).
    """
    while True:
        try:
            file_size_str = input("Enter the file size to download (in bytes): ")
            file_size = int(file_size_str)
            if file_size <= 0:
                print(Fore.RED + "File size must be a positive integer." + Style.RESET_ALL)
                continue
            tcp_connections_str = input("Enter the number of TCP connections: ")
            tcp_connections = int(tcp_connections_str)
            if tcp_connections < 0:
                print(Fore.RED + "Number of TCP connections must be a positive integer." + Style.RESET_ALL)
                continue
            udp_connections_str = input("Enter the number of UDP connections: ")
            udp_connections = int(udp_connections_str)
            if udp_connections < 0:
                print(Fore.RED + "Number of UDP connections must be a positive integer." + Style.RESET_ALL)
                continue
            if udp_connections == 0 and tcp_connections == 0:
                print(Fore.RED + "At least one TCP or UDP connection is required." + Style.RESET_ALL)
                continue
            return file_size, tcp_connections, udp_connections
        except ValueError:
            print(Fore.RED + "Invalid input. Please enter integer values." + Style.RESET_ALL)


def tcp_transfer(server_ip, tcp_port, file_size, transfer_id, results):
    """
    Performs a TCP transfer to the server and records the transfer statistics.

    Args:
        server_ip (str): The server's IP address.
        tcp_port (int): The server's TCP port.
        file_size (int): The size of the file to download in bytes.
        transfer_id (int): Identifier for the transfer.
        results (list): List to store result strings.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            start_time = time.time()
            s.connect((server_ip, tcp_port))
            # Send the file size followed by a newline
            s.sendall(f"{file_size}\n".encode())
            # Receive the data
            bytes_received = 0
            while bytes_received < file_size:
                data = s.recv(BUFFER_SIZE)
                if not data:
                    break
                bytes_received += len(data)
            end_time = time.time()
            total_time = end_time - start_time
            speed = (bytes_received * 8) / total_time if total_time > 0 else 0  # bits per second
            results.append(
                f"{Fore.GREEN}TCP transfer #{transfer_id} finished, total time: {total_time:.2f} seconds, total speed: {speed:.2f} bits/second{Style.RESET_ALL}")
    except Exception as e:
        results.append(f"{Fore.RED}TCP transfer #{transfer_id} failed: {e}{Style.RESET_ALL}")


def udp_transfer(server_ip, udp_port, file_size, transfer_id, results):
    """
    Performs a UDP transfer to the server and records the transfer statistics.

    Args:
        server_ip (str): The server's IP address.
        udp_port (int): The server's UDP port.
        file_size (int): The size of the file to download in bytes.
        transfer_id (int): Identifier for the transfer.
        results (list): List to store result strings.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(2)  # Timeout to detect end of transfer
            # Send request message
            request = create_request_message(file_size)
            s.sendto(request, (server_ip, udp_port))
            start_time = time.time()
            bytes_received = 0
            segments_received = set()
            total_segments = None
            while True:
                try:
                    data, addr = s.recvfrom(BUFFER_SIZE)
                    parsed = parse_payload_message(data)
                    if not parsed:
                        continue
                    seg_total, seg_current, payload = parsed
                    if total_segments is None:
                        total_segments = seg_total
                    segments_received.add(seg_current)
                    bytes_received += len(payload)
                except socket.timeout:
                    break
            end_time = time.time()
            total_time = end_time - start_time
            speed = (bytes_received * 8) / total_time if total_time > 0 else 0
            if total_segments:
                packets_lost = total_segments - len(segments_received)
                loss_percentage = (packets_lost / total_segments) * 100
            else:
                loss_percentage = 100.0
            results.append(
                f"{Fore.YELLOW}UDP transfer #{transfer_id} finished, total time: {total_time:.2f} seconds, total speed: {speed:.2f} bits/second, percentage of packets received successfully: {100 - loss_percentage:.2f}%{Style.RESET_ALL}")
    except Exception as e:
        results.append(f"{Fore.RED}UDP transfer #{transfer_id} failed: {e}{Style.RESET_ALL}")


def perform_speed_test(server_ip, udp_port, tcp_port, file_size, tcp_connections, udp_connections):
    """
    Initiates TCP and UDP transfers based on the specified number of connections.

    Args:
        server_ip (str): The server's IP address.
        udp_port (int): The server's UDP port.
        tcp_port (int): The server's TCP port.
        file_size (int): The size of the file to download in bytes.
        tcp_connections (int): Number of TCP connections to use.
        udp_connections (int): Number of UDP connections to use.
    """
    global is_transfer_active
    # The flag is already set in main() before calling this function

    threads = []
    results = []
    transfer_id = 1

    # Start TCP transfer threads
    for _ in range(tcp_connections):
        t = threading.Thread(target=tcp_transfer, args=(server_ip, tcp_port, file_size, transfer_id, results))
        threads.append(t)
        t.start()
        transfer_id += 1

    # Start UDP transfer threads
    for _ in range(udp_connections):
        t = threading.Thread(target=udp_transfer, args=(server_ip, udp_port, file_size, transfer_id, results))
        threads.append(t)
        t.start()
        transfer_id += 1

    # Wait for all threads to finish
    for t in threads:
        t.join()

    # Print results
    for res in results:
        print(res)
    print(Fore.GREEN + "All transfers complete, listening to offer requests" + Style.RESET_ALL)


def main():
    """
    The main function to start the client application.
    """
    stop_event = threading.Event()
    offer_queue = []

    # Start listening for offers in a separate thread
    listener_thread = threading.Thread(target=listen_for_offers, args=(stop_event, offer_queue), daemon=True)
    listener_thread.start()

    try:
        while True:
            # Wait until at least one offer is received
            while not offer_queue:
                time.sleep(0.1)
            # Get the first offer
            server_ip, udp_port, tcp_port = offer_queue.pop(0)
            # Set transfer as active before prompting the user
            with transfer_lock:
                global is_transfer_active
                is_transfer_active = True
            # Prompt user for parameters
            file_size, tcp_connections, udp_connections = get_user_parameters()
            # Start speed test
            perform_speed_test(server_ip, udp_port, tcp_port, file_size, tcp_connections, udp_connections)
            # Reset the flag after transfer is complete
            with transfer_lock:
                is_transfer_active = False
    except KeyboardInterrupt:
        print(Fore.RED + "\nClient shutting down." + Style.RESET_ALL)
        stop_event.set()
        sys.exit()


if __name__ == "__main__":
    main()
