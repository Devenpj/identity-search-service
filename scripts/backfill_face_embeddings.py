"""Backfill durable InsightFace embeddings for registered identity photos."""

import argparse
import os
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.config import settings
from backend.services.database_service import DatabaseService
from backend.services.face_service import FaceVerificationService


def parse_args():
    """Return safe foreground backfill options."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--employee-id", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--progress-every", type=int, default=100)

    return parser.parse_args()


def main():
    """Generate missing/stale embeddings and print visible progress."""

    args = parse_args()
    database = DatabaseService()
    face_service = FaceVerificationService()
    started_at = time.perf_counter()
    created = 0
    skipped = 0
    failed = 0

    try:
        if not settings.FACE_ENGINE_URL:
            raise ValueError("FACE_ENGINE_URL is not configured")

        identities = database.get_identities_with_photos()
        existing_embeddings = database.get_face_embedding_index()
        employee_filter = str(args.employee_id or "").strip()

        if employee_filter:
            identities = [
                identity
                for identity in identities
                if identity.get("employee_id") == employee_filter
            ]

        offset = max(0, int(args.offset or 0))

        if offset:
            identities = identities[offset:]

        if args.limit > 0:
            identities = identities[:args.limit]

        total = len(identities)
        print(
            "Face embedding backfill started: "
            f"total={total} model={settings.FACE_EMBEDDING_MODEL}"
        )

        for index, identity in enumerate(identities, start=1):
            employee_id = identity.get("employee_id")
            photo_path = identity.get("photo_path")

            try:
                resolved_path = face_service.resolve_database_photo_path(photo_path)
                photo_hash = face_service.photo_fingerprint(resolved_path)
                existing = existing_embeddings.get(employee_id) or {}

                if (
                    not args.force
                    and existing.get("photo_hash") == photo_hash
                    and existing.get("model_name") == settings.FACE_EMBEDDING_MODEL
                    and existing.get("embedding_dimension") == 512
                ):
                    skipped += 1
                    if index % max(1, args.progress_every) == 0 or index == total:
                        print(f"[{index}/{total}] SKIP {employee_id} unchanged")
                    continue

                embedding_payload = face_service.extract_external_embedding(
                    resolved_path,
                    assume_cropped=True
                )
                database.upsert_face_embedding(
                    employee_id=employee_id,
                    photo_path=photo_path,
                    photo_hash=photo_hash,
                    model_name=(
                        embedding_payload.get("model_name")
                        or settings.FACE_EMBEDDING_MODEL
                    ),
                    embedding=embedding_payload.get("embedding"),
                    face_quality=embedding_payload.get("quality"),
                    detection_score=embedding_payload.get("det_score")
                )
                created += 1
                if index % max(1, args.progress_every) == 0 or index == total:
                    print(
                        f"[{index}/{total}] STORED {employee_id} "
                        f"det_score={embedding_payload.get('det_score')}"
                    )

            except Exception as error:
                failed += 1
                database.delete_face_embedding(employee_id)
                print(f"[{index}/{total}] FAILED {employee_id}: {error}")

        coverage = database.get_face_embedding_coverage()
        elapsed = round(time.perf_counter() - started_at, 2)
        print(
            "Face embedding backfill completed: "
            f"stored={created} skipped={skipped} failed={failed} "
            f"coverage={coverage['ready_embeddings']}/{coverage['total_photos']} "
            f"elapsed_seconds={elapsed}"
        )

        return 1 if failed else 0

    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())