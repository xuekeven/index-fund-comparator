import subprocess
import time

import pytest

import app.sync_jobs as sync_jobs


def wait_until_finished(runner: sync_jobs.SyncJobRunner) -> dict[str, object]:
    for _ in range(100):
        snapshot = runner.snapshot()
        if snapshot["activeJob"] is None:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("sync job did not finish")


def test_runs_single_fixed_script(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        environments.append(kwargs["env"])
        return subprocess.CompletedProcess(command, 0, "synced", "")

    monkeypatch.setattr(sync_jobs.subprocess, "run", fake_run)
    runner = sync_jobs.SyncJobRunner(
        lock_path=tmp_path / "sync.lock",
        state_path=tmp_path / "sync-state.json",
    )

    runner.start("D")
    finished = wait_until_finished(runner)

    assert calls == [[sync_jobs.sys.executable, "-m", "app.sync.szse_details"]]
    assert environments[0]["IFC_SYNC_METHOD"] == "dialog"
    assert finished["tasks"]["D"]["status"] == "succeeded"
    assert finished["tasks"]["D"]["output"] == "synced"
    assert finished["tasks"]["D"]["lastSucceededAt"] == finished["tasks"]["D"]["finishedAt"]


def test_all_runs_a_through_f_in_order(monkeypatch, tmp_path) -> None:
    modules: list[str] = []

    def fake_run(command, **_kwargs):
        modules.append(command[-1])
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(sync_jobs.subprocess, "run", fake_run)
    runner = sync_jobs.SyncJobRunner(
        lock_path=tmp_path / "sync.lock",
        state_path=tmp_path / "sync-state.json",
    )
    runner.start("all")
    finished = wait_until_finished(runner)

    assert modules == list(sync_jobs.SCRIPT_MODULES.values())
    assert finished["tasks"]["all"]["status"] == "succeeded"
    assert finished["tasks"]["all"]["lastSucceededAt"] == finished["tasks"]["all"]["finishedAt"]
    assert all(
        finished["tasks"][key]["lastSucceededAt"]
        for key in sync_jobs.SCRIPT_MODULES
    )
    assert runner.history("all")[0]["result"] == "succeeded"
    assert runner.history("all")[0]["method"] == "dialog"


def test_failed_run_preserves_previous_success_time(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "sync-state.json"
    previous_success = "2026-08-31T01:00:00+00:00"
    sync_jobs.write_json_object(
        state_path,
        {
            "tasks": {
                "F": {
                    "status": "succeeded",
                    "finishedAt": previous_success,
                }
            }
        },
    )
    monkeypatch.setattr(
        sync_jobs.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command, 1, "", "failed"
        ),
    )
    runner = sync_jobs.SyncJobRunner(
        lock_path=tmp_path / "sync.lock",
        state_path=state_path,
    )

    runner.start("F")
    finished = wait_until_finished(runner)

    assert finished["tasks"]["F"]["status"] == "failed"
    assert finished["tasks"]["F"]["lastSucceededAt"] == previous_success


def test_rejects_overlapping_jobs(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        sync_jobs.subprocess,
        "run",
        lambda command, **_kwargs: time.sleep(0.2),
    )
    runner = sync_jobs.SyncJobRunner(
        lock_path=tmp_path / "sync.lock",
        state_path=tmp_path / "sync-state.json",
    )
    runner.start("A")

    with pytest.raises(sync_jobs.SyncJobBusyError):
        runner.start("B")


def test_rejects_job_when_external_process_lock_is_held(tmp_path) -> None:
    lock_path = tmp_path / "sync.lock"
    descriptor = sync_jobs.acquire_process_lock(lock_path)
    runner = sync_jobs.SyncJobRunner(
        lock_path=lock_path,
        state_path=tmp_path / "sync-state.json",
    )
    try:
        with pytest.raises(sync_jobs.SyncJobBusyError, match="已有定时或手动"):
            runner.start("A")
    finally:
        sync_jobs.release_process_lock(descriptor)


def test_marks_incomplete_persisted_job_as_failed(tmp_path) -> None:
    state_path = tmp_path / "sync-state.json"
    sync_jobs.write_json_object(
        state_path,
        {
            "activeJob": "D",
            "currentScript": "D",
            "tasks": {
                "D": {
                    "status": "running",
                    "startedAt": "2026-08-31T10:00:00+00:00",
                }
            },
        },
    )

    runner = sync_jobs.SyncJobRunner(
        lock_path=tmp_path / "sync.lock",
        state_path=state_path,
    )

    snapshot = runner.snapshot()
    assert snapshot["activeJob"] is None
    assert snapshot["tasks"]["D"]["status"] == "failed"
    assert "服务重启" in snapshot["tasks"]["D"]["output"]
