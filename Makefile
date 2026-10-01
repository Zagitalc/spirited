# Thin wrappers. Each target is one command you can also run by hand,
# so nothing here is needed on a machine without make.

.PHONY: backend-install backend-test backend-lint backend-run extract android

backend-install:
	cd backend && uv sync

backend-test:
	cd backend && uv run pytest -q

backend-lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run pyright

backend-run:
	cd backend && uv run uvicorn spirited.api:app --reload

extract:
	cd backend && uv run python -m spirited.extract all

android:
	cd android && ./gradlew spotlessCheck assembleDebug
