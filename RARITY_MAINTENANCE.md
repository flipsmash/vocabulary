# Vocabulary Rarity Maintenance Guide

This guide explains how to maintain up-to-date word rarity data in the vocabulary database.

## Overview

Word rarity scores (`defined.final_rarity`) are calculated from three frequency sources:
- **python_wordfreq** (45% weight) - Zipf frequency from the wordfreq library
- **ngram_freq** (35% weight) - Google Books N-gram frequency
- **commoncrawl_freq** (20% weight) - Common Crawl web corpus frequency

The system uses a PostgreSQL materialized view (`word_rarity_metrics`) that:
1. Converts frequency values to percentile ranks
2. Inverts percentiles so rare words get high scores (0 = common, 1 = rare)
3. Calculates weighted averages with dynamic re-normalization for missing data

## Current Status

As of the last check:
- **Total words**: 23,148
- **python_wordfreq**: 9,022 valid (13,970 missing)
- **ngram_freq**: 22,992 valid (156 missing) ✓
- **commoncrawl_freq**: 3,973 valid (19,019 missing)
- **final_rarity**: 23,145 populated (3 missing)

## Maintenance Script

The comprehensive maintenance script is located at:
```bash
scripts/maintain_rarity.py
```

### Features

- **Complete frequency backfill** - Updates ALL missing frequency data (not just words with NULL rarity)
- **Materialized view refresh** - Recalculates rarity percentiles
- **Final rarity update** - Copies calculated values to `defined.final_rarity`
- **Dry-run mode** - Preview changes without committing
- **Silent mode** - Minimal output for cron jobs
- **Progress tracking** - Detailed statistics and timing

### Usage

#### Interactive Mode (Full Maintenance)
```bash
# Activate virtual environment
source .venv/bin/activate

# Run full maintenance (updates frequencies + refreshes rarity)
python scripts/maintain_rarity.py
```

**Expected runtime**: 5-15 minutes depending on missing data volume

#### Preview Changes (Dry Run)
```bash
python scripts/maintain_rarity.py --dry-run
```

Shows what would be updated without making changes.

#### Quick Rarity Refresh (Skip Frequency Updates)
```bash
python scripts/maintain_rarity.py --skip-frequency
```

Only refreshes rarity calculations from existing frequency data. Much faster (~30 seconds).

#### Frequency Updates Only (Skip Rarity Refresh)
```bash
python scripts/maintain_rarity.py --skip-refresh
```

Only updates missing frequency data without refreshing final_rarity.

#### Silent Mode (For Cron)
```bash
python scripts/maintain_rarity.py --silent
```

Minimal output - only errors to stderr. Perfect for cron jobs.

### Options Summary

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview changes without committing |
| `--skip-frequency` | Skip frequency updates (only refresh rarity) |
| `--skip-refresh` | Skip view refresh (only update frequencies) |
| `--silent` | Minimal output (cron-friendly) |
| `--no-concurrently` | Refresh view with locking (default: concurrent) |

## Automated Maintenance with Cron

### Recommended Schedule

**Daily full maintenance (2 AM)**
```cron
0 2 * * * cd /mnt/c/Users/Brian/vocabulary && /mnt/c/Users/Brian/vocabulary/.venv/bin/python scripts/maintain_rarity.py --silent >> /var/log/vocab_maintenance.log 2>&1
```

**Quick rarity refresh only (every 6 hours)**
```cron
0 */6 * * * cd /mnt/c/Users/Brian/vocabulary && /mnt/c/Users/Brian/vocabulary/.venv/bin/python scripts/maintain_rarity.py --skip-frequency --silent >> /var/log/vocab_maintenance_quick.log 2>&1
```

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
   # Vocabulary rarity maintenance - daily at 2 AM
   0 2 * * * cd /mnt/c/Users/Brian/vocabulary && .venv/bin/python scripts/maintain_rarity.py --silent >> /var/log/vocabulary/maintenance.log 2>&1

   # Quick rarity refresh - every 6 hours
   0 */6 * * * cd /mnt/c/Users/Brian/vocabulary && .venv/bin/python scripts/maintain_rarity.py --skip-frequency --silent >> /var/log/vocabulary/quick_refresh.log 2>&1
   ```

4. **Verify cron is running**:
   ```bash
   sudo service cron status
   # If not running:
   sudo service cron start
   ```

5. **Check cron logs**:
   ```bash
   # View maintenance log
   tail -f /var/log/vocabulary/maintenance.log

   # Check for errors
   grep ERROR /var/log/vocabulary/maintenance.log
   ```

### Log Rotation

To prevent log files from growing too large, set up log rotation:

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

### Check Current Status
```bash
source .venv/bin/activate
python check_frequency_status.py
```

### Manually Refresh Materialized View
```sql
-- From psql or any PostgreSQL client
SET search_path TO vocab;

