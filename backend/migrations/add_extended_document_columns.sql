ALTER TABLE demodataset
ADD COLUMN IF NOT EXISTS voter_id_number TEXT,
ADD COLUMN IF NOT EXISTS driving_license_number TEXT,
ADD COLUMN IF NOT EXISTS passport_number TEXT;
