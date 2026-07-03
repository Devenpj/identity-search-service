# Persistent InsightFace Embeddings

## Architecture

Registered profile-photo embeddings are stored in the local `excel_import`
PostgreSQL database in `identity_face_embeddings`. This PostgreSQL installation
does not provide pgvector, so normalized 512-value ArcFace embeddings are stored
as `REAL[]` and searched in one vectorized NumPy cosine-similarity operation.

The isolated face engine exposes `POST /embedding`. The main backend calls this
endpoint, persists the returned vector, and keeps InsightFace dependencies out
of the Indian ID validator environment.

## Runtime Search

1. FastAPI saves the uploaded probe image.
2. InsightFace extracts one probe embedding.
3. PostgreSQL returns the 3,500 stored identity embeddings.
4. NumPy ranks all candidates in one matrix operation.
5. Existing threshold and score-gap rules produce the final match.
6. If embedding coverage is incomplete or the face engine is unavailable, the
   previous candidate-image/OpenCV workflow remains available as fallback.

## Enrollment

Admin create, admin photo update, and identity registration queue automatic
embedding generation. Identity deletion removes the matching embedding.
New uploads require face detection.

Legacy profile photos are already cropped portraits and can be enrolled with the
explicit detector-free compatibility mode used only by the backfill script.

## Backfill

Run the face engine in its own visible terminal:

```powershell
cd C:\AIProjects\identity-search-service\face_engine
.\.venv-face\Scripts\Activate.ps1
uvicorn app:app --host 127.0.0.1 --port 8010
```

Run/resume the foreground backfill from the project root:

```powershell
.\.venv\Scripts\python.exe scripts\backfill_face_embeddings.py
```

Useful options:

```text
--limit 250
--offset 1000
--employee-id IA202610039
--force
--progress-every 50
```

The script hashes each photo and skips unchanged vectors, making repeated runs
safe and resumable. Current enrollment coverage can be checked with
`DatabaseService.get_face_embedding_coverage()`.