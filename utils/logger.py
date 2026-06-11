"""Central logging setup for the identity search service.

Every project module should import `get_logger` from this file instead of
calling `logging.basicConfig` directly. That keeps log formatting, log levels,
console output, and file output consistent across backend routes and services.
"""

import logging
import os
from logging.handlers import RotatingFileHandler


PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        ".."
    )
)
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "identity_search_service.log")
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(level=logging.INFO, log_file=LOG_FILE):
    """Configure console and rotating file logging once for the whole project.

    The console handler keeps backend logs visible in the running terminal.
    The rotating file handler keeps a persistent central log file without
    allowing it to grow forever during long demos or repeated test runs.
    """

    global _configured

    if _configured:
        return

    os.makedirs(
        os.path.dirname(log_file),
        exist_ok=True
    )

    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=DATE_FORMAT
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger.handlers.clear()
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)

    _configured = True


def get_logger(name):
    """Return a named logger after ensuring central logging is configured."""

    configure_logging()

    return logging.getLogger(name)
