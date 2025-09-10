Cron Scheduling for Candidate Ingestion

Examples using system cron (adjust paths/venv):

- Every 6 hours: run RSS ingestion (limit 200)
  0 */6 * * * cd /path/to/vocabulary && . .venv/bin/activate && python main_cli.py --ingest-run rss --ingest-limit 200 >> logs/ingest_rss.log 2>&1

- Daily at 01:15: run arXiv ingestion (limit 200)
  15 1 * * * cd /path/to/vocabulary && . .venv/bin/activate && python main_cli.py --ingest-run arxiv --ingest-limit 200 >> logs/ingest_arxiv.log 2>&1

- Daily at 01:45: run GitHub releases ingestion (limit 50 per repo)
  45 1 * * * cd /path/to/vocabulary && . .venv/bin/activate && python main_cli.py --ingest-run github --ingest-limit 50 >> logs/ingest_github.log 2>&1

- Daily at 02:30: recompute scores and fetch definitions (lightweight)
  30 2 * * * cd /path/to/vocabulary && . .venv/bin/activate && python main_cli.py --score-recompute >> logs/score_recompute.log 2>&1

Notes
- Jobs are idempotent via document hashes/external IDs.
- Adjust concurrency if running alongside other workloads; these jobs are light.
- Ensure dependencies installed: feedparser, wordfreq, nltk (optional).
