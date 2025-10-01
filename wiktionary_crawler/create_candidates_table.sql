-- ============================================================================
-- Vocabulary Candidates Table for Wiktionary Rare Word Crawler
-- ============================================================================
-- Author: Claude Code
-- Date: 2025-10-01
-- Purpose: Store rare word candidates extracted from Wiktionary for manual review

SET search_path TO vocab;

-- Create vocabulary_candidates table
CREATE TABLE IF NOT EXISTS vocabulary_candidates (
    id SERIAL PRIMARY KEY,
    term TEXT NOT NULL UNIQUE,
    final_rarity FLOAT,
    zipf_score FLOAT,
    definition TEXT NOT NULL,
    part_of_speech TEXT,
    etymology TEXT,
    obsolete_or_archaic BOOLEAN DEFAULT FALSE,
    source_dump_date TEXT,
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_candidates_term ON vocabulary_candidates(term);
CREATE INDEX IF NOT EXISTS idx_candidates_rarity ON vocabulary_candidates(final_rarity DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_candidates_pos ON vocabulary_candidates(part_of_speech);
CREATE INDEX IF NOT EXISTS idx_candidates_obsolete ON vocabulary_candidates(obsolete_or_archaic);
CREATE INDEX IF NOT EXISTS idx_candidates_date ON vocabulary_candidates(date_added);

-- Add comments
COMMENT ON TABLE vocabulary_candidates IS
  'Rare word candidates extracted from Wiktionary for vocabulary enhancement.
   Words are filtered by final_rarity threshold and excluded if already in defined table.';

COMMENT ON COLUMN vocabulary_candidates.term IS 'Word lemma from Wiktionary';
COMMENT ON COLUMN vocabulary_candidates.final_rarity IS 'Rarity score from word_rarity_metrics view (0=common, 1=rare)';
COMMENT ON COLUMN vocabulary_candidates.zipf_score IS 'Zipf frequency score if available from source data';
COMMENT ON COLUMN vocabulary_candidates.definition IS 'Primary definition(s) from Wiktionary';
COMMENT ON COLUMN vocabulary_candidates.part_of_speech IS 'Part of speech (noun, verb, adjective, etc.)';
COMMENT ON COLUMN vocabulary_candidates.etymology IS 'Word origin/etymology (immediate language/root)';
COMMENT ON COLUMN vocabulary_candidates.obsolete_or_archaic IS 'Flag for archaic or obsolete words';
COMMENT ON COLUMN vocabulary_candidates.source_dump_date IS 'Wiktionary dump date (YYYYMMDD format)';
COMMENT ON COLUMN vocabulary_candidates.date_added IS 'Timestamp when candidate was added';

-- Display creation success
SELECT
    'vocabulary_candidates table created successfully!' as status,
    COUNT(*) as existing_records
FROM vocabulary_candidates;
