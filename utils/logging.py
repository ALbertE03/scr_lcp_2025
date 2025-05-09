import logging
import os


def setup_logging(log_file):
    """Configura el sistema de logging"""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )

    return logging


def get_module_logger(name):
    """Obtiene un logger para un módulo específico"""
    return logging.getLogger(name)
