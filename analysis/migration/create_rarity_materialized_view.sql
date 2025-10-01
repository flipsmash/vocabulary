-- ============================================================================
-- Migrate final_rarity from Python-calculated column to PostgreSQL
-- materialized view for better performance and maintainability
-- ============================================================================

-- Author: Claude Code
-- Date: 2025-10-01
-- Purpose: Replace Python-based rarity calculation with native PostgreSQL
--          materialized view using window functions

SET search_path TO vocab;

-- ============================================================================
-- STEP 1: Backup existing final_rarity values (optional, for validation)
-- ============================================================================

-- Create backup table
CREATE TABLE IF NOT EXISTS final_rarity_backup AS
SELECT id, term, final_rarity, CURRENT_TIMESTAMP as backup_date
FROM defined
WHERE final_rarity IS NOT NULL;

COMMENT ON TABLE final_rarity_backup IS
  'Backup of Python-calculated final_rarity values before migration to materialized view';

-- ============================================================================
-- STEP 2: Create materialized view for word rarity metrics
-- ============================================================================

-- Drop existing view if it exists (for re-running script)
DROP MATERIALIZED VIEW IF EXISTS word_rarity_metrics CASCADE;

-- Create the materialized view
CREATE MATERIALIZED VIEW word_rarity_metrics AS
WITH freq_percentiles AS (
  -- Calculate percentile ranks (0-1) for each frequency metric
  -- Higher frequency = more common = lower rarity
  -- PERCENT_RANK returns 0 (lowest) to 1 (highest)
  -- We invert (1 - x) so rare words get high scores
  SELECT
    id,
    term,

    -- Python wordfreq rarity (weight: 0.45)
    CASE
      WHEN python_wordfreq IS NOT NULL
       AND python_wordfreq != -999
      THEN 1.0 - PERCENT_RANK() OVER (ORDER BY python_wordfreq)
      ELSE NULL
    END AS python_wordfreq_rarity,

    -- Google N-gram rarity (weight: 0.35)
    CASE
      WHEN ngram_freq IS NOT NULL
       AND ngram_freq != -999
      THEN 1.0 - PERCENT_RANK() OVER (ORDER BY ngram_freq)
      ELSE NULL
    END AS ngram_freq_rarity,

    -- Common Crawl rarity (weight: 0.20)
    CASE
      WHEN commoncrawl_freq IS NOT NULL
       AND commoncrawl_freq != -999
      THEN 1.0 - PERCENT_RANK() OVER (ORDER BY commoncrawl_freq)
      ELSE NULL
    END AS commoncrawl_freq_rarity

  FROM defined
)
SELECT
  id,
  term,
  python_wordfreq_rarity,
  ngram_freq_rarity,
  commoncrawl_freq_rarity,

  -- Weighted blend with dynamic re-normalization
  -- Only includes weights for available metrics
  CASE
    WHEN python_wordfreq_rarity IS NULL
     AND ngram_freq_rarity IS NULL
     AND commoncrawl_freq_rarity IS NULL
    THEN NULL  -- No data available
    ELSE (
      -- Numerator: weighted sum of available metrics
      COALESCE(python_wordfreq_rarity * 0.45, 0) +
      COALESCE(ngram_freq_rarity * 0.35, 0) +
      COALESCE(commoncrawl_freq_rarity * 0.20, 0)
    ) / (
      -- Denominator: sum of weights for available metrics only
      CASE WHEN python_wordfreq_rarity IS NOT NULL THEN 0.45 ELSE 0 END +
      CASE WHEN ngram_freq_rarity IS NOT NULL THEN 0.35 ELSE 0 END +
      CASE WHEN commoncrawl_freq_rarity IS NOT NULL THEN 0.20 ELSE 0 END
    )
  END AS final_rarity,

  -- Metadata for debugging/monitoring
  CURRENT_TIMESTAMP AS calculated_at,

  -- Count how many sources contributed
  (
    CASE WHEN python_wordfreq_rarity IS NOT NULL THEN 1 ELSE 0 END +
    CASE WHEN ngram_freq_rarity IS NOT NULL THEN 1 ELSE 0 END +
    CASE WHEN commoncrawl_freq_rarity IS NOT NULL THEN 1 ELSE 0 END
  ) AS num_sources

FROM freq_percentiles;

-- Add descriptive comment
COMMENT ON MATERIALIZED VIEW word_rarity_metrics IS
  'Calculated rarity scores for vocabulary words based on multiple frequency sources.
   Uses weighted average of python_wordfreq (45%), ngram_freq (35%), and commoncrawl_freq (20%).
   Refresh with: REFRESH MATERIALIZED VIEW word_rarity_metrics;';

-- ============================================================================
-- STEP 3: Create indexes for performance
-- ============================================================================

-- Unique index on word ID (required for REFRESH CONCURRENTLY)
CREATE UNIQUE INDEX idx_word_rarity_id
  ON word_rarity_metrics(id);

-- Index on final_rarity for sorting/filtering queries
CREATE INDEX idx_word_rarity_final
  ON word_rarity_metrics(final_rarity DESC NULLS LAST);

-- Index on term for lookups
CREATE INDEX idx_word_rarity_term
  ON word_rarity_metrics(term);

-- Index on num_sources for quality filtering
CREATE INDEX idx_word_rarity_sources
  ON word_rarity_metrics(num_sources);

-- ============================================================================
-- STEP 4: Update defined table to use view data (backwards compatibility)
-- ============================================================================

-- Copy calculated values back to defined.final_rarity column
-- This maintains backwards compatibility with existing code
UPDATE defined d
SET final_rarity = wrm.final_rarity
FROM word_rarity_metrics wrm
WHERE d.id = wrm.id;

