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


def test_runs_single_fixed_script(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "synced", "")

    monkeypatch.setattr(sync_jobs.subprocess, "run", fake_run)
    runner = sync_jobs.SyncJobRunner()

    runner.start("D")
    finished = wait_until_finished(runner)

    assert calls == [[sync_jobs.sys.executable, "-m", "app.sync.szse_details"]]
    assert finished["tasks"]["D"]["status"] == "succeeded"
    assert finished["tasks"]["D"]["output"] == "synced"


def test_all_runs_a_through_f_in_order(monkeypatch) -> None:
    modules: list[str] = []

    def fake_run(command, **_kwargs):
        modules.append(command[-1])
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(sync_jobs.subprocess, "run", fake_run)
    runner = sync_jobs.SyncJobRunner()
    runner.start("all")
    finished = wait_until_finished(runner)

    assert modules == list(sync_jobs.SCRIPT_MODULES.values())
    assert finished["tasks"]["all"]["status"] == "succeeded"


def test_rejects_overlapping_jobs(monkeypatch) -> None:
    monkeypatch.setattr(
        sync_jobs.subprocess,
        "run",
        lambda command, **_kwargs: time.sleep(0.2),
    )
    runner = sync_jobs.SyncJobRunner()
    runner.start("A")

    with pytest.raises(sync_jobs.SyncJobBusyError):
        runner.start("B")
