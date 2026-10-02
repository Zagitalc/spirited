# Thin wrappers. Each target is one command you can also run by hand,
# so nothing here is needed on a machine without make.

.PHONY: backend-install backend-test backend-lint backend-run extract routing-data routing routing-rebuild routing-test scores evaluate android

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
	cp backend/data/osm/region-filtered.osm.pbf routing/custom_files/

routing: routing-data
	cd routing && docker compose up -d && docker compose logs -f valhalla

# After a new extract: drop the tiles and the boundary database, which Valhalla
# would otherwise reuse, then rebuild. Elevation and time zones are kept.
routing-rebuild: routing-data
	cd routing/custom_files && rm -rf valhalla_tiles valhalla_tiles.tar admins.sqlite file_hashes.txt
	cd routing && FORCE_REBUILD=True docker compose up -d --force-recreate && docker compose logs -f valhalla

routing-test:
	cd backend && uv run pytest -q -m valhalla

# Score every road (needs Valhalla running for heights), then rank the reference
# roads in backend/data/reference_roads.json.
scores:
	cd backend && uv run python -m spirited.scoring build

evaluate:
	cd backend && uv run python -m spirited.scoring evaluate

android:
	cd android && ./gradlew spotlessCheck assembleDebug
