from __future__ import annotations

import os
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Literal

from app.sync_runtime import (
    ProcessLockBusyError,
    acquire_process_lock,
    read_json_object,
    release_process_lock,
    write_json_object,
)
from app.sync_history import SyncHistoryStore


SyncTaskKey = Literal["all", "A", "B", "C", "D", "E", "F"]

SCRIPT_MODULES = {
    "A": "app.sync.sse_funds",
    "B": "app.sync.sse_details",
    "C": "app.sync.szse_funds",
    "D": "app.sync.szse_details",
    "E": "app.sync.csrc_funds",
    "F": "app.sync.csrc_details",
}
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LOCK_PATH = BACKEND_DIR / ".sync.lock"
DEFAULT_STATE_PATH = BACKEND_DIR / ".sync-state.json"


class SyncJobBusyError(RuntimeError):
    pass


def _empty_state() -> dict[str, object]:
    return {
        "status": "idle",
        "startedAt": None,
        "finishedAt": None,
        "lastSucceededAt": None,
        "returnCode": None,
        "output": "",
    }


class SyncJobRunner:
    """Run only the six predefined sync modules, one job at a time."""

    def __init__(
        self,
        *,
        lock_path: Path = DEFAULT_LOCK_PATH,
        state_path: Path = DEFAULT_STATE_PATH,
        history_path: Path | None = None,
    ) -> None:
        self._lock = Lock()
        self._lock_path = lock_path
        self._state_path = state_path
        self._history = SyncHistoryStore(
            history_path or state_path.with_name(".sync-history.json")
        )
        self._active_job: SyncTaskKey | None = None
        self._current_script: str | None = None
        self._tasks = {key: _empty_state() for key in ("all", *SCRIPT_MODULES)}
        self._restore_state()

    def _restore_state(self) -> None:
        saved = read_json_object(self._state_path)
        if saved is None:
            return
        saved_tasks = saved.get("tasks")
        if not isinstance(saved_tasks, dict):
            return
        for key in self._tasks:
            state = saved_tasks.get(key)
            if isinstance(state, dict):
                self._tasks[key] = {**_empty_state(), **state}
                if (
                    self._tasks[key]["lastSucceededAt"] is None
                    and self._tasks[key]["status"] == "succeeded"
                ):
                    self._tasks[key]["lastSucceededAt"] = self._tasks[key][
                        "finishedAt"
                    ]
            if self._tasks[key]["status"] in {"queued", "running"}:
                self._tasks[key].update(
                    status="failed",
                    finishedAt=datetime.now(UTC).isoformat(),
                    output="服务重启，无法确认原同步任务的最终状态。",
                )
            last_succeeded_at = self._tasks[key]["lastSucceededAt"]
            if isinstance(last_succeeded_at, str):
                started_at = self._tasks[key]["startedAt"]
                self._history.add_completed(
                    record_id=f"legacy-{key}-{last_succeeded_at}",
                    task=key,  # type: ignore[arg-type]
                    started_at=(
                        started_at
                        if isinstance(started_at, str)
                        else last_succeeded_at
                    ),
                    finished_at=last_succeeded_at,
                    result="succeeded",
                    method="dialog",
                )
        self._persist_locked()

    def _snapshot_locked(self) -> dict[str, object]:
        return {
            "activeJob": self._active_job,
            "currentScript": self._current_script,
            "tasks": deepcopy(self._tasks),
        }

    def _persist_locked(self) -> None:
        try:
            write_json_object(self._state_path, self._snapshot_locked())
        except OSError:
            # 状态文件用于恢复和展示，不应因磁盘瞬时故障阻断实际同步。
            pass

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot_locked()

    def history(self, task: SyncTaskKey) -> list[dict[str, object]]:
        return self._history.recent(task)

    def start(self, task: SyncTaskKey) -> dict[str, object]:
        scripts = tuple(SCRIPT_MODULES) if task == "all" else (task,)
        with self._lock:
            if self._active_job is not None:
                raise SyncJobBusyError(f"同步任务 {self._active_job} 正在执行")
            try:
                process_lock = acquire_process_lock(self._lock_path)
            except ProcessLockBusyError as exc:
                raise SyncJobBusyError("已有定时或手动同步任务正在执行") from exc
            self._active_job = task
            self._current_script = None
            self._tasks[task] = {
                **_empty_state(),
                "lastSucceededAt": self._tasks[task]["lastSucceededAt"],
                "status": "queued",
                "startedAt": datetime.now(UTC).isoformat(),
            }
            self._persist_locked()
        Thread(
            target=self._run,
            args=(task, scripts, process_lock),
            daemon=True,
        ).start()
        return self.snapshot()

    def _run(
        self,
        task: SyncTaskKey,
        scripts: tuple[str, ...],
        process_lock: int,
    ) -> None:
        failed = False
        history_id: str | None = None
        try:
            if task == "all":
                try:
                    history_id = self._history.start("all", "dialog")
                except OSError:
                    history_id = None
            for script in scripts:
                started_at = datetime.now(UTC).isoformat()
                with self._lock:
                    self._current_script = script
                    self._tasks[task]["status"] = "running"
                    self._tasks[script] = {
                        **_empty_state(),
                        "lastSucceededAt": self._tasks[script][
                            "lastSucceededAt"
                        ],
                        "status": "running",
                        "startedAt": started_at,
                    }
                    self._persist_locked()
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", SCRIPT_MODULES[script]],
                        cwd=BACKEND_DIR,
                        env={**os.environ, "IFC_SYNC_METHOD": "dialog"},
                        capture_output=True,
                        text=True,
                        check=False,
                        pass_fds=(process_lock,),
                    )
                    output = "\n".join(
                        part.strip() for part in (result.stdout, result.stderr) if part.strip()
                    )[-4000:]
                    status = "succeeded" if result.returncode == 0 else "failed"
                    failed = failed or result.returncode != 0
                    return_code = result.returncode
                except Exception as exc:  # pragma: no cover - OS-level failure
                    output = str(exc)
                    status = "failed"
                    failed = True
                    return_code = None
                finished_at = datetime.now(UTC).isoformat()
                with self._lock:
                    self._tasks[script].update(
                        status=status,
                        finishedAt=finished_at,
                        returnCode=return_code,
                        output=output,
                    )
                    if status == "succeeded":
                        self._tasks[script]["lastSucceededAt"] = finished_at
                    self._persist_locked()
        finally:
            finished_at = datetime.now(UTC).isoformat()
            with self._lock:
                self._tasks[task].update(
                    status="failed" if failed else "succeeded",
                    finishedAt=finished_at,
                )
                if not failed:
                    self._tasks[task]["lastSucceededAt"] = finished_at
                self._active_job = None
                self._current_script = None
                self._persist_locked()
            try:
                if history_id is not None:
                    try:
                        self._history.finish(
                            history_id, "failed" if failed else "succeeded"
                        )
                    except OSError:
                        pass
            finally:
                release_process_lock(process_lock)


sync_job_runner = SyncJobRunner()
