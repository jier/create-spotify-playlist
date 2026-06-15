.PHONY: lint
lint:
	uv run ruff check src/

.PHONY: format
format:
	uv run ruff format src/

.PHONY: typecheck
typecheck:
	uv run pyright src/

.PHONY: check
check: lint typecheck

.PHONY: test
test:
	uv run pytest tests/
