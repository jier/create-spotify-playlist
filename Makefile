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
