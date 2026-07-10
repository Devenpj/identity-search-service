"""InsightFace embedding service used by the isolated face engine API."""

import os
import time
from functools import lru_cache

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from insightface.utils import face_align


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
FACE_ENGINE_DET_THRESHOLD = float(
    os.environ.get(
        "FACE_ENGINE_DET_THRESHOLD",
        "0.35"
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
        det_thresh=FACE_ENGINE_DET_THRESHOLD,
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


def extract_embedding(image_path, assume_cropped=False):
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
        file_stats.st_size,
        bool(assume_cropped)
    )


@lru_cache(maxsize=10000)
def _extract_embedding_cached(
    image_path,
    modified_time,
    file_size,
    assume_cropped
):
    """Compute and cache one face embedding until the source file changes."""

    image = load_image(image_path)
    app = load_face_app()
    detection_image = image
    faces = app.get(detection_image)
    face = largest_face(faces)

    if face is None and min(image.shape[:2]) < 320:
        scale = min(
            4.0,
            max(2.0, 320.0 / max(1, min(image.shape[:2])))
        )
        detection_image = cv2.resize(
            image,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )
        faces = app.get(detection_image)
        face = largest_face(faces)

    extraction_method = "detected_face"

    if face is None and assume_cropped:
        height, width = image.shape[:2]
        aspect_ratio = width / max(1, height)

        if min(height, width) < 64 or not 0.65 <= aspect_ratio <= 1.55:

            raise ValueError(
                f"No face detected and image is not a valid profile crop: {image_path}"
            )

        recognition_model = app.models.get("recognition")

        if recognition_model is None:

            raise ValueError("InsightFace recognition model is unavailable")

        aligned_crop = cv2.resize(
            image,
            (112, 112),
            interpolation=cv2.INTER_CUBIC
        )
        embedding = np.asarray(
            recognition_model.get_feat(aligned_crop),
            dtype=np.float32
        ).reshape(-1)
        embedding_norm = float(np.linalg.norm(embedding))

        if embedding_norm <= 0:

            raise ValueError(f"Could not encode cropped profile image: {image_path}")

        embedding = embedding / embedding_norm
        bbox = [0.0, 0.0, float(width), float(height)]
        detection_score = None
        extraction_method = "trusted_profile_crop"

    elif face is None:

        raise ValueError(f"No face detected in image: {image_path}")

    else:
        embedding = np.asarray(
            face.normed_embedding,
            dtype=np.float32
        )
        bbox = [
            round(float(value), 2)
            for value in face.bbox
        ]
        detection_score = round(float(face.det_score), 4)

    return {
        "embedding": embedding,
        "quality": image_quality(image),
        "bbox": bbox,
        "det_score": detection_score,
        "extraction_method": extraction_method
    }


def embedding_payload(image_path, assume_cropped=False):
    """Return one JSON-safe normalized embedding and its extraction metadata."""

    extracted = extract_embedding(image_path, assume_cropped=assume_cropped)
    embedding = np.asarray(
        extracted["embedding"],
        dtype=np.float32
    )

    return {
        "embedding": embedding.tolist(),
        "dimension": int(embedding.shape[0]),
        "model_name": FACE_ENGINE_MODEL,
        "quality": extracted["quality"],
        "bbox": extracted["bbox"],
        "det_score": extracted["det_score"],
        "extraction_method": extracted["extraction_method"]
    }


def _safe_file_part(value):
    """Keep generated crop filenames readable and filesystem-safe."""

    return "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in str(value or "face")
    ).strip("_") or "face"


def _square_padded_crop(image, bbox, padding_ratio=0.22):
    """Crop one face as a padded square so dashboard thumbnails look stable."""

    height, width = image.shape[:2]
    x1, y1, x2, y2 = [float(value) for value in bbox]
    face_width = max(1.0, x2 - x1)
    face_height = max(1.0, y2 - y1)
    center_x = x1 + face_width / 2.0
    center_y = y1 + face_height / 2.0
    side = max(face_width, face_height) * (1.0 + padding_ratio)
    crop_x1 = max(0, int(round(center_x - side / 2.0)))
    crop_y1 = max(0, int(round(center_y - side / 2.0)))
    crop_x2 = min(width, int(round(center_x + side / 2.0)))
    crop_y2 = min(height, int(round(center_y + side / 2.0)))

    if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:

        raise ValueError("Invalid face crop bounds")

    return image[crop_y1:crop_y2, crop_x1:crop_x2]




