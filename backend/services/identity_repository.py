import json
import re

from psycopg2 import errors

try:
    from utils.logger import get_logger
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from utils.logger import get_logger


logger = get_logger("identity-search-service.database")


class IdentityRepositoryMixin:
    """Repository methods split out of DatabaseService."""

    def _ensure_manual_review_table(self):
        """Create the manual review queue table used by reviewer workflows."""

        query = """
        CREATE TABLE IF NOT EXISTS manual_review_cases (
            id SERIAL PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'PENDING',
            document_type TEXT,
            employee_id TEXT,
            full_name TEXT,
            uploaded_document_path TEXT,
            extracted_data TEXT,
            database_match TEXT,
            face_result TEXT,
            decision TEXT,
            reviewer_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _ensure_face_embeddings_table(self):
        """Create durable storage for normalized InsightFace embeddings."""

        query = """
        CREATE TABLE IF NOT EXISTS identity_face_embeddings (
            employee_id TEXT PRIMARY KEY,
            photo_path TEXT NOT NULL,
            photo_hash TEXT NOT NULL,
            model_name TEXT NOT NULL,
            embedding_dimension INTEGER NOT NULL,
            embedding REAL[] NOT NULL,
            face_quality JSONB NOT NULL DEFAULT '{}'::jsonb,
            detection_score REAL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT identity_face_embedding_dimension_check
                CHECK (embedding_dimension > 0),
            CONSTRAINT identity_face_embedding_array_check
                CHECK (cardinality(embedding) = embedding_dimension)
        );

        CREATE INDEX IF NOT EXISTS idx_identity_face_embeddings_photo_hash
        ON identity_face_embeddings(photo_hash);

        CREATE INDEX IF NOT EXISTS idx_identity_face_embeddings_model
        ON identity_face_embeddings(model_name);
        """

        self.cursor.execute(query)
        self.connection.commit()

    def _get_existing_extended_columns(self):
        """Detect optional document columns so old databases still work."""

        query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'demodataset'
        AND column_name IN (
            'voter_id_number',
            'driving_license_number',
            'passport_number'
        )
        """

        self.cursor.execute(query)

        return {
            row[0]
            for row in self.cursor.fetchall()
        }

    def _ensure_document_columns(self):
        """Add optional document-number columns used by extended ID types."""


        query = """
        ALTER TABLE demodataset
        ADD COLUMN IF NOT EXISTS voter_id_number TEXT,
        ADD COLUMN IF NOT EXISTS driving_license_number TEXT,
        ADD COLUMN IF NOT EXISTS passport_number TEXT
        """

        try:

            self.cursor.execute("SET lock_timeout TO '2s'")
            self.cursor.execute(query)
            self.connection.commit()

        except errors.LockNotAvailable:

            self.connection.rollback()

    def search_identity(
        self,
        field,
        value=None
    ):
        """Search `demodataset` by one field or a list of field/value criteria."""

        is_multi_search = isinstance(field, list) and value is None

        if is_multi_search:

            criteria = field
            limit = 50
            include_matched_fields = True

        else:

            criteria = [
                {
                    "field": field,
                    "value": value
                }
            ]
            limit = 20
            include_matched_fields = False

        conditions = []
        parameters = []
        matched_criteria = []

        for item in criteria or []:

            condition = self._build_search_condition(
                item.get("field"),
                item.get("value")
            )

            if not condition:

                continue

            where_clause, parameter = condition
            conditions.append(where_clause)
            parameters.extend(
                self._condition_parameters(parameter)
            )
            matched_criteria.append(item)

        if not conditions:

            return []

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE {" AND ".join(f"({condition})" for condition in conditions)}
        LIMIT %s
        """

        self.cursor.execute(
            query,
            tuple(parameters + [limit])
        )

        formatted_results = [
            self._format_identity_row(row)
            for row in self.cursor.fetchall()
        ]

        if include_matched_fields:

            for result in formatted_results:

                result["_matched_fields"] = self._matched_fields_for_identity(
                    result,
                    matched_criteria
                )

        return formatted_results

    def close(self):
        """Close cursor and connection for request-scoped/background services."""

        try:

            self.cursor.close()

        finally:

            self.connection.close()

    def _allowed_search_fields(self):
        """Map public search field names to safe database column names."""

        allowed_fields = {
            "full_name": "full_name",
            "date_of_birth": "date_of_birth",
            "dob": "date_of_birth",
            "aadhar_number": "aadhar_number",
            "aadhaar": "aadhar_number",
            "aadhar": "aadhar_number",
            "pan_number": "pan_number",
            "pan": "pan_number",
            "phone_number": "phone_number",
            "phone": "phone_number",
            "email": "email",
            "username": "username",
            "employee_id": "employee_id",
            "department": "department",
            "state": "state"
        }

        if "voter_id_number" in self.extended_document_columns:

            allowed_fields["voter_id_number"] = "voter_id_number"
            allowed_fields["voter_id"] = "voter_id_number"

        if "driving_license_number" in self.extended_document_columns:

            allowed_fields["driving_license_number"] = "driving_license_number"
            allowed_fields["driving_license"] = "driving_license_number"

        if "passport_number" in self.extended_document_columns:

            allowed_fields["passport_number"] = "passport_number"
            allowed_fields["passport"] = "passport_number"

        return allowed_fields

    def _condition_parameters(self, parameter):
        """ Convert value into a tuple for psycopg2."""

        if isinstance(parameter, (list, tuple)):

            return tuple(parameter)

        return (parameter,) 
    """ tuple is required for psycopg2 parameterization, even if it's a single value. and , is important as it describe the tuple  """

    def _matched_fields_for_identity(
        self,
        identity,
        criteria
    ):
        """Explain which submitted fields caused a DB row to appear."""

        matches = []

        for item in criteria or []:

            field = str(item.get("field") or "").strip()
            searched_value = str(item.get("value") or "").strip()

            if not field or not searched_value:

                continue

            if field == "username":

                matches.extend(
                    self._username_matches_for_identity(
                        identity,
                        searched_value
                    )
                )
                continue

            allowed_fields = self._allowed_search_fields()
            db_field = allowed_fields.get(field)

            if not db_field or db_field == "username":

                continue

            database_value = identity.get(db_field)

            if self._field_value_matches(field, searched_value, database_value):

                matches.append(
                    {
                        "searched_field": field,
                        "searched_value": searched_value,
                        "matched_column": db_field,
                        "matched_value": database_value
                    }
                )

        return matches

    def _username_matches_for_identity(
        self,
        identity,
        searched_value
    ):
        """Explain username matches against email, employee ID, and full name."""

        normalized_username = searched_value.lstrip("@#").strip()
        spaced_username = re.sub(
            r"[._]+",
            " ",
            normalized_username
        )
        matches = []

        for matched_column, candidate_value, search_text in [
            ("email", identity.get("email"), normalized_username),
            ("employee_id", identity.get("employee_id"), normalized_username),
            ("full_name", identity.get("full_name"), spaced_username)
        ]:

            if self._text_contains(candidate_value, search_text):

                matches.append(
                    {
                        "searched_field": "username",
                        "searched_value": searched_value,
                        "matched_column": matched_column,
                        "matched_value": candidate_value
                    }
                )

        return matches

    def _field_value_matches(
        self,
        field,
        searched_value,
        database_value
    ):
        """Mirror DB search normalization to explain frontend match reasons."""

        if field in {
            "aadhaar",
            "aadhar",
            "aadhar_number",
            "phone",
            "phone_number"
        }:

            return self._digits_only(searched_value) in self._digits_only(database_value)

        if field in {
            "pan",
            "pan_number",
            "voter_id",
            "voter_id_number",
            "driving_license",
            "driving_license_number",
            "passport",
            "passport_number"
        }:

            return self._normalize_identifier(searched_value) in self._normalize_identifier(database_value)

        return self._text_contains(database_value, searched_value)

    def _text_contains(
        self,
        database_value,
        searched_value
    ):
        """Case-insensitive contains check used for match explanations."""

        database_text = str(database_value or "").strip().lower()
        searched_text = str(searched_value or "").strip().lower()

        return bool(searched_text  and searched_text in database_text)

    def _digits_only(
        self,
        value
    ):
        """Return only digits for phone and Aadhaar match explanations."""

        return re.sub(
            r"\D",
            "",
            str(value or "")
        )

    def _normalize_identifier(
        self,
        value
    ):
        """Return uppercase alphanumeric text for ID match explanations."""

        return re.sub(
            r"[^A-Za-z0-9]",
            "",
            str(value or "")
        ).upper()

    def _build_search_condition(
        self,
        field,
        value
    ):
        """Build a parameterized WHERE clause for one allowed search field."""

        allowed_fields = self._allowed_search_fields()
        field = str(field or "").strip()

        if field not in allowed_fields:

            return None

        db_column = allowed_fields[field]
        search_value = str(value or "").strip()

        if field == "username":

            normalized_username = search_value.lstrip("@#").strip()
            spaced_username = re.sub(
                r"[._]+",
                " ",
                normalized_username
            )

            if not normalized_username:

                return None

            where_clause = """
            (
                CAST(email AS TEXT) ILIKE %s
                OR CAST(employee_id AS TEXT) ILIKE %s
                OR CAST(full_name AS TEXT) ILIKE %s
            )
            """

            return where_clause, (
                f"%{normalized_username}%",
                f"%{normalized_username}%",
                f"%{spaced_username}%"
            )

        if field in {
            "aadhaar",
            "aadhar",
            "aadhar_number",
            "phone",
            "phone_number"
        }:

            where_clause = f"REGEXP_REPLACE(CAST({db_column} AS TEXT), '\\D', '', 'g') ILIKE %s"
            search_value = re.sub(r"\D", "", search_value)

        elif field in {
            "pan",
            "pan_number",
            "voter_id",
            "voter_id_number",
            "driving_license",
            "driving_license_number",
            "passport",
            "passport_number"
        }:

            where_clause = f"UPPER(REGEXP_REPLACE(CAST({db_column} AS TEXT), '[^A-Za-z0-9]', '', 'g')) ILIKE %s"
            search_value = re.sub(r"[^A-Za-z0-9]", "", search_value).upper()

        else:

            where_clause = f"CAST({db_column} AS TEXT) ILIKE %s"

        if not search_value:

            return None

        return where_clause, f"%{search_value}%"

    def verify_identity_document(
        self,
        extracted_data
    ):
        """Find a database identity that matches the uploaded document number."""

        document_type = self._normalize_document_type(
            extracted_data.get("document_type")
        )
        search_value = None
        search_field = None

        if document_type == "aadhaar":

            search_field = "aadhaar"
            search_value = extracted_data.get("aadhar_number")

        elif document_type == "pan":

            search_field = "pan"
            search_value = extracted_data.get("pan_number")

        elif document_type == "voter_id":

            search_field = "voter_id"
            search_value = extracted_data.get("voter_id_number")

        elif document_type == "driving_license":

            search_field = "driving_license"
            search_value = extracted_data.get("driving_license_number")

        elif document_type == "passport":

            search_field = "passport"
            search_value = extracted_data.get("passport_number")

        if not search_field or not search_value:

            return None

        matches = self.search_identity(
            search_field,
            search_value
        )

        if matches:

            matches[0]["_document_match_type"] = "exact"
            matches[0]["_document_match_field"] = search_field

            return matches[0]

        fuzzy_match = self._find_fuzzy_aadhaar_match(
            search_field,
            search_value
        )

        if fuzzy_match:

            return fuzzy_match

        return None

    def _find_fuzzy_aadhaar_match(
        self,
        search_field,
        search_value

    ):
        """Recover Aadhaar matches when OCR has up to two digit mistakes."""

        if search_field != "aadhaar":

            return None

        search_digits = re.sub(
            r"\D",
            "",
            str(search_value or "")
        )

        if len(search_digits) != 12:

            return None

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE aadhar_number IS NOT NULL
        AND TRIM(CAST(aadhar_number AS TEXT)) <> ''
        LIMIT 5000
        """

        self.cursor.execute(query)

        best_match = None
        best_distance = None

        for row in self.cursor.fetchall():

            database_digits = re.sub(
                r"\D",
                "",
                str(row[3] or "")
            )

            if len(database_digits) != 12:

                continue

            distance = self._hamming_distance(
                search_digits,
                database_digits
            )

            if distance <= 2 and (best_distance is None or distance < best_distance):

                best_distance = distance
                best_match = self._format_identity_row(row)

        if not best_match:

            return None

        best_match["_document_match_type"] = "fuzzy_ocr_correction"
        best_match["_document_match_field"] = search_field
        best_match["_document_match_distance"] = best_distance

        return best_match

    def _hamming_distance(
        self,
        value_one,
        value_two
    ):
        """Count character positions that differ between equal-length strings."""

        if len(value_one) != len(value_two):

            return max(
                len(value_one),
                len(value_two)
            )

        return sum(
            character_one != character_two
            for character_one, character_two in zip(value_one, value_two)
        )

    def _format_identity_row(
        self,
        row
    ):
        """Convert a `demodataset` row into the identity JSON contract."""

        return {

            "employee_id": row[0],

            "full_name": row[1],

            "date_of_birth": str(row[2]),

            "aadhar_number": row[3],

            "pan_number": row[4],

            "voter_id_number": row[5],

            "driving_license_number": row[6],

            "passport_number": row[7],

            "phone_number": row[8],

            "email": row[9],

            "department": row[10],

            "state": row[11],

            "photo_path": row[12]
        }

    def _normalize_document_type(
        self,
        document_type
    ):
        """Normalize document labels before selecting DB search fields."""

        normalized_type = re.sub(
            r"[^a-z0-9]+",
            "_",
            str(document_type or "").lower().strip()
        ).strip("_")

        aliases = {
            "aadhar": "aadhaar",
            "aadhar_card": "aadhaar",
            "aadhaar_card": "aadhaar",
            "pan_card": "pan",
            "voter": "voter_id",
            "voter_card": "voter_id",
            "voter_id_card": "voter_id",
            "driving_licence": "driving_license",
            "license": "driving_license",
            "licence": "driving_license"
        }

        return aliases.get(normalized_type, normalized_type)

    def upsert_face_embedding(
        self,
        employee_id,
        photo_path,
        photo_hash,
        model_name,
        embedding,
        face_quality=None,
        detection_score=None
    ):
        """Persist one normalized embedding, replacing stale photo/model data."""

        normalized_embedding = [float(value) for value in embedding or []]

        if not normalized_embedding:

            raise ValueError("Face embedding cannot be empty")

        self.cursor.execute(
            """
            INSERT INTO identity_face_embeddings (
                employee_id,
                photo_path,
                photo_hash,
                model_name,
                embedding_dimension,
                embedding,
                face_quality,
                detection_score
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (employee_id) DO UPDATE
            SET
                photo_path = EXCLUDED.photo_path,
                photo_hash = EXCLUDED.photo_hash,
                model_name = EXCLUDED.model_name,
                embedding_dimension = EXCLUDED.embedding_dimension,
                embedding = EXCLUDED.embedding,
                face_quality = EXCLUDED.face_quality,
                detection_score = EXCLUDED.detection_score,
                updated_at = CURRENT_TIMESTAMP
            RETURNING employee_id
            """,
            (
                str(employee_id or "").strip(),
                str(photo_path or "").strip(),
                str(photo_hash or "").strip(),
                str(model_name or "").strip(),
                len(normalized_embedding),
                normalized_embedding,
                json.dumps(face_quality or {}),
                detection_score
            )
        )
        row = self.cursor.fetchone()
        self.connection.commit()

        return row[0] if row else None

    def delete_face_embedding(self, employee_id):
        """Delete a stored embedding when an identity or photo is removed."""

        self.cursor.execute(
            "DELETE FROM identity_face_embeddings WHERE employee_id = %s",
            (str(employee_id or "").strip(),)
        )
        deleted_rows = self.cursor.rowcount
        self.connection.commit()

        return deleted_rows

    def get_face_embedding_index(self):
        """Return stored metadata keyed by employee ID for incremental backfills."""

        self.cursor.execute(
            """
            SELECT
                employee_id,
                photo_path,
                photo_hash,
                model_name,
                embedding_dimension,
                updated_at
            FROM identity_face_embeddings
            """
        )

        return {
            row[0]: {
                "employee_id": row[0],
                "photo_path": row[1],
                "photo_hash": row[2],
                "model_name": row[3],
                "embedding_dimension": row[4],
                "updated_at": row[5].isoformat() if row[5] else None
            }
            for row in self.cursor.fetchall()
        }

    def get_identity_face_embedding_candidates(self):
        """Return current identity records joined to matching stored embeddings."""

        query = f"""
        SELECT
            d.employee_id,
            d.full_name,
            d.date_of_birth,
            d.aadhar_number,
            d.pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            d.phone_number,
            d.email,
            d.department,
            d.state,
            d.photo_path,
            e.embedding,
            e.face_quality,
            e.detection_score,
            e.model_name,
            e.photo_hash
        FROM demodataset d
        JOIN identity_face_embeddings e
            ON e.employee_id = d.employee_id
            AND e.photo_path = d.photo_path
        WHERE d.photo_path IS NOT NULL
        AND TRIM(CAST(d.photo_path AS TEXT)) <> ''
        AND e.embedding_dimension = 512
        """

        self.cursor.execute(query)
        candidates = []

        for row in self.cursor.fetchall():
            person = self._format_identity_row(row[:13])
            person.update(
                {
                    "embedding": row[13],
                    "embedding_quality": row[14] or {},
                    "embedding_detection_score": row[15],
                    "embedding_model": row[16],
                    "photo_hash": row[17]
                }
            )
            candidates.append(person)

        return candidates

    def get_face_embedding_coverage(self):
        """Return photo/embedding counts used to choose fast or fallback search."""

        self.cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE d.photo_path IS NOT NULL
                    AND TRIM(CAST(d.photo_path AS TEXT)) <> ''
                ) AS total_photos,
                COUNT(e.employee_id) FILTER (
                    WHERE d.photo_path IS NOT NULL
                    AND TRIM(CAST(d.photo_path AS TEXT)) <> ''
                    AND e.photo_path = d.photo_path
                    AND e.embedding_dimension = 512
                ) AS ready_embeddings
            FROM demodataset d
            LEFT JOIN identity_face_embeddings e
                ON e.employee_id = d.employee_id
            """
        )
        row = self.cursor.fetchone() or (0, 0)

        return {
            "total_photos": int(row[0] or 0),
            "ready_embeddings": int(row[1] or 0),
            "complete": bool(row[0] and row[0] == row[1])
        }

    def get_identities_with_photos(self):
        """Return all identities that can participate in face search."""

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE photo_path IS NOT NULL
        AND TRIM(CAST(photo_path AS TEXT)) <> ''
        """

        self.cursor.execute(query)

        results = self.cursor.fetchall()

        formatted_results = []

        for row in results:

            formatted_results.append({

                "employee_id": row[0],

                "full_name": row[1],

                "date_of_birth": str(row[2]),

                "aadhar_number": row[3],

                "pan_number": row[4],

                "voter_id_number": row[5],

                "driving_license_number": row[6],

                "passport_number": row[7],

                "phone_number": row[8],

                "email": row[9],

                "department": row[10],

                "state": row[11],

                "photo_path": row[12]
            })

        return formatted_results

    def _select_extended_column(self, column_name):
        """Select optional columns safely even when older DBs do not have them."""

        if column_name in self.extended_document_columns:

            return column_name

        return f"NULL AS {column_name}"

    def register_identity(
        self,
        identity_data
    ):
        """Create a new identity record after required-field and duplicate checks."""

        employee_id = str(identity_data.get("employee_id") or "").strip()

        if not employee_id:

            raise ValueError("Employee ID is required")

        if not str(identity_data.get("full_name") or "").strip():

            raise ValueError("Full name is required")

        self.cursor.execute(
            """
            SELECT employee_id
            FROM demodataset
            WHERE employee_id = %s
            LIMIT 1
            """,
            (employee_id,)
        )

        if self.cursor.fetchone():

            raise ValueError(f"Employee ID already exists: {employee_id}")

        query = """
        INSERT INTO demodataset (
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            voter_id_number,
            driving_license_number,
            passport_number,
            phone_number,
            email,
            department,
            state,
            photo_path
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """

        self.cursor.execute(
            query,
            (
                employee_id,
                identity_data.get("full_name"),
                identity_data.get("date_of_birth") or None,
                identity_data.get("aadhar_number") or None,
                identity_data.get("pan_number") or None,
                identity_data.get("voter_id_number") or None,
                identity_data.get("driving_license_number") or None,
                identity_data.get("passport_number") or None,
                identity_data.get("phone_number") or None,
                identity_data.get("email") or None,
                identity_data.get("department") or None,
                identity_data.get("state") or None,
                identity_data.get("photo_path") or None
            )
        )
        self.connection.commit()

        matches = self.search_identity(
            "employee_id",
            employee_id
        )

        if matches:

            return matches[0]

        return identity_data

    def list_identities(
        self,
        limit=100
    ):
        """Return a limited admin view of identity records ordered by employee ID."""

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        ORDER BY employee_id
        LIMIT %s
        """

        self.cursor.execute(
            query,
            (limit,)
        )

        return [
            self._format_identity_row(row)
            for row in self.cursor.fetchall()
        ]

    def get_identity_by_employee_id(
        self,
        employee_id
    ):
        """Fetch one identity record for update/delete/admin display."""

        query = f"""
        SELECT
            employee_id,
            full_name,
            date_of_birth,
            aadhar_number,
            pan_number,
            {self._select_extended_column("voter_id_number")},
            {self._select_extended_column("driving_license_number")},
            {self._select_extended_column("passport_number")},
            phone_number,
            email,
            department,
            state,
            photo_path
        FROM demodataset
        WHERE employee_id = %s
        LIMIT 1
        """

        self.cursor.execute(
            query,
            (employee_id,)
        )

        row = self.cursor.fetchone()

        if not row:

            return None

        return self._format_identity_row(row)

    def create_identity_admin(
        self,
        identity_data
    ):
        """Admin create wrapper that normalizes payload before registration."""

        return self.register_identity(
            self._normalize_identity_payload(identity_data)
        )

    def update_identity_admin(
        self,
        employee_id,
        identity_data
    ):
        """Update an existing identity while preserving photo when not replaced."""

        employee_id = str(employee_id or "").strip()

        if not employee_id:

            raise ValueError("Employee ID is required")

        existing_identity = self.get_identity_by_employee_id(employee_id)

        if not existing_identity:

            raise ValueError(f"Identity not found: {employee_id}")

        normalized_data = self._normalize_identity_payload(identity_data)
        full_name = normalized_data.get("full_name")

        if not full_name:

            raise ValueError("Full name is required")

        photo_path = normalized_data.get("photo_path") or existing_identity.get("photo_path")

        query = """
        UPDATE demodataset
        SET
            full_name = %s,
            date_of_birth = %s,
            aadhar_number = %s,
            pan_number = %s,
            voter_id_number = %s,
            driving_license_number = %s,
            passport_number = %s,
            phone_number = %s,
            email = %s,
            department = %s,
            state = %s,
            photo_path = %s
        WHERE employee_id = %s
        """

        self.cursor.execute(
            query,
            (
                full_name,
                normalized_data.get("date_of_birth"),
                normalized_data.get("aadhar_number"),
                normalized_data.get("pan_number"),
                normalized_data.get("voter_id_number"),
                normalized_data.get("driving_license_number"),
                normalized_data.get("passport_number"),
                normalized_data.get("phone_number"),
                normalized_data.get("email"),
                normalized_data.get("department"),
                normalized_data.get("state"),
                photo_path,
                employee_id
            )
        )
        self.connection.commit()

        return self.get_identity_by_employee_id(employee_id)

    def delete_identity_admin(
        self,
        employee_id
    ):
        """Delete an identity and return the removed record for confirmation."""

        employee_id = str(employee_id or "").strip()

        if not employee_id:

            raise ValueError("Employee ID is required")

        existing_identity = self.get_identity_by_employee_id(employee_id)

        if not existing_identity:

            raise ValueError(f"Identity not found: {employee_id}")

        self.cursor.execute(
            "DELETE FROM identity_face_embeddings WHERE employee_id = %s",
            (employee_id,)
        )
        self.cursor.execute(
            """
            DELETE FROM demodataset
            WHERE employee_id = %s
            """,
            (employee_id,)
        )
        self.connection.commit()

        return existing_identity

    def _normalize_identity_payload(
        self,
        identity_data
    ):
        """Strip strings and convert empty form values into database NULLs."""

        identity_data = identity_data or {}
        normalized_data = {}

        for field_name in {
            "employee_id",
            "full_name",
            "date_of_birth",
            "aadhar_number",
            "pan_number",
            "voter_id_number",
            "driving_license_number",
            "passport_number",
            "phone_number",
            "email",
            "department",
            "state",
            "photo_path"
        }:

            value = identity_data.get(field_name)

            if value is None:

                normalized_data[field_name] = None

            else:

                normalized_data[field_name] = str(value).strip() or None

        return normalized_data

    def create_manual_review_case(
        self,
        extracted_data,
        database_match,
        face_result,
        decision,
        uploaded_document_path
    ):
        """Store a document verification case that needs human review."""

        query = """
        INSERT INTO manual_review_cases (
            status,
            document_type,
            employee_id,
            full_name,
            uploaded_document_path,
            extracted_data,
            database_match,
            face_result,
            decision
        )
        VALUES (
            'PENDING', %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """

        self.cursor.execute(
            query,
            (
                extracted_data.get("document_type"),
                (database_match or {}).get("employee_id"),
                (database_match or {}).get("full_name") or extracted_data.get("full_name"),
                uploaded_document_path,
                json.dumps(extracted_data, default=str),
                json.dumps(database_match, default=str),
                json.dumps(face_result, default=str),
                json.dumps(decision, default=str)
            )
        )
        case_id = self.cursor.fetchone()[0]
        self.connection.commit()

        return self.get_manual_review_case(case_id)

    def get_manual_review_case(
        self,
        case_id
    ):
        """Fetch a single manual review case by numeric ID."""

        self.cursor.execute(
            """
            SELECT
                id,
                status,
                document_type,
                employee_id,
                full_name,
                uploaded_document_path,
                extracted_data,
                database_match,
                face_result,
                decision,
                reviewer_notes,
                created_at,
                updated_at
            FROM manual_review_cases
            WHERE id = %s
            """,
            (case_id,)
        )

        row = self.cursor.fetchone()

        if not row:

            return None

        return self._format_manual_review_case(row)

    def list_manual_review_cases(
        self,
        status="PENDING"
    ):
        """List review cases by status for the dashboard queue."""

        allowed_statuses = {
            "PENDING",
            "APPROVED",
            "REJECTED",
            "ALL"
        }

        normalized_status = str(status or "PENDING").upper()

        if normalized_status not in allowed_statuses:

            normalized_status = "PENDING"

        if normalized_status == "ALL":

            query = """
            SELECT
                id,
                status,
                document_type,
                employee_id,
                full_name,
                uploaded_document_path,
                extracted_data,
                database_match,
                face_result,
                decision,
                reviewer_notes,
                created_at,
                updated_at
            FROM manual_review_cases
            ORDER BY created_at DESC
            LIMIT 100
            """
            params = ()

        else:

            query = """
            SELECT
                id,
                status,
                document_type,
                employee_id,
                full_name,
                uploaded_document_path,
                extracted_data,
                database_match,
                face_result,
                decision,
                reviewer_notes,
                created_at,
                updated_at
            FROM manual_review_cases
            WHERE status = %s
            ORDER BY created_at DESC
            LIMIT 100
            """
            params = (normalized_status,)

        self.cursor.execute(query, params)

        return [
            self._format_manual_review_case(row)
            for row in self.cursor.fetchall()
        ]

    def update_manual_review_case(
        self,
        case_id,
        reviewer_decision,
        reviewer_notes=""
    ):
        """Apply reviewer decision and notes to a manual review case."""

        normalized_decision = str(reviewer_decision or "").upper()

        if normalized_decision not in {
            "APPROVED",
            "REJECTED",
            "PENDING"
        }:

            raise ValueError("Reviewer decision must be APPROVED, REJECTED, or PENDING")

        self.cursor.execute(
            """
            UPDATE manual_review_cases
            SET
                status = %s,
                reviewer_notes = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
            """,
            (
                normalized_decision,
                reviewer_notes,
                case_id
            )
        )

        updated = self.cursor.fetchone()

        if not updated:

            self.connection.rollback()
            raise ValueError(f"Manual review case not found: {case_id}")

        self.connection.commit()

        return self.get_manual_review_case(case_id)

    def _format_manual_review_case(
        self,
        row
    ):
        """Convert a manual review SQL row into API/dashboard format."""

        return {
            "id": row[0],
            "status": row[1],
            "document_type": row[2],
            "employee_id": row[3],
            "full_name": row[4],
            "uploaded_document_path": row[5],
            "extracted_data": self._load_json(row[6]),
            "database_match": self._load_json(row[7]),
            "face_result": self._load_json(row[8]),
            "decision": self._load_json(row[9]),
            "reviewer_notes": row[10],
            "created_at": str(row[11]),
            "updated_at": str(row[12])
        }

    def _load_json(
        self,
        value
    ):
        """Decode stored JSON text while tolerating legacy plain strings."""

        if not value:

            return None

        try:

            return json.loads(value)

        except (TypeError, json.JSONDecodeError):

            return value
