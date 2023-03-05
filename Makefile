## Lint your code using pylint
.PHONY: lint
lint:
	python -m flake8 --version
	python -m flake8 src/
	## Run tests using pytest
.PHONY: test
test:
	python -m pytest --version
	python -m pytest tests## Format your code using black
.PHONY: black
black:
	python -m black --version
	python -m black src/

.PHONY: sort
sort:
	python -m isort .
