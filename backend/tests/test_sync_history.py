from datetime import UTC, datetime, timedelta

import pytest

from app.sync_history import SyncHistoryStore, run_tracked_sync


def test_tracks_success_failure_and_stop_with_execution_method(
    monkeypatch, tmp_path
) -> None:
    store = SyncHistoryStore(tmp_path / "history.json")

    monkeypatch.setenv("IFC_SYNC_METHOD", "scheduled")
    assert run_tracked_sync("A", lambda: "ok", store=store) == "ok"

    monkeypatch.setenv("IFC_SYNC_METHOD", "dialog")
    with pytest.raises(RuntimeError, match="boom"):
        run_tracked_sync(
            "A",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            store=store,
        )

    monkeypatch.delenv("IFC_SYNC_METHOD", raising=False)
    with pytest.raises(KeyboardInterrupt):
        run_tracked_sync(
            "A",
            lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
            store=store,
        )

    records = store.recent("A")
    assert {record["result"] for record in records} == {
        "succeeded",
        "failed",
        "stopped",
    }
    assert {record["method"] for record in records} == {
        "scheduled",
        "dialog",
        "terminal",
    }


def test_returns_only_last_seven_days_in_descending_order(tmp_path) -> None:
    store = SyncHistoryStore(tmp_path / "history.json")
    now = datetime.now(UTC)
    recent_times = [now - timedelta(hours=2), now - timedelta(hours=1)]
    for index, started_at in enumerate(recent_times):
        store.add_completed(
            record_id=f"recent-{index}",
            task="F",
            started_at=started_at.isoformat(),
            finished_at=(started_at + timedelta(minutes=1)).isoformat(),
            result="succeeded",
            method="terminal",
        )
    old_time = now - timedelta(days=8)
    store.add_completed(
        record_id="old",
        task="F",
        started_at=old_time.isoformat(),
        finished_at=old_time.isoformat(),
        result="failed",
        method="scheduled",
    )

    records = store.recent("F")

    assert [record["time"] for record in records] == [
        recent_times[1].isoformat(),
        recent_times[0].isoformat(),
    ]
