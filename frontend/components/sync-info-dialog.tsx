import { useEffect, useRef } from "react";

import { CloseIcon } from "./icons";

interface SyncInfoDialogProps {
  onClose: () => void;
}

const SYNC_ROWS = [
  {
    scope: "场内基金 · 上交所",
    master: "每周一 09:00：读取基金列表，筛选目标基金并更新基金主数据。",
    detail: "周一至周五 16:00：更新行情、净值、费率、规模、交易日和区间收益率。",
  },
  {
    scope: "场内基金 · 深交所",
    master: "每周一 09:00：读取基金列表，筛选目标基金，并更新主数据和产品概要费率。",
    detail: "周一至周五 22:00：更新行情、净值、规模、交易日和区间收益率。",
  },
  {
    scope: "场外基金",
    master: "每月 1 日 09:00：读取证监会公募基金目录，筛选目标基金并更新基金和主份额。",
    detail: "周一至周五 22:00：更新产品概要费率、季度规模、正式净值、申购状态和区间收益率。",
  },
];

export function SyncInfoDialog({ onClose }: SyncInfoDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

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
            <h2 id="sync-info-title">数据同步机制</h2>
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
          {SYNC_ROWS.map((row) => (
            <section key={row.scope} className="sync-info-section">
              <h3>{row.scope}</h3>
              <p>{row.master}</p>
              <p>{row.detail}</p>
            </section>
          ))}

          <div className="sync-info-note">
            <strong>页面时间怎样理解？</strong>
            <p>“同步时间”取当前指数、场内/场外及交易所筛选范围内，相关同步任务最近一次实际采集数据的时间，不是计划启动时间；任务需要逐只访问官方页面，因此完成时间可能晚于对应任务的计划时间。</p>
            <p>“交易日”是当前列表数据覆盖到的最近交易日期。页面展示数据库中已经完成同步的数据，具体数值仍以对应官方来源为准。</p>
          </div>
        </div>
      </div>
    </div>
  );
}
