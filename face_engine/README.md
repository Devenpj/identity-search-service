# Isolated InsightFace Engine

This service keeps the stronger face-recognition dependencies away from the
main identity-search backend and the Indian ID validator environment.

## Run

```powershell
cd face_engine
python -m venv .venv-face
.\.venv-face\Scripts\Activate.ps1
pip install -r requirements-face.txt
uvicorn app:app --host 127.0.0.1 --port 8010
```

Then set this in the main project's `.env`:

```env
FACE_ENGINE_URL=http://127.0.0.1:8010
FACE_ENGINE_TIMEOUT_SECONDS=60
```

Restart the main backend after changing `.env`.

## Endpoints

- `GET /health`
- `POST /verify` for one uploaded face against one candidate image
- `POST /search` for one uploaded face against many database candidates

The main backend falls back to the old OpenCV matcher if this service is not
running, so the project remains usable during setup.
