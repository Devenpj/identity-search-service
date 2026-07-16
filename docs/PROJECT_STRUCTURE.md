# Project Structure

This project is organized as a small company-style service with separate API,
service, model-engine, dashboard, migration, and documentation areas.

## Root

```text
identity-search-service/
`-- backend/                 FastAPI backend application
`-- frontend/                Streamlit operator dashboard
`-- face_engine/             Separate InsightFace microservice
`-- scripts/                 Operational scripts and backfills
`-- docs/                    Architecture, setup, and interview documentation
`-- utils/                   Shared cross-project utilities
`-- .streamlit/              Streamlit theme/runtime configuration
`-- requirements.txt         Main backend/dashboard dependencies
`-- .env.example             Safe environment variable template
`-- .gitignore               Runtime/generated file exclusions
`-- README.md                Primary project overview
```

## Backend

```text
backend/
`-- app.py                   FastAPI entrypoint
`-- config.py                Environment-driven settings
`-- api/
|   `-- __init__.py
|   `-- routes.py            HTTP endpoints and webhook routes
`-- services/
|   `-- database_service.py  Database coordinator and repository composer
|   `-- identity_repository.py
|   `-- job_repository.py
|   `-- osint_repository.py
|   `-- news_repository.py
|   `-- database_mixins.py
|   `-- document_verification_service.py
|   `-- ocr_service.py
|   `-- face_service.py
|   `-- video_face_service.py
|   `-- osint_service.py
|   `-- osint_normalizer_service.py
|   `-- news_database_service.py
|   `-- risk_service.py
|   `-- decision_service.py
|   `-- file_service.py
`-- migrations/             SQL migrations and seed files
`-- uploads/                Runtime uploads, ignored by Git
`-- vendor/                 Specialized Indian ID validator dependency
```

## Repository Layer

The database layer is intentionally split by responsibility:

- `database_service.py` opens the PostgreSQL connection and composes repository mixins.
- `identity_repository.py` handles identity search, admin CRUD, manual review, and face embeddings.
- `job_repository.py` handles face search, video face search, and document validation job tables.
- `osint_repository.py` handles OSINT jobs and normalized OSINT result storage.
- `news_repository.py` handles news clusters, articles, entities, topics, and ingestion events.
- `database_mixins.py` provides shared async job lifecycle helpers.

This keeps route code stable because the backend still imports one class:

```python
DatabaseService
```

## Face Engine

```text
face_engine/
`-- app.py                   FastAPI endpoints for face detection/search
`-- engine.py                InsightFace model loading and embedding logic
`-- requirements-face.txt    Isolated face-engine dependencies
`-- README.md                Face engine setup notes
```

The face engine is separated to avoid dependency conflicts with the document
OCR/vendor model stack.

## Frontend

```text
frontend/
`-- dashboard.py             Legacy Streamlit dashboard for all operator workflows

web/
|-- package.json             React/Vite scripts and dependencies
|-- index.html               Browser entrypoint
`-- src/
    |-- App.jsx              React workflow screens
    |-- api.js               FastAPI client helpers
    `-- styles.css           Modern dashboard theme
```

Runtime matched photos and generated previews are ignored by Git.

## Runtime Data

These folders are runtime-only and should not be committed:

- `uploads/`
- `backend/uploads/`
- `logs/`
- `results/`
- `frontend/matched_employee_photos/`
- virtual environments such as `.venv/` and `face_engine/.venv-face/`

## Professional Conventions

- Keep secrets in `.env`, never in Git.
- Keep dependency templates in `requirements.txt` and `face_engine/requirements-face.txt`.
- Keep schema changes in `backend/migrations/`.
- Keep generated logs/uploads/results out of Git.
- Keep long explanations in `docs/`.
- Keep one external-facing backend entrypoint: `backend/app.py`.
- Keep one dashboard entrypoint: `frontend/dashboard.py`.
