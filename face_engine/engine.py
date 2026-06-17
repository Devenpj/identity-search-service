"""InsightFace embedding service used by the isolated face engine API."""

import os
import time
from functools import lru_cache

import cv2
import numpy as np
from insightface.app import FaceAnalysis


FACE_ENGINE_MODEL = os.environ.get(
    "FACE_ENGINE_MODEL",
    "buffalo_l"
)
FACE_ENGINE_PROVIDERS = [
    provider.strip()
    for provider in os.environ.get(
        "FACE_ENGINE_PROVIDERS",
        "CPUExecutionProvider"
    ).split(",")
    if provider.strip()
]
FACE_ENGINE_DET_SIZE = int(
    os.environ.get(
        "FACE_ENGINE_DET_SIZE",
        "640"
    )
)
FACE_ENGINE_THRESHOLD = float(
    os.environ.get(
        "FACE_ENGINE_THRESHOLD",
        "0.38"
    )
)
FACE_ENGINE_MIN_SCORE_GAP = float(
    os.environ.get(
        "FACE_ENGINE_MIN_SCORE_GAP",
        "0.05"
    )
)
FACE_ENGINE_STRONG_THRESHOLD = float(
    os.environ.get(
        "FACE_ENGINE_STRONG_THRESHOLD",
        "0.45"
    )
)


@lru_cache(maxsize=1)
def load_face_app():
    """Load InsightFace once per process."""

    app = FaceAnalysis(
        name=FACE_ENGINE_MODEL,
        providers=FACE_ENGINE_PROVIDERS
    )
    app.prepare(
        ctx_id=0,
        det_size=(
            FACE_ENGINE_DET_SIZE,
            FACE_ENGINE_DET_SIZE
        )
    )

    return app


def image_quality(image):
    """Return simple quality signals that help explain weak matches."""

    gray_image = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )
    blur_score = float(
        cv2.Laplacian(
            gray_image,
            cv2.CV_64F
        ).var()
    )
    brightness_score = float(
        np.mean(gray_image)
    )

    return {
        "blur_score": round(blur_score, 2),
        "brightness_score": round(brightness_score, 2),
        "blur": "low" if blur_score >= 80 else "high",
        "brightness": (
            "low"
            if brightness_score < 70
            else "high"
            if brightness_score > 190
            else "acceptable"
        )
    }


def load_image(image_path):
    """Load an image from disk and raise a clear error when it cannot be read."""

    if not image_path:

        raise ValueError("Image path is empty")

    image = cv2.imread(image_path)

    if image is None:

        raise ValueError(f"Could not load image: {image_path}")

    return image


def largest_face(faces):
    """Choose the largest detected face when an image contains multiple faces."""

    if not faces:

        return None

    return max(
        faces,
        key=lambda face: (
            face.bbox[2] - face.bbox[0]
        ) * (
            face.bbox[3] - face.bbox[1]
        )
    )


def extract_embedding(image_path):
    """Return a cached normalized face embedding for one image path."""

    if not image_path:

        raise ValueError("Image path is empty")

    resolved_path = os.path.abspath(image_path)

    if not os.path.exists(resolved_path):

        raise ValueError(f"Image does not exist: {resolved_path}")

    file_stats = os.stat(resolved_path)

    return _extract_embedding_cached(
        resolved_path,
        file_stats.st_mtime_ns,
        file_stats.st_size
    )


@lru_cache(maxsize=10000)
def _extract_embedding_cached(
    image_path,
    modified_time,
    file_size
):
    """Compute and cache one face embedding until the source file changes."""

    image = load_image(image_path)
    app = load_face_app()
    faces = app.get(image)
    face = largest_face(faces)

    if face is None:

        raise ValueError(f"No face detected in image: {image_path}")

    embedding = np.asarray(
        face.normed_embedding,
        dtype=np.float32
    )
    bbox = [
        round(float(value), 2)
        for value in face.bbox
    ]

    return {
        "embedding": embedding,
        "quality": image_quality(image),
        "bbox": bbox,
        "det_score": round(float(face.det_score), 4)
    }


def cosine_similarity(
    embedding_one,
    embedding_two
):
    """Compare two normalized embeddings with cosine similarity."""

    return float(
        np.dot(
            embedding_one,
            embedding_two
        )
    )


