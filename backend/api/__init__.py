"""API package containing FastAPI route definitions for the backend.The blank __init__.py is just a package marker. It can be empty and still useful.backend/api/__init__.py does not run the app.
It only tells Python:
backend/api is a package
python -m uvicorn backend.api.routes:app
backend          package/folder
backend.api      package/folder, helped by backend/api/__init__.py
backend.api.routes  actual file: backend/api/routes.py
app              FastAPI object inside routes.py
"""