def _aligned_face_crop(image, face, fallback_bbox, image_size=256):
    """Use InsightFace landmarks for a centered, pose-normalized face crop."""

    keypoints = getattr(face, "kps", None)

    if keypoints is not None:
        try:
            aligned_crop = face_align.norm_crop(
                image,
                landmark=keypoints,
                image_size=image_size
            )

            if aligned_crop is not None and aligned_crop.size > 0:

                return aligned_crop, "insightface_landmark_aligned"

        except Exception:
            pass

    return _square_padded_crop(
        image,
        fallback_bbox
    ), "bbox_square_fallback"
def _enhance_face_crop(crop):
    """Keep a detected face crop natural while making tiny crops reviewable."""

    if crop is None or crop.size == 0:

        raise ValueError("Cannot enhance an empty face crop")

    enhanced = crop.copy()
    height, width = enhanced.shape[:2]
    min_side = min(height, width)

    if min_side < 224:
        scale = min(
            2.5,
            max(1.0, 224.0 / max(1, min_side))
        )
        enhanced = cv2.resize(
            enhanced,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC
        )

    gray_image = cv2.cvtColor(
        enhanced,
        cv2.COLOR_BGR2GRAY
    )
    brightness = float(np.mean(gray_image))

    if brightness < 65 or brightness > 195:
        lab_image = cv2.cvtColor(
            enhanced,
            cv2.COLOR_BGR2LAB
        )
        lightness, channel_a, channel_b = cv2.split(lab_image)
        clahe = cv2.createCLAHE(
            clipLimit=1.2,
            tileGridSize=(8, 8)
        )
        lightness = clahe.apply(lightness)
        enhanced = cv2.cvtColor(
            cv2.merge((lightness, channel_a, channel_b)),
            cv2.COLOR_LAB2BGR
        )

    enhanced = cv2.fastNlMeansDenoisingColored(
        enhanced,
        None,
        1,
        1,
        5,
        15
    )

    return enhanced

def detect_faces_payload(image_path, output_dir, output_prefix):
    """Detect all faces in one frame, save crops, and return embeddings."""

    image = load_image(image_path)
    app = load_face_app()
    faces = app.get(image)
    os.makedirs(output_dir, exist_ok=True)
    safe_prefix = _safe_file_part(output_prefix)
    detected_faces = []

    for face_index, face in enumerate(faces, start=1):

        embedding = np.asarray(
            face.normed_embedding,
            dtype=np.float32
        )
        embedding_norm = float(np.linalg.norm(embedding))

        if embedding_norm <= 0:

            continue

        embedding = embedding / embedding_norm
        bbox = [
            round(float(value), 2)
            for value in face.bbox
        ]
        crop, crop_method = _aligned_face_crop(
            image,
            face,
            bbox
        )
        enhanced_crop = _enhance_face_crop(crop)
        crop_filename = f"{safe_prefix}_face_{face_index}.jpg"
        crop_path = os.path.abspath(
            os.path.join(
                output_dir,
                crop_filename
            )
        )
        cv2.imwrite(
            crop_path,
            enhanced_crop,
            [int(cv2.IMWRITE_JPEG_QUALITY), 95]
        )
        detected_faces.append(
            {
                "face_image_path": crop_path,
                "bbox": bbox,
                "det_score": round(float(face.det_score), 4),
                "embedding": embedding.tolist(),
                "quality": image_quality(enhanced_crop),
                "enhanced": True,
                "crop_method": crop_method,
                "model_name": FACE_ENGINE_MODEL
            }
        )

    return detected_faces
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