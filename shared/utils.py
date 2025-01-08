# shared/utils.py

import socket
import logging


def get_local_ip():
    """
    Retrieves the local IP address of the machine.

    Returns:
        str: The local IP address.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            # The IP does not need to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
    return IP


def setup_logger(name, log_file, level=logging.DEBUG):
    """
    Sets up a logger with the specified name and log file.

    Args:
        name (str): The name of the logger.
        log_file (str): The file to which logs will be written.
        level (int): Logging level.

    Returns:
        logging.Logger: Configured logger.
    """
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')

    handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Avoid adding multiple handlers if logger already has handlers
    if not logger.handlers:
        logger.addHandler(handler)

    return logger
