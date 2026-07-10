import json

try:
    from utils.logger import get_logger
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from utils.logger import get_logger


logger = get_logger("identity-search-service.database")


class JobRepositoryMixin:
    """Repository methods split out of DatabaseService."""

    def _ensure_face_search_jobs_table(self):
        """Create the persisted face-search job table used for async polling."""

        query = """
        CREATE SEQUENCE IF NOT EXISTS face_search_job_number_seq START 1;

        CREATE TABLE IF NOT EXISTS face_search_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            uploaded_image_path TEXT NOT NULL,
            total_candidates INTEGER,
            progress_percent INTEGER NOT NULL DEFAULT 5,
            progress_message TEXT,
            result JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS total_candidates INTEGER;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 5;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS progress_message TEXT;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS result JSONB;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS error_message TEXT;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;

        ALTER TABLE face_search_jobs
        ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

        CREATE INDEX IF NOT EXISTS idx_face_search_jobs_status
        ON face_search_jobs(status);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_video_face_search_tables(self):
        """Create tables for incremental video face detection and matching."""

        query = """
        CREATE SEQUENCE IF NOT EXISTS video_face_job_number_seq START 1;

        CREATE TABLE IF NOT EXISTS video_face_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            uploaded_video_path TEXT NOT NULL,
            original_filename TEXT,
            total_frames INTEGER,
            sampled_frames_processed INTEGER NOT NULL DEFAULT 0,
            unique_faces_detected INTEGER NOT NULL DEFAULT 0,
            progress_percent INTEGER NOT NULL DEFAULT 5,
            progress_message TEXT,
            result JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS video_detected_faces (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES video_face_jobs(job_id) ON DELETE CASCADE,
            face_image_path TEXT NOT NULL,
            frame_number INTEGER,
            timestamp_seconds NUMERIC,
            bbox JSONB NOT NULL DEFAULT '[]'::jsonb,
            detection_score REAL,
            quality JSONB NOT NULL DEFAULT '{}'::jsonb,
            embedding JSONB,
            verification_status TEXT NOT NULL DEFAULT 'PENDING',
            matched_employee_id TEXT,
            match_score NUMERIC,
            match_result JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_video_face_jobs_status
        ON video_face_jobs(status);

        CREATE INDEX IF NOT EXISTS idx_video_detected_faces_job_id
        ON video_detected_faces(job_id);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_document_validation_jobs_table(self):
        """Create the persisted document-validation job table for async polling."""

        query = """
        CREATE SEQUENCE IF NOT EXISTS document_validation_job_number_seq START 1;

        CREATE TABLE IF NOT EXISTS document_validation_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            document_type TEXT NOT NULL,
            uploaded_document_path TEXT NOT NULL,
            original_filename TEXT,
            manual_values JSONB NOT NULL DEFAULT '{}'::jsonb,
            progress_percent INTEGER NOT NULL DEFAULT 5,
            progress_message TEXT,
            result JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS original_filename TEXT;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS manual_values JSONB NOT NULL DEFAULT '{}'::jsonb;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 5;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS progress_message TEXT;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS result JSONB;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS error_message TEXT;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;

        ALTER TABLE document_validation_jobs
        ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

        CREATE INDEX IF NOT EXISTS idx_document_validation_jobs_status
        ON document_validation_jobs(status);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _next_face_search_job_id(self):
        """Generate the next readable async face-search job ID like FACE00001."""

        self.cursor.execute(
            """
            SELECT 'FACE' || LPAD(nextval('face_search_job_number_seq')::TEXT, 5, '0')
            """
        )

        return self.cursor.fetchone()[0]

    def create_face_search_job(
        self,
        uploaded_image_path
    ):
        """Insert a pending face-search job and return the stored job payload."""

        job_id = self._next_face_search_job_id()
        query = """
        INSERT INTO face_search_jobs (
            job_id,
            status,
            uploaded_image_path,
            progress_percent,
            progress_message
        )
        VALUES (%s, 'PENDING', %s, 10, 'Face image uploaded. Waiting to start search.')
        RETURNING
            job_id,
            status,
            uploaded_image_path,
            total_candidates,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                job_id,
                uploaded_image_path
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_face_search_job_row(row)

        logger.info(
            "Face search DB state: job_id=%s status=PENDING uploaded_image_path=%s",
            job_id,
            uploaded_image_path
        )

        return formatted_job

    def mark_face_search_job_processing(
        self,
        job_id,
        total_candidates
    ):
        """Move a face-search job into processing after candidates are loaded."""

        query = """
        UPDATE face_search_jobs
        SET
            status = 'PROCESSING',
            total_candidates = %s,
            progress_percent = 35,
            progress_message = 'Database face candidates loaded. Comparing faces now.',
            error_message = NULL,
            started_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(
            query,
            (
                total_candidates,
                job_id
            )
        )
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.info(
                "Face search DB state: job_id=%s status=PROCESSING total_candidates=%s",
                job_id,
                total_candidates
            )
        else:
            logger.error(
                "Face search DB state update failed: job_id=%s status=PROCESSING reason=job_not_found",
                job_id
            )

    def complete_face_search_job(
        self,
        job_id,
        result_payload,
        total_candidates
    ):
        """Persist a completed face-search result for polling and later display."""

        serialized_payload = json.dumps(result_payload or {})
        query = """
        UPDATE face_search_jobs
        SET
            status = 'COMPLETED',
            total_candidates = %s,
            progress_percent = 100,
            progress_message = 'Face search completed.',
            result = %s::jsonb,
            error_message = NULL,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        RETURNING
            job_id,
            status,
            uploaded_image_path,
            total_candidates,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                total_candidates,
                serialized_payload,
                job_id
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_face_search_job_row(row)

        if formatted_job:
            logger.info(
                "Face search DB state: job_id=%s status=COMPLETED matched=%s best_score=%s",
                job_id,
                formatted_job.get("matched"),
                formatted_job.get("best_score")
            )
        else:
            logger.error(
                "Face search DB complete failed: job_id=%s reason=job_not_found",
                job_id
            )

        return formatted_job

    def mark_face_search_job_failed(
        self,
        job_id,
        error_message
    ):
        """Persist a failed face-search state and its error message."""

        self._mark_async_job_failed(
            table_name="face_search_jobs",
            job_id=job_id,
            error_message=error_message,
            default_error="Unknown face search error",
            label="Face search",
            progress_message="Face search failed."
        )

    def update_face_search_job_progress(
        self,
        job_id,
        progress_percent,
        progress_message
    ):
        """Update visible face-search progress for dashboard polling."""

        self._update_job_progress(
            table_name="face_search_jobs",
            job_id=job_id,
            progress_percent=progress_percent,
            progress_message=progress_message
        )

    def mark_stale_face_search_jobs_failed(
        self,
        max_age_minutes=30
    ):
        """Fail face-search jobs that exceeded the allowed processing window."""

        stale_minutes = self._coerce_minutes(max_age_minutes, 30)
        error_message = (
            "Face search job timed out before completion. "
            f"No final result was saved within {stale_minutes} minutes. "
            "Likely causes: face engine stopped, backend restarted, network timeout, "
            "or a long-running comparison failure."
        )

        return self._mark_stale_async_jobs_failed(
            table_name="face_search_jobs",
            max_age_minutes=stale_minutes,
            default_minutes=30,
            error_message=error_message,
            label="Face search",
            progress_message="Face search timed out."
        )

    def get_face_search_job(
        self,
        job_id
    ):
        """Fetch one face-search job for dashboard polling and final display."""

        query = """
        SELECT
            job_id,
            status,
            uploaded_image_path,
            total_candidates,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        FROM face_search_jobs
        WHERE job_id = %s
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (job_id,)
        )

        return self._format_face_search_job_row(
            self.cursor.fetchone()
        )

    def _next_video_face_job_id(self):
        """Generate a readable video face job ID like VIDFACE00001."""

        self.cursor.execute(
            """
            SELECT 'VIDFACE' || LPAD(nextval('video_face_job_number_seq')::TEXT, 5, '0')
            """
        )

        return self.cursor.fetchone()[0]

    def create_video_face_search_job(
        self,
        uploaded_video_path,
        original_filename
    ):
        """Insert a video face-search job and return it for dashboard polling."""

        job_id = self._next_video_face_job_id()
        query = """
        INSERT INTO video_face_jobs (
            job_id,
            status,
            uploaded_video_path,
            original_filename,
            progress_percent,
            progress_message
        )
        VALUES (%s, 'PENDING', %s, %s, 5, 'Video uploaded. Waiting to start face detection.')
        RETURNING
            job_id,
            status,
            uploaded_video_path,
            original_filename,
            total_frames,
            sampled_frames_processed,
            unique_faces_detected,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                job_id,
                uploaded_video_path,
                original_filename
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        logger.info(
            "Video face DB state: job_id=%s status=PENDING video_path=%s",
            job_id,
            uploaded_video_path
        )

        return self._format_video_face_job_row(row)

    def mark_video_face_job_processing(
        self,
        job_id,
        total_frames
    ):
        """Move a video face job into processing once the video opens."""

        self.cursor.execute(
            """
            UPDATE video_face_jobs
            SET
                status = 'PROCESSING',
                total_frames = %s,
                progress_percent = 10,
                progress_message = 'Video opened. Sampling frames for face detection.',
                error_message = NULL,
                started_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
            """,
            (
                total_frames,
                job_id
            )
        )
        self.connection.commit()

    def update_video_face_job_progress(
        self,
        job_id,
        sampled_frames_processed,
        unique_faces_detected,
        progress_percent,
        progress_message
    ):
        """Update visible video-processing progress for dashboard polling."""

        self.cursor.execute(
            """
            UPDATE video_face_jobs
            SET
                sampled_frames_processed = %s,
                unique_faces_detected = %s,
                progress_percent = %s,
                progress_message = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
            """,
            (
                int(sampled_frames_processed or 0),
                int(unique_faces_detected or 0),
                int(progress_percent or 0),
                str(progress_message or ""),
                job_id
            )
        )
        self.connection.commit()

    def insert_video_detected_face(
        self,
        job_id,
        face_payload
    ):
        """Store one detected face immediately so the dashboard can show it."""

        self.cursor.execute(
            """
            INSERT INTO video_detected_faces (
                job_id,
                face_image_path,
                frame_number,
                timestamp_seconds,
                bbox,
                detection_score,
                quality,
                embedding,
                verification_status
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s::jsonb, 'PENDING')
            RETURNING
                id,
                job_id,
                face_image_path,
                frame_number,
                timestamp_seconds,
                bbox,
                detection_score,
                quality,
                verification_status,
                matched_employee_id,
                match_score,
                match_result,
                created_at,
                updated_at
            """,
            (
                job_id,
                face_payload.get("face_image_path"),
                face_payload.get("frame_number"),
                face_payload.get("timestamp_seconds"),
                json.dumps(face_payload.get("bbox") or []),
                face_payload.get("det_score"),
                json.dumps(face_payload.get("quality") or {}),
                json.dumps(face_payload.get("embedding") or [])
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()

        return self._format_video_detected_face_row(row)

    def mark_video_detected_faces_searching(
        self,
        job_id,
        face_ids
    ):
        """Mark selected detected video faces as queued for DB verification."""

        normalized_face_ids = [
            int(face_id)
            for face_id in face_ids or []
        ]

        if not normalized_face_ids:

            return []

        self.cursor.execute(
            """
            UPDATE video_detected_faces
            SET
                verification_status = 'SEARCHING',
                matched_employee_id = NULL,
                match_score = NULL,
                match_result = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
            AND id = ANY(%s)
            AND verification_status IN ('PENDING', 'NO_MATCH', 'MATCHED')
            RETURNING
                id,
                job_id,
                face_image_path,
                frame_number,
                timestamp_seconds,
                bbox,
                detection_score,
                quality,
                verification_status,
                matched_employee_id,
                match_score,
                match_result,
                created_at,
                updated_at
            """,
            (
                job_id,
                normalized_face_ids
            )
        )
        rows = self.cursor.fetchall()
        self.connection.commit()

        return [
            self._format_video_detected_face_row(row)
            for row in rows
        ]

    def get_video_detected_faces_by_ids(
        self,
        job_id,
        face_ids
    ):
        """Fetch selected detected video faces for reviewer-approved verification."""

        normalized_face_ids = [
            int(face_id)
            for face_id in face_ids or []
        ]

        if not normalized_face_ids:

            return []

        self.cursor.execute(
            """
            SELECT
                id,
                job_id,
                face_image_path,
                frame_number,
                timestamp_seconds,
                bbox,
                detection_score,
                quality,
                verification_status,
                matched_employee_id,
                match_score,
                match_result,
                created_at,
                updated_at
            FROM video_detected_faces
            WHERE job_id = %s
            AND id = ANY(%s)
            ORDER BY id ASC
            """,
            (
                job_id,
                normalized_face_ids
            )
        )

        return [
            self._format_video_detected_face_row(row)
            for row in self.cursor.fetchall()
        ]

    def update_video_detected_face_match(
        self,
        face_id,
        match_result
    ):
        """Attach database verification result to one detected video face."""

        match_result = match_result or {}
        matched = bool(match_result.get("matched"))
        best_match = match_result.get("best_match") or {}
        score = match_result.get("best_score")
        status = "MATCHED" if matched and best_match else "NO_MATCH"

        self.cursor.execute(
            """
            UPDATE video_detected_faces
            SET
                verification_status = %s,
                matched_employee_id = %s,
                match_score = %s,
                match_result = %s::jsonb,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (
                status,
                best_match.get("employee_id"),
                score,
                json.dumps(match_result),
                face_id
            )
        )
        self.connection.commit()

    def complete_video_face_search_job(
        self,
        job_id,
        result_payload
    ):
        """Mark a video face-search job completed with final summary counts."""

        self.cursor.execute(
            """
            UPDATE video_face_jobs
            SET
                status = 'COMPLETED',
                progress_percent = 100,
                progress_message = 'Video face detection completed.',
                result = %s::jsonb,
                error_message = NULL,
                completed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = %s
            """,
            (
                json.dumps(result_payload or {}),
                job_id
            )
        )
        self.connection.commit()

    def mark_video_face_job_failed(
        self,
        job_id,
        error_message
    ):
        """Persist a failed video face job state and its error message."""

        self._mark_async_job_failed(
            table_name="video_face_jobs",
            job_id=job_id,
            error_message=error_message,
            default_error="Unknown video face search error",
            label="Video face search",
            progress_message="Video face search failed."
        )

    def mark_stale_video_face_jobs_failed(
        self,
        max_age_minutes=45
    ):
        """Fail video face jobs that exceeded the allowed processing window."""

        return self._mark_stale_async_jobs_failed(
            table_name="video_face_jobs",
            max_age_minutes=max_age_minutes,
            default_minutes=45,
            error_message="Video face search timed out before completion.",
            label="Video face search",
            progress_message="Video face search timed out."
        )

    def get_video_face_search_job(
        self,
        job_id
    ):
        """Fetch one video face job with all detected faces for live polling."""

        self.cursor.execute(
            """
            SELECT
                job_id,
                status,
                uploaded_video_path,
                original_filename,
                total_frames,
                sampled_frames_processed,
                unique_faces_detected,
                progress_percent,
                progress_message,
                result,
                error_message,
                created_at,
                started_at,
                completed_at,
                updated_at
            FROM video_face_jobs
            WHERE job_id = %s
            LIMIT 1
            """,
            (job_id,)
        )
        job = self._format_video_face_job_row(self.cursor.fetchone())

        if not job:

            return None

        self.cursor.execute(
            """
            SELECT
                id,
                job_id,
                face_image_path,
                frame_number,
                timestamp_seconds,
                bbox,
                detection_score,
                quality,
                verification_status,
                matched_employee_id,
                match_score,
                match_result,
                created_at,
                updated_at
            FROM video_detected_faces
            WHERE job_id = %s
            ORDER BY id ASC
            """,
            (job_id,)
        )
        job["detected_faces"] = [
            self._format_video_detected_face_row(row)
            for row in self.cursor.fetchall()
        ]

        return job

    def _next_document_validation_job_id(self):
        """Generate the next readable document-validation job ID like DOC00001."""

        self.cursor.execute(
            """
            SELECT 'DOC' || LPAD(nextval('document_validation_job_number_seq')::TEXT, 5, '0')
            """
        )

        return self.cursor.fetchone()[0]

    def create_document_validation_job(
        self,
        document_type,
        uploaded_document_path,
        original_filename,
        manual_values
    ):
        """Insert a pending document-validation job and return its payload."""

        job_id = self._next_document_validation_job_id()
        query = """
        INSERT INTO document_validation_jobs (
            job_id,
            status,
            document_type,
            uploaded_document_path,
            original_filename,
            manual_values,
            progress_percent,
            progress_message
        )
        VALUES (%s, 'PENDING', %s, %s, %s, %s::jsonb, 10, 'Document uploaded. Waiting to start validation.')
        RETURNING
            job_id,
            status,
            document_type,
            uploaded_document_path,
            original_filename,
            manual_values,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                job_id,
                document_type,
                uploaded_document_path,
                original_filename,
                json.dumps(manual_values or {})
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_document_validation_job_row(row)

        logger.info(
            "Document validation DB state: job_id=%s status=PENDING document_type=%s path=%s",
            job_id,
            document_type,
            uploaded_document_path
        )

        return formatted_job

    def mark_document_validation_job_processing(
        self,
        job_id
    ):
        """Move a document-validation job into processing."""

        query = """
        UPDATE document_validation_jobs
        SET
            status = 'PROCESSING',
            progress_percent = 30,
            progress_message = 'Document validation started. Checking document type and OCR.',
            error_message = NULL,
            started_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(query, (job_id,))
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.info(
                "Document validation DB state: job_id=%s status=PROCESSING",
                job_id
            )
        else:
            logger.error(
                "Document validation DB state update failed: job_id=%s status=PROCESSING reason=job_not_found",
                job_id
            )

    def complete_document_validation_job(
        self,
        job_id,
        result_payload
    ):
        """Persist a completed document-validation result for polling/display."""

        serialized_payload = json.dumps(result_payload or {})
        query = """
        UPDATE document_validation_jobs
        SET
            status = 'COMPLETED',
            progress_percent = 100,
            progress_message = 'Document validation completed.',
            result = %s::jsonb,
            error_message = NULL,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        RETURNING
            job_id,
            status,
            document_type,
            uploaded_document_path,
            original_filename,
            manual_values,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                serialized_payload,
                job_id
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_document_validation_job_row(row)

        if formatted_job:
            decision = (formatted_job.get("result") or {}).get("decision") or {}
            logger.info(
                "Document validation DB state: job_id=%s status=COMPLETED decision=%s",
                job_id,
                decision.get("status")
            )
        else:
            logger.error(
                "Document validation DB complete failed: job_id=%s reason=job_not_found",
                job_id
            )

        return formatted_job

    def mark_document_validation_job_failed(
        self,
        job_id,
        error_message
    ):
        """Persist a failed document-validation state and its error message."""

        self._mark_async_job_failed(
            table_name="document_validation_jobs",
            job_id=job_id,
            error_message=error_message,
            default_error="Unknown document validation error",
            label="Document validation",
            progress_message="Document validation failed."
        )

    def update_document_validation_job_progress(
        self,
        job_id,
        progress_percent,
        progress_message
    ):
        """Update visible document-validation progress for dashboard polling."""

        self._update_job_progress(
            table_name="document_validation_jobs",
            job_id=job_id,
            progress_percent=progress_percent,
            progress_message=progress_message
        )

    def mark_stale_document_validation_jobs_failed(
        self,
        max_age_minutes=30
    ):
        """Fail document-validation jobs that exceeded the allowed processing window."""

        stale_minutes = self._coerce_minutes(max_age_minutes, 30)
        error_message = (
            "Document validation job timed out before completion. "
            f"No final result was saved within {stale_minutes} minutes. "
            "Likely causes: OCR process stopped, backend restarted, or a long-running verification failure."
        )

        return self._mark_stale_async_jobs_failed(
            table_name="document_validation_jobs",
            max_age_minutes=stale_minutes,
            default_minutes=30,
            error_message=error_message,
            label="Document validation",
            progress_message="Document validation timed out."
        )

    def get_document_validation_job(
        self,
        job_id
    ):
        """Fetch one document-validation job for dashboard polling and display."""

        query = """
        SELECT
            job_id,
            status,
            document_type,
            uploaded_document_path,
            original_filename,
            manual_values,
            progress_percent,
            progress_message,
            result,
            error_message,
            created_at,
            started_at,
            completed_at,
            updated_at
        FROM document_validation_jobs
        WHERE job_id = %s
        LIMIT 1
        """

        self.cursor.execute(query, (job_id,))

        return self._format_document_validation_job_row(
            self.cursor.fetchone()
        )

    def _format_document_validation_job_row(
        self,
        row
    ):
        """Convert a document-validation SQL row into dashboard/API shape."""

        if not row:

            return None

        result_payload = row[8] or {}

        return {
            "job_id": row[0],
            "status": row[1],
            "document_type": row[2],
            "uploaded_document_path": row[3],
            "original_filename": row[4],
            "manual_values": row[5] or {},
            "progress_percent": row[6] or 0,
            "progress_message": row[7],
            "result": result_payload,
            "decision": result_payload.get("decision"),
            "extracted_data": result_payload.get("extracted_data"),
            "database_match": result_payload.get("database_match"),
            "face_verification": result_payload.get("face_verification"),
            "risk_assessment": result_payload.get("risk_assessment"),
            "manual_review_case": result_payload.get("manual_review_case"),
            "error_message": row[9],
            "created_at": row[10].isoformat() if row[10] else None,
            "started_at": row[11].isoformat() if row[11] else None,
            "completed_at": row[12].isoformat() if row[12] else None,
            "updated_at": row[13].isoformat() if row[13] else None
        }

    def _format_face_search_job_row(
        self,
        row
    ):
        """Convert a face-search SQL row into the API/dashboard payload shape."""

        if not row:

            return None

        result_payload = row[6] or {}

        return {
            "job_id": row[0],
            "status": row[1],
            "uploaded_image_path": row[2],
            "total_candidates": row[3],
            "progress_percent": row[4] or 0,
            "progress_message": row[5],
            "result": result_payload,
            "matched": result_payload.get("matched"),
            "best_score": result_payload.get("best_score"),
            "database_match": result_payload.get("database_match"),
            "face_verification": result_payload.get("face_verification"),
            "top_candidates": result_payload.get("top_candidates", []),
            "error_message": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "started_at": row[9].isoformat() if row[9] else None,
            "completed_at": row[10].isoformat() if row[10] else None,
            "updated_at": row[11].isoformat() if row[11] else None
        }

    def _format_video_face_job_row(
        self,
        row
    ):
        """Convert a video face-search SQL row into dashboard/API shape."""

        if not row:

            return None

        result_payload = row[9] or {}

        return {
            "job_id": row[0],
            "status": row[1],
            "uploaded_video_path": row[2],
            "original_filename": row[3],
            "total_frames": row[4],
            "sampled_frames_processed": row[5] or 0,
            "unique_faces_detected": row[6] or 0,
            "progress_percent": row[7] or 0,
            "progress_message": row[8],
            "result": result_payload,
            "error_message": row[10],
            "created_at": row[11].isoformat() if row[11] else None,
            "started_at": row[12].isoformat() if row[12] else None,
            "completed_at": row[13].isoformat() if row[13] else None,
            "updated_at": row[14].isoformat() if row[14] else None,
            "detected_faces": []
        }

    def _format_video_detected_face_row(
        self,
        row
    ):
        """Convert a detected video face SQL row into API/dashboard shape."""

        if not row:

            return None

        match_result = row[11] or {}

        return {
            "face_id": row[0],
            "job_id": row[1],
            "face_image_path": row[2],
            "frame_number": row[3],
            "timestamp_seconds": float(row[4]) if row[4] is not None else None,
            "bbox": row[5] or [],
            "detection_score": row[6],
            "quality": row[7] or {},
            "verification_status": row[8],
            "matched_employee_id": row[9],
            "match_score": float(row[10]) if row[10] is not None else None,
            "match_result": match_result,
            "matched": bool(match_result.get("matched")),
            "database_match": match_result.get("best_match"),
            "face_verification": match_result.get("face_verification"),
            "top_candidates": match_result.get("top_candidates", []),
            "created_at": row[12].isoformat() if row[12] else None,
            "updated_at": row[13].isoformat() if row[13] else None
        }

