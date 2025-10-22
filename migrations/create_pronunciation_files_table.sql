-- Create pronunciation_files table to track downloaded/generated pronunciation files
-- Run this migration once to set up the table

CREATE TABLE IF NOT EXISTS pronunciation_files (
    id SERIAL PRIMARY KEY,
    word_id INTEGER NOT NULL UNIQUE REFERENCES defined(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    filename TEXT NOT NULL,
    source TEXT NOT NULL,  -- 'merriam-webster', 'wordnik', 'free-dictionary', 'wiktionary', 'forvo', 'local-tts'
    accent TEXT,  -- 'us', 'uk', or NULL for local-tts
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_pronunciation_files_word_id ON pronunciation_files(word_id);
CREATE INDEX IF NOT EXISTS idx_pronunciation_files_source ON pronunciation_files(source);

-- Add trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_pronunciation_files_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER pronunciation_files_updated_at_trigger
    BEFORE UPDATE ON pronunciation_files
    FOR EACH ROW
    EXECUTE FUNCTION update_pronunciation_files_updated_at();

-- Add comment
COMMENT ON TABLE pronunciation_files IS 'Tracks pronunciation audio files for vocabulary words';
COMMENT ON COLUMN pronunciation_files.source IS 'Source: merriam-webster, wordnik, free-dictionary, wiktionary, forvo, or local-tts';
COMMENT ON COLUMN pronunciation_files.accent IS 'Accent type: us (preferred), uk (fallback), or NULL for synthesized';
