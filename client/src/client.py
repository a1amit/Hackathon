# client/src/client.py

import sys
import os
import socket
import struct
import threading
import time
import queue

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
from shared.utils import setup_logger, load_config
from colorama import Fore, Style

CONFIG = load_config()  # Load entire JSON
CLIENT_CONFIG = CONFIG["client"]  # Extract just client portion

# Constants
OFFER_PORT = CLIENT_CONFIG["OFFER_PORT"] # UDP port to listen for offer messages
BUFFER_SIZE = CLIENT_CONFIG["BUFFER_SIZE"]  # Maximum UDP datagram size
UDP_RECEIVE_TIMEOUT = CLIENT_CONFIG["UDP_RECEIVE_TIMEOUT"]  # or 2, or allow user to supply

# Maximum limits to prevent resource exhaustion
MAX_FILE_SIZE = CLIENT_CONFIG["MAX_FILE_SIZE"] # Maximum file size in bytes
MAX_CONNECTIONS = CLIENT_CONFIG["MAX_CONNECTIONS"] # Maximum number of connections

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
        offer_queue (queue.Queue): Queue to store received offers.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # Enable multiple clients to bind to the same port
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            # Some systems might not support SO_REUSEPORT
            logger.warning("SO_REUSEPORT not supported on this system.")
        s.bind(('', OFFER_PORT))
        s.settimeout(UDP_RECEIVE_TIMEOUT)  # Set timeout to allow periodic checks for stop_event
        print(Fore.GREEN + "Client started, listening for offer requests..." + Style.RESET_ALL)
        while not stop_event.is_set():
            try:
                data, addr = s.recvfrom(BUFFER_SIZE)
                offer = parse_offer_message(data)
                if offer and not is_transfer_active:
                    udp_port, tcp_port = offer
                    server_ip = addr[0]
                    offer_queue.put((server_ip, udp_port, tcp_port))
                    print(Fore.CYAN + f"Received offer from {server_ip}" + Style.RESET_ALL)
                    logger.info(f"Received offer from {server_ip}:{tcp_port} via UDP port {udp_port}.")
                elif offer and is_transfer_active:
                    logger.info(f"Ignored offer from {server_ip} as a transfer is already active.")
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
            if file_size > MAX_FILE_SIZE:
                print(
                    Fore.RED + f"File size too large. Please enter a value less than {MAX_FILE_SIZE} bytes." + Style.RESET_ALL)
                continue

            tcp_connections_str = input("Enter the number of TCP connections: ")
            tcp_connections = int(tcp_connections_str)
            if tcp_connections < 0:
                print(Fore.RED + "Number of TCP connections must be a non-negative integer." + Style.RESET_ALL)
                continue
            if tcp_connections > MAX_CONNECTIONS:
                print(
                    Fore.RED + f"Number of TCP connections too high. Please enter a value less than or equal to {MAX_CONNECTIONS}." + Style.RESET_ALL)
                continue

            udp_connections_str = input("Enter the number of UDP connections: ")
            udp_connections = int(udp_connections_str)
            if udp_connections < 0:
                print(Fore.RED + "Number of UDP connections must be a non-negative integer." + Style.RESET_ALL)
                continue
            if udp_connections > MAX_CONNECTIONS:
                print(
                    Fore.RED + f"Number of UDP connections too high. Please enter a value less than or equal to {MAX_CONNECTIONS}." + Style.RESET_ALL)
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
            logger.info(f"Initiating TCP transfer #{transfer_id} to {server_ip}:{tcp_port} for {file_size} bytes.")
            start_time = time.time()
            s.connect((server_ip, tcp_port))

            # Send the file size followed by a newline
            s.sendall(f"{file_size}\n".encode())

            # Metrics Initialization
            bytes_received = 0
            throughput_log = []  # Logs throughput over time
            packet_times = []  # Logs time per packet
            last_time = start_time

            # Receive the data
            while bytes_received < file_size:
                data = s.recv(BUFFER_SIZE)
                if not data:
                    logger.warning(f"TCP transfer #{transfer_id}: Connection closed prematurely.")
                    break

                # Metrics per packet
                bytes_received += len(data)
                current_time = time.time()
                packet_time = current_time - last_time
                packet_times.append(packet_time)
                throughput = (len(data) * 8) / packet_time if packet_time > 0 else 0
                throughput_log.append(throughput)
                last_time = current_time

                # Calculate ETA
                remaining_bytes = file_size - bytes_received
                avg_speed = bytes_received / (current_time - start_time)
                eta = remaining_bytes / avg_speed if avg_speed > 0 else float('inf')

                # Log progress
                logger.info(
                    f"TCP transfer #{transfer_id}: {bytes_received}/{file_size} bytes received, "
                    f"ETA: {eta:.2f} seconds."
                )

            end_time = time.time()
            total_time = end_time - start_time
            avg_throughput = (bytes_received * 8) / total_time if total_time > 0 else 0  # bits per second

            # Calculate average packet size and jitter
            avg_packet_time = sum(packet_times) / len(packet_times) if packet_times else 0
            jitter = max(packet_times) - min(packet_times) if packet_times else 0

            # Results Summary
            logger.info(
                f"TCP transfer #{transfer_id} completed: {bytes_received} bytes in {total_time:.2f} seconds "
                f"at {avg_throughput:.2f} bps."
            )
            results.append(
                f"{Fore.GREEN}TCP transfer #{transfer_id} finished, total time: {total_time:.2f} seconds, "
                f"average speed: {avg_throughput:.2f} bits/second, "
                f"average packet time: {avg_packet_time:.4f} seconds, jitter: {jitter:.4f} seconds{Style.RESET_ALL}"
            )

            # Throughput over time
            logger.info(f"Throughput log (bps): {throughput_log}")
    except Exception as e:
        logger.error(f"TCP transfer #{transfer_id} failed: {e}")
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
            s.settimeout(1)  # Timeout to detect end of transfer

            # Send request message
            request = create_request_message(file_size)
            s.sendto(request, (server_ip, udp_port))
            logger.info(f"Initiating UDP transfer #{transfer_id} to {server_ip}:{udp_port} for {file_size} bytes.")

            # Metrics initialization
            start_time = time.time()
            bytes_received = 0
            segments_received = set()
            total_segments = None
            packet_times = []  # Logs time for receiving each packet
            throughput_log = []  # Logs throughput per packet
            last_time = start_time

            while True:
                try:
                    # Receive data
                    data, addr = s.recvfrom(BUFFER_SIZE)
                    current_time = time.time()

                    # Parse payload
                    parsed = parse_payload_message(data)
                    if not parsed:
                        logger.warning(f"UDP transfer #{transfer_id}: Received malformed payload from {addr}.")
                        continue

                    seg_total, seg_current, payload = parsed

                    # Track total segments to receive
                    if total_segments is None:
                        total_segments = seg_total
                        logger.info(f"UDP transfer #{transfer_id}: Total segments to receive: {total_segments}.")

                    # Process packet if not already received
                    if seg_current not in segments_received:
                        segments_received.add(seg_current)
                        bytes_received += len(payload)

                        # Metrics calculations
                        packet_time = current_time - last_time
                        throughput = (len(payload) * 8) / packet_time if packet_time > 0 else 0
                        packet_times.append(packet_time)
                        throughput_log.append(throughput)
                        last_time = current_time

                        logger.debug(f"UDP transfer #{transfer_id}: Received segment {seg_current}/{seg_total}.")

                    # Stop if all segments are received
                    if total_segments and len(segments_received) >= total_segments:
                        logger.info(f"UDP transfer #{transfer_id}: All segments received.")
                        break
                except socket.timeout:
                    logger.info(f"UDP transfer #{transfer_id}: Transfer timed out.")
                    break

            # Final calculations
            end_time = time.time()
            total_time = end_time - start_time
            avg_throughput = (bytes_received * 8) / total_time if total_time > 0 else 0  # bits per second

            # Packet loss calculation
            if total_segments:
                packets_lost = total_segments - len(segments_received)
                loss_percentage = (packets_lost / total_segments) * 100
            else:
                loss_percentage = 100.0

            # Jitter calculation
            avg_packet_time = sum(packet_times) / len(packet_times) if packet_times else 0
            jitter = max(packet_times) - min(packet_times) if packet_times else 0

            # Log results
            logger.info(
                f"UDP transfer #{transfer_id} completed: {bytes_received} bytes in {total_time:.2f} seconds "
                f"at {avg_throughput:.2f} bps with {100 - loss_percentage:.2f}% packets received. "
                f"Average packet time: {avg_packet_time:.4f} seconds, jitter: {jitter:.4f} seconds."
            )
            results.append(
                f"{Fore.YELLOW}UDP transfer #{transfer_id} finished, "
                f"total time: {total_time:.2f} seconds, "
                f"total speed: {avg_throughput:.2f} bits/second, "
                f"percentage of packets received successfully: {100 - loss_percentage:.2f}%, "
                f"average packet time: {avg_packet_time:.4f} seconds, jitter: {jitter:.4f} seconds{Style.RESET_ALL}"
            )
    except Exception as e:
        logger.error(f"UDP transfer #{transfer_id} failed: {e}")
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
    offer_queue = queue.Queue()

    # Start listening for offers in a separate thread
    listener_thread = threading.Thread(target=listen_for_offers, args=(stop_event, offer_queue), daemon=True)
    listener_thread.start()

    try:
        while True:
            try:
                # Wait indefinitely until an offer is received
                server_ip, udp_port, tcp_port = offer_queue.get(timeout=1)
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
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        print(Fore.RED + "\nClient shutting down." + Style.RESET_ALL)
        stop_event.set()
        listener_thread.join()
        sys.exit()


if __name__ == "__main__":
    main()
