"""OpenCV-based face comparison used by document and face search flows."""

import os
import threading
from urllib.parse import urljoin

import cv2
import numpy as np
import requests

try:
    from backend.config import settings
except ImportError:
    from config import settings


class FaceVerificationService:
    """Detect faces and compare them with a lightweight OpenCV similarity score."""

    def __init__(
        self,
        match_threshold=None,
        min_score_gap=None,
        target_size=(128, 128)
    ):
        """Load the Haar cascade once and store comparison tuning values."""

        self.match_threshold = (
            float(match_threshold)
            if match_threshold is not None
            else float(settings.FACE_MATCH_THRESHOLD)
        )
        self.min_score_gap = (
            float(min_score_gap)
            if min_score_gap is not None
            else float(settings.FACE_MIN_SCORE_GAP)
        )
        self.strong_match_threshold = float(
            settings.FACE_STRONG_MATCH_THRESHOLD
        )
        self.target_size = target_size
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self._cascade_lock = threading.Lock()

    def compare_faces(
        self,
        uploaded_face_path,
        database_face_path
    ):
        """Compare two image paths and return match status, score, and evidence.

        The method tries to crop faces first. If no face is detected, it falls
        back to the full image so low-quality documents can still be scored.
        """

        if not uploaded_face_path:

            return {
                "matched": False,
                "score": 0.0,
                "method": "opencv_histogram_ncc",
                "error": "No face was extracted from uploaded document"
            }

        resolved_database_path = self.resolve_database_photo_path(
            database_face_path
        )

        external_result = self._compare_with_external_engine(
            uploaded_face_path,
            resolved_database_path
        )

        if external_result:

            return external_result

        uploaded_image, uploaded_error = self._load_image(uploaded_face_path)
        database_image, database_error = self._load_image(resolved_database_path)

        if uploaded_image is None:

            return self._error_result(uploaded_error)

        if database_image is None:

            return self._error_result(database_error)

        uploaded_face = self._prepare_face_for_scoring(uploaded_image)
        database_face = self._prepare_face_for_scoring(database_image)

        score_details = self._score_details(
            uploaded_face,
            database_face
        )
        score = score_details["score"]

        return {
            "matched": score >= self.match_threshold,
            "score": round(score, 4),
            "score_details": score_details,
            "threshold": self.match_threshold,
            "min_score_gap": self.min_score_gap,
            "strong_match_threshold": self.strong_match_threshold,
            "method": "opencv_histogram_ncc",
            "uploaded_face_path": uploaded_face_path,
            "database_face_path": resolved_database_path,
            "error": None
        }

    def find_best_database_match(
        self,
        uploaded_face_path,
        database_people
    ):
        """Compare one uploaded face against all database photos and keep best hit."""

        if not uploaded_face_path:

            return self._no_comparable_faces_result(
                "No face image was uploaded for comparison"
            )

        external_result = self._find_best_with_external_engine(
            uploaded_face_path,
            database_people
        )

        if external_result:

            return external_result

        uploaded_image, uploaded_error = self._load_image(uploaded_face_path)

        if uploaded_image is None:

            return self._no_comparable_faces_result(uploaded_error)

        uploaded_face = self._prepare_face_for_scoring(uploaded_image)
        best_person = None
        best_result = None
        candidate_results = []

        for person in database_people:

            photo_path = person.get("photo_path")

            if not photo_path:

                continue

            result = self._compare_prepared_uploaded_face(
                uploaded_face,
                uploaded_face_path,
                photo_path
            )

            if result.get("error"):

                continue

            candidate_results.append(
                self._candidate_summary(
                    person,
                    result
                )
            )

            if best_result is None or result.get("score", 0.0) > best_result.get("score", 0.0):

                best_result = result
                best_person = person

        if best_result is None:

            return self._no_comparable_faces_result(
                "No comparable database photos were found"
            )

        candidate_results.sort(
            key=lambda candidate: candidate.get("score", 0.0),
            reverse=True
        )
        second_best_score = (
            candidate_results[1].get("score", 0.0)
            if len(candidate_results) > 1
            else 0.0
        )
        best_score = best_result.get("score", 0.0)
        score_gap = round(
            best_score - second_best_score,
            4
        )
        confident_match = (
            best_result.get("matched", False)
            and (
                score_gap >= self.min_score_gap
                or best_score >= self.strong_match_threshold
            )
        )

        best_result["second_best_score"] = round(second_best_score, 4)
        best_result["score_gap"] = score_gap
        best_result["strong_match_threshold"] = self.strong_match_threshold

        if not confident_match and best_result.get("matched", False):
            best_result["matched"] = False
            best_result["error"] = (
                "Ambiguous face match. Best candidate is too close to another "
                "database photo, so the system did not auto-verify the identity."
            )

        return {
            "matched": confident_match,
            "best_score": best_score,
            "second_best_score": second_best_score,
            "score_gap": score_gap,
            "best_match": best_person if confident_match else None,
            "face_verification": best_result,
            "top_candidates": candidate_results[:5]
        }

    def _compare_with_external_engine(
        self,
        uploaded_face_path,
        resolved_database_path
    ):
        """Use the isolated InsightFace service for one-to-one verification."""

        if not self._external_engine_enabled():

            return None

        try:

            response = requests.post(
                self._engine_url("/verify"),
                json={
                    "probe_image_path": uploaded_face_path,
                    "candidate_image_path": resolved_database_path
                },
                timeout=settings.FACE_ENGINE_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            payload = response.json()

            if payload.get("status") != "success":

                raise ValueError(
                    payload.get("message") or "Face engine returned an error"
                )

            result = payload.get("face_verification") or {}
            result["uploaded_face_path"] = uploaded_face_path
            result["database_face_path"] = resolved_database_path

            return result

        except Exception as error:

            print(
                "Face engine unavailable for pair verification; "
                f"falling back to OpenCV. Reason: {error}"
            )

            return None

    def _find_best_with_external_engine(
        self,
        uploaded_face_path,
        database_people
    ):
        """Use the isolated InsightFace service for one-to-many face search."""

        if not self._external_engine_enabled():

            return None

        candidates = []

        for person in database_people:

            photo_path = person.get("photo_path")

            if not photo_path:

                continue

            candidates.append(
                {
                    "employee_id": person.get("employee_id"),
                    "full_name": person.get("full_name"),
                    "photo_path": self.resolve_database_photo_path(photo_path)
                }
            )

        if not candidates:

            return None

        try:

            batch_size = int(
                getattr(
                    settings,
                    "FACE_ENGINE_BATCH_SIZE",
                    100
                )
            )
            batch_results = []

            for batch_number, batch in enumerate(
                self._chunks(
                    candidates,
                    batch_size
                ),
                start=1
            ):

                print(
                    "Face engine batch search started: "
                    f"batch={batch_number} size={len(batch)} "
                    f"total_candidates={len(candidates)}"
                )
                response = requests.post(
                    self._engine_url("/search"),
                    json={
                        "probe_image_path": uploaded_face_path,
                        "candidates": batch
                    },
                    timeout=settings.FACE_ENGINE_TIMEOUT_SECONDS
                )
                response.raise_for_status()
                payload = response.json()

                if payload.get("status") != "success":

                    raise ValueError(
                        payload.get("message") or "Face engine returned an error"
                    )

                batch_result = payload.get("result") or {}
                batch_results.append(batch_result)
                print(
                    "Face engine batch search completed: "
                    f"batch={batch_number} best_score={batch_result.get('best_score')}"
                )

            result = self._merge_external_face_results(batch_results)
            face_verification = result.get("face_verification") or {}
            face_verification["uploaded_face_path"] = uploaded_face_path
            result["face_verification"] = face_verification
            best_match = result.get("best_match") or {}
            best_employee_id = best_match.get("employee_id")

            if best_employee_id:

                for person in database_people:

                    if person.get("employee_id") == best_employee_id:

                        result["best_match"] = person
                        break

            return result

        except Exception as error:

            print(
                "Face engine unavailable for database search; "
                f"falling back to OpenCV. Reason: {error}"
            )

            return None

    def _merge_external_face_results(
        self,
        batch_results
    ):
        """Merge multiple face-engine batch responses into one ranked result."""

        all_candidates = []

        for batch_result in batch_results or []:

            all_candidates.extend(
                batch_result.get("top_candidates") or []
            )

        all_candidates.sort(
            key=lambda candidate: candidate.get("score", 0.0),
            reverse=True
        )

        best_candidate = all_candidates[0] if all_candidates else None
        second_best_score = (
            all_candidates[1].get("score", 0.0)
            if len(all_candidates) > 1
            else 0.0
        )
        best_score = best_candidate.get("score", 0.0) if best_candidate else 0.0
        score_gap = round(
            best_score - second_best_score,
            4
        )
        confident_match = bool(
            best_candidate
            and best_candidate.get("matched_raw_threshold")
            and (
                score_gap >= 0.05
                or best_score >= 0.45
            )
        )

        return {
            "matched": confident_match,
            "best_score": best_score,
            "second_best_score": second_best_score,
            "score_gap": score_gap,
            "best_match": (
                {
                    "employee_id": best_candidate.get("employee_id"),
                    "full_name": best_candidate.get("full_name"),
                    "photo_path": best_candidate.get("photo_path")
                }
                if confident_match and best_candidate
                else None
            ),
            "face_verification": {
                "matched": confident_match,
                "score": best_score,
                "second_best_score": second_best_score,
                "score_gap": score_gap,
                "threshold": 0.38,
                "min_score_gap": 0.05,
                "strong_match_threshold": 0.45,
                "method": "insightface_arcface_cosine_batched",
                "database_face_path": (
                    best_candidate.get("photo_path")
                    if best_candidate
                    else None
                ),
                "error": (
                    None
                    if confident_match
                    else "No confident InsightFace match was found."
                )
            },
            "top_candidates": all_candidates[:5]
        }

    def _chunks(
        self,
        values,
        chunk_size
    ):
        """Yield list chunks for timeout-safe face-engine requests."""

        chunk_size = max(
            1,
            int(chunk_size or 100)
        )

        for index in range(
            0,
            len(values),
            chunk_size
        ):

            yield values[index:index + chunk_size]

    def _external_engine_enabled(self):
        """Return True when the optional isolated face service is configured."""

        return bool(
            str(settings.FACE_ENGINE_URL or "").strip()
        )

    def _engine_url(self, path):
        """Build a face-engine endpoint URL from configured base URL."""

        return urljoin(
            f"{settings.FACE_ENGINE_URL.rstrip('/')}/",
            path.lstrip("/")
        )

    def _compare_prepared_uploaded_face(
        self,
        uploaded_face,
        uploaded_face_path,
        database_face_path
    ):
        """Compare a cached uploaded face crop against one database photo."""

        resolved_database_path = self.resolve_database_photo_path(
            database_face_path
        )
        database_image, database_error = self._load_image(resolved_database_path)

        if database_image is None:

            return self._error_result(database_error)

        database_face = self._prepare_face_for_scoring(database_image)
        score_details = self._score_details(
            uploaded_face,
            database_face
        )
        score = score_details["score"]

        return {
            "matched": score >= self.match_threshold,
            "score": round(score, 4),
            "score_details": score_details,
            "threshold": self.match_threshold,
            "min_score_gap": self.min_score_gap,
            "strong_match_threshold": self.strong_match_threshold,
            "method": "opencv_histogram_ncc",
            "uploaded_face_path": uploaded_face_path,
            "database_face_path": resolved_database_path,
            "error": None
        }

    def resolve_database_photo_path(self, database_face_path):
        """Convert stored relative photo paths into local filesystem paths."""

        if not database_face_path:

            return ""

        if os.path.isabs(database_face_path) and os.path.exists(database_face_path):

            return database_face_path

        relative_path = database_face_path.lstrip("/\\")
        project_root = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                ".."
            )
        )

        candidates = [
            os.path.join(project_root, relative_path),
            os.path.join(project_root, "frontend", relative_path),
            os.path.join(
                r"C:\AIProjects\indian-id-validator",
                relative_path
            )
        ]

        for candidate in candidates:

            if os.path.exists(candidate):

                return candidate

        return candidates[1]

    def _load_image(self, image_path):
        """Read an image from disk and return a clear error message on failure."""

        if not image_path:

            return None, "Image path is empty"

        image = cv2.imread(image_path)

        if image is None:

            return None, f"Could not load image: {image_path}"

        return image, None

    def _prepare_face_for_scoring(self, image):
        """Extract the largest face once and resize it for repeated scoring."""

        face = self._extract_face(image)

        if face is None:

            face = image

        return cv2.resize(
            face,
            self.target_size
        )

    def _extract_face(self, image):
        """Find the largest detected face and return a padded crop."""

        if image is None or image.size == 0:

            return None

        if self.face_cascade.empty():

            return None

        gray_image = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )
        gray_image = cv2.equalizeHist(gray_image)
        gray_image = np.ascontiguousarray(
            gray_image,
            dtype=np.uint8
        )

        try:
            with self._cascade_lock:
                faces = self.face_cascade.detectMultiScale(
                    gray_image,
                    scaleFactor=1.05,
                    minNeighbors=4,
                    minSize=(40, 40)
                )
        except cv2.error:

            return None

        if len(faces) == 0:

            return None

        x, y, width, height = max(
            faces,
            key=lambda face: face[2] * face[3]
        )
        image_height, image_width = image.shape[:2]
        padding = int(min(width, height) * 0.15)

        x1 = max(0, x - padding)
        y1 = max(0, y - padding)
        x2 = min(image_width, x + width + padding)
        y2 = min(image_height, y + height + padding)

        return image[y1:y2, x1:x2]

    def _histogram_score(
        self,
        image_one,
        image_two
    ):
        """Compare color-channel histograms as one part of face similarity."""

        scores = []

        for channel in range(3):

            hist_one = cv2.calcHist(
                [image_one],
                [channel],
                None,
                [64],
                [0, 256]
            )
            hist_two = cv2.calcHist(
                [image_two],
                [channel],
                None,
                [64],
                [0, 256]
            )

            cv2.normalize(hist_one, hist_one)
            cv2.normalize(hist_two, hist_two)

            scores.append(
                cv2.compareHist(
                    hist_one,
                    hist_two,
                    cv2.HISTCMP_CORREL
                )
            )

        return float(np.clip(np.mean(scores), 0.0, 1.0))

    def _structural_score(
        self,
        image_one,
        image_two
    ):
        """Compare grayscale structure using normalized cross-correlation."""

        gray_one = cv2.cvtColor(
            image_one,
            cv2.COLOR_BGR2GRAY
        ).astype(np.float32)
        gray_two = cv2.cvtColor(
            image_two,
            cv2.COLOR_BGR2GRAY
        ).astype(np.float32)

        score = np.mean(
            (gray_one - gray_one.mean()) * (gray_two - gray_two.mean())
        )
        score = score / (
            gray_one.std() * gray_two.std() + 1e-6
        )

        return float(np.clip((score + 1) / 2, 0.0, 1.0))

    def _score_details(
        self,
        image_one,
        image_two
    ):
        """Return each OpenCV score component plus the final blended score."""

        histogram_score = self._histogram_score(
            image_one,
            image_two
        )
        structural_score = self._structural_score(
            image_one,
            image_two
        )
        score = (
            0.30 * histogram_score
            + 0.70 * structural_score
        )

        return {
            "histogram_score": round(histogram_score, 4),
            "structural_score": round(structural_score, 4),
            "score": round(float(score), 4)
        }

    def _candidate_summary(
        self,
        person,
        result
    ):
        """Return a compact ranked candidate payload for face-search review."""

        return {
            "employee_id": person.get("employee_id"),
            "full_name": person.get("full_name"),
            "score": result.get("score", 0.0),
            "matched_raw_threshold": result.get("matched", False),
            "photo_path": result.get("database_face_path"),
            "score_details": result.get("score_details", {})
        }

    def _error_result(self, message):
        """Return a standard failed face-comparison payload."""

        return {
            "matched": False,
            "score": 0.0,
            "threshold": self.match_threshold,
            "min_score_gap": self.min_score_gap,
            "strong_match_threshold": self.strong_match_threshold,
            "method": "opencv_histogram_ncc",
            "error": message
        }

    def _no_comparable_faces_result(self, message):
        """Return the standard no-match payload for failed face-search setup."""

        return {
            "matched": False,
            "best_score": 0.0,
            "second_best_score": 0.0,
            "score_gap": 0.0,
            "best_match": None,
            "face_verification": {
                "matched": False,
                "score": 0.0,
                "threshold": self.match_threshold,
                "min_score_gap": self.min_score_gap,
                "strong_match_threshold": self.strong_match_threshold,
                "method": "opencv_histogram_ncc",
                "error": message
            },
            "top_candidates": []
        }
