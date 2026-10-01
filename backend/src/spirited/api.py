"""HTTP API. Stage 0 only exposes a health check; docs/api.md is the contract."""

from fastapi import FastAPI

from spirited import __version__

app = FastAPI(title="Spirited", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
