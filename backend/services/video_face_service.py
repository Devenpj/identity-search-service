"""Incremental video face detection service."""

import math
import os
from urllib.parse import urljoin

import cv2
import numpy as np
import requests

try:
    from backend.config import settings
except ImportError:
    from config import settings

from utils.logger import get_logger


logger = get_logger("identity-search-service.video-face")


class VideoFaceProcessingService:
    """Sample videos, detect unique faces, and wait for reviewer-selected verification."""

    def __init__(self):
        """Prepare upload folders used for sampled frames and detected face crops."""

        self.frame_dir = os.path.join(
            settings.BACKEND_ROOT,
            "uploads",
            "video_frames"
        )
        self.face_dir = os.path.join(
            settings.BACKEND_ROOT,
            "uploads",
            "video_faces"
        )
        os.makedirs(self.frame_dir, exist_ok=True)
        os.makedirs(self.face_dir, exist_ok=True)

    def process_job(
        self,
        job_id,
        video_path,
        database_service,
        face_service
    ):
        """Run one video job and commit every detected unique face immediately."""

        if not self._engine_enabled():

            raise ValueError(
                "InsightFace engine is not configured. Start face_engine on "
                "FACE_ENGINE_URL before running video face search."
            )

        capture = cv2.VideoCapture(video_path)

        if not capture.isOpened():

            raise ValueError(f"Could not open uploaded video: {video_path}")

        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            if fps <= 0:
                fps = 25.0

            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            sample_every_frames = max(
                1,
                int(round(fps * max(settings.VIDEO_FACE_SAMPLE_SECONDS, 0.2)))
            )
            max_sampled_frames = max(
                1,
                int(settings.VIDEO_FACE_MAX_SAMPLED_FRAMES or 600)
            )
            expected_samples = self._expected_sample_count(
                total_frames,
                sample_every_frames,
                max_sampled_frames
            )

            database_service.mark_video_face_job_processing(
                job_id,
                total_frames
            )
            logger.info(
                "Video face job started: job_id=%s total_frames=%s fps=%.2f sample_every_frames=%s expected_samples=%s",
                job_id,
                total_frames,
                fps,
                sample_every_frames,
                expected_samples
            )

            known_embeddings = []
            sampled_frames = 0
            unique_faces = 0

            for frame_number in self._sample_frame_numbers(
                total_frames,
                sample_every_frames,
                max_sampled_frames
            ):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                success, frame = capture.read()

                if not success or frame is None:

                    continue

                sampled_frames += 1
                frame_path = self._save_frame(
                    job_id,
                    frame_number,
                    frame
                )
                timestamp_seconds = round(frame_number / fps, 2)
                detections = self._detect_faces(
                    frame_path,
                    job_id,
                    frame_number
                )

                for detection in detections:
                    embedding = np.asarray(
                        detection.get("embedding") or [],
                        dtype=np.float32
                    )

                    if embedding.shape != (512,):

                        continue

                    if self._is_duplicate_face(
                        embedding,
                        known_embeddings
                    ):

                        continue

                    known_embeddings.append(embedding)
                    unique_faces += 1
                    detection.update(
                        {
                            "frame_number": frame_number,
                            "timestamp_seconds": timestamp_seconds
                        }
                    )
                    detected_face = database_service.insert_video_detected_face(
                        job_id,
                        detection
                    )
                    logger.info(
                        "Video face detected: job_id=%s face_id=%s frame=%s timestamp=%s image=%s",
                        job_id,
                        detected_face.get("face_id"),
                        frame_number,
                        timestamp_seconds,
                        detected_face.get("face_image_path")
                    )


                progress_percent = self._progress_percent(
                    sampled_frames,
                    expected_samples
                )
                database_service.update_video_face_job_progress(
                    job_id,
                    sampled_frames,
                    unique_faces,
                    progress_percent,
                    f"Processed {sampled_frames}/{expected_samples} sampled frames. Found {unique_faces} unique faces."
                )

            result_payload = {
                "status": "success",
                "total_frames": total_frames,
                "sampled_frames_processed": sampled_frames,
                "unique_faces_detected": unique_faces,
                "sample_every_seconds": settings.VIDEO_FACE_SAMPLE_SECONDS,
                "dedup_threshold": settings.VIDEO_FACE_DEDUP_THRESHOLD
            }
            database_service.complete_video_face_search_job(
                job_id,
                result_payload
            )
            logger.info(
                "Video face job completed: job_id=%s sampled_frames=%s unique_faces=%s",
                job_id,
                sampled_frames,
                unique_faces
            )

        finally:
            capture.release()

    def _detect_faces(
        self,
        frame_path,
        job_id,
        frame_number
    ):
        """Ask the isolated InsightFace engine to detect and crop frame faces."""

        response = requests.post(
            self._engine_url("/detect-faces"),
            json={
                "image_path": frame_path,
                "output_dir": self.face_dir,
                "output_prefix": f"{job_id}_frame_{frame_number}"
            },
            timeout=settings.FACE_ENGINE_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "success":

            raise ValueError(
                payload.get("message") or "Face engine could not detect video faces"
            )

        return payload.get("faces") or []

    def _save_frame(
        self,
        job_id,
        frame_number,
        frame
    ):
        """Save one sampled frame for the isolated face engine to read."""

        frame_path = os.path.abspath(
            os.path.join(
                self.frame_dir,
                f"{job_id}_frame_{frame_number}.jpg"
            )
        )
        cv2.imwrite(
            frame_path,
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 88]
        )

        return frame_path

    def _is_duplicate_face(
        self,
        embedding,
        known_embeddings
    ):
        """Return True when a face is already represented by an earlier crop."""

        if not known_embeddings:

            return False

        threshold = float(settings.VIDEO_FACE_DEDUP_THRESHOLD)
        normalized = embedding / max(float(np.linalg.norm(embedding)), 1e-8)

        for known_embedding in known_embeddings:
            known_normalized = known_embedding / max(
                float(np.linalg.norm(known_embedding)),
                1e-8
            )
            score = float(np.dot(normalized, known_normalized))

            if score >= threshold:

                return True

        return False

    def _sample_frame_numbers(
        self,
        total_frames,
        sample_every_frames,
        max_sampled_frames
    ):
        """Yield frame numbers to inspect without decoding the whole video."""

        if total_frames > 0:
            yielded = 0

            for frame_number in range(0, total_frames, sample_every_frames):
                if yielded >= max_sampled_frames:
                    break

                yielded += 1
                yield frame_number

            return

        for frame_number in range(max_sampled_frames):
            yield frame_number * sample_every_frames

    @staticmethod
    def _expected_sample_count(
        total_frames,
        sample_every_frames,
        max_sampled_frames
    ):
        """Estimate samples for progress text."""

        if total_frames <= 0:

            return max_sampled_frames

        return min(
            max_sampled_frames,
            max(1, int(math.ceil(total_frames / sample_every_frames)))
        )

    @staticmethod
    def _progress_percent(
        sampled_frames,
        expected_samples
    ):
        """Map sampled-frame progress into a stable 10-95 percent range."""

        if expected_samples <= 0:

            return 15

        return min(
            95,
            10 + int((sampled_frames / expected_samples) * 85)
        )

    @staticmethod
    def _engine_enabled():
        """Return True when the isolated InsightFace service URL is configured."""

        return bool(str(settings.FACE_ENGINE_URL or "").strip())

    @staticmethod
    def _engine_url(path):
        """Build a face-engine endpoint URL."""

        return urljoin(
            f"{settings.FACE_ENGINE_URL.rstrip('/')}/",
            path.lstrip("/")
        )