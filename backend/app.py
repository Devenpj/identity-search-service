"""FastAPI application entrypoint.

The route handlers live in `backend/api/routes.py`. This file stays small so
existing commands such as `python -m uvicorn app:app` from the backend folder
and `python -m uvicorn backend.app:app` from the project root keep working.
"""

try:
    from backend.api.routes import app
except ModuleNotFoundError:
    from api.routes import app


"""Because your startup flow is:
cd backend
uvicorn app:app --reload
That command specifically looks for:
backend/app.py
app
"""
