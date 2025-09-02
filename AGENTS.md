# Repository Guidelines

## Project Structure & Module Organization
- `vocabulary_web_app.py`: FastAPI app and routes; HTML in `templates/`.
- CLI and utilities: `main_cli.py`, `cuda_enhanced_cli.py`, data processors like `definition_similarity_calculator.py`.
- Config and auth: `config.py`, `auth.py`.
- Tests: `tests/` with `test_*.py` modules; sample `test_main.http`.
- Assets/data: `cmudict-0.7b.txt`, caches (`*.pkl`), reports (`*.png`, `*.txt`).
- Packaging: `pyproject.toml` (tools, deps); optional web-only deps in `requirements_web.txt`.

## Build, Test, and Development Commands
- Create env: `python -m venv .venv && source .venv/bin/activate` (Windows: `./.venv/Scripts/activate`).
- Install dev deps: `pip install -e .[dev]` or web-only: `pip install -r requirements_web.txt`.
- Run API locally: `uvicorn vocabulary_web_app:app --reload` (or `python vocabulary_web_app.py`).
- CLI entry: `python main_cli.py --help` and `python cuda_enhanced_cli.py --help`.
- Tests: `pytest -q` (verbose+cov: `pytest -vv`).
- Lint/format: `black . && isort . && flake8` (type check: `mypy .`).

## Coding Style & Naming Conventions
- Python 3.10+; format with Black (88 cols) and isort (Black profile).
- Naming: files/modules `snake_case.py`, classes `CamelCase`, functions/vars `snake_case`.
- Keep modules focused; place HTML under `templates/`; SQL in `*.sql` files.
- Prefer pure functions; add docstrings for public functions and FastAPI endpoints.

## Testing Guidelines
- Framework: pytest. Tests live in `tests/`, named `test_*.py` with `Test*` classes and `test_*` functions.
- Add tests for new behavior, edge cases, and DB access wrappers (mock connections).
- Run `pytest -q` before PRs; include regression tests for fixed bugs.

## Commit & Pull Request Guidelines
- Commits: concise, imperative subject (e.g., `add`, `fix`, `refactor`), scope when helpful: `fix(api): handle empty query`.
- PRs: include summary, rationale, test evidence (`pytest` output), screenshots for UI, and notes on schema/migrations.
- Checklist: formatting and lint pass, tests pass, no secrets committed, docs updated when behavior changes.

## Security & Configuration Tips
- Configure MySQL via env vars consumed by `config.py`: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
- Never commit credentials; prefer a local `.env` and export vars in your shell.
- DB bootstrap: `mysql -u <user> -p <db> < create_user_tables.sql` (then run `setup_user_tables.py` if needed).