def verify_pair(
    probe_image_path,
    candidate_image_path
):
    """Verify whether two face images appear to be the same person."""

    probe = extract_embedding(probe_image_path)
    candidate = extract_embedding(candidate_image_path)
    score = round(
        cosine_similarity(
            probe["embedding"],
            candidate["embedding"]
        ),
        4
    )
    matched = score >= FACE_ENGINE_THRESHOLD

    return {
        "matched": matched,
        "score": score,
        "threshold": FACE_ENGINE_THRESHOLD,
        "min_score_gap": FACE_ENGINE_MIN_SCORE_GAP,
        "strong_match_threshold": FACE_ENGINE_STRONG_THRESHOLD,
        "method": "insightface_arcface_cosine",
        "quality": {
            "probe": probe["quality"],
            "candidate": candidate["quality"]
        },
        "face_detection": {
            "probe_bbox": probe["bbox"],
            "candidate_bbox": candidate["bbox"],
            "probe_det_score": probe["det_score"],
            "candidate_det_score": candidate["det_score"]
        },
        "error": None
    }


def search_candidates(
    probe_image_path,
    candidates
):
    """Search one probe image against many candidate profile photos."""

    started_at = time.perf_counter()
    probe = extract_embedding(probe_image_path)
    candidate_results = []
    total_candidates = len(candidates or [])

    print(
        "Face engine search started: "
        f"probe={probe_image_path} total_candidates={total_candidates}"
    )

    for index, candidate in enumerate(candidates, start=1):

        if index == 1 or index % 250 == 0 or index == total_candidates:

            print(
                "Face engine search progress: "
                f"{index}/{total_candidates} candidates processed"
            )

        try:

            candidate_embedding = extract_embedding(
                candidate.get("photo_path")
            )
            score = round(
                cosine_similarity(
                    probe["embedding"],
                    candidate_embedding["embedding"]
                ),
                4
            )
            candidate_results.append(
                {
                    "employee_id": candidate.get("employee_id"),
                    "full_name": candidate.get("full_name"),
                    "score": score,
                    "matched_raw_threshold": score >= FACE_ENGINE_THRESHOLD,
                    "photo_path": candidate.get("photo_path"),
                    "quality": candidate_embedding["quality"],
                    "score_details": {
                        "cosine_similarity": score
                    }
                }
            )

        except Exception as error:

            candidate_results.append(
                {
                    "employee_id": candidate.get("employee_id"),
                    "full_name": candidate.get("full_name"),
                    "score": 0.0,
                    "matched_raw_threshold": False,
                    "photo_path": candidate.get("photo_path"),
                    "error": str(error)
                }
            )

    candidate_results.sort(
        key=lambda candidate: candidate.get("score", 0.0),
        reverse=True
    )
    best_candidate = candidate_results[0] if candidate_results else None
    second_best_score = (
        candidate_results[1].get("score", 0.0)
        if len(candidate_results) > 1
        else 0.0
    )
    best_score = best_candidate.get("score", 0.0) if best_candidate else 0.0
    score_gap = round(
        best_score - second_best_score,
        4
    )
    confident_match = bool(
        best_candidate
        and best_score >= FACE_ENGINE_THRESHOLD
        and (
            score_gap >= FACE_ENGINE_MIN_SCORE_GAP
            or best_score >= FACE_ENGINE_STRONG_THRESHOLD
        )
    )
    best_record = None

    if confident_match:

        best_record = {
            "employee_id": best_candidate.get("employee_id"),
            "full_name": best_candidate.get("full_name"),
            "photo_path": best_candidate.get("photo_path")
        }

    face_verification = {
        "matched": confident_match,
        "score": best_score,
        "second_best_score": second_best_score,
        "score_gap": score_gap,
        "threshold": FACE_ENGINE_THRESHOLD,
        "min_score_gap": FACE_ENGINE_MIN_SCORE_GAP,
        "strong_match_threshold": FACE_ENGINE_STRONG_THRESHOLD,
        "method": "insightface_arcface_cosine",
        "uploaded_face_path": probe_image_path,
        "database_face_path": (
            best_candidate.get("photo_path")
            if best_candidate
            else None
        ),
        "quality": {
            "probe": probe["quality"],
            "best_candidate": (
                best_candidate.get("quality")
                if best_candidate
                else None
            )
        },
        "error": (
            None
            if confident_match
            else "No confident InsightFace match was found."
        )
    }

    elapsed_seconds = round(
        time.perf_counter() - started_at,
        2
    )

    print(
        "Face engine search completed: "
        f"matched={confident_match} best_score={best_score} "
        f"second_best_score={second_best_score} elapsed_seconds={elapsed_seconds}"
    )

    return {
        "matched": confident_match,
        "best_score": best_score,
        "second_best_score": second_best_score,
        "score_gap": score_gap,
        "best_match": best_record,
        "face_verification": face_verification,
        "top_candidates": candidate_results[:5]
    }
