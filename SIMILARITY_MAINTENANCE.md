# Vocabulary Similarity Maintenance Guide

This guide explains how to maintain up-to-date word similarity data in the vocabulary database.

## Overview

Word semantic similarities are calculated using transformer-based embedding models. The system compares word definitions to find semantically related words, which powers:
- Similar words display on word detail pages
- Semantic network visualizations
- Enhanced quiz distract generation (future)

### Embedding Models

The system supports two embedding models:

| Model | Dimensions | Quality | Speed | Use Case |
|-------|-----------|---------|-------|----------|
| **all-mpnet-base-v2** (default) | 768 | Higher | Slower | Primary model for similarity |
| **all-MiniLM-L6-v2** (legacy) | 384 | Good | Faster | Visualization fallback |

**Current Recommendation**: Use **all-mpnet-base-v2** for all new similarity calculations. The MiniLM model is retained for legacy visualization support.

## Current Status

As of the last update:
- **Total words**: ~23,148
- **all-mpnet-base-v2**: 13,218,508 similarity pairs
- **all-MiniLM-L6-v2**: 12,851,431 similarity pairs (legacy)
- **Similarity threshold**: 0.4 (pairs below this are not stored)

## How Similarities Are Calculated

1. **Embedding Generation**: Word definitions are converted to 768-dimensional vectors using the sentence-transformers model
2. **Cosine Similarity**: All pairwise cosine similarities are calculated between embeddings
3. **Threshold Filtering**: Only pairs with similarity ≥ 0.4 are stored (reduces storage from ~270M to ~13M pairs)
4. **Database Storage**: Similarities stored in `vocab.definition_similarity` table

## Maintenance Scripts

### Check Current Status

```bash
source .venv/bin/activate
python scripts/check_similarity_status.py
```

**Output**:
- Total words in database
- Embedding models available
- Coverage per model (% of words with similarities)
- Words missing similarities
- Sample words needing updates

### Full Maintenance

```bash
source .venv/bin/activate
python scripts/maintain_similarity.py
```

**What it does**:
1. Loads all word definitions
2. Generates embeddings for words missing them
3. Calculates pairwise similarities above threshold
4. Stores results in database

**Expected runtime**:
- New words only: 5-15 minutes per 100 words
- Full recalculation: Several hours for 23K words (rarely needed)

### Command Options

```bash
# Preview what would be done
python scripts/maintain_similarity.py --dry-run

# Use specific model
python scripts/maintain_similarity.py --model sentence-transformers/all-mpnet-base-v2

# Adjust similarity threshold
python scripts/maintain_similarity.py --threshold 0.35

# Only generate embeddings (skip similarity calculation)
python scripts/maintain_similarity.py --skip-similarities

# Only calculate similarities (skip embedding generation)
python scripts/maintain_similarity.py --skip-embeddings

# Silent mode for cron
python scripts/maintain_similarity.py --silent

# Adjust batch size (memory vs speed trade-off)
python scripts/maintain_similarity.py --batch-size 500

# View all options
python scripts/maintain_similarity.py --help
```

## Automated Maintenance with Cron

### Recommended Schedule

**Daily maintenance (3 AM)** - After rarity maintenance
```cron
0 3 * * * cd /mnt/c/Users/Brian/vocabulary && .venv/bin/python scripts/maintain_similarity.py --silent >> /var/log/vocabulary/similarity_maintenance.log 2>&1
```

**Why daily?**
- New words added occasionally need similarity calculations
- Embeddings must be generated before similarities can be calculated
- Daily ensures new words become discoverable quickly

### Setting Up Cron (WSL/Linux)

1. **Create log directory**:
   ```bash
   sudo mkdir -p /var/log/vocabulary
   sudo chown $USER:$USER /var/log/vocabulary
   ```

2. **Edit crontab**:
   ```bash
   crontab -e
   ```

