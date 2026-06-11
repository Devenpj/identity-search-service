"""Risk scoring rules for document verification decisions."""

import re
from difflib import SequenceMatcher


class RiskScoringService:
    """Score identity evidence and produce a risk level plus decision hint."""

    DOCUMENT_FIELD_BY_TYPE = {
        "aadhaar": "aadhar_number",
        "pan": "pan_number",
        "voter_id": "voter_id_number",
        "driving_license": "driving_license_number",
        "passport": "passport_number"
    }

    def calculate(
        self,
        extracted_data,
        database_match,
        face_result
    ):
        """Combine document, DOB, name, face, and format checks into 0-100 risk.

        The returned dictionary is consumed by `DecisionService` and the
        dashboard score breakdown, so each check records both points and
        reviewer-friendly reasons/flags.
        """

        extracted_data = extracted_data or {}
        face_result = face_result or {}

        score = 0
        reasons = []
        flags = []
        checks = {}

        document_score = self._score_document_number(
            extracted_data,
            database_match,
            reasons,
            flags
        )
        score += document_score
        checks["document_number"] = document_score

        dob_score = self._score_dob(
            extracted_data,
            database_match,
            reasons,
            flags
        )
        score += dob_score
        checks["date_of_birth"] = dob_score

        name_score = self._score_name(
            extracted_data,
            database_match,
            reasons,
            flags
        )
        score += name_score
        checks["name"] = name_score

        face_score = self._score_face(
            face_result,
            reasons,
            flags
        )
        score += face_score
        checks["face"] = face_score

        format_score = self._score_document_format(
            extracted_data,
            reasons,
            flags
        )
        score += format_score
        checks["document_format"] = format_score

        score = max(0, min(100, score))
        decision = self._decision_for_score(score, flags)

        return {
            "risk_score": score,
            "decision": decision,
            "risk_level": self._risk_level(score),
            "checks": checks,
            "reasons": reasons,
            "flags": flags
        }

    def _score_document_number(
        self,
        extracted_data,
        database_match,
        reasons,
        flags
    ):
        """Give the highest weight to matching the document number in the DB."""

        document_type = self._normalize_document_type(
            extracted_data.get("document_type")
        )
        field_name = self.DOCUMENT_FIELD_BY_TYPE.get(document_type)

        if not database_match:

            flags.append("No database record was found for the uploaded document number")
            return 0

        if not field_name:

            flags.append("Unsupported document type for risk scoring")
            return 0

        extracted_value = extracted_data.get(field_name)
        database_value = database_match.get(field_name)

        if not extracted_value:

            flags.append("Document number was not extracted")
            return 0

        if self._normalize_identifier(extracted_value) == self._normalize_identifier(database_value):

            reasons.append("Document number matched exactly")
            return 35

        if (
            database_match.get("_document_match_type") == "fuzzy_ocr_correction"
            and int(database_match.get("_document_match_distance") or 99) <= 2
        ):

            reasons.append(
                f"Document number matched after OCR correction with {database_match.get('_document_match_distance')} digit difference"
            )
            flags.append("Aadhaar OCR digit correction was applied")
            return 30

        flags.append("Document number does not match the database record")
        return 0

    def _score_dob(
        self,
        extracted_data,
        database_match,
        reasons,
        flags
    ):
        """Award date-of-birth points when OCR and database DOB normalize equal."""

        if not database_match:

            return 0

        extracted_dob = self._normalize_dob(extracted_data.get("date_of_birth"))
        database_dob = self._normalize_dob(database_match.get("date_of_birth"))

        if not extracted_dob:

            flags.append("Date of birth was not extracted")
            return 0

        if extracted_dob == database_dob:

            reasons.append("Date of birth matched exactly")
            return 20

        flags.append("Date of birth does not match the database record")
        return 0

    def _score_name(
        self,
        extracted_data,
        database_match,
        reasons,
        flags
    ):
        """Use fuzzy name similarity so minor OCR/name spacing issues can pass."""

        if not database_match:

            return 0

        extracted_name = self._normalize_name(extracted_data.get("full_name"))
        database_name = self._normalize_name(database_match.get("full_name"))

        if not extracted_name:

            flags.append("Name was not extracted")
            return 0

        similarity = round(
            SequenceMatcher(
                None,
                extracted_name,
                database_name
            ).ratio() * 100
        )

        if similarity >= 90:

            reasons.append(f"Name matched strongly at {similarity}% similarity")
            return 20

        if similarity >= 75:

            reasons.append(f"Name partially matched at {similarity}% similarity")
            flags.append("Name requires reviewer confirmation")
            return 12

        if similarity >= 55:

            flags.append(f"Name similarity is weak at {similarity}%")
            return 6

        flags.append(f"Name mismatch detected at {similarity}% similarity")
        return 0

    def _score_face(
        self,
        face_result,
        reasons,
        flags
    ):
        """Translate the face comparison result into risk-score points."""

        score = float(face_result.get("score") or 0.0)
        threshold = float(face_result.get("threshold") or 0.60)

        if face_result.get("matched"):

            reasons.append(f"Face matched with score {score}")
            return 20

        if face_result.get("error"):

            flags.append(face_result.get("error"))
            return 0

        if score >= threshold * 0.90:

            flags.append(f"Face score {score} is close to threshold {threshold}")
            return 10

        flags.append("Face did not match confidently")
        return 0

    def _score_document_format(
        self,
        extracted_data,
        reasons,
        flags
    ):
        """Validate the extracted document number against expected ID formats."""

        document_type = self._normalize_document_type(
            extracted_data.get("document_type")
        )
        field_name = self.DOCUMENT_FIELD_BY_TYPE.get(document_type)
        document_number = extracted_data.get(field_name)

        if not field_name or not document_number:

            flags.append("Document format could not be validated")
            return 0

        normalized_value = self._normalize_identifier(document_number)
        is_valid = False

        if document_type == "aadhaar":

            is_valid = bool(re.fullmatch(r"\d{12}", self._digits_only(document_number)))

        elif document_type == "pan":

            is_valid = bool(re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", normalized_value))

        elif document_type == "voter_id":

            is_valid = bool(re.fullmatch(r"[A-Z0-9]{6,20}", normalized_value))

        elif document_type == "driving_license":

            is_valid = bool(re.fullmatch(r"[A-Z0-9]{8,25}", normalized_value))

        elif document_type == "passport":

            is_valid = bool(re.fullmatch(r"[A-Z][0-9]{7}", normalized_value))

        if is_valid:

            reasons.append("Document number format is valid")
            return 5

        flags.append("Document number format is suspicious")
        return 0

    def _decision_for_score(
        self,
        score,
        flags
    ):
        """Map the final score and severe flags into an approval decision."""

        severe_flags = {
            "No database record was found for the uploaded document number",
            "Document number does not match the database record"
        }

        if any(flag in severe_flags for flag in flags):

            return "REJECTED"

        if score >= 85:

            return "APPROVED"

        if score >= 60:

            return "MANUAL REVIEW"

        return "REJECTED"

    def _risk_level(
        self,
        score
    ):
        """Convert numeric score into LOW, MEDIUM, or HIGH risk labels."""

        if score >= 85:

            return "LOW"

        if score >= 60:

            return "MEDIUM"

        return "HIGH"

    def _normalize_identifier(
        self,
        value
    ):
        """Remove punctuation/spaces from ID values for comparison."""

        return re.sub(
            r"[^A-Za-z0-9]",
            "",
            str(value or "")
        ).upper()

    def _normalize_document_type(
        self,
        document_type
    ):
        """Normalize UI/model document labels into canonical service names."""

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

    def _digits_only(
        self,
        value
    ):
        """Return only numeric characters from a value."""

        return re.sub(
            r"\D",
            "",
            str(value or "")
        )

    def _normalize_name(
        self,
        value
    ):
        """Uppercase names and collapse punctuation/extra whitespace."""

        return re.sub(
            r"\s+",
            " ",
            re.sub(
                r"[^A-Za-z ]",
                " ",
                str(value or "")
            )
        ).strip().upper()

    def _normalize_dob(
        self,
        value
    ):
        """Normalize common DOB formats before comparing OCR and database values."""

        if not value:

            return ""

        text = str(value).strip().replace("/", "-")

        dd_mm_yyyy = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", text)

        if dd_mm_yyyy:

            return f"{dd_mm_yyyy.group(3)}-{dd_mm_yyyy.group(2)}-{dd_mm_yyyy.group(1)}"

        yyyy_mm_dd = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)

        if yyyy_mm_dd:

            return text

        return text
