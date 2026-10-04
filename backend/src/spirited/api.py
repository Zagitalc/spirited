"""HTTP API. docs/api.md is the contract."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from spirited import __version__
from spirited.loops.generate import OutsideRegion, Router, generate_loops
from spirited.loops.output import loop_to_dict
from spirited.routing.client import ValhallaClient, ValhallaError
from spirited.scoring.build import SCORES_PATH
from spirited.scoring.store import ScoreStore

app = FastAPI(title="Spirited", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


class Point(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class LoopRequest(BaseModel):
    start: Point
    duration_min: int = Field(ge=20, le=240, description="Target drive time in minutes")
    count: int = Field(default=3, ge=1, le=5, description="How many loops to return, at most")


class Shares(BaseModel):
    recommended: float
    not_recommended: float
    built_up: float


class SegmentOut(BaseModel):
    from_km: float
    to_km: float
    road: str
    group: str
    score: float | None
    geometry: dict[str, Any]


class LoopOut(BaseModel):
    distance_km: float
    duration_min: int
    score: float
    shares: Shares
    reuse_share: float
    geometry: dict[str, Any]
    polyline: str
    gpx: str
    segments: list[SegmentOut]
    warnings: list[str]


class LoopResponse(BaseModel):
    loops: list[LoopOut]
    notes: list[str]


def get_router() -> Iterator[Router]:
    client = ValhallaClient()
    try:
        if not client.is_up():
            raise HTTPException(503, "The routing service is not running.")
        yield client
    finally:
        client.close()


def get_store() -> Iterator[ScoreStore]:
    try:
        store = ScoreStore(SCORES_PATH)
    except FileNotFoundError as error:
        raise HTTPException(503, "Road scores have not been built yet.") from error
    try:
        yield store
    finally:
        store.close()


@app.post("/loops", response_model=LoopResponse)
def loops(
    request: LoopRequest,
    router: Router = Depends(get_router),  # noqa: B008
    store: ScoreStore = Depends(get_store),  # noqa: B008
) -> LoopResponse:
    try:
        result = generate_loops(
            (request.start.lat, request.start.lon),
            request.duration_min,
            router,
            store,
            count=request.count,
        )
    except OutsideRegion as error:
        raise HTTPException(422, str(error)) from error
    except ValhallaError as error:
        raise HTTPException(422, "We could not find a road near that start.") from error
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error
    return LoopResponse(
        loops=[
            LoopOut(**loop_to_dict(loop, name=f"Spirited loop {n}"))
            for n, loop in enumerate(result.loops, 1)
        ],
        notes=result.notes,
    )
