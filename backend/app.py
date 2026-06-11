"""FastAPI application entrypoint.

The route handlers live in `backend/api/routes.py`. This file stays small so
existing commands such as `python -m uvicorn app:app` from the backend folder
and `python -m uvicorn backend.app:app` from the project root keep working.
"""

try:
    from backend.api.routes import app
except ModuleNotFoundError:
    from api.routes import app
