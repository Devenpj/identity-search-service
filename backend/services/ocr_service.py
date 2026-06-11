"""OCR adapter around the vendored Indian ID validator model."""

import json
import os
import re
import subprocess
import sys

from config import settings


class OCRService:
    """Run document-specific OCR and normalize model output for verification."""

    def __init__(self):
        """Resolve validator paths and track the latest extracted face path."""

        self.validator_root = settings.INDIAN_ID_VALIDATOR_ROOT
        self.validator_python = settings.INDIAN_ID_VALIDATOR_PYTHON
        self.last_face_path = None

    def extract_text(
        self,
        image_path,
        document_type=None
    ):
        """Run the external validator model and return its JSON OCR output."""

        return self._run_validator_model(
            image_path,
            document_type
        )

    def classify_document(self, image_path):
        """Run the validator classifier and return normalized document type data."""

        if not os.path.exists(self.validator_root):

            raise RuntimeError(
                f"Vendored Indian ID validator folder not found: {self.validator_root}"
            )

        python_executable = (
            self.validator_python
            if self.validator_python and os.path.exists(self.validator_python)
            else sys.executable
        )
        command = [
            python_executable,
            "inference.py",
            image_path,
            "--classify-only"
        ]

        result = subprocess.run(
            command,
            cwd=self.validator_root,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:

            raise RuntimeError(
                f"Indian ID validator classification failed: {result.stderr or result.stdout}"
            )

        classifier_output = self._parse_classifier_stdout(result.stdout)
        raw_doc_type = classifier_output.get("doc_type")
        confidence = float(classifier_output.get("confidence") or 0)

        return {
            "raw_document_type": raw_doc_type,
            "document_type": self._normalize_classifier_document_type(raw_doc_type),
            "confidence": confidence
        }

    def extract_identity_fields(self, document_type, extracted_text):
        """Normalize raw OCR output into the identity fields used by the backend."""

        if isinstance(extracted_text, dict):

            model_data = extracted_text

        else:

            model_data = {
                "raw_text": extracted_text
            }

        raw_text = json.dumps(
            model_data,
            indent=2
        )

        normalized_type = self._normalize_document_type(document_type)

        aadhaar_number = self._clean_aadhaar(
            self._get_value(
                model_data,
                [
                    "Aadhaar",
                    "Aadhar",
                    "aadhaar",
                    "aadhar",
                    "Aadhaar Number",
                    "Aadhar Number",
                    "UID"
                ]
            )
        )

        if not aadhaar_number:

            aadhaar_number = self._extract_aadhaar_from_text(raw_text)

        pan_number = self._clean_pan(
            self._get_value(
                model_data,
                [
                    "PAN",
                    "pan",
                    "PAN Number",
                    "pan_number"
                ]
            )
        )
        voter_id_number = self._clean_identifier(
            self._get_value(
                model_data,
                [
                    "Voter ID",
                    "voter_id",
                    "Voter_Id",
                    "EPIC",
                    "Election"
                ]
            )
        )
        driving_license_number = self._clean_identifier(
            self._get_value(
                model_data,
                [
                    "DL No",
                    "DL Number",
                    "Driving License",
                    "Driving Licence",
                    "driving_license_number"
                ]
            )
        )
        passport_number = self._clean_identifier(
            self._get_value(
                model_data,
                [
                    "Code",
                    "Passport",
                    "Passport Number",
                    "passport_number"
                ]
            )
        )

        extracted_data = {
            "document_type": normalized_type,
            "raw_text": raw_text,
            "model_output": model_data,
            "full_name": self._get_value(model_data, ["Name", "name"]),
            "date_of_birth": self._extract_dob(model_data),
            "aadhar_number": aadhaar_number,
            "pan_number": pan_number,
            "voter_id_number": voter_id_number,
            "driving_license_number": driving_license_number,
            "passport_number": passport_number
        }

        return extracted_data

    def _run_validator_model(
        self,
        image_path,
        document_type
    ):
        """Execute `inference.py` in the vendored validator folder.

        The subprocess writes a detected-text JSON file beside the upload and
        may also write `results/face.jpg`, which is reused by face verification.
        """

        if not os.path.exists(self.validator_root):

            raise RuntimeError(
                f"Vendored Indian ID validator folder not found: {self.validator_root}"
            )

        python_executable = (
            self.validator_python
            if self.validator_python and os.path.exists(self.validator_python)
            else sys.executable
        )

        output_json = os.path.join(
            os.path.dirname(image_path),
            f"{os.path.splitext(os.path.basename(image_path))[0]}_detected_text.json"
        )
        face_path = os.path.join(
            self.validator_root,
            "results",
            "face.jpg"
        )

        self.last_face_path = None

        if os.path.exists(face_path):

            os.remove(face_path)

        command = [
            python_executable,
            "inference.py",
            image_path,
            "--model",
            self._get_model_name(document_type),
            "--output-json",
            output_json
        ]

        result = subprocess.run(
            command,
            cwd=self.validator_root,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:

            raise RuntimeError(
                f"Indian ID validator OCR failed: {result.stderr or result.stdout}"
            )

        if not os.path.exists(output_json):

            raise RuntimeError("Indian ID validator did not produce OCR output JSON")

        if os.path.exists(face_path):

            self.last_face_path = face_path

        with open(output_json, "r") as file_object:

            return json.load(file_object)

    def get_last_face_path(self):
        """Return the face image path produced by the most recent OCR run."""

        return self.last_face_path

    def _get_model_name(self, document_type):
        """Map normalized document type to the YOLO model expected by inference."""

        normalized_type = self._normalize_document_type(document_type)

        if normalized_type in {
            "pan",
            "pan card",
            "pan_card"
        }:

            return "Pan_Card"

        if normalized_type in {
            "voter",
            "voter id",
            "voter_id",
            "voter card",
            "voter_card"
        }:

            return "Voter_Id"

        if normalized_type in {
            "driving_license",
            "driving license",
            "driving licence",
            "driving_licence",
            "license",
            "licence"
        }:

            return "Driving_License"

        if normalized_type == "passport":

            return "Passport"

        return "Aadhaar"

    def _normalize_document_type(self, document_type):
        """Normalize user-facing document labels into canonical names."""

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
            "driving_license": "driving_license",
            "driving_licence": "driving_license",
            "license": "driving_license",
            "licence": "driving_license"
        }

        return aliases.get(normalized_type, normalized_type)

    def _normalize_classifier_document_type(self, document_type):
        """Map classifier labels into the same canonical types used by the UI."""

        normalized_type = self._normalize_document_type(document_type)
        aliases = {
            "aadhar_front": "aadhaar",
            "aadhar_back": "aadhaar",
            "aadhaar_front": "aadhaar",
            "aadhaar_back": "aadhaar",
            "pan_card_front": "pan",
            "pan_card": "pan",
            "voter_id": "voter_id",
            "driving_license_front": "driving_license",
            "driving_license_back": "driving_license",
            "passport": "passport"
        }

        return aliases.get(normalized_type, normalized_type)

    def _parse_classifier_stdout(self, stdout):
        """Extract the JSON classifier result printed by inference.py."""

        stdout = stdout or ""
        start_index = stdout.find("{")
        end_index = stdout.rfind("}")

        if start_index == -1 or end_index == -1 or end_index < start_index:

            raise RuntimeError("Indian ID validator classification did not return JSON")

        return json.loads(stdout[start_index:end_index + 1])

    def _get_value(self, data, keys):
        """Return the first useful OCR value from a list of possible keys."""

        for key in keys:

            value = data.get(key)

            if value and str(value).lower() != "no text detected":

                return str(value).strip()

        return None

    def _clean_aadhaar(self, value):
        """Extract only Aadhaar digits from model output."""

        if not value:

            return None

        digits = re.sub(r"\D", "", value)

        return digits if re.fullmatch(r"\d{12}", digits) else None

    def _extract_aadhaar_from_text(self, text):
        """Fallback regex search for Aadhaar when the model key is missing."""

        match = re.search(
            r"\b\d{4}\s?\d{4}\s?\d{4}\b",
            str(text or "")
        )

        if not match:

            return None

        return self._clean_aadhaar(match.group(0))

    def _clean_pan(self, value):
        """Normalize and validate a PAN-like value from OCR output."""

        if not value:

            return None

        normalized_value = re.sub(
            r"[^A-Z0-9]",
            "",
            value.upper()
        )

        match = re.search(r"[A-Z]{5}[0-9]{4}[A-Z]?", normalized_value)

        if not match:

            return None

        return match.group(0)

    def _clean_identifier(self, value):
        """Normalize generic ID values such as voter ID, DL, and passport."""

        if not value:

            return None

        normalized_value = re.sub(
            r"[^A-Za-z0-9]",
            "",
            value
        ).upper()

        return normalized_value or None

    def _normalize_dob(self, value):
        """Normalize date strings while preserving unknown free-form values."""

        if not value:

            return None

        text = str(value)

        patterns = [
            r"\b(\d{2}[/-]\d{2}[/-]\d{4})\b",
            r"\b(\d{4}[/-]\d{2}[/-]\d{2})\b"
        ]

        for pattern in patterns:

            match = re.search(pattern, text)

            if match:

                return match.group(1).replace("/", "-")

        return text.replace("/", "-").strip()

    def _extract_dob(self, data):
        """Find DOB from direct fields first, then scan all OCR values."""

        direct_value = self._get_value(
            data,
            [
                "DOB",
                "dob",
                "Date of Birth",
                "date_of_birth",
                "Birth Date",
                "Year of Birth",
                "YOB"
            ]
        )

        normalized_direct_value = self._normalize_dob(direct_value)

        if normalized_direct_value:

            return normalized_direct_value

        for value in data.values():

            normalized_value = self._normalize_dob(value)

            if normalized_value and re.search(r"\d{2,4}-\d{2}-\d{2,4}", normalized_value):

                return normalized_value

        return None
