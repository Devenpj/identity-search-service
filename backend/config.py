"""Central runtime configuration for the identity verification backend.

This module loads optional values from the project `.env` file and exposes a
single `settings` object used by services that need paths, OSINT credentials,
or integration URLs. Keeping these values here prevents secrets and environment
specific paths from being scattered through the codebase.
"""

import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


class Settings:
    """Resolve project paths and environment-backed integration settings."""

    BACKEND_ROOT = os.path.dirname(__file__)
    PROJECT_ROOT = os.path.abspath(
        os.path.join(
            BACKEND_ROOT,
            ".."
        )
    )
    for import_root in (PROJECT_ROOT, BACKEND_ROOT):
        if import_root not in sys.path:
            sys.path.insert(0, import_root)

    if load_dotenv:
        load_dotenv(
            os.path.join(
                PROJECT_ROOT,
                ".env"
            )
        )

    PROJECT_VENV_PYTHON = os.path.join(
        PROJECT_ROOT,
        ".venv",
        "Scripts",
        "python.exe"
    )
    INDIAN_ID_VALIDATOR_ROOT = os.environ.get(
        "INDIAN_ID_VALIDATOR_ROOT",
        os.path.join(
            BACKEND_ROOT,
            "vendor",
            "indian-id-validator"
        )
    )
    INDIAN_ID_VALIDATOR_PYTHON = os.environ.get(
        "INDIAN_ID_VALIDATOR_PYTHON",
        PROJECT_VENV_PYTHON if os.path.exists(PROJECT_VENV_PYTHON) else ""
    )
    OSINT_API_BASE_URL = os.environ.get(
        "OSINT_API_BASE_URL",
        ""
    ).rstrip("/")
    OSINT_API_KEY = os.environ.get(
        "OSINT_API_KEY",
        ""
    )
    OSINT_SCAN_PATH = os.environ.get(
        "OSINT_SCAN_PATH",
        "/api/v1/scan"
    )
    OSINT_CALLBACK_URL = os.environ.get(
        "OSINT_CALLBACK_URL",
        ""
    )
    OSINT_WEBHOOK_TOKEN = os.environ.get(
        "OSINT_WEBHOOK_TOKEN",
        ""
    )
    OSINT_REQUEST_TIMEOUT_SECONDS = float(
        os.environ.get(
            "OSINT_REQUEST_TIMEOUT_SECONDS",
            "20"
        )
    )


settings = Settings()
