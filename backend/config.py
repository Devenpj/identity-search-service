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
    OSINT_JOB_STALE_MINUTES = int(
        os.environ.get(
            "OSINT_JOB_STALE_MINUTES",
            "15"
        )
    )
    FACE_MATCH_THRESHOLD = float(
        os.environ.get(
            "FACE_MATCH_THRESHOLD",
            "0.72"
        )
    )
    FACE_MIN_SCORE_GAP = float(
        os.environ.get(
            "FACE_MIN_SCORE_GAP",
            "0.08"
        )
    )
    FACE_STRONG_MATCH_THRESHOLD = float(
        os.environ.get(
            "FACE_STRONG_MATCH_THRESHOLD",
            "0.74"
        )
    )
    FACE_ENGINE_URL = os.environ.get(
        "FACE_ENGINE_URL",
        ""
    )
    FACE_ENGINE_TIMEOUT_SECONDS = float(
        os.environ.get(
            "FACE_ENGINE_TIMEOUT_SECONDS",
            "300"
        )
    )
    FACE_ENGINE_BATCH_SIZE = int(
        os.environ.get(
            "FACE_ENGINE_BATCH_SIZE",
            "100"
        )
    )
    FACE_SEARCH_JOB_STALE_MINUTES = int(
        os.environ.get(
            "FACE_SEARCH_JOB_STALE_MINUTES",
            "30"
        )
    )
    DOCUMENT_VALIDATION_JOB_STALE_MINUTES = int(
        os.environ.get(
            "DOCUMENT_VALIDATION_JOB_STALE_MINUTES",
            "30"
        )
    )


settings = Settings()
