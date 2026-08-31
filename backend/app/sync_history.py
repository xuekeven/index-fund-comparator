from __future__ import annotations

import fcntl
import os
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, TypeVar
from uuid import uuid4

from app.sync_runtime import read_json_object, write_json_object


SyncTaskKey = Literal["all", "A", "B", "C", "D", "E", "F"]
SyncExecutionMethod = Literal["scheduled", "dialog", "terminal"]
SyncExecutionResult = Literal["succeeded", "failed", "stopped"]

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_PATH = BACKEND_DIR / ".sync-history.json"
HISTORY_WINDOW_DAYS = 7
_METHODS = {"scheduled", "dialog", "terminal"}
_RESULTS = {"succeeded", "failed", "stopped"}
_T = TypeVar("_T")


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _process_is_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


class SyncHistoryStore:
    def __init__(self, path: Path = DEFAULT_HISTORY_PATH) -> None:
        self.path = path
        self.lock_path = path.with_suffix(f"{path.suffix}.lock")

    def _mutate(self, callback: Callable[[list[dict[str, object]]], _T]) -> _T:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            payload = read_json_object(self.path) or {}
            raw_records = payload.get("records")
            records = [
                dict(record)
                for record in raw_records
                if isinstance(record, dict)
            ] if isinstance(raw_records, list) else []
            cutoff = datetime.now(UTC) - timedelta(days=HISTORY_WINDOW_DAYS)
            records[:] = [
                record
                for record in records
                if (
                    (started_at := _parse_datetime(record.get("startedAt")))
                    is not None
                    and started_at >= cutoff
                )
            ]
            result = callback(records)
            write_json_object(self.path, {"records": records})
            return result
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def start(
        self,
        task: SyncTaskKey,
        method: SyncExecutionMethod,
    ) -> str:
        record_id = uuid4().hex

        def add(records: list[dict[str, object]]) -> None:
            records.append(
                {
                    "id": record_id,
                    "task": task,
                    "startedAt": datetime.now(UTC).isoformat(),
                    "finishedAt": None,
                    "result": None,
                    "method": method,
                    "pid": os.getpid(),
                }
            )

        self._mutate(add)
        return record_id

    def finish(self, record_id: str, result: SyncExecutionResult) -> None:
        def update(records: list[dict[str, object]]) -> None:
            for record in records:
                if record.get("id") == record_id:
                    record["finishedAt"] = datetime.now(UTC).isoformat()
                    record["result"] = result
                    return

        self._mutate(update)

    def add_completed(
        self,
        *,
        record_id: str,
        task: SyncTaskKey,
        started_at: str,
        finished_at: str,
        result: SyncExecutionResult,
        method: SyncExecutionMethod,
    ) -> None:
        def add(records: list[dict[str, object]]) -> None:
            if any(record.get("id") == record_id for record in records):
                return
            records.append(
                {
                    "id": record_id,
                    "task": task,
                    "startedAt": started_at,
                    "finishedAt": finished_at,
                    "result": result,
                    "method": method,
                    "pid": None,
                }
            )

        self._mutate(add)

    def recent(self, task: SyncTaskKey) -> list[dict[str, object]]:
        def collect(records: list[dict[str, object]]) -> list[dict[str, object]]:
            now = datetime.now(UTC).isoformat()
            for record in records:
                if record.get("result") is None and not _process_is_alive(
                    record.get("pid")
                ):
                    record["result"] = "stopped"
                    record["finishedAt"] = now
            completed = [
                {
                    "time": record.get("startedAt"),
                    "result": record.get("result"),
                    "method": record.get("method"),
                }
                for record in records
                if record.get("task") == task
                and record.get("result") in _RESULTS
                and record.get("method") in _METHODS
            ]
            return sorted(
                completed,
                key=lambda record: str(record["time"]),
                reverse=True,
            )

        return self._mutate(collect)


def execution_method() -> SyncExecutionMethod:
    value = os.environ.get("IFC_SYNC_METHOD", "terminal")
    if value == "scheduled":
        return "scheduled"
    if value == "dialog":
        return "dialog"
    return "terminal"


def run_tracked_sync(
    task: SyncTaskKey,
    callback: Callable[[], _T],
    *,
    store: SyncHistoryStore | None = None,
) -> _T:
    store = store or SyncHistoryStore()
    record_id = store.start(task, execution_method())
    finished = False

    def finish(result: SyncExecutionResult) -> None:
        nonlocal finished
        if not finished:
            store.finish(record_id, result)
            finished = True

    previous_handlers: dict[int, signal.Handlers] = {}

    def stop(signum: int, _frame: object) -> None:
        finish("stopped")
        raise SystemExit(128 + signum)

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, stop)

    try:
        result = callback()
    except KeyboardInterrupt:
        finish("stopped")
        raise
    except SystemExit as exc:
        if not finished:
            finish("succeeded" if exc.code in (None, 0) else "failed")
        raise
    except BaseException:
        finish("failed")
        raise
    else:
        finish("succeeded")
        return result
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