3. **Add maintenance job**:
   ```cron
   # Vocabulary similarity maintenance - daily at 3 AM
   0 3 * * * cd /mnt/c/Users/Brian/vocabulary && .venv/bin/python scripts/maintain_similarity.py --silent >> /var/log/vocabulary/similarity_maintenance.log 2>&1
   ```

4. **Verify cron is running**:
   ```bash
   sudo service cron status
   # If not running:
   sudo service cron start
   ```

5. **Check logs**:
   ```bash
   # View maintenance log
   tail -f /var/log/vocabulary/similarity_maintenance.log

   # Check for errors
   grep ERROR /var/log/vocabulary/similarity_maintenance.log
   ```

### Log Rotation

Create `/etc/logrotate.d/vocabulary`:
```
/var/log/vocabulary/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 brian brian
}
```

## Manual Database Operations

### Check Similarity Coverage

```sql
-- Check total similarities per model
SELECT embedding_model, COUNT(*) as total_pairs
FROM vocab.definition_similarity
GROUP BY embedding_model;

-- Find words without similarities
SELECT d.id, d.term
FROM vocab.defined d
WHERE NOT EXISTS (
    SELECT 1 FROM vocab.definition_similarity ds
    WHERE ds.word1_id = d.id OR ds.word2_id = d.id
)
LIMIT 100;

-- Check similarity distribution
SELECT
    ROUND(cosine_similarity::numeric, 1) as similarity_bucket,
    COUNT(*) as count
FROM vocab.definition_similarity
WHERE embedding_model = 'sentence-transformers/all-mpnet-base-v2'
GROUP BY similarity_bucket
ORDER BY similarity_bucket DESC;
```

### Manually Query Similar Words

```sql
-- Get similar words for a specific term
SELECT d.term, ds.cosine_similarity
FROM vocab.definition_similarity ds
JOIN vocab.defined d ON (
    CASE WHEN ds.word1_id = (SELECT id FROM vocab.defined WHERE term = 'ephemeral')
         THEN ds.word2_id
         ELSE ds.word1_id END = d.id
)
WHERE (ds.word1_id = (SELECT id FROM vocab.defined WHERE term = 'ephemeral')
   OR ds.word2_id = (SELECT id FROM vocab.defined WHERE term = 'ephemeral'))
  AND ds.embedding_model = 'sentence-transformers/all-mpnet-base-v2'
ORDER BY ds.cosine_similarity DESC
LIMIT 10;
```

## Web App Integration

### Word Detail Pages

**Function**: `get_similar_words(word_id, limit=10, embedding_model=None)`
- **Default model**: sentence-transformers/all-mpnet-base-v2
- **Display**: Shows top 10 most similar words with similarity scores
- **Location**: web_apps/vocabulary_web_app.py:1075-1109

### Visualization Graph

**Endpoint**: `/api/visualizations/word-graph`
- **Default model**: sentence-transformers/all-mpnet-base-v2
- **User selectable**: Users can choose between models via API parameter
- **Min similarity**: 0.4 (configurable)
- **Location**: web_apps/vocabulary_web_app.py:789-1074

## Troubleshooting

### Issue: Script runs very slowly
**Solution**:
- Use `--batch-size 500` to reduce memory usage
- Ensure you're not recalculating all similarities (check logs)
- Consider running on a machine with GPU support (10x faster)

### Issue: Out of memory errors
**Solution**:
- Reduce `--batch-size` (default: 1000, try: 500 or 250)
- Close other applications
- Ensure adequate swap space

### Issue: Some words have no similarities
**Causes**:
1. Word definition too short/generic
2. Word definition is unique (no similar concepts)
3. Word was added after last similarity calculation

**Solution**:
```bash
# Run maintenance to catch up
python scripts/maintain_similarity.py
```

### Issue: Similarities seem wrong/inconsistent
**Check**:
1. Which model is being used? (mpnet vs MiniLM)
2. Threshold setting (0.4 vs 0.3)
3. When were similarities last calculated?

