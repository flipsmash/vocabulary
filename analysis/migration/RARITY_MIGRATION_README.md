# Final Rarity Calculation Migration

## Overview
Migrated `final_rarity` calculation from Python pandas script to PostgreSQL materialized view for better performance, maintainability, and real-time accuracy.

## Migration Date
2025-10-01

## What Changed

### Before (Python Script)
- Manual execution of `analysis/update_final_rarity.py` required
- Pandas-based calculation with in-memory processing
- Batch updates to database
- Required periodic re-runs to keep data fresh
- Single-threaded Python execution

### After (PostgreSQL Materialized View)
- Native PostgreSQL calculation using window functions
- Automatic refresh via database trigger
- Real-time updates when frequency data changes
- Leverages PostgreSQL's query optimizer
- Backwards compatible (updates `defined.final_rarity` column)

## Architecture

### Materialized View: `word_rarity_metrics`
Located in: `vocab` schema

**Columns:**
- `id` - Word ID (unique index)
- `term` - Word term
- `python_wordfreq_rarity` - Percentile rank from python_wordfreq (0-1)
- `ngram_freq_rarity` - Percentile rank from Google N-grams (0-1)
- `commoncrawl_freq_rarity` - Percentile rank from Common Crawl (0-1)
- `final_rarity` - Weighted blend of all available sources (0-1)
- `calculated_at` - Timestamp of last calculation
- `num_sources` - Count of contributing frequency sources (1-3)

**Weighting Formula:**
```
final_rarity = (
    python_wordfreq_rarity * 0.45 +
    ngram_freq_rarity * 0.35 +
    commoncrawl_freq_rarity * 0.20
) / (sum of available weights)
```

Automatically re-normalizes weights when sources are missing.

### Automatic Refresh Mechanism

**Trigger:** `trg_refresh_rarity_on_freq_update`
- Fires after INSERT or UPDATE on `defined.python_wordfreq`, `defined.ngram_freq`, or `defined.commoncrawl_freq`
- Statement-level trigger (once per transaction, not per row)
- Calls `refresh_word_rarity_metrics()` function

**Refresh Function:** `refresh_word_rarity_metrics()`
```sql
SELECT refresh_word_rarity_metrics();
```

Uses `REFRESH MATERIALIZED VIEW CONCURRENTLY` for non-blocking updates.

### Backwards Compatibility

The migration maintains full backwards compatibility:
- `defined.final_rarity` column still exists and is kept up-to-date
- All existing queries continue to work without modification
- Web application requires no code changes

## Performance Benefits

1. **Native SQL Performance**: PostgreSQL window functions are highly optimized
2. **Incremental Updates**: Only recalculates when data changes (via trigger)
3. **Concurrent Refresh**: Uses `CONCURRENTLY` option to avoid blocking queries
4. **Query Optimization**: Materialized view can be indexed and optimized
5. **Parallel Execution**: PostgreSQL can parallelize window function calculations

## Usage

### Manual Refresh
```sql
-- Refresh the materialized view and update defined table
SELECT refresh_word_rarity_metrics();
```

### Query Examples

**Get rarest words:**
```sql
SELECT term, final_rarity, num_sources
FROM word_rarity_metrics
WHERE final_rarity IS NOT NULL
ORDER BY final_rarity DESC
LIMIT 20;
```

**Get most common words:**
```sql
SELECT term, final_rarity, num_sources
FROM word_rarity_metrics
WHERE final_rarity IS NOT NULL
ORDER BY final_rarity ASC
LIMIT 20;
```

**Quality check (words with all 3 sources):**
```sql
SELECT COUNT(*) as words_with_all_sources
FROM word_rarity_metrics
WHERE num_sources = 3;
```

**Detailed breakdown for specific word:**
```sql
SELECT
    term,
    python_wordfreq_rarity,
    ngram_freq_rarity,
    commoncrawl_freq_rarity,
    final_rarity,
    num_sources
FROM word_rarity_metrics
WHERE term = 'example';
```

## Migration Files

- **SQL Script**: `analysis/migration/create_rarity_materialized_view.sql`
- **Legacy Python Script**: `archived/python_scripts/update_final_rarity_LEGACY.py`
- **This Documentation**: `analysis/migration/RARITY_MIGRATION_README.md`

## Validation Results

**Coverage Stats** (as of migration):
- Total words: 23,153
- Words with rarity scores: 22,997 (99.3%)
- Words with all 3 frequency sources: 3,952 (17.1%)

**Sample Rarest Words:**
- aibohphobia (1.0)
- karimption (1.0)
- avetrol (1.0)
- paedonymic (1.0)
- imsonic (1.0)

**Sample Most Common Words:**
- york (0.0067)
- em (0.0073)
- se (0.0075)
- pace (0.0077)
- lasting (0.0085)

## Rollback Procedure

If needed, the migration can be rolled back:

```sql
-- Drop the materialized view and trigger
DROP TRIGGER IF EXISTS trg_refresh_rarity_on_freq_update ON defined;
DROP FUNCTION IF EXISTS trigger_refresh_rarity_metrics();
DROP FUNCTION IF EXISTS refresh_word_rarity_metrics();
DROP MATERIALIZED VIEW IF EXISTS word_rarity_metrics CASCADE;

-- Restore from backup (if needed)
UPDATE defined d
SET final_rarity = frb.final_rarity
FROM final_rarity_backup frb
WHERE d.id = frb.id;
```

Then re-run the legacy Python script:
```bash
cd archived/python_scripts
python update_final_rarity_LEGACY.py
```

## Future Enhancements

- [ ] Schedule periodic full refresh (nightly) using pg_cron
- [ ] Add monitoring/alerting for failed refreshes
- [ ] Create additional indexes for common query patterns
- [ ] Add composite view joining `defined` with `word_rarity_metrics` for detailed queries
- [ ] Consider partitioning for very large datasets

## Notes

- The materialized view uses `PERCENT_RANK()` window function for percentile calculations
- Higher frequency = more common = lower rarity (inverted: `1.0 - PERCENT_RANK()`)
- Missing frequency values (-999) are treated as NULL and excluded from calculations
- The backup table `final_rarity_backup` contains pre-migration values for validation

## Contact

For questions about this migration, refer to:
- Migration script: `analysis/migration/create_rarity_materialized_view.sql`
- Database schema: `vocab` schema in PostgreSQL database
- Web application: `web_apps/vocabulary_web_app.py` (uses `defined.final_rarity`)
