-- Existing messages retain their content and receive an empty sources list.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb;
