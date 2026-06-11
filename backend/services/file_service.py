"""File persistence helpers for uploaded documents and profile photos."""

import os
import uuid


class FileService:
    """Validate image uploads and place them where backend/frontend can use them."""

    def __init__(self, upload_dir="uploads"):
        """Create the upload directory used for temporary document images."""

        self.upload_dir = upload_dir
        os.makedirs(self.upload_dir, exist_ok=True)

    def save_upload(self, uploaded_file):
        """Save a document upload for OCR and return its absolute local path."""

        original_name = uploaded_file.filename or "uploaded_document"
        extension = os.path.splitext(original_name)[1].lower()

        allowed_extensions = {
            ".jpg",
            ".jpeg",
            ".png"
        }

        if extension not in allowed_extensions:

            raise ValueError("Only JPG, JPEG, and PNG uploads are supported")

        file_name = f"{uuid.uuid4().hex}{extension}"
        file_path = os.path.join(self.upload_dir, file_name)

        with open(file_path, "wb") as file_object:

            file_object.write(uploaded_file.file.read())

        return os.path.abspath(file_path)

    def save_employee_photo(
        self,
        uploaded_file,
        employee_id
    ):
        """Save a profile photo under frontend assets and return dashboard path."""

        extension = self._validate_image_extension(uploaded_file.filename)
        safe_employee_id = "".join(
            character
            for character in employee_id
            if character.isalnum() or character in {"_", "-"}
        )

        if not safe_employee_id:

            raise ValueError("Employee ID is required to save profile photo")

        relative_path = os.path.join(
            "matched_employee_photos",
            safe_employee_id,
            f"{safe_employee_id}_face{extension}"
        )
        frontend_root = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "frontend"
            )
        )
        absolute_path = os.path.join(
            frontend_root,
            relative_path
        )

        os.makedirs(
            os.path.dirname(absolute_path),
            exist_ok=True
        )

        with open(absolute_path, "wb") as file_object:

            file_object.write(uploaded_file.file.read())

        return "/" + relative_path.replace("\\", "/")

    def _validate_image_extension(self, filename):
        """Allow only image formats supported by OCR and face comparison."""

        original_name = filename or "uploaded_image"
        extension = os.path.splitext(original_name)[1].lower()

        allowed_extensions = {
            ".jpg",
            ".jpeg",
            ".png"
        }

        if extension not in allowed_extensions:

            raise ValueError("Only JPG, JPEG, and PNG uploads are supported")

        return extension
