CREATE TABLE IF NOT EXISTS news_ingestion_events (
    batch_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'news-intelligence-engine',
    reported_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
    database_snapshot JSONB,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    engine_completed_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT news_ingestion_events_status_check
        CHECK (status IN ('COMPLETED', 'FAILED'))
);

CREATE INDEX IF NOT EXISTS idx_news_ingestion_events_received_at
ON news_ingestion_events(received_at DESC);
