import { useCallback, useEffect, useRef, useState } from "react";

import {
  getSyncTasks,
  startSyncTask,
  type SyncTaskKey,
  type SyncTaskSnapshot,
} from "@/lib/api";
import { CloseIcon } from "./icons";

interface SyncInfoDialogProps {
  onClose: () => void;
}

const SYNC_ROWS: Array<{
  scope: string;
  tasks: Array<{ key: Exclude<SyncTaskKey, "all">; description: string }>;
}> = [
  {
    scope: "场内基金 · 上交所",
    tasks: [
      { key: "A", description: "每周一 09:00：读取基金列表，筛选目标基金并更新基金主数据。" },
      { key: "B", description: "周一至周五 16:00：更新行情、净值、费率、规模、交易日和区间收益率。" },
    ],
  },
  {
    scope: "场内基金 · 深交所",
    tasks: [
      { key: "C", description: "每周一 09:00：读取基金列表，筛选目标基金，并更新主数据和产品概要费率。" },
      { key: "D", description: "周一至周五 22:00：更新行情、净值、规模、交易日和区间收益率。" },
    ],
  },
  {
    scope: "场外基金",
    tasks: [
      { key: "E", description: "每月 1 日 09:00：读取证监会公募基金目录，筛选目标基金并更新基金和主份额。" },
      { key: "F", description: "周一至周五 22:00：更新产品概要费率、季度规模、正式净值、申购状态和区间收益率。" },
    ],
  },
];

function statusLabel(
  task: SyncTaskKey,
  snapshot: SyncTaskSnapshot | null,
) {
  const state = snapshot?.tasks[task];
  if (!state || state.status === "idle") return null;
  if (state.status === "queued") return "等待执行";
  if (state.status === "running") {
    return task === "all" && snapshot?.currentScript
      ? `正在执行脚本 ${snapshot.currentScript}`
      : "执行中";
  }
  return state.status === "succeeded" ? "执行成功" : "执行失败";
}

export function SyncInfoDialog({ onClose }: SyncInfoDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [snapshot, setSnapshot] = useState<SyncTaskSnapshot | null>(null);
  const [startingTask, setStartingTask] = useState<SyncTaskKey | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  const refreshStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      setSnapshot(await getSyncTasks(signal));
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setRunError("无法读取同步任务状态。");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => void refreshStatus(controller.signal));
    const timer = window.setInterval(() => void refreshStatus(), 2000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refreshStatus]);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [onClose]);

  async function runTask(task: SyncTaskKey) {
    setStartingTask(task);
    setRunError(null);
    try {
      setSnapshot(await startSyncTask(task));
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "同步任务启动失败。");
      await refreshStatus();
    } finally {
      setStartingTask(null);
    }
  }

  function taskControl(task: SyncTaskKey, buttonLabel = "立即执行") {
    const state = snapshot?.tasks[task];
    const label = statusLabel(task, snapshot);
    const busy = Boolean(snapshot?.activeJob) || startingTask !== null;
    return (
      <span className="sync-task-control">
        <button
          className="sync-run-button"
          type="button"
          disabled={busy}
          onClick={() => void runTask(task)}
          aria-label={task === "all" ? "立即执行脚本 A 到 F" : `立即执行脚本 ${task}`}
        >
          {startingTask === task ? "启动中" : buttonLabel}
        </button>
        {label && (
          <small
            className={`sync-task-status ${state?.status ?? ""}`}
            title={state?.output || undefined}
          >
            {label}
          </small>
        )}
      </span>
    );
  }

  return (
    <div
      className="comparison-overlay sync-info-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sync-info-title"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="sync-info-sheet">
        <header className="comparison-header">
          <div>
            <span className="section-kicker">数据说明</span>
            <div className="sync-info-title-row">
              <h2 id="sync-info-title">数据同步机制</h2>
              {taskControl("all", "立即执行所有同步")}
            </div>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label="关闭数据同步机制"
          >
            <CloseIcon />
          </button>
        </header>

        <div className="sync-info-content">
          {runError && <p className="sync-run-error">{runError}</p>}
          {SYNC_ROWS.map((row) => (
            <section key={row.scope} className="sync-info-section">
              <h3>{row.scope}</h3>
              {row.tasks.map((task) => (
                <div key={task.key} className="sync-task-line">
                  <p>
                    {task.description}
                    {taskControl(task.key)}
                  </p>
                </div>
              ))}
            </section>
          ))}

        </div>
      </div>
    </div>
  );
}
