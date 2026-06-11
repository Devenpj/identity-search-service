"""OpenCV-based face comparison used by document and face search flows."""

import os

import cv2
import numpy as np


class FaceVerificationService:
    """Detect faces and compare them with a lightweight OpenCV similarity score."""

    def __init__(
        self,
        match_threshold=0.60,
        target_size=(128, 128)
    ):
        """Load the Haar cascade once and store comparison tuning values."""

        self.match_threshold = match_threshold
        self.target_size = target_size
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

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

        uploaded_image, uploaded_error = self._load_image(uploaded_face_path)
        database_image, database_error = self._load_image(resolved_database_path)

        if uploaded_image is None:

            return self._error_result(uploaded_error)

        if database_image is None:

            return self._error_result(database_error)

        uploaded_face = self._extract_face(uploaded_image)
        database_face = self._extract_face(database_image)

        if uploaded_face is None:

            uploaded_face = uploaded_image

        if database_face is None:

            database_face = database_image

        uploaded_face = cv2.resize(
            uploaded_face,
            self.target_size
        )
        database_face = cv2.resize(
            database_face,
            self.target_size
        )

        score = self._blended_score(
            uploaded_face,
            database_face
        )

        return {
            "matched": score >= self.match_threshold,
            "score": round(score, 4),
            "threshold": self.match_threshold,
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

        best_person = None
        best_result = None

        for person in database_people:

            photo_path = person.get("photo_path")

            if not photo_path:

                continue

            result = self.compare_faces(
                uploaded_face_path,
                photo_path
            )

            if result.get("error"):

                continue

            if best_result is None or result.get("score", 0.0) > best_result.get("score", 0.0):

                best_result = result
                best_person = person

        if best_result is None:

            return {
                "matched": False,
                "best_score": 0.0,
                "best_match": None,
                "face_verification": {
                    "matched": False,
                    "score": 0.0,
                    "threshold": self.match_threshold,
                    "method": "opencv_histogram_ncc",
                    "error": "No comparable database photos were found"
                }
            }

        return {
            "matched": best_result.get("matched", False),
            "best_score": best_result.get("score", 0.0),
            "best_match": best_person if best_result.get("matched", False) else None,
            "face_verification": best_result
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

    def _extract_face(self, image):
        """Find the largest detected face and return a padded crop."""

        gray_image = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )
        gray_image = cv2.equalizeHist(gray_image)

        faces = self.face_cascade.detectMultiScale(
            gray_image,
            scaleFactor=1.05,
            minNeighbors=4,
            minSize=(40, 40)
        )

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

    def _blended_score(
        self,
        image_one,
        image_two
    ):
        """Blend color and structure scores into the final face score."""

        return (
            0.40 * self._histogram_score(image_one, image_two)
            + 0.60 * self._structural_score(image_one, image_two)
        )

    def _error_result(self, message):
        """Return a standard failed face-comparison payload."""

        return {
            "matched": False,
            "score": 0.0,
            "threshold": self.match_threshold,
            "method": "opencv_histogram_ncc",
            "error": message
        }
