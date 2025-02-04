# shared/utils.py

import os
import json
import socket
import logging
from logging.handlers import RotatingFileHandler


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


def load_config():
    """
    Loads configuration from a JSON file.
    Returns a dict containing 'client' and 'server' sections.
    """
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config


def setup_logger(name, log_file, level=logging.INFO, max_bytes=10 * 1024 * 1024, backup_count=5):
    """
    Sets up a logger with the specified name and log file.

    Args:
        name (str): The name of the logger.
        log_file (str): The file to which logs will be written.
        level (int): Logging level.
        max_bytes (int): Maximum size in bytes before rotation.
        backup_count (int): Number of backup files to keep.

    Returns:
        logging.Logger: Configured logger.
    """
    formatter = logging.Formatter('%(asctime)s [%(name)s] [%(levelname)s] %(message)s')

    handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Avoid adding multiple handlers if logger already has handlers
    if not logger.handlers:
        logger.addHandler(handler)

    return logger
