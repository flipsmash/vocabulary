# Wiktionary Rare Word Crawler

Automated system to extract rare, useful English vocabulary from Wiktionary for manual review and potential inclusion in your vocabulary database.

## Overview

This crawler downloads the complete English Wiktionary XML dump, processes it offline, and identifies rare words that:
- Are NOT in your existing `defined` table (production vocabulary)
- Are NOT in your `vocabulary_candidates` table (pending review)
- Are NOT in the stoplist of ~20,000 most common English words
- Have a `final_rarity` score above your configured threshold (default: 0.6)
- Match specific parts of speech (nouns, verbs, adjectives, adverbs, interjections, prepositions)
- Are NOT proper nouns

## Features

✅ **Offline Processing** - Downloads Wiktionary dump once, processes locally (no API calls)
✅ **Respectful** - Zero load on Wiktionary servers after initial download
✅ **Resumable** - Automatic checkpointing every 10,000 pages
✅ **Idempotent** - Safe to rerun, handles duplicates gracefully
✅ **Batch Processing** - Efficient database operations with configurable batch sizes
✅ **Comprehensive Filtering** - Multiple stages to ensure quality candidates
✅ **Integrated** - Uses your existing `word_rarity_metrics` materialized view
✅ **Archaic Word Detection** - Flags obsolete/archaic words but includes them

## Quick Start

### 1. Setup

```bash
# Create required directories (auto-created on first run)
mkdir -p wiktionary_crawler/dumps

# Install dependencies (if not already in project)
pip install requests psycopg psycopg-pool

# OR use uv
uv pip install requests psycopg psycopg-pool
```

### 2. Create Database Table

```bash
# Run the SQL schema creation script
psql "postgresql://postgres.your-tenant-id:your-super-secret-and-long-postgres-password@10.0.0.99:6543/postgres" < wiktionary_crawler/create_candidates_table.sql
```

### 3. Run the Crawler

```bash
# Basic run with defaults (rarity threshold 0.6, stoplist 20k words)
python wiktionary_crawler/wiktionary_rare_word_crawler.py

# Custom threshold (0.7 = even rarer words only)
python wiktionary_crawler/wiktionary_rare_word_crawler.py --threshold 0.7

# Custom stoplist size
python wiktionary_crawler/wiktionary_rare_word_crawler.py --stoplist-size 30000

# Reset checkpoint and start fresh
python wiktionary_crawler/wiktionary_rare_word_crawler.py --reset

# Combine options
python wiktionary_crawler/wiktionary_rare_word_crawler.py --threshold 0.65 --stoplist-size 25000 --batch-size 1000
```

## Configuration

### Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--threshold` | 0.6 | Final rarity threshold (0-1 scale, higher=rarer) |
| `--stoplist-size` | 20000 | Number of common words to exclude |
| `--batch-size` | 500 | Database batch size for inserts |
| `--reset` | False | Clear checkpoint and start from beginning |

### Rarity Threshold Guide

Based on analysis of your existing database:

| Threshold | Description | Example Words |
|-----------|-------------|---------------|
| 0.0 - 0.3 | Very common | york, pace, wood, capitalism |
| 0.3 - 0.6 | Medium | jack-cross-tree, bright-eyed, law-abiding |
| **0.6 - 0.8** | **Rare** (recommended) | baragouin, symmachy, lapstrake, exocentric |
| 0.8 - 1.0 | Extremely rare | aibohphobia, karimption, scaldabanco |

**Default 0.6** captures genuinely rare but still useful vocabulary words.

### Parts of Speech Included

- Nouns (excluding proper nouns)
- Verbs
- Adjectives
- Adverbs
- Interjections
- Prepositions

### Filtering Criteria

**Included:**
- English lemmas only
- Single words (hyphens and apostrophes OK)
- Words with rarity scores above threshold
- Archaic/obsolete words (flagged in database)

**Excluded:**
- Proper nouns
- Multi-word phrases (with spaces)
- Words in stoplist (20k most common)
- Words already in `defined` table
- Words already in `vocabulary_candidates` table
- Words without rarity scores in `word_rarity_metrics` view

## Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Download Wiktionary XML Dump (~500MB compressed)            │
│    - Only downloads once                                        │
│    - Cached in wiktionary_crawler/dumps/                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Download/Load Stoplist (20k common words)                   │
│    - Google 10k + MIT 10k word lists                           │
│    - Cached in wiktionary_crawler/stoplist.txt                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Load Existing Terms                                          │
│    - Query defined table (production words)                     │
│    - Query vocabulary_candidates (pending review)               │
│    - Total: ~23k+ existing terms                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. Parse Wiktionary Dump (1-3 hours)                           │
│    - Extract English lemmas                                     │
│    - Parse wiki markup                                          │
│    - Extract definitions, etymology, POS                        │
│    - Checkpoint every 10k pages                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Filter Candidates                                            │
│    - Skip stoplist words                                        │
│    - Skip existing terms (defined + candidates)                 │
│    - Batch query rarity scores (500 at a time)                  │
│    - Apply rarity threshold                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. Insert to vocabulary_candidates                              │
│    - Batch inserts (500 records)                                │
│    - ON CONFLICT DO NOTHING (idempotent)                        │
│    - Track statistics                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

