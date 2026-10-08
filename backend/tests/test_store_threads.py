"""The score store is opened by one request and may be used on another worker thread."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loop_support import make_store

from spirited.scoring.store import ScoreStore


def in_new_thread(call: Callable[[], Any]) -> Any:
    """Run `call` on a thread of its own and return what it returned, or raise what it raised."""
    outcome: list[Any] = []

    def run() -> None:
        try:
            outcome.append(call())
        except Exception as error:
            outcome.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    if isinstance(outcome[0], Exception):
        raise outcome[0]
    return outcome[0]


def test_a_store_opened_in_one_thread_can_be_used_and_closed_in_others(tmp_path: Path) -> None:
    make_store(tmp_path / "scores.sqlite")
    made: list[ScoreStore] = []
    created, release = threading.Event(), threading.Event()

    def open_and_wait() -> None:
        made.append(ScoreStore(tmp_path / "scores.sqlite"))
        created.set()
        release.wait()  # stay alive, so no later thread can reuse this thread's id

    opener = threading.Thread(target=open_and_wait)
    opener.start()
    created.wait()
    try:
        store = made[0]
        rows = in_new_thread(lambda: store.corridors_for_ways([10, 20]))
        in_new_thread(store.close)
    finally:
        release.set()
        opener.join()
    assert set(rows) == {10, 20}