**Fix**:
```bash
# Check status
python scripts/check_similarity_status.py

# Regenerate if needed (this takes hours!)
python scripts/maintain_similarity.py --model sentence-transformers/all-mpnet-base-v2
```

### Issue: Cron job not running
```bash
# Check cron service
sudo service cron status

# View cron logs
grep CRON /var/log/syslog

# Test script manually
cd /mnt/c/Users/Brian/vocabulary
source .venv/bin/activate
python scripts/maintain_similarity.py --dry-run
```

### Issue: "sentence-transformers not installed"
```bash
# Install required package
pip install sentence-transformers

# Verify installation
python -c "from sentence_transformers import SentenceTransformer; print('OK')"
```

## Performance Notes

- **Embedding generation**: ~0.3 seconds per word (batched)
- **Similarity calculation**: ~5-10 minutes per 1000 words (depends on threshold)
- **Database storage**: ~50 bytes per similarity pair
- **Full corpus calculation**: 2-4 hours for 23K words (rarely needed)

**Daily maintenance** (incremental):
- Typical runtime: 5-30 minutes (only processes new words)
- Database writes: Minimal (only new similarities)

**Full recalculation** (rare):
- When needed: Model change, threshold change, data corruption
- Runtime: 2-4 hours for full corpus
- Should be done during low-traffic periods

## Architecture

```
┌──────────────────┐
│  defined table   │
│  (word + def)    │
└────────┬─────────┘
         │
         ├──> Sentence Transformer Model (all-mpnet-base-v2)
         │    - Converts definition to 768-dim embedding
         │    - Stored temporarily (not in database)
         │
         ├──> Pairwise Cosine Similarity
         │    - Calculate similarity for all word pairs
         │    - Filter by threshold (≥ 0.4)
         │
         └──> definition_similarity table
              - Stores: word1_id, word2_id, cosine_similarity, model
              - ~13M pairs for mpnet @ 0.4 threshold
              - Used by web app for "similar words" display
```

## Best Practices

1. **Run maintenance daily** - Keeps similarities current for new words
2. **Monitor logs** - Check for consistent failures
3. **Use dry-run before manual runs** - Preview impact of changes
4. **Stick with mpnet model** - Higher quality, better results
5. **Don't lower threshold below 0.3** - Too many weak similarities
6. **Use --silent for cron** - Reduces log noise
7. **Keep both models for now** - Legacy visualization support

## Model Comparison Example

For the word "ephemeral":

**all-mpnet-base-v2** (recommended):
- transient (0.72)
- fleeting (0.68)
- evanescent (0.65)
- momentary (0.61)

**all-MiniLM-L6-v2** (legacy):
- transient (0.70)
- fleeting (0.65)
- momentary (0.59)
- temporary (0.58)

*Note: Scores differ slightly due to different embedding spaces*

## Related Files

- `scripts/maintain_similarity.py` - Main maintenance script (**USE THIS**)
- `scripts/check_similarity_status.py` - Quick status checker
- `analysis/definition_similarity_calculator.py` - Core similarity calculation engine
- `add_mpnet_embeddings.py` - Initial mpnet model setup (one-time use)
- `web_apps/vocabulary_web_app.py` - Web app similarity integration

## Quick Reference Commands

```bash
# Check status
python scripts/check_similarity_status.py

# Full maintenance (recommended)
python scripts/maintain_similarity.py

# Preview changes
python scripts/maintain_similarity.py --dry-run

# Only new embeddings
python scripts/maintain_similarity.py --skip-similarities

# Only new similarities
python scripts/maintain_similarity.py --skip-embeddings

# Silent cron mode
python scripts/maintain_similarity.py --silent

# View help
python scripts/maintain_similarity.py --help
```

---

**Last Updated**: 2025-10-20
**Default Model**: sentence-transformers/all-mpnet-base-v2
**Default Threshold**: 0.4
**Database**: PostgreSQL (vocab schema)
