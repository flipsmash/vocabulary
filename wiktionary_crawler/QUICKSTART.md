# Quick Start Guide - Wiktionary Rare Word Crawler

## 30-Second Setup

```bash
# 1. Create the database table
psql "postgresql://postgres.your-tenant-id:your-super-secret-and-long-postgres-password@10.0.0.99:6543/postgres" < wiktionary_crawler/create_candidates_table.sql

# 2. Test components (optional but recommended)
uv run python3 wiktionary_crawler/test_components.py

# 3. Run the crawler (1-3 hours)
uv run python3 wiktionary_crawler/wiktionary_rare_word_crawler.py

# 4. Review results
psql "postgresql://postgres.your-tenant-id:your-super-secret-and-long-postgres-password@10.0.0.99:6543/postgres" -c "SET search_path TO vocab; SELECT term, final_rarity, definition FROM vocabulary_candidates ORDER BY final_rarity DESC LIMIT 20;"
```

## What It Does

1. **Downloads** Wiktionary XML dump (~500MB, one-time)
2. **Filters** for rare English words not in your database
3. **Extracts** definitions, etymologies, parts of speech
4. **Stores** candidates in `vocabulary_candidates` table

## Configuration Options

```bash
# Higher threshold = rarer words only
uv run python3 wiktionary_crawler/wiktionary_rare_word_crawler.py --threshold 0.7

# Larger stoplist = fewer common words included
uv run python3 wiktionary_crawler/wiktionary_rare_word_crawler.py --stoplist-size 30000

# Reset and start fresh
uv run python3 wiktionary_crawler/wiktionary_rare_word_crawler.py --reset
```

## Expected Results

With default threshold **0.6**:
- **Processing time**: 1-3 hours
- **Expected candidates**: 4,000-8,000 rare words
- **Quality**: Genuinely rare but still useful vocabulary

Sample candidates at threshold 0.6+:
- baragouin (0.60) - jargon, unintelligible speech
- symmachy (0.60) - fighting on the same side
- lapstrake (0.60) - overlapping planks on a boat
- exocentric (0.60) - having external reference

## Interruption & Resume

The crawler auto-saves progress every 10,000 pages. If interrupted:

```bash
# Just rerun the same command - it will resume automatically
uv run python3 wiktionary_crawler/wiktionary_rare_word_crawler.py
```

## Quick Queries

```sql
-- Top 50 rarest words
SELECT term, final_rarity, part_of_speech, LEFT(definition, 80)
FROM vocabulary_candidates
ORDER BY final_rarity DESC
LIMIT 50;

-- Count by part of speech
SELECT part_of_speech, COUNT(*)
FROM vocabulary_candidates
GROUP BY part_of_speech
ORDER BY COUNT(*) DESC;

-- Archaic words only
SELECT term, final_rarity, definition
FROM vocabulary_candidates
WHERE obsolete_or_archaic = TRUE
ORDER BY final_rarity DESC
LIMIT 20;
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No candidates found | Lower `--threshold` to 0.5 or 0.4 |
| Out of memory | Reduce `--batch-size` to 100 |
| Too many candidates | Increase `--threshold` to 0.7+ |
| Want to restart | Use `--reset` flag |

## Full Documentation

See `README.md` for comprehensive documentation.

---

**Ready? Run the crawler and discover rare vocabulary! 🚀**
