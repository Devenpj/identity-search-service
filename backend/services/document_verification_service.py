"""Orchestrates document verification from upload to final decision."""

import re

from utils.logger import get_logger


class DocumentVerificationService:
    """Coordinate file saving, OCR, DB matching, face checks, risk, and review."""

    DOCUMENT_LABELS = {
        "aadhaar": "Aadhaar Card",
        "pan": "PAN Card",
        "voter_id": "Voter ID Card",
        "driving_license": "Driving Licence",
        "passport": "Passport"
    }

    CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.50
    WRONG_DOCUMENT_MESSAGE = "User has uploaded the wrong document. Please upload the right document."

    def __init__(
        self,
        file_service,
        ocr_service,
        database_service,
        face_service,
        risk_service,
        decision_service
    ):
        """Receive service dependencies so the workflow stays easy to test."""

        self.file_service = file_service
        self.ocr_service = ocr_service
        self.database_service = database_service
        self.face_service = face_service
        self.risk_service = risk_service
        self.decision_service = decision_service
        self.logger = get_logger("identity-search-service.document-verification")

    def verify(
        self,
        document_type,
        document,
        manual_values=None
    ):
        """Run document verification for one uploaded file object."""

        manual_values = manual_values or {}

        self.logger.info(
            "Document verification started: document_type=%s filename=%s",
            document_type,
            document.filename
        )

        saved_file_path = self.file_service.save_upload(document)

        return self.verify_saved_file(
            document_type=document_type,
            saved_file_path=saved_file_path,
            original_filename=document.filename,
            manual_values=manual_values
        )

    def verify_saved_file(
        self,
        document_type,
        saved_file_path,
        original_filename="uploaded_document",
        manual_values=None,
        progress_callback=None
    ):
        """Run the full verification pipeline for an already-saved document image."""

        manual_values = manual_values or {}
        progress_callback = progress_callback or (lambda percent, message: None)

        self.logger.info(
            "Document verification processing saved file: document_type=%s filename=%s path=%s",
            document_type,
            original_filename,
            saved_file_path
        )

        self.logger.info("Document upload saved: path=%s", saved_file_path)

        classification = self._validate_selected_document_type(
            document_type,
            saved_file_path
        )
        progress_callback(
            35,
            "Document type checked. Running OCR."
        )

        extracted_text = self.ocr_service.extract_text(
            saved_file_path,
            document_type
        )
        progress_callback(
            50,
            "OCR completed. Extracting identity fields."
        )

        self.logger.info("OCR completed: document_type=%s", document_type)

        extracted_data = self.ocr_service.extract_identity_fields(
            document_type,
            extracted_text
        )

        self.logger.info(
            "Identity fields extracted: document_type=%s name=%s aadhaar=%s pan=%s voter_id=%s driving_license=%s passport=%s",
            extracted_data.get("document_type"),
            extracted_data.get("full_name"),
            extracted_data.get("aadhar_number"),
            extracted_data.get("pan_number"),
            extracted_data.get("voter_id_number"),
            extracted_data.get("driving_license_number"),
            extracted_data.get("passport_number")
        )

        self._validate_extracted_document_type(
            document_type,
            extracted_data,
            classification
        )
        progress_callback(
            60,
            "Identity fields extracted. Applying manual overrides."
        )

        self._apply_manual_values(
            extracted_data,
            manual_values
        )

        database_match = self.database_service.verify_identity_document(
            extracted_data
        )
        progress_callback(
            75,
            "Database verification completed. Checking face match."
        )

        self._apply_ocr_correction_metadata(
            extracted_data,
            database_match
        )

        self.logger.info(
            "Database verification completed: matched=%s employee_id=%s",
            bool(database_match),
            (database_match or {}).get("employee_id")
        )

        face_result = self._verify_face(database_match)
        progress_callback(
            85,
            "Face verification completed. Calculating risk."
        )

        risk_assessment = self.risk_service.calculate(
            extracted_data,
            database_match,
            face_result
        )
        progress_callback(
            92,
            "Risk score calculated. Building final decision."
        )

        self.logger.info(
            "Risk assessment completed: score=%s level=%s decision=%s",
            risk_assessment.get("risk_score"),
            risk_assessment.get("risk_level"),
            risk_assessment.get("decision")
        )

        decision = self.decision_service.build_decision(
            database_match,
            face_result,
            risk_assessment
        )

        self.logger.info(
            "Document verification decision built: status=%s message=%s",
            decision.get("status"),
            decision.get("message")
        )

        manual_review_case = self._create_manual_review_case(
            extracted_data,
            database_match,
            face_result,
            decision,
            saved_file_path
        )
        progress_callback(
            98,
            "Final decision built. Saving result."
        )

        self.logger.info(
            "Document verification completed: document_type=%s status=%s",
            extracted_data.get("document_type"),
            decision.get("status")
        )

        return {
            "status": "success",
            "extracted_data": extracted_data,
            "database_match": database_match,
            "face_verification": face_result,
            "risk_assessment": risk_assessment,
            "decision": decision,
            "manual_review_case": manual_review_case
        }
    def _validate_selected_document_type(
        self,
        selected_document_type,
        saved_file_path
    ):
        """Stop verification early when uploaded ID type differs from dropdown."""

        expected_type = self.ocr_service._normalize_document_type(
            selected_document_type
        )
        classification = self.ocr_service.classify_document(saved_file_path)
        detected_type = classification.get("document_type")
        confidence = classification.get("confidence") or 0

        self.logger.info(
            "Document type classification completed: expected=%s detected=%s raw_detected=%s confidence=%s",
            expected_type,
            detected_type,
            classification.get("raw_document_type"),
            confidence
        )

        if not detected_type or confidence < self.CLASSIFICATION_CONFIDENCE_THRESHOLD:

            raise ValueError(self.WRONG_DOCUMENT_MESSAGE)

        if detected_type != expected_type:

            raise ValueError(self.WRONG_DOCUMENT_MESSAGE)

        return classification

    def _validate_extracted_document_type(
        self,
        selected_document_type,
        extracted_data,
        classification
    ):
        """Catch wrong uploads that classifier allowed but OCR signals reject."""

        expected_type = self.ocr_service._normalize_document_type(
            selected_document_type
        )
        detected_from_content = self._infer_document_type_from_content(
            extracted_data
        )
        confidence = (classification or {}).get("confidence") or 0

        self.logger.info(
            "Document content validation completed: expected=%s content_detected=%s classifier_confidence=%s",
            expected_type,
            detected_from_content,
            confidence
        )

        if detected_from_content and detected_from_content != expected_type:

            raise ValueError(self.WRONG_DOCUMENT_MESSAGE)

    def _infer_document_type_from_content(
        self,
        extracted_data
    ):
        """Infer document type from extracted fields and text-specific signals."""

        extracted_data = extracted_data or {}

        raw_text = str(extracted_data.get("raw_text") or "").lower()

        strong_signal_checks = [
            (
                "pan",
                (
                    "income tax",
                    "permanent account",
                    "pan card"
                )
            ),
            (
                "voter_id",
                (
                    "election commission",
                    "elector",
                    "voter id",
                    "epic"
                )
            ),
            (
                "driving_license",
                (
                    "driving licence",
                    "driving license",
                    "transport department",
                    "dl no",
                    "licence no",
                    "license no"
                )
            ),
            (
                "passport",
                (
                    "passport",
                    "nationality",
                    "place of birth",
                    "date of expiry"
                )
            ),
            (
                "aadhaar",
                (
                    "unique identification",
                    "uidai",
                    "aadhaar",
                    "aadhar"
                )
            )
        ]

        for document_type, signals in strong_signal_checks:

            if any(signal in raw_text for signal in signals):

                return document_type

        if self._raw_text_has_pan_number(raw_text):

            return "pan"

        if extracted_data.get("aadhar_number"):

            return "aadhaar"

        if extracted_data.get("pan_number"):

            return "pan"

        if extracted_data.get("voter_id_number"):

            return "voter_id"

        if extracted_data.get("driving_license_number"):

            return "driving_license"

        if extracted_data.get("passport_number"):

            return "passport"

        return None

    def _raw_text_has_pan_number(
        self,
        raw_text
    ):
        """Return True when raw OCR text contains a PAN-number-like token."""

        normalized_text = str(raw_text or "").upper()

        return bool(
            re.search(
                r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
                normalized_text
            )
        )

    def _document_label(
        self,
        document_type
    ):
        """Return a clean user-facing document label from a canonical type."""

        return self.DOCUMENT_LABELS.get(
            document_type,
            str(document_type or "another document").replace("_", " ").title()
        )

    def _apply_manual_values(
        self,
        extracted_data,
        manual_values
    ):
        """Overwrite OCR fields with reviewer/user supplied values when present."""

        for key, value in manual_values.items():

            if value and value.strip():

                extracted_data[key] = value.strip()

                self.logger.info(
                    "Manual document field override applied: field=%s",
                    key
                )

    def _verify_face(
        self,
        database_match
    ):
        """Compare extracted document face against the matched database photo."""

        if not database_match:

            self.logger.info("Face verification skipped because database match was not found")

            return {
                "matched": False,
                "score": 0.0,
                "method": "opencv_histogram_ncc",
                "error": "Face verification skipped because database match was not found"
            }

        face_result = self.face_service.compare_faces(
            self.ocr_service.get_last_face_path(),
            database_match.get("photo_path")
        )

        self.logger.info(
            "Face verification completed: matched=%s score=%s error=%s",
            face_result.get("matched"),
            face_result.get("score"),
            face_result.get("error")
        )

        return face_result

    def _apply_ocr_correction_metadata(
        self,
        extracted_data,
        database_match
    ):
        """Record fuzzy Aadhaar correction details when DB matching repaired OCR."""

        if not database_match:

            return

        if database_match.get("_document_match_type") != "fuzzy_ocr_correction":

            return

        field_name = "aadhar_number"
        original_value = extracted_data.get(field_name)
        corrected_value = database_match.get(field_name)

        extracted_data["ocr_correction"] = {
            "applied": True,
            "field": field_name,
            "original_value": original_value,
            "corrected_value": corrected_value,
            "digit_difference": database_match.get("_document_match_distance")
        }
        extracted_data[field_name] = corrected_value

        self.logger.info(
            "OCR correction applied: field=%s original=%s corrected=%s digit_difference=%s",
            field_name,
            original_value,
            corrected_value,
            database_match.get("_document_match_distance")
        )

    def _create_manual_review_case(
        self,
        extracted_data,
        database_match,
        face_result,
        decision,
        saved_file_path
    ):
        """Create a review queue entry only when the decision asks for it."""

        if decision.get("status") != "MANUAL REVIEW":

            return None

        manual_review_case = self.database_service.create_manual_review_case(
            extracted_data,
            database_match,
            face_result,
            decision,
            saved_file_path
        )

        self.logger.info(
            "Manual review case created: case_id=%s",
            manual_review_case.get("id") if manual_review_case else None
        )

        return manual_review_case
