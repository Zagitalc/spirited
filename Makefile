# Thin wrappers. Each target is one command you can also run by hand,
# so nothing here is needed on a machine without make.

.PHONY: backend-install backend-test backend-lint backend-run extract routing-data routing routing-test android

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

# Copy the filtered extract into Valhalla's input folder, then build and serve.
routing-data:
	cp backend/data/osm/region-filtered.osm.pbf backend/data/osm/uk-admin.osm.pbf routing/custom_files/

routing: routing-data
	cd routing && docker compose up -d && docker compose logs -f valhalla

routing-test:
	cd backend && uv run pytest -q -m valhalla

android:
	cd android && ./gradlew spotlessCheck assembleDebug
