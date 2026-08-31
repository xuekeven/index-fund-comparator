import { useCallback, useEffect, useRef, useState } from "react";

import {
  getSyncTaskHistory,
  getSyncTasks,
  startSyncTask,
  type SyncHistoryItem,
  type SyncTaskKey,
  type SyncTaskSnapshot,
} from "@/lib/api";
import type { DataFreshness } from "@/lib/types";
import { CloseIcon } from "./icons";

interface SyncInfoDialogProps {
  dataFreshness: DataFreshness;
  onClose: () => void;
}

const FRESHNESS_ROWS: Array<{
  key: keyof DataFreshness;
  label: string;
}> = [
  { key: "master", label: "基金主数据" },
  { key: "nav", label: "基金净值" },
  { key: "quote", label: "场内行情" },
  { key: "fee", label: "费率" },
  { key: "scale", label: "基金规模" },
  { key: "metric", label: "收益指标" },
  { key: "subscription", label: "申购状态" },
];

function formatFreshness(value: string | null) {
  if (!value) return "暂无数据";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function formatHistoryTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

const HISTORY_RESULT_LABELS: Record<SyncHistoryItem["result"], string> = {
  succeeded: "成功",
  failed: "失败",
  stopped: "停止",
};

const HISTORY_METHOD_LABELS: Record<SyncHistoryItem["method"], string> = {
  scheduled: "定时计划",
  dialog: "弹层按钮",
  terminal: "终端命令行",
};

function SyncHistoryDialog({
  task,
  onClose,
}: {
  task: SyncTaskKey;
  onClose: () => void;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [items, setItems] = useState<SyncHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void getSyncTaskHistory(task, controller.signal)
      .then((response) => setItems(response.items))
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError("无法读取脚本执行历史。");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [task]);

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    closeButtonRef.current?.focus();

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      onClose();
    }

    window.addEventListener("keydown", closeOnEscape, true);
    return () => {
      window.removeEventListener("keydown", closeOnEscape, true);
      previousFocus?.focus();
    };
  }, [onClose]);

  return (
    <div
      className="sync-history-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sync-history-title"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="sync-history-sheet">
        <header className="comparison-header">
          <div>
            <span className="section-kicker">最近 7 天</span>
            <h2 id="sync-history-title">
              {task === "all" ? "所有同步" : `脚本 ${task}`} 执行历史
            </h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label="关闭脚本执行历史"
          >
            <CloseIcon />
          </button>
        </header>
        <div className="sync-history-content">
          {loading ? (
            <p className="sync-history-state">正在读取执行历史…</p>
          ) : error ? (
            <p className="sync-history-state error">{error}</p>
          ) : items.length === 0 ? (
            <p className="sync-history-state">最近 7 天暂无执行记录。</p>
          ) : (
            <table className="sync-history-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>结果</th>
                  <th>方式</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => (
                  <tr key={`${item.time}-${item.method}-${index}`}>
                    <td>{formatHistoryTime(item.time)}</td>
                    <td>
                      <span className={`sync-history-result ${item.result}`}>
                        {HISTORY_RESULT_LABELS[item.result]}
                      </span>
                    </td>
                    <td>{HISTORY_METHOD_LABELS[item.method]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
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
  return state.status === "succeeded" ? null : "执行失败";
}

export function SyncInfoDialog({
  dataFreshness,
  onClose,
}: SyncInfoDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [snapshot, setSnapshot] = useState<SyncTaskSnapshot | null>(null);
  const [startingTask, setStartingTask] = useState<SyncTaskKey | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [historyTask, setHistoryTask] = useState<SyncTaskKey | null>(null);

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

  function taskControl(task: SyncTaskKey, buttonLabel = "执行") {
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
          aria-label={task === "all" ? "执行脚本 A 到 F" : `执行脚本 ${task}`}
        >
          {startingTask === task ? "启动中" : buttonLabel}
        </button>
        <button
          className="sync-history-button"
          type="button"
          onClick={() => setHistoryTask(task)}
          aria-label={task === "all" ? "查看所有同步执行历史" : `查看脚本 ${task} 执行历史`}
        >
          历史
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
              {taskControl("all", "执行所有同步")}
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
          <section className="sync-info-section">
            <h3>当前筛选数据的采集时间</h3>
            <dl className="sync-freshness-grid">
              {FRESHNESS_ROWS.map(({ key, label }) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{formatFreshness(dataFreshness[key])}</dd>
                </div>
              ))}
            </dl>
          </section>
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
      {historyTask && (
        <SyncHistoryDialog
          task={historyTask}
          onClose={() => setHistoryTask(null)}
        />
      )}
    </div>
  );
}
