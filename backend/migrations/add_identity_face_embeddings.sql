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