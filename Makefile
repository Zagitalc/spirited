# Thin wrappers. Each target is one command you can also run by hand,
# so nothing here is needed on a machine without make.

.PHONY: backend-install backend-test backend-lint backend-run backend-run-lan extract routing-data routing routing-rebuild routing-test scores evaluate loops android

backend-install:
	cd backend && uv sync

backend-test:
	cd backend && uv run pytest -q

backend-lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run pyright

backend-run:
	cd backend && uv run uvicorn spirited.api:app --reload

# Serve the API to other devices on this network, such as a phone running the app.
# The API has no login: use it on a network you trust and never forward the port.
backend-run-lan:
	@ip=$$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | cut -d" " -f1); \
	echo "Phone browser: http://$${ip:-YOUR-COMPUTER-ADDRESS}:8000/health should say ok"; \
	echo "Android emulator: http://10.0.2.2:8000"
	cd backend && uv run uvicorn spirited.api:app --reload --host 0.0.0.0

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

# Generate loops from START ("lat,lon") and write out/loops/loops.html plus GPX files.
# Example: make loops START=51.4545,-0.9781 MINUTES=90 ARGS="--tolerance 0.2"
MINUTES ?= 90
loops:
	cd backend && uv run python -m spirited.loops $(START) --minutes $(MINUTES) --out ../out/loops $(ARGS)

android:
	cd android && ./gradlew spotlessCheck assembleDebug
