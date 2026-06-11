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
ALTER COLUMN status SET DEFAULT 'PENDING';
