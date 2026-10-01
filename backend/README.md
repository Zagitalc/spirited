# Spirited backend

Python service for routing, scoring and loop generation. In Stage 0 it holds
the OSM extract pipeline, the road safety filter and a health-check endpoint.

```sh
uv sync                                   # create .venv and install
uv run pytest                             # tests
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run uvicorn spirited.api:app --reload  # http://127.0.0.1:8000/health
uv run python -m spirited.extract all     # download, merge, clip and filter the region
```

The extract steps need `osmium-tool` on your `PATH`. See the top-level README.
