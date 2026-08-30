from __future__ import annotations

import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Literal


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


class SyncJobBusyError(RuntimeError):
    pass


def _empty_state() -> dict[str, object]:
    return {
        "status": "idle",
        "startedAt": None,
        "finishedAt": None,
        "returnCode": None,
        "output": "",
    }


class SyncJobRunner:
    """Run only the six predefined sync modules, one job at a time."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._active_job: SyncTaskKey | None = None
        self._current_script: str | None = None
        self._tasks = {key: _empty_state() for key in ("all", *SCRIPT_MODULES)}

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "activeJob": self._active_job,
                "currentScript": self._current_script,
                "tasks": deepcopy(self._tasks),
            }

    def start(self, task: SyncTaskKey) -> dict[str, object]:
        scripts = tuple(SCRIPT_MODULES) if task == "all" else (task,)
        with self._lock:
            if self._active_job is not None:
                raise SyncJobBusyError(f"同步任务 {self._active_job} 正在执行")
            self._active_job = task
            self._current_script = None
            self._tasks[task] = {
                **_empty_state(),
                "status": "queued",
                "startedAt": datetime.now(UTC).isoformat(),
            }
        Thread(target=self._run, args=(task, scripts), daemon=True).start()
        return self.snapshot()

    def _run(self, task: SyncTaskKey, scripts: tuple[str, ...]) -> None:
        failed = False
        try:
            for script in scripts:
                started_at = datetime.now(UTC).isoformat()
                with self._lock:
                    self._current_script = script
                    self._tasks[task]["status"] = "running"
                    self._tasks[script] = {
                        **_empty_state(),
                        "status": "running",
                        "startedAt": started_at,
                    }
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", SCRIPT_MODULES[script]],
                        cwd=BACKEND_DIR,
                        capture_output=True,
                        text=True,
                        check=False,
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
                with self._lock:
                    self._tasks[script].update(
                        status=status,
                        finishedAt=datetime.now(UTC).isoformat(),
                        returnCode=return_code,
                        output=output,
                    )
        finally:
            with self._lock:
                self._tasks[task].update(
                    status="failed" if failed else "succeeded",
                    finishedAt=datetime.now(UTC).isoformat(),
                )
                self._active_job = None
                self._current_script = None


sync_job_runner = SyncJobRunner()