-- Refresh without locking (requires unique index)
REFRESH MATERIALIZED VIEW CONCURRENTLY word_rarity_metrics;

-- Or use the convenience function
SELECT refresh_word_rarity_metrics();
```

### Update Only Missing Rarity Values
```bash
source .venv/bin/activate
python analysis/update_missing_final_rarity.py
```

This script only updates words where `final_rarity IS NULL` (not comprehensive).

## Frequency Data Sources

### Python wordfreq
- **Source**: wordfreq library (amalgamation of multiple corpora)
- **Format**: Zipf frequency (0-8 scale, higher = more common)
- **Coverage**: Best coverage for common English words
- **Fallback value**: -999 (not found)

### Google N-gram
- **Source**: Google Books N-gram corpus (1900-2019)
- **Format**: Normalized frequency
- **Requires**: `temp/googlebooks-eng-all-totalcounts-20120701.txt`
- **Setup**: Run download scripts in `temp/` directory
- **Fallback value**: -999 (not found)

### Common Crawl
- **Source**: Common Crawl web corpus via fastText
- **Format**: Frequency count
- **Requires**: `commoncrawl_data/fasttext_commoncrawl_lookup.txt.gz`
- **Setup**: Run `download_commoncrawl_frequencies.py`
- **Fallback value**: -999 (not found)

## Troubleshooting

### Issue: Script takes too long
**Solution**: Use `--skip-frequency` for quick rarity-only updates

### Issue: Missing N-gram data file
```bash
# Download required files
cd temp/
# Follow instructions in temp/README.md or download scripts
```

### Issue: Missing Common Crawl lookup
```bash
# Generate lookup file
python download_commoncrawl_frequencies.py
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
python scripts/maintain_rarity.py --dry-run
```

### Issue: Database connection errors
Check credentials in `core/secure_config.py`:
- Host: 10.0.0.99
- Port: 6543
- Database: postgres
- Schema: vocab
- User/password: Configured in secure_config

### Issue: View refresh fails with "could not create unique index"
The materialized view needs a unique index for CONCURRENT refresh:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_word_rarity_id ON word_rarity_metrics(id);
```

## Performance Notes

- **Full maintenance**: 5-15 minutes (depends on missing data volume)
- **Quick refresh** (--skip-frequency): ~30-60 seconds
- **View refresh only**: ~30 seconds
- **Frequency lookup**: ~0.1-1 second per word (bulk operations faster)

## Architecture

```
┌─────────────────┐
│  defined table  │
│  ┌───────────┐  │
│  │python_wf  │  │──┐
│  │ngram_freq │  │  │
│  │cc_freq    │  │  │
│  └───────────┘  │  │
└─────────────────┘  │
                     │
                     ├──> Materialized View: word_rarity_metrics
                     │    - Converts frequencies to percentiles
                     │    - Calculates weighted average
                     │    - Stores calculated final_rarity
                     │
                     └──> Copy back to defined.final_rarity
                          (for backward compatibility)
```

## Best Practices

1. **Run full maintenance daily** - Keeps all frequency data current
2. **Use quick refresh for real-time updates** - Fast rarity recalculation
3. **Monitor logs** - Check for consistent failures
4. **Dry-run before manual runs** - Preview impact of changes
5. **Keep source data updated** - Regenerate N-gram/CommonCrawl lookups periodically
6. **Backup before major changes** - The view creation script creates backups automatically

## Related Files

- `scripts/maintain_rarity.py` - Main maintenance script (**USE THIS**)
- `analysis/update_missing_final_rarity.py` - Legacy script (only updates NULL rarity)
- `analysis/migration/create_rarity_materialized_view.sql` - View definition
- `check_frequency_status.py` - Quick status checker
- `core/config.py` - Database configuration
- `core/secure_config.py` - Secure credential management

## Quick Reference Commands

```bash
# Check status
python check_frequency_status.py

# Full maintenance
python scripts/maintain_rarity.py

# Preview changes
python scripts/maintain_rarity.py --dry-run

# Quick refresh (no frequency updates)
python scripts/maintain_rarity.py --skip-frequency

# Silent cron mode
python scripts/maintain_rarity.py --silent

# View help
python scripts/maintain_rarity.py --help
```

---

**Last Updated**: 2025-10-20
**Script Version**: 1.0
**Database**: PostgreSQL (vocab schema)
