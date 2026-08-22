.PHONY: lint
lint:
	uv run ruff check src/ tests/

.PHONY: format
format:
	uv run ruff format src/ tests/

.PHONY: typecheck
typecheck:
	uv run pyright src/ tests/

.PHONY: test
test:
	uv run pytest tests/

.PHONY: check
check: lint typecheck test

.PHONY: clean-runs
clean-runs:
	uv run python -c "from src.algorithms.persistence import cleanup_old_runs; from src.settings import settings; deleted = cleanup_old_runs(settings.runs_dir, settings.runs_retention_days); print(f'Deleted {len(deleted)} run trace(s) older than {settings.runs_retention_days} days')"
