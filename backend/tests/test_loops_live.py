"""Loops from the real Valhalla and the real scores. Skipped unless both exist
(see routing/README.md, then `make scores`)."""

from __future__ import annotations

import pytest

from spirited.loops.generate import Group, generate_loops
from spirited.routing.client import ValhallaClient
from spirited.scoring.build import SCORES_PATH
from spirited.scoring.store import ScoreStore

# A village in the Kennet valley with the Downs to the north and the Hampshire hills south.
KINTBURY = (51.4046, -1.4430)


@pytest.fixture(scope="module")
def client():
    client = ValhallaClient()
    if not client.is_up():
        pytest.skip("Valhalla is not running; see routing/README.md")
    yield client
    client.close()


@pytest.fixture(scope="module")
def store():
    if not SCORES_PATH.exists():
        pytest.skip("scores.sqlite not built: run `make scores`")
    with ScoreStore(SCORES_PATH) as store:
        yield store


@pytest.mark.valhalla
def test_a_ninety_minute_loop_from_a_village(client: ValhallaClient, store: ScoreStore) -> None:
    result = generate_loops(KINTBURY, 90, client, store, count=3)
    assert result.loops, result.notes
    for loop in result.loops:
        assert abs(loop.duration_min - 90) <= 13.5
        assert loop.shares[Group.RECOMMENDED] >= 0.55
        assert loop.reuse_share <= 0.1
        assert loop.points[0] == pytest.approx(KINTBURY, abs=0.01)