### Table: `vocabulary_candidates`

```sql
CREATE TABLE vocabulary_candidates (
    id SERIAL PRIMARY KEY,
    term TEXT NOT NULL UNIQUE,                 -- Word lemma
    final_rarity FLOAT,                        -- From word_rarity_metrics view
    zipf_score FLOAT,                          -- Reserved for future use
    definition TEXT NOT NULL,                  -- Primary definition(s)
    part_of_speech TEXT,                       -- noun, verb, adjective, etc.
    etymology TEXT,                            -- Word origin (immediate)
    obsolete_or_archaic BOOLEAN DEFAULT FALSE, -- Archaic/obsolete flag
    source_dump_date TEXT,                     -- Wiktionary dump version
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
- `term` (unique)
- `final_rarity` (DESC for sorting rare → common)
- `part_of_speech`
- `obsolete_or_archaic`
- `date_added`

## Querying Results

### View Top Rare Candidates

```sql
-- Top 20 rarest words
SELECT term, final_rarity, part_of_speech, definition
FROM vocabulary_candidates
ORDER BY final_rarity DESC
LIMIT 20;

-- Rare nouns only
SELECT term, final_rarity, definition
FROM vocabulary_candidates
WHERE part_of_speech = 'noun'
  AND obsolete_or_archaic = FALSE
ORDER BY final_rarity DESC
LIMIT 50;

-- Recently added candidates
SELECT term, final_rarity, part_of_speech, date_added
FROM vocabulary_candidates
ORDER BY date_added DESC
LIMIT 30;

-- Archaic words
SELECT term, final_rarity, definition
FROM vocabulary_candidates
WHERE obsolete_or_archaic = TRUE
ORDER BY final_rarity DESC
LIMIT 20;
```

### Statistics

```sql
-- Total candidates by POS
SELECT part_of_speech, COUNT(*) as count
FROM vocabulary_candidates
GROUP BY part_of_speech
ORDER BY count DESC;

-- Rarity distribution
SELECT
    CASE
        WHEN final_rarity >= 0.9 THEN '0.9-1.0 (Extremely rare)'
        WHEN final_rarity >= 0.8 THEN '0.8-0.9 (Very rare)'
        WHEN final_rarity >= 0.7 THEN '0.7-0.8 (Rare)'
        WHEN final_rarity >= 0.6 THEN '0.6-0.7 (Medium-rare)'
        ELSE '0.0-0.6 (Common)'
    END as rarity_bracket,
    COUNT(*) as count
FROM vocabulary_candidates
GROUP BY rarity_bracket
ORDER BY rarity_bracket DESC;

-- Archaic vs modern
SELECT
    obsolete_or_archaic,
    COUNT(*) as count,
    ROUND(AVG(final_rarity), 3) as avg_rarity
FROM vocabulary_candidates
GROUP BY obsolete_or_archaic;
```

## Performance & Resource Usage

### Expected Runtime

| Stage | Duration | Notes |
|-------|----------|-------|
| **Download Dump** | 10-30 min | One-time download (~500MB) |
| **Download Stoplist** | 5 seconds | One-time download (~200KB) |
| **Load Existing** | 5-10 seconds | Queries both tables |
| **Parse Dump** | 1-3 hours | Main processing time |
| **Total First Run** | 1.5-3.5 hours | Depends on CPU speed |
| **Subsequent Runs** | 1-3 hours | No download needed |

### Resource Requirements

- **Disk Space**: 2-3 GB (500MB compressed dump + extracted XML)
- **RAM**: 2-4 GB recommended for XML parsing
- **CPU**: Single-threaded (one core utilized)
- **Network**: ~500MB download (one-time)

### Checkpointing

Progress is automatically saved every 10,000 pages:
- File: `wiktionary_crawler/checkpoint.json`
- Tracks: pages processed, candidates added
- Interrupt safely: Ctrl+C or system crash
- Resume: Simply rerun the same command

## Files Created

```
wiktionary_crawler/
├── wiktionary_rare_word_crawler.py    # Main crawler script
├── create_candidates_table.sql         # Database schema
├── requirements.txt                    # Python dependencies
├── README.md                           # This file
├── dumps/                              # Wiktionary XML dumps
│   └── enwiktionary-YYYYMMDD-pages-articles.xml.bz2
├── stoplist.txt                        # Common words list (auto-generated)
└── checkpoint.json                     # Progress tracking (auto-generated)
```

## Example Output

```
================================================================================
WIKTIONARY RARE WORD CRAWLER
================================================================================
Final rarity threshold: 0.6
Stoplist size: 20,000
Allowed POS: adjective, adverb, interjection, noun, preposition, verb

