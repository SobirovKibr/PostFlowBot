"""
Logging configuration module for Telegram Userbot.
Handles structured logging to both console (stdout) and rotating/appended file (bot.log).
"""

import logging
import sys
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent / "bot.log"

def setup_logger(name: str = "TelegramUserBot") -> logging.Logger:
    """
    Configures and returns a logger instance with dual output:
    1. Console (StreamHandler) with formatted timestamps and log levels.
    2. File (FileHandler) writing to bot.log with UTF-8 encoding.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if setup_logger is invoked multiple times
    if logger.handlers:
        return logger

    # Formatters
    log_format = "[%(asctime)s] [%(levelname)-8s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    # 1. Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File handler (UTF-8 encoding to preserve unicode and emojis)
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not set up file logger to {LOG_FILE}: {e}", file=sys.stderr)

    return logger

# Default logger instance
logger = setup_logger()