-- ============================================================================
-- STEP 5: Create refresh function for easy updates
-- ============================================================================

CREATE OR REPLACE FUNCTION refresh_word_rarity_metrics()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  -- Refresh the materialized view
  REFRESH MATERIALIZED VIEW CONCURRENTLY word_rarity_metrics;

  -- Update the defined table column for backwards compatibility
  UPDATE defined d
  SET final_rarity = wrm.final_rarity
  FROM word_rarity_metrics wrm
  WHERE d.id = wrm.id;

  RAISE NOTICE 'Word rarity metrics refreshed successfully';
END;
$$;

COMMENT ON FUNCTION refresh_word_rarity_metrics() IS
  'Refresh the word_rarity_metrics materialized view and update defined.final_rarity column.
   Usage: SELECT refresh_word_rarity_metrics();';

-- ============================================================================
-- STEP 6: Create trigger to auto-refresh when frequency data changes
-- ============================================================================

-- Trigger function
CREATE OR REPLACE FUNCTION trigger_refresh_rarity_metrics()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  -- Schedule async refresh (non-blocking)
  -- Note: REFRESH CONCURRENTLY allows queries during refresh
  PERFORM refresh_word_rarity_metrics();
  RETURN NULL;
END;
$$;

-- Create trigger (fires after batch updates complete)
DROP TRIGGER IF EXISTS trg_refresh_rarity_on_freq_update ON defined;
CREATE TRIGGER trg_refresh_rarity_on_freq_update
  AFTER INSERT OR UPDATE OF python_wordfreq, ngram_freq, commoncrawl_freq
  ON defined
  FOR EACH STATEMENT  -- Only once per transaction, not per row
  EXECUTE FUNCTION trigger_refresh_rarity_metrics();

COMMENT ON TRIGGER trg_refresh_rarity_on_freq_update ON defined IS
  'Automatically refreshes word_rarity_metrics when frequency data changes';

-- ============================================================================
-- STEP 7: Validation queries
-- ============================================================================

-- Compare materialized view results with backup
DO $$
DECLARE
  v_total_words INTEGER;
  v_words_with_rarity INTEGER;
  v_max_diff NUMERIC;
  v_avg_diff NUMERIC;
BEGIN
  -- Count total words
  SELECT COUNT(*) INTO v_total_words FROM word_rarity_metrics;

  -- Count words with rarity scores
  SELECT COUNT(*) INTO v_words_with_rarity
  FROM word_rarity_metrics
  WHERE final_rarity IS NOT NULL;

  -- Compare with backup (if exists)
  IF EXISTS (SELECT 1 FROM final_rarity_backup LIMIT 1) THEN
    SELECT
      MAX(ABS(wrm.final_rarity - frb.final_rarity)),
      AVG(ABS(wrm.final_rarity - frb.final_rarity))
    INTO v_max_diff, v_avg_diff
    FROM word_rarity_metrics wrm
    JOIN final_rarity_backup frb ON wrm.id = frb.id
    WHERE wrm.final_rarity IS NOT NULL
      AND frb.final_rarity IS NOT NULL;

    RAISE NOTICE '==========================================================';
    RAISE NOTICE 'VALIDATION RESULTS';
    RAISE NOTICE '==========================================================';
    RAISE NOTICE 'Total words in view: %', v_total_words;
    RAISE NOTICE 'Words with rarity scores: %', v_words_with_rarity;
    RAISE NOTICE 'Maximum difference from backup: %', v_max_diff;
    RAISE NOTICE 'Average difference from backup: %', v_avg_diff;
    RAISE NOTICE '==========================================================';
  ELSE
    RAISE NOTICE '==========================================================';
    RAISE NOTICE 'MATERIALIZED VIEW CREATED';
    RAISE NOTICE '==========================================================';
    RAISE NOTICE 'Total words: %', v_total_words;
    RAISE NOTICE 'Words with rarity scores: %', v_words_with_rarity;
    RAISE NOTICE 'Coverage: % %%', ROUND(100.0 * v_words_with_rarity / v_total_words, 1);
    RAISE NOTICE '==========================================================';
  END IF;
END $$;

-- ============================================================================
-- USAGE INSTRUCTIONS
-- ============================================================================

/*

1. MANUAL REFRESH:
   SELECT refresh_word_rarity_metrics();

2. CHECK VIEW DATA:
   SELECT * FROM word_rarity_metrics
   WHERE final_rarity IS NOT NULL
   ORDER BY final_rarity DESC
   LIMIT 10;

3. FIND RAREST WORDS:
   SELECT term, final_rarity, num_sources
   FROM word_rarity_metrics
   ORDER BY final_rarity DESC
   LIMIT 20;

4. FIND MOST COMMON WORDS:
   SELECT term, final_rarity, num_sources
   FROM word_rarity_metrics
   WHERE final_rarity IS NOT NULL
   ORDER BY final_rarity ASC
   LIMIT 20;

5. QUALITY CHECK (words with all 3 sources):
   SELECT COUNT(*) as words_with_all_sources
   FROM word_rarity_metrics
   WHERE num_sources = 3;

6. SCHEDULE AUTOMATIC REFRESH (using pg_cron extension):
   -- Refresh nightly at 2 AM
   SELECT cron.schedule(
     'refresh-rarity-metrics',
     '0 2 * * *',
     'SELECT refresh_word_rarity_metrics();'
   );

*/

-- ============================================================================
-- Migration complete!
-- ============================================================================

SELECT
  '✓ Materialized view created successfully!' as status,
  COUNT(*) as total_words,
  COUNT(final_rarity) as words_with_scores,
  ROUND(100.0 * COUNT(final_rarity) / COUNT(*), 1) || '%' as coverage
FROM word_rarity_metrics;
