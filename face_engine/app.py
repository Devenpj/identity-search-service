"""FastAPI wrapper around the isolated InsightFace recognition engine."""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from engine import embedding_payload
from engine import load_face_app
from engine import search_candidates
from engine import verify_pair


app = FastAPI(
    title="Identity Search Face Engine",
    version="1.0.0"
)


class EmbeddingRequest(BaseModel):
    """Request for extracting one normalized face embedding."""

    image_path: str
    assume_cropped: bool = False

class VerifyRequest(BaseModel):
    """Request for one-to-one face verification."""

    probe_image_path: str
    candidate_image_path: str


class SearchCandidate(BaseModel):
    """One database candidate used during one-to-many face search."""

    employee_id: str | None = None
    full_name: str | None = None
    photo_path: str
    record: dict[str, Any] | None = None


class SearchRequest(BaseModel):
    """Request for searching one probe face against many candidate faces."""

    probe_image_path: str
    candidates: list[SearchCandidate]


@app.get("/health")
def health():
    """Load the model if needed and report readiness."""

    load_face_app()

    return {
        "status": "ok",
        "engine": "insightface"
    }


@app.post("/embedding")
def embedding(request: EmbeddingRequest):
    """Extract one normalized InsightFace embedding for persistent storage/search."""

    try:

        return {
            "status": "success",
            "embedding": embedding_payload(
                request.image_path,
                assume_cropped=request.assume_cropped
            )
        }

    except Exception as error:

        return {
            "status": "error",
            "message": str(error)
        }

@app.post("/verify")
def verify(request: VerifyRequest):
    """Compare two images and return InsightFace cosine similarity."""

    try:

        return {
            "status": "success",
            "face_verification": verify_pair(
                request.probe_image_path,
                request.candidate_image_path
            )
        }

    except Exception as error:

        return {
            "status": "error",
            "message": str(error)
        }


@app.post("/search")
def search(request: SearchRequest):
    """Search one image against multiple database candidate photos."""

    try:

        candidates = [
            candidate.dict()
            for candidate in request.candidates
        ]

        return {
            "status": "success",
            "result": search_candidates(
                request.probe_image_path,
                candidates
            )
        }

    except Exception as error:

        return {
            "status": "error",
            "message": str(error)
        }
