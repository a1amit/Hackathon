# shared/protocol.py

import struct

# Constants for packet formats
MAGIC_COOKIE = 0xabcddcba
OFFER_TYPE = 0x2
REQUEST_TYPE = 0x3
PAYLOAD_TYPE = 0x4

# Struct formats
OFFER_STRUCT = '!IBHH'  # Magic cookie (4 bytes), Message type (1 byte), UDP port (2 bytes), TCP port (2 bytes)
REQUEST_STRUCT = '!IBQ'  # Magic cookie (4 bytes), Message type (1 byte), File size (8 bytes)
PAYLOAD_STRUCT = '!IBQQ'  # Magic cookie (4 bytes), Message type (1 byte), Total segments (8 bytes), Current segment (8 bytes)


def create_offer_message(tcp_port, udp_port):
    """
    Creates an offer message with the specified TCP and UDP ports.

    Args:
        tcp_port (int): The TCP port number.
        udp_port (int): The UDP port number.

    Returns:
        bytes: The packed offer message.
    """
    return struct.pack(OFFER_STRUCT, MAGIC_COOKIE, OFFER_TYPE, udp_port, tcp_port)


def parse_offer_message(data):
    """
    Parses an offer message and extracts the UDP and TCP ports.

    Args:
        data (bytes): The received offer message.

    Returns:
        tuple or None: A tuple (udp_port, tcp_port) if parsing is successful, else None.
    """
    if len(data) < struct.calcsize(OFFER_STRUCT):
        return None
    magic, msg_type, udp_port, tcp_port = struct.unpack(OFFER_STRUCT, data[:struct.calcsize(OFFER_STRUCT)])
    if magic != MAGIC_COOKIE or msg_type != OFFER_TYPE:
        return None
    return udp_port, tcp_port


def create_request_message(file_size):
    """
    Creates a request message with the specified file size.

    Args:
        file_size (int): The size of the file to request in bytes.

    Returns:
        bytes: The packed request message.
    """
    return struct.pack(REQUEST_STRUCT, MAGIC_COOKIE, REQUEST_TYPE, file_size)


def parse_request_message(data):
    """
    Parses a request message and extracts the file size.

    Args:
        data (bytes): The received request message.

    Returns:
        int or None: The file size if parsing is successful, else None.
    """
    if len(data) < struct.calcsize(REQUEST_STRUCT):
        return None
    magic, msg_type, file_size = struct.unpack(REQUEST_STRUCT, data[:struct.calcsize(REQUEST_STRUCT)])
    if magic != MAGIC_COOKIE or msg_type != REQUEST_TYPE:
        return None
    return file_size


def create_payload_message(total_segments, current_segment, payload_data):
    """
    Creates a payload message with the specified total segments, current segment, and payload data.

    Args:
        total_segments (int): Total number of segments in the data stream.
        current_segment (int): The current segment number.
        payload_data (bytes): The actual payload data.

    Returns:
        bytes: The packed payload message.
    """
    header = struct.pack(PAYLOAD_STRUCT, MAGIC_COOKIE, PAYLOAD_TYPE, total_segments, current_segment)
    return header + payload_data


def parse_payload_message(data):
    """
    Parses a payload message and extracts total segments, current segment, and payload data.

    Args:
        data (bytes): The received payload message.

    Returns:
        tuple or None: A tuple (total_segments, current_segment, payload_data) if parsing is successful, else None.
    """
    header_size = struct.calcsize(PAYLOAD_STRUCT)
    if len(data) < header_size:
        return None
    magic, msg_type, total_segments, current_segment = struct.unpack(PAYLOAD_STRUCT, data[:header_size])
    if magic != MAGIC_COOKIE or msg_type != PAYLOAD_TYPE:
        return None
    payload = data[header_size:]
    return total_segments, current_segment, payload
