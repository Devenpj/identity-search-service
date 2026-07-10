import json

try:
    from utils.logger import get_logger
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from utils.logger import get_logger


logger = get_logger("identity-search-service.database")


class OSINTRepositoryMixin:
    """Repository methods split out of DatabaseService."""

    def _ensure_osint_jobs_table(self):
        """Create or migrate the OSINT job table to the single JOB00001 ID model."""

        query = """
        CREATE SEQUENCE IF NOT EXISTS osint_job_number_seq START 1;

        CREATE TABLE IF NOT EXISTS osint_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            targets JSONB NOT NULL DEFAULT '[]'::jsonb,
            provider_response JSONB,
            result JSONB,
            result_payload JSONB,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            submitted_at TIMESTAMP,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'osint_jobs'
                AND column_name = 'job_id'
            )
            AND EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'osint_jobs'
                AND column_name = 'local_job_id'
            ) THEN
                ALTER TABLE osint_jobs RENAME COLUMN local_job_id TO job_id;
            END IF;
        END $$;

        ALTER TABLE osint_jobs
        ADD COLUMN IF NOT EXISTS job_id TEXT;

        ALTER TABLE osint_jobs
        ADD COLUMN IF NOT EXISTS result JSONB;

        ALTER TABLE osint_jobs
        ADD COLUMN IF NOT EXISTS result_payload JSONB;

        UPDATE osint_jobs
        SET result = result_payload
        WHERE result IS NULL
        AND result_payload IS NOT NULL;

        UPDATE osint_jobs
        SET job_id = 'JOB' || LPAD(nextval('osint_job_number_seq')::TEXT, 5, '0')
        WHERE job_id IS NULL
        OR TRIM(job_id) = '';

        ALTER TABLE osint_jobs
        ALTER COLUMN job_id SET NOT NULL;

        ALTER TABLE osint_jobs
        DROP COLUMN IF EXISTS external_job_id;

        ALTER TABLE osint_jobs
        DROP COLUMN IF EXISTS id CASCADE;

        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_name = 'osint_jobs'
                AND constraint_type = 'PRIMARY KEY'
            ) THEN
                ALTER TABLE osint_jobs ADD PRIMARY KEY (job_id);
            END IF;
        END $$;

        ALTER TABLE osint_jobs
        ALTER COLUMN status SET DEFAULT 'PENDING'
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_osint_normalized_tables(self):
        """Create searchable OSINT tables derived from raw provider payloads."""

        query = """
        CREATE TABLE IF NOT EXISTS osint_profiles (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
            employee_id TEXT,
            platform TEXT,
            target TEXT,
            username TEXT,
            full_name TEXT,
            profile_url TEXT,
            avatar_url TEXT,
            avatar_path TEXT,
            bio TEXT,
            status TEXT,
            confidence TEXT,
            extracted_text TEXT,
            raw_payload JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_osint_profiles_job_id
        ON osint_profiles(job_id);

        CREATE INDEX IF NOT EXISTS idx_osint_profiles_employee_id
        ON osint_profiles(employee_id);

        CREATE INDEX IF NOT EXISTS idx_osint_profiles_platform
        ON osint_profiles(platform);

        CREATE TABLE IF NOT EXISTS osint_contacts (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
            employee_id TEXT,
            contact_type TEXT,
            target TEXT,
            platform TEXT,
            status TEXT,
            category TEXT,
            details TEXT,
            raw_payload JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_osint_contacts_job_id
        ON osint_contacts(job_id);

        CREATE INDEX IF NOT EXISTS idx_osint_contacts_target
        ON osint_contacts(target);

        CREATE TABLE IF NOT EXISTS osint_matches (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
            employee_id TEXT,
            platform TEXT,
            url TEXT,
            bio TEXT,
            avatar_url TEXT,
            avatar_path TEXT,
            confidence TEXT,
            raw_payload JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_osint_matches_job_id
        ON osint_matches(job_id);

        CREATE TABLE IF NOT EXISTS osint_identity_links (
            id SERIAL PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
            employee_id TEXT,
            link_reason TEXT,
            match_score NUMERIC,
            face_match_status TEXT,
            face_score NUMERIC,
            decision TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_osint_identity_links_job_id
        ON osint_identity_links(job_id);

        CREATE INDEX IF NOT EXISTS idx_osint_identity_links_employee_id
        ON osint_identity_links(employee_id);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def create_osint_job(
        self,
        targets,
        job_id=None
    ):
        """Insert a pending OSINT job and return the stored job payload."""

        if not job_id:

            job_id = self._next_osint_job_id()

        query = """
        INSERT INTO osint_jobs (
            job_id,
            status,
            targets
        )
        VALUES (%s, 'PENDING', %s::jsonb)
        RETURNING
            job_id,
            status,
            targets,
            provider_response,
            result,
            error_message,
            created_at,
            submitted_at,
            completed_at,
            updated_at
        """

        self.cursor.execute(
            query,
            (
                job_id,
                json.dumps(targets)
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_osint_job_row(row)

        if not formatted_job or not formatted_job.get("job_id"):
            logger.error(
                "OSINT DB insert verification failed: job_id=%s reason=missing_returned_row",
                job_id
            )
            raise ValueError("OSINT job could not be saved in the database")

        persisted_job = self.get_osint_job(
            formatted_job.get("job_id")
        )

        if not persisted_job:
            logger.error(
                "OSINT DB insert verification failed: job_id=%s reason=post_commit_lookup_missing",
                formatted_job.get("job_id")
            )
            raise ValueError("OSINT job was not visible in the database after creation")

        logger.info(
            "OSINT DB state: job_id=%s status=PENDING targets=%s persisted=True",
            formatted_job.get("job_id"),
            len(targets or [])
        )

        return persisted_job

    def _next_osint_job_id(self):
        """Generate the next human-readable OSINT job ID like JOB00001."""

        query = """
        SELECT 'JOB' || LPAD(nextval('osint_job_number_seq')::TEXT, 5, '0')
        """

        self.cursor.execute(query)

        return self.cursor.fetchone()[0]

    def mark_osint_job_submitted(
        self,
        job_id,
        provider_response
    ):
        """Move an OSINT job from PENDING to PROCESSING after provider accepts it."""

        query = """
        UPDATE osint_jobs
        SET
            status = 'PROCESSING',
            provider_response = %s::jsonb,
            error_message = NULL,
            submitted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        """

        self.cursor.execute(
            query,
            (
                json.dumps(provider_response),
                job_id
            )
        )
        updated_rows = self.cursor.rowcount
        self.connection.commit()

        if updated_rows:
            logger.info(
                "OSINT DB state: job_id=%s status=PROCESSING provider_response_saved=True",
                job_id
            )
        else:
            logger.error(
                "OSINT DB state update failed: job_id=%s status=PROCESSING reason=job_not_found",
                job_id
            )

    def mark_osint_job_failed(
        self,
        job_id,
        error_message
    ):
        """Persist a failed OSINT state and its error message."""

        self._mark_async_job_failed(
            table_name="osint_jobs",
            job_id=job_id,
            error_message=error_message,
            default_error="Unknown OSINT error",
            label="OSINT"
        )

    def mark_stale_osint_jobs_failed(
        self,
        max_age_minutes=15
    ):
        """Fail OSINT jobs that exceeded the allowed processing window."""

        stale_minutes = self._coerce_minutes(max_age_minutes, 15)
        error_message = (
            "OSINT job timed out before completion. "
            f"No completed webhook was received within {stale_minutes} minutes. "
            "Likely causes: OSINT engine stopped, callback URL unreachable, "
            "network/firewall issue, or provider processing failure."
        )

        return self._mark_stale_async_jobs_failed(
            table_name="osint_jobs",
            max_age_minutes=stale_minutes,
            default_minutes=15,
            error_message=error_message,
            label="OSINT",
            timestamp_expression="COALESCE(submitted_at, created_at)"
        )

    def complete_osint_job(
        self,
        job_id,
        status,
        result_payload
    ):
        """Store a webhook payload and mark the OSINT job terminal/non-terminal."""

        normalized_status = str(status or "COMPLETED").strip().upper()

        if normalized_status not in {
            "COMPLETED",
            "FAILED",
            "PROCESSING",
            "PENDING"
        }:

            normalized_status = "COMPLETED"

        query = """
        UPDATE osint_jobs
        SET
            status = %s,
            result = %s::jsonb,
            result_payload = %s::jsonb,
            error_message = CASE
                WHEN %s = 'FAILED'
                THEN COALESCE(%s::jsonb ->> 'message', 'OSINT provider reported failure')
                ELSE NULL
            END,
            completed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = %s
        RETURNING
            job_id,
            status,
            targets,
            provider_response,
            result,
            error_message,
            created_at,
            submitted_at,
            completed_at,
            updated_at
        """
        serialized_payload = json.dumps(result_payload)

        self.cursor.execute(
            query,
            (
                normalized_status,
                serialized_payload,
                serialized_payload,
                normalized_status,
                serialized_payload,
                job_id
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()
        formatted_job = self._format_osint_job_row(row)

        if formatted_job:
            logger.info(
                "OSINT DB state: job_id=%s status=%s result_saved=%s",
                job_id,
                formatted_job.get("status"),
                formatted_job.get("results") is not None
            )
        else:
            logger.error(
                "OSINT DB complete failed: job_id=%s reason=job_not_found",
                job_id
            )

        return formatted_job

    def find_latest_osint_job_by_targets(
        self,
        target_values
    ):
        """Find the newest active OSINT job whose stored targets match payload values."""

        normalized_values = [
            str(value or "").strip().lower()
            for value in target_values or []
            if str(value or "").strip()
        ]

        if not normalized_values:

            return None

        query = """
        SELECT
            job_id,
            status,
            targets,
            provider_response,
            result,
            error_message,
            created_at,
            submitted_at,
            completed_at,
            updated_at
        FROM osint_jobs
        WHERE status IN ('PENDING', 'PROCESSING')
        AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements(targets) AS target_item
            WHERE LOWER(target_item ->> 'value') = ANY(%s)
        )
        ORDER BY
            updated_at DESC NULLS LAST,
            created_at DESC NULLS LAST
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (normalized_values,)
        )

        return self._format_osint_job_row(
            self.cursor.fetchone()
        )

    def get_osint_job(
        self,
        job_id
    ):
        """Fetch one OSINT job for dashboard polling/display."""

        query = """
        SELECT
            job_id,
            status,
            targets,
            provider_response,
            result,
            error_message,
            created_at,
            submitted_at,
            completed_at,
            updated_at
        FROM osint_jobs
        WHERE job_id = %s
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (job_id,)
        )

        return self._format_osint_job_row(
            self.cursor.fetchone()
        )

    def get_normalized_osint_data(
        self,
        job_id
    ):
        """Return normalized OSINT rows for clean dashboard retrieval."""

        self.cursor.execute(
            """
            SELECT
                platform,
                target,
                username,
                full_name,
                profile_url,
                avatar_url,
                avatar_path,
                bio,
                status,
                confidence,
                extracted_text
            FROM osint_profiles
            WHERE job_id = %s
            ORDER BY id
            """,
            (job_id,)
        )
        profiles = [
            {
                "platform": row[0],
                "target": row[1],
                "username": row[2],
                "full_name": row[3],
                "profile_url": row[4],
                "avatar_url": row[5],
                "avatar_path": row[6],
                "bio": row[7],
                "status": row[8],
                "confidence": row[9],
                "extracted_text": row[10]
            }
            for row in self.cursor.fetchall()
        ]

        self.cursor.execute(
            """
            SELECT
                contact_type,
                target,
                platform,
                status,
                category,
                details
            FROM osint_contacts
            WHERE job_id = %s
            ORDER BY id
            """,
            (job_id,)
        )
        contacts = [
            {
                "contact_type": row[0],
                "target": row[1],
                "platform": row[2],
                "status": row[3],
                "category": row[4],
                "details": row[5]
            }
            for row in self.cursor.fetchall()
        ]

        self.cursor.execute(
            """
            SELECT
                platform,
                url,
                bio,
                avatar_url,
                avatar_path,
                confidence
            FROM osint_matches
            WHERE job_id = %s
            ORDER BY id
            """,
            (job_id,)
        )
        matches = [
            {
                "platform": row[0],
                "url": row[1],
                "bio": row[2],
                "avatar_url": row[3],
                "avatar_path": row[4],
                "confidence": row[5]
            }
            for row in self.cursor.fetchall()
        ]

        return {
            "profiles": profiles,
            "contacts": contacts,
            "matches": matches
        }

    def replace_normalized_osint_data(
        self,
        job_id,
        profiles=None,
        contacts=None,
        matches=None,
        identity_links=None
    ):
        """Replace searchable OSINT rows for one job without touching raw JSON."""

        profiles = profiles or []
        contacts = contacts or []
        matches = matches or []
        identity_links = identity_links or []

        try:

            for table_name in (
                "osint_identity_links",
                "osint_matches",
                "osint_contacts",
                "osint_profiles"
            ):

                self.cursor.execute(
                    f"DELETE FROM {table_name} WHERE job_id = %s",
                    (job_id,)
                )

            for profile in profiles:

                self.cursor.execute(
                    """
                    INSERT INTO osint_profiles (
                        job_id,
                        employee_id,
                        platform,
                        target,
                        username,
                        full_name,
                        profile_url,
                        avatar_url,
                        avatar_path,
                        bio,
                        status,
                        confidence,
                        extracted_text,
                        raw_payload
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb
                    )
                    """,
                    (
                        job_id,
                        profile.get("employee_id"),
                        profile.get("platform"),
                        profile.get("target"),
                        profile.get("username"),
                        profile.get("full_name"),
                        profile.get("profile_url"),
                        profile.get("avatar_url"),
                        profile.get("avatar_path"),
                        profile.get("bio"),
                        profile.get("status"),
                        profile.get("confidence"),
                        profile.get("extracted_text"),
                        json.dumps(profile.get("raw_payload") or {})
                    )
                )

            for contact in contacts:

                self.cursor.execute(
                    """
                    INSERT INTO osint_contacts (
                        job_id,
                        employee_id,
                        contact_type,
                        target,
                        platform,
                        status,
                        category,
                        details,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        job_id,
                        contact.get("employee_id"),
                        contact.get("contact_type"),
                        contact.get("target"),
                        contact.get("platform"),
                        contact.get("status"),
                        contact.get("category"),
                        contact.get("details"),
                        json.dumps(contact.get("raw_payload") or {})
                    )
                )

            for match in matches:

                self.cursor.execute(
                    """
                    INSERT INTO osint_matches (
                        job_id,
                        employee_id,
                        platform,
                        url,
                        bio,
                        avatar_url,
                        avatar_path,
                        confidence,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        job_id,
                        match.get("employee_id"),
                        match.get("platform"),
                        match.get("url"),
                        match.get("bio"),
                        match.get("avatar_url"),
                        match.get("avatar_path"),
                        match.get("confidence"),
                        json.dumps(match.get("raw_payload") or {})
                    )
                )

            for identity_link in identity_links:

                self.cursor.execute(
                    """
                    INSERT INTO osint_identity_links (
                        job_id,
                        employee_id,
                        link_reason,
                        match_score,
                        face_match_status,
                        face_score,
                        decision
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        identity_link.get("employee_id"),
                        identity_link.get("link_reason"),
                        identity_link.get("match_score"),
                        identity_link.get("face_match_status"),
                        identity_link.get("face_score"),
                        identity_link.get("decision")
                    )
                )

            self.connection.commit()

            logger.info(
                "OSINT normalized data stored: job_id=%s profiles=%s contacts=%s matches=%s identity_links=%s",
                job_id,
                len(profiles),
                len(contacts),
                len(matches),
                len(identity_links)
            )

        except Exception:

            self.connection.rollback()
            raise

    def _format_osint_job_row(
        self,
        row
    ):
        """Convert an OSINT SQL row into JSON-friendly API shape."""

        if not row:

            return None

        return {
            "job_id": row[0],
            "status": row[1],
            "targets": row[2] or [],
            "provider_response": row[3],
            "results": row[4],
            "error_message": row[5],
            "created_at": row[6].isoformat() if row[6] else None,
            "submitted_at": row[7].isoformat() if row[7] else None,
            "completed_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None
        }

