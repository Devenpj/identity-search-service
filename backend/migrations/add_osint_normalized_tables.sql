-- Normalized OSINT storage derived from osint_jobs.result.
-- Raw JSON remains in osint_jobs.result for lossless debugging/backfill.

CREATE TABLE IF NOT EXISTS osint_profiles (
    id SERIAL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
    employee_id TEXT,
    platform TEXT,
    target TEXT,
    username TEXT,
    full_name TEXT,
    profile_url TEXT,
    avatar_url TEXT,
    avatar_path TEXT,
    bio TEXT,
    status TEXT,
    confidence TEXT,
    extracted_text TEXT,
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_osint_profiles_job_id
ON osint_profiles(job_id);

CREATE INDEX IF NOT EXISTS idx_osint_profiles_employee_id
ON osint_profiles(employee_id);

CREATE INDEX IF NOT EXISTS idx_osint_profiles_platform
ON osint_profiles(platform);

CREATE TABLE IF NOT EXISTS osint_contacts (
    id SERIAL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
    employee_id TEXT,
    contact_type TEXT,
    target TEXT,
    platform TEXT,
    status TEXT,
    category TEXT,
    details TEXT,
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_osint_contacts_job_id
ON osint_contacts(job_id);

CREATE INDEX IF NOT EXISTS idx_osint_contacts_target
ON osint_contacts(target);

CREATE TABLE IF NOT EXISTS osint_matches (
    id SERIAL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
    employee_id TEXT,
    platform TEXT,
    url TEXT,
    bio TEXT,
    avatar_url TEXT,
    avatar_path TEXT,
    confidence TEXT,
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_osint_matches_job_id
ON osint_matches(job_id);

CREATE TABLE IF NOT EXISTS osint_identity_links (
    id SERIAL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES osint_jobs(job_id) ON DELETE CASCADE,
    employee_id TEXT,
    link_reason TEXT,
    match_score NUMERIC,
    face_match_status TEXT,
    face_score NUMERIC,
    decision TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_osint_identity_links_job_id
ON osint_identity_links(job_id);

CREATE INDEX IF NOT EXISTS idx_osint_identity_links_employee_id
ON osint_identity_links(employee_id);