Loading stoplist from wiktionary_crawler/stoplist.txt
Loaded 20,000 stoplist words

Wiktionary dump already exists: wiktionary_crawler/dumps/enwiktionary-20251001-pages-articles.xml.bz2 (523.4 MB)

Loading existing terms from database...
Loaded 23,153 terms from defined table
Loaded 0 terms from vocabulary_candidates table
Total existing terms: 23,153

Starting Wiktionary dump parsing...
This will take 1-3 hours depending on your system...

Processed 50,000 entries | Added 234 candidates | Filtered: stoplist=12,453, exists=1,234, no_rarity=23,456, common=8,765
Processed 100,000 entries | Added 487 candidates | Filtered: stoplist=25,123, exists=2,456, no_rarity=45,678, common=17,234
...
Processed 1,000,000 entries | Added 4,532 candidates | Filtered: stoplist=234,567, exists=12,345, no_rarity=456,789, common=123,456

================================================================================
CRAWLING COMPLETE
================================================================================
Pages processed:       1,234,567
Entries extracted:       567,890

Filtering Results:
  In stoplist:           234,567
  Already exists:         12,345
  No rarity score:       456,789
  Too common:            123,456

Candidates added:         4,532
================================================================================

Review candidates in vocabulary_candidates table:
  SELECT * FROM vocabulary_candidates ORDER BY final_rarity DESC LIMIT 20;
```

## Troubleshooting

### "Connection refused" Error
Check your database connection in `core/secure_config.py` or environment variables.

### "Out of memory" Error
Reduce `--batch-size` to process smaller batches (e.g., `--batch-size 100`).

### Crawler Stuck/Frozen
The XML parsing is slow but steady. Check progress with:
```sql
SELECT COUNT(*) FROM vocabulary_candidates;
```

### Resume After Interruption
Simply rerun the same command - the checkpoint system will resume automatically.

### No Candidates Added
- Lower the `--threshold` (try 0.5 or 0.4)
- Check if your `word_rarity_metrics` view is populated
- Increase `--stoplist-size` to be less restrictive

### Duplicate Key Error
Should not happen due to `ON CONFLICT DO NOTHING`, but if it does:
```sql
-- Clear candidates table and restart
TRUNCATE vocabulary_candidates;
```

## Advanced Usage

### Running in Background

```bash
# Linux/Mac
nohup python wiktionary_crawler/wiktionary_rare_word_crawler.py > crawler.log 2>&1 &

# Follow progress
tail -f crawler.log
```

### Custom Configuration

Edit the `CrawlerConfig` class in the script:
- Adjust `allowed_pos` to include/exclude parts of speech
- Modify `max_definition_length` / `max_etymology_length`
- Change `log_interval` for more/less frequent updates

### Batch Review Workflow

1. Run crawler with high threshold (0.7+) for highest quality
2. Review candidates in database
3. Manually promote good words to `defined` table
4. Rerun crawler with lower threshold (0.5-0.6)
5. Repeat

## Integration with Vocabulary System

### Promoting Candidates to Production

```sql
-- Review and select candidates
SELECT id, term, definition, final_rarity
FROM vocabulary_candidates
WHERE part_of_speech = 'noun'
  AND obsolete_or_archaic = FALSE
  AND final_rarity > 0.7
ORDER BY final_rarity DESC
LIMIT 50;

-- Manually promote to defined table (adapt to your schema)
INSERT INTO defined (term, definition, part_of_speech, obsolete_or_archaic)
SELECT term, definition, part_of_speech, obsolete_or_archaic
FROM vocabulary_candidates
WHERE id = 12345;  -- Replace with actual ID

-- Remove from candidates after promotion
DELETE FROM vocabulary_candidates WHERE id = 12345;
```

## Future Enhancements

Potential improvements:
- [ ] Parallel processing (multiprocessing for XML parsing)
- [ ] Web UI for candidate review
- [ ] Automatic word quality scoring
- [ ] Integration with pronunciation system
- [ ] Export candidates to CSV/JSON
- [ ] Wiktionary API fallback for missing data
- [ ] Support for multiple languages

## Support

For issues or questions:
1. Check this README thoroughly
2. Review the SQL schema in `create_candidates_table.sql`
3. Examine logs and checkpoint file
4. Test with `--reset` flag to start fresh

## License

Part of the Vocabulary Enhancement Project.

---

**Happy word hunting! 📚✨**
