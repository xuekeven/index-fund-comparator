import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { getFundDetailUrl } from "@/lib/fund-links";
import type { FundComparisonRow, FundTag } from "@/lib/types";
import { FUND_TAG_META } from "./fund-tag-meta";
import { CloseIcon } from "./icons";

interface TaggedFundsDialogProps {
  tag: FundTag;
  funds: FundComparisonRow[];
  indexNames: Record<string, string>;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onRetry: () => void;
}

export function TaggedFundsDialog({
  tag,
  funds,
  indexNames,
  loading,
  error,
  onClose,
  onRetry,
}: TaggedFundsDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const meta = FUND_TAG_META[tag];

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

  return createPortal(
    <div
      className="comparison-overlay tagged-funds-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tagged-funds-title"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="tagged-funds-sheet">
        <header className="comparison-header">
          <div>
            <span className="section-kicker">我的基金</span>
            <h2 id="tagged-funds-title">{meta.title}</h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label={`关闭${meta.title}`}
          >
            <CloseIcon />
          </button>
        </header>

        <div className="tagged-funds-content">
          {loading ? (
            <div className="tagged-funds-state">
              <span className="spinner" />
              <p>正在加载…</p>
            </div>
          ) : error ? (
            <div className="tagged-funds-state">
              <strong>加载失败</strong>
              <p>{error}</p>
              <button type="button" onClick={onRetry}>重新加载</button>
            </div>
          ) : funds.length === 0 ? (
            <div className="tagged-funds-state">
              <strong>暂无{meta.label}基金</strong>
              <p>在基金列表的“编辑”中添加“{meta.label}”标签后，会显示在这里。</p>
            </div>
          ) : (
            <>
              <p className="tagged-funds-summary">
                共有 <strong>{funds.length}</strong> 个基金份额
              </p>
              <div className="tagged-funds-table-wrap">
                <table className="tagged-funds-table">
                  <thead>
                    <tr>
                      <th>基金代码</th>
                      <th>基金份额</th>
                      <th>跟踪指数</th>
                      <th>类型</th>
                      <th>币种</th>
                    </tr>
                  </thead>
                  <tbody>
                    {funds.map((fund) => {
                      const detailUrl = getFundDetailUrl(fund);
                      return (
                        <tr key={fund.id}>
                          <td>
                            {detailUrl ? (
                              <a
                                className="fund-code-link"
                                href={detailUrl}
                                target="_blank"
                                rel="noreferrer"
                                title={`查看${fund.displayName}官方详情`}
                              >
                                {fund.code}
                              </a>
                            ) : <span className="tagged-fund-code">{fund.code}</span>}
                          </td>
                          <td>
                            <strong>{fund.displayName}</strong>
                            <small>{fund.fundCompany}</small>
                          </td>
                          <td>{indexNames[fund.indexId] ?? fund.indexId}</td>
                          <td>
                            {fund.tradingVenue}
                            {fund.exchange ? <small>{fund.exchange}</small> : null}
                          </td>
                          <td>{fund.currency}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
