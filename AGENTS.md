# Repository Guidelines

## Project Structure & Module Organization
- Full FastAPI experience lives in `web_apps/vocabulary_web_app.py`; run it from repo root so `templates/` resolves correctly. Avoid `simple_vocab_app.py` except for historical reference.
- GPU pronunciation stack spans `cuda_enhanced_cli.py`, `cuda_similarity_calculator.py`, `modern_pronunciation_system.py`, and database helpers such as `custom_database_manager.py`.
- Semantic tooling sits in `definition_similarity_calculator.py`, `process_definitions_chunked.py`, and `ai_definition_corrector.py`.
- Shared config/auth logic is in `config.py` and `auth.py`; tests reside under `tests/`, with assets like `cmudict-0.7b.txt`, `*.pkl`, and reports at the repo root.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create and enter the virtualenv.
- `pip install -e .[dev]` (or `pip install -r requirements_web.txt` for web-only) installs dependencies, including optional CUDA extras when available.
- `python web_apps/vocabulary_web_app.py`: launch the full web app on port 8001; this is the only supported runtime for feature work.
- `python cuda_enhanced_cli.py --process-words --batch-size 1000` and `--calculate-similarities --similarity-threshold 0.2`: core GPU workflows; use `--status` or `--check-cuda` to confirm environment health.
- `python definition_similarity_calculator.py`: run semantic similarity batches; use the chunked variant for large jobs.
- `pytest tests/ -v --cov=pronunciation --cov-report=term-missing`: execute the suite with coverage; add `black . --line-length 88`, `isort . --profile black`, `flake8 .`, and `mypy . --ignore-missing-imports` before PRs.

## Coding Style & Naming Conventions
- Target Python 3.10+ with 88-character lines; format via Black and isort (Black profile), lint with Flake8, and type-check with mypy.
- Use snake_case for modules, functions, and variables; classes stay CamelCase. Keep modules focused and place HTML in `templates/` and SQL in `*.sql` files.

## Testing Guidelines
- Structure tests as `tests/test_*.py` with `Test*` classes or `test_*` functions. Mock external services (CUDA, MySQL) when needed.
- Before sharing changes, run the precise feature (API, CLI, or UI) you touched, observe the outcome, and capture any regressions with new pytest cases.

## Commit & Pull Request Guidelines
- Write imperative commits with optional scope, e.g., `add(cli): batch pronunciation processing`.
- PR descriptions should summarize behavior changes, list linked issues, and attach `pytest` output plus UI screenshots where relevant.
- Confirm formatting, linting, typing, and tests succeed; never include secrets—load MySQL credentials via env vars consumed by `config.py`.

## Quality & Operations Expectations
- Follow the "Always Works" checklist: run the artifact you changed end-to-end, verify the exact scenario, and inspect logs for errors before submitting.
- Database tasks use MySQL at `10.0.0.160:3306/vocab`; bootstrap via `setup_user_tables.py` and monitor performance with `mysql_performance_monitor.py` when diagnosing issues.
