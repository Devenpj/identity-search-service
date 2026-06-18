"""Normalize raw OSINT provider JSON into searchable rows and saved images."""

import base64
import binascii
import io
import json
import os
import re
from uuid import uuid4

from PIL import Image
from PIL import UnidentifiedImageError

from utils.logger import get_logger


logger = get_logger("identity-search-service.osint-normalizer")


class OSINTNormalizerService:
    """Convert flexible OSINT payloads into stable database rows."""

    def __init__(self, image_dir=None):
        """Create the OSINT image folder used for decoded provider avatars."""

        project_root = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                ".."
            )
        )
        self.image_dir = image_dir or os.path.join(
            project_root,
            "backend",
            "uploads",
            "osint_images"
        )
        os.makedirs(
            self.image_dir,
            exist_ok=True
        )

    def normalize_and_store(
        self,
        job_id,
        payload,
        database_service
    ):
        """Normalize a webhook payload and store it beside the raw job result."""

        result_payload = payload.get("results") if isinstance(payload, dict) else None

        if isinstance(result_payload, dict):
            source_payload = result_payload
        elif isinstance(payload, dict):
            source_payload = payload
        else:
            source_payload = {}

        profiles = self._profile_rows(
            job_id,
            source_payload
        )
        contacts = self._contact_rows(source_payload)
        matches = self._match_rows(
            job_id,
            source_payload
        )
        profiles = self._dedupe_rows(
            profiles,
            [
                "platform",
                "target",
                "username",
                "profile_url",
                "avatar_url",
                "bio",
                "status"
            ]
        )
        matches = self._dedupe_rows(
            matches,
            [
                "platform",
                "url",
                "avatar_url",
                "bio"
            ]
        )

        database_service.replace_normalized_osint_data(
            job_id=job_id,
            profiles=profiles,
            contacts=contacts,
            matches=matches
        )

        return {
            "profiles": len(profiles),
            "contacts": len(contacts),
            "matches": len(matches)
        }

    def _profile_rows(
        self,
        job_id,
        payload
    ):
        """Collect social/profile rows from all social-media result sections."""

        rows = []
        excluded_sections = {
            "phone_results",
            "email_results",
            "all_matches",
            "inputs_processed"
        }

        for section_key, section_value in payload.items():

            if section_key in excluded_sections:
                continue

            if section_key == "profile_url":
                rows.append(
                    {
                        "platform": "OSINT",
                        "target": None,
                        "username": None,
                        "full_name": None,
                        "profile_url": section_value,
                        "avatar_url": self._find_nested_url(
                            payload,
                            ["avatar", "image", "photo", "picture"],
                            ["base64"]
                        ),
                        "avatar_path": self._save_first_base64_image(
                            job_id,
                            "osint",
                            "profile",
                            payload
                        ),
                        "bio": None,
                        "status": "found",
                        "confidence": None,
                        "extracted_text": self._readable_text(payload),
                        "raw_payload": payload
                    }
                )
                continue

            if not section_key.endswith("_results"):
                continue

            section_rows = section_value if isinstance(section_value, list) else [section_value]

            for item in section_rows:

                if not isinstance(item, dict):
                    continue

                if section_key == "username_results" and item.get("matches"):
                    for match in item.get("matches") or []:
                        if not isinstance(match, dict):
                            continue

                        enriched_data = match.get("enriched_data") or {}
                        platform = match.get("platform") or item.get("platform")
                        platform = self._display_platform(
                            platform,
                            match
                        )
                        target = item.get("target")
                        avatar_path = self._save_first_base64_image(
                            job_id,
                            platform,
                            target,
                            match
                        )

                        rows.append(
                            {
                                "platform": platform,
                                "target": target,
                                "username": item.get("username") or target,
                                "full_name": (
                                    match.get("full_name")
                                    or match.get("name")
                                    or enriched_data.get("full_name")
                                    or enriched_data.get("display_name")
                                    or enriched_data.get("name")
                                ),
                                "profile_url": self._profile_url(match),
                                "avatar_url": self._avatar_url(match),
                                "avatar_path": avatar_path,
                                "bio": match.get("bio") or enriched_data.get("bio"),
                                "status": match.get("status") or item.get("status"),
                                "confidence": match.get("confidence") or enriched_data.get("confidence"),
                                "extracted_text": self._readable_text(
                                    enriched_data
                                    or match.get("details")
                                    or match.get("message")
                                ),
                                "raw_payload": match
                            }
                        )
                    continue

                platform = (
                    item.get("platform")
                    or self._humanize(section_key)
                )
                platform = self._display_platform(
                    platform,
                    item
                )
                target = (
                    item.get("target")
                    or item.get("target_username")
                    or item.get("username")
                )
                extracted_data = item.get("extracted_data") or {}
                avatar_path = self._save_first_base64_image(
                    job_id,
                    platform,
                    target,
                    item
                )

                rows.append(
                    {
                        "platform": platform,
                        "target": target,
                        "username": item.get("username") or item.get("target_username"),
                        "full_name": (
                            item.get("full_name")
                            or item.get("name")
                            or extracted_data.get("full_name")
                            or extracted_data.get("display_name")
                            or extracted_data.get("name")
                        ),
                        "profile_url": self._profile_url(item),
                        "avatar_url": self._avatar_url(item),
                        "avatar_path": avatar_path,
                        "bio": (
                            item.get("bio")
                            or extracted_data.get("bio")
                            or self._nested_value(item, ["details", "bio"])
                        ),
                        "status": item.get("status"),
                        "confidence": (
                            item.get("confidence")
                            or extracted_data.get("confidence")
                            or self._nested_value(item, ["details", "confidence"])
                        ),
                        "extracted_text": self._readable_text(item),
                        "raw_payload": item
                    }
                )

        return rows

    def _contact_rows(self, payload):
        """Collect phone and email evidence rows."""

        rows = []

        for contact_type, section_key in (
            ("phone", "phone_results"),
            ("email", "email_results")
        ):

            for result_row in payload.get(section_key) or []:

                matches = result_row.get("matches") or []

                if not matches:
                    rows.append(
                        {
                            "contact_type": contact_type,
                            "target": result_row.get("target"),
                            "platform": None,
                            "status": result_row.get("status"),
                            "category": None,
                            "details": (
                                result_row.get("message")
                                or self._readable_text(result_row)
                            ),
                            "raw_payload": result_row
                        }
                    )
                    continue

                for match in matches:
                    rows.append(
                        {
                            "contact_type": contact_type,
                            "target": result_row.get("target"),
                            "platform": match.get("platform"),
                            "status": match.get("status") or result_row.get("status"),
                            "category": match.get("category"),
                            "details": (
                                match.get("details")
                                or match.get("message")
                                or self._readable_text(match)
                            ),
                            "raw_payload": match
                        }
                    )

        return rows

    def _match_rows(
        self,
        job_id,
        payload
    ):
        """Collect enriched match rows with decoded avatars when available."""

        rows = []

        for item in payload.get("all_matches") or []:

            if not isinstance(item, dict):
                continue

            enriched_data = item.get("enriched_data") or {}
            platform = item.get("platform")
            platform = self._display_platform(
                platform,
                item
            )

            if self._is_phone_or_email_platform(platform):
                continue

            avatar_path = self._save_first_base64_image(
                job_id,
                platform,
                "match",
                item
            )

            rows.append(
                {
                    "platform": platform,
                    "url": item.get("url") or item.get("profile_url"),
                    "bio": enriched_data.get("bio") or item.get("bio"),
                    "avatar_url": (
                        item.get("avatar_url")
                        or enriched_data.get("avatar_url")
                    ),
                    "avatar_path": avatar_path,
                    "confidence": item.get("confidence") or enriched_data.get("confidence"),
                    "raw_payload": item
                }
            )

        return rows

    def _dedupe_rows(
        self,
        rows,
        keys
    ):
        """Remove duplicate normalized rows without using generated file paths."""

        deduped_rows = []
        seen = set()

        for row in rows:
            fingerprint = tuple(
                str(row.get(key) or "").strip().lower()
                for key in keys
            )

            if fingerprint in seen:
                continue

            seen.add(fingerprint)
            deduped_rows.append(row)

        return deduped_rows

    def _is_phone_or_email_platform(self, platform):
        """Return True when an all_matches row belongs in phone/email results."""

        normalized_platform = str(platform or "").lower()
        phone_email_tokens = [
            "phone",
            "phonenumber",
            "phonenumbers",
            "network",
            "carrier",
            "telecom",
            "email",
            "gmail",
            "zerobounce",
            "domain"
        ]

        return any(token in normalized_platform for token in phone_email_tokens)

    def _save_first_base64_image(
        self,
        job_id,
        platform,
        target,
        payload
    ):
        """Decode the first base64 image found in a provider payload."""

        base64_value = self._find_base64_image(payload)

        if not base64_value:
            return None

        try:
            image_bytes, extension = self._decode_base64_image(base64_value)
        except ValueError as error:
            logger.warning(
                "OSINT base64 image skipped: job_id=%s platform=%s reason=%s",
                job_id,
                platform,
                error
            )
            return None

        file_name = "{}_{}_{}_{}.{}".format(
            self._safe_name(job_id),
            self._safe_name(platform or "platform"),
            self._safe_name(target or "target"),
            uuid4().hex[:8],
            extension
        )
        absolute_path = os.path.join(
            self.image_dir,
            file_name
        )

        with open(absolute_path, "wb") as image_file:
            image_file.write(image_bytes)

        return os.path.relpath(
            absolute_path,
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    ".."
                )
            )
        ).replace("\\", "/")

    def _decode_base64_image(self, value):
        """Decode raw/data-URI base64 image data and infer an extension."""

        if not isinstance(value, str):
            raise ValueError("Image value is not a string")

        image_value = value.strip()
        extension = "jpg"

        if image_value.startswith("data:image/"):
            header, _, image_value = image_value.partition(",")
            extension = header.split("data:image/", 1)[1].split(";", 1)[0]
            if extension == "jpeg":
                extension = "jpg"

        try:
            image_bytes = base64.b64decode(
                image_value,
                validate=True
            )
        except (binascii.Error, ValueError) as error:
            raise ValueError("Invalid base64 image data") from error

        if len(image_bytes) < 64:
            raise ValueError("Decoded image is too small")

        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
                image_format = (image.format or "").upper()
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise ValueError("Decoded image is not a renderable image") from error

        extension_map = {
            "JPEG": "jpg",
            "JPG": "jpg",
            "PNG": "png",
            "WEBP": "webp"
        }
        extension = extension_map.get(image_format)

        if not extension:
            raise ValueError(f"Unsupported avatar image format: {image_format or 'unknown'}")

        return image_bytes, extension

    def _find_base64_image(self, value):
        """Find base64 image data anywhere in nested OSINT payloads."""

        if isinstance(value, dict):
            for key, nested_value in value.items():
                normalized_key = str(key or "").lower()

                if (
                    "base64" in normalized_key
                    or "image_data" in normalized_key
                    or "avatar_data" in normalized_key
                ) and self._looks_like_base64(nested_value):
                    return nested_value

            for nested_value in value.values():
                found_value = self._find_base64_image(nested_value)
                if found_value:
                    return found_value

        elif isinstance(value, list):
            for nested_value in value:
                found_value = self._find_base64_image(nested_value)
                if found_value:
                    return found_value

        elif self._looks_like_base64(value):
            return value

        return None

    def _looks_like_base64(self, value):
        """Return True for likely image base64 strings."""

        if not isinstance(value, str):
            return False

        stripped_value = value.strip()

        if stripped_value.startswith("data:image"):
            return True

        if len(stripped_value) < 120:
            return False

        compact_value = stripped_value.replace("\n", "").replace("\r", "")

        if compact_value.startswith(("/9j/", "iVBOR", "AAAA")):
            return True

        return bool(
            re.fullmatch(
                r"[A-Za-z0-9+/=]+",
                compact_value[:240]
            )
        )

    def _profile_url(self, item):
        """Extract public profile URLs without mistaking avatar URLs as profiles."""

        return (
            item.get("profile_url")
            or item.get("profileUrl")
            or item.get("url")
            or item.get("link")
            or self._find_nested_url(
                item,
                ["profile", "url", "link"],
                ["avatar", "image", "photo", "base64"]
            )
        )

    def _avatar_url(self, item):
        """Extract avatar/photo URLs."""

        return (
            item.get("avatar_url")
            or item.get("avatarUrl")
            or item.get("image_url")
            or item.get("photo_url")
            or self._find_nested_url(
                item,
                ["avatar", "image", "photo", "picture"],
                ["base64"]
            )
        )

    def _find_nested_url(
        self,
        value,
        key_tokens,
        excluded_tokens=None
    ):
        """Find a nested URL whose key matches expected semantic tokens."""

        excluded_tokens = excluded_tokens or []

        if isinstance(value, dict):
            for key, nested_value in value.items():
                normalized_key = str(key or "").lower()

                if any(token in normalized_key for token in excluded_tokens):
                    continue

                if (
                    any(token in normalized_key for token in key_tokens)
                    and isinstance(nested_value, str)
                    and nested_value.startswith(("http://", "https://"))
                ):
                    return nested_value

            for nested_value in value.values():
                found_url = self._find_nested_url(
                    nested_value,
                    key_tokens,
                    excluded_tokens
                )

                if found_url:
                    return found_url

        if isinstance(value, list):
            for nested_value in value:
                found_url = self._find_nested_url(
                    nested_value,
                    key_tokens,
                    excluded_tokens
                )

                if found_url:
                    return found_url

        return None

    def _readable_text(self, value):
        """Flatten useful OSINT fields into readable text without image blobs."""

        if value in (None, "", [], {}):
            return None

        if self._looks_like_base64(value):
            return "[hidden base64 image]"

        if isinstance(value, dict):
            lines = []
            hidden_tokens = {
                "base64",
                "avatar_url",
                "avatarurl",
                "profile_url",
                "profileurl",
                "image_url",
                "photo_url",
                "url",
                "link",
                "local_avatar_path"
            }

            for key, nested_value in value.items():
                normalized_key = str(key or "").lower()

                if any(token in normalized_key for token in hidden_tokens):
                    continue

                readable_value = self._readable_text(nested_value)

                if readable_value:
                    lines.append(
                        f"{self._humanize(key)}: {readable_value}"
                    )

            return "\n".join(lines) if lines else None

        if isinstance(value, list):
            items = [
                self._readable_text(item)
                for item in value
            ]
            items = [
                item
                for item in items
                if item
            ]

            return "\n".join(
                f"{index}. {item}"
                for index, item in enumerate(items, 1)
            ) if items else None

        return str(value)

    def _nested_value(self, value, path):
        """Read a nested dictionary value using a list path."""

        current_value = value

        for key in path:
            if not isinstance(current_value, dict):
                return None

            current_value = current_value.get(key)

        return current_value

    def _humanize(self, value):
        """Convert provider keys into readable labels."""

        return str(value or "").replace("_", " ").strip().title()

    def _display_platform(
        self,
        platform,
        item
    ):
        """Clean provider platform labels that come from URL subdomains."""

        platform_text = str(platform or "").strip()
        profile_url = self._profile_url(item) if isinstance(item, dict) else ""
        avatar_url = self._avatar_url(item) if isinstance(item, dict) else ""
        combined_urls = f"{profile_url} {avatar_url}".lower()

        if platform_text.lower() in {"en", "www"} and "gravatar.com" in combined_urls:
            return "Gravatar"

        return platform_text or None

    def _safe_name(self, value):
        """Return a filesystem-safe name component."""

        safe_value = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(value or "")
        ).strip("_")

        return safe_value[:60] or "unknown"
