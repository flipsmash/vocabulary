-- Create vocab.no_definition table for words that cannot be defined
-- These are typically proper nouns, obscure terms, or words not in dictionary APIs

CREATE TABLE IF NOT EXISTS vocab.no_definition (
    id SERIAL PRIMARY KEY,
    term VARCHAR(255) NOT NULL,
    part_of_speech VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    date_moved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure uniqueness of term+POS combinations
    UNIQUE(term, part_of_speech)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_no_definition_term ON vocab.no_definition(term);
CREATE INDEX IF NOT EXISTS idx_no_definition_pos ON vocab.no_definition(part_of_speech);
CREATE INDEX IF NOT EXISTS idx_no_definition_date ON vocab.no_definition(date_moved);

-- Add comment explaining the table's purpose
COMMENT ON TABLE vocab.no_definition IS 'Words moved from vocab.defined that have no available definition from dictionary APIs. Typically proper nouns, place names, or extremely obscure terms.';
COMMENT ON COLUMN vocab.no_definition.reason IS 'Why this word has no definition. Examples: "not_found_in_api", "no_matching_pos", "api_error"';
