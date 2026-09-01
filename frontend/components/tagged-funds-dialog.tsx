import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import {
  calculateSubscriptionLimitTotals,
  groupFundRowsByIndex,
} from "@/lib/fund-list";
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

function SubscriptionLimit({ fund }: { fund: FundComparisonRow }) {
  if (fund.tradingVenue !== "场外" || fund.subscriptionStatus === null) {
    return <span className="tagged-limit-muted">—</span>;
  }
  if (fund.subscriptionStatus === "suspended") {
    return <span className="subscription-tag suspended">暂停申购</span>;
  }
  if (fund.subscriptionStatus === "open") {
    return <span className="subscription-tag open">开放申购</span>;
  }
  const amount = fund.subscriptionLimitAmount;
  const unit = fund.subscriptionLimitCurrency === "美元" ? "美元" : "元";
  const label = amount === null
    ? "限额申购"
    : `限额${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(amount)}${unit}`;
  return <span className="subscription-tag limited">{label}</span>;
}

const amountFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

function RecurringTotal({ funds }: { funds: FundComparisonRow[] }) {
  const { cny, usd } = calculateSubscriptionLimitTotals(funds);
  if (cny === 0 && usd === 0) {
    return <span className="tagged-recurring-total muted">总定投金额暂无</span>;
  }
  return (
    <strong className="tagged-recurring-total">
      总定投{cny > 0 ? `${amountFormatter.format(cny)}元` : ""}
      {usd > 0 ? `${amountFormatter.format(usd)}美元` : ""}
    </strong>
  );
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
  const groups = groupFundRowsByIndex(funds);

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
                共有 <strong>{groups.length}</strong> 种基金、
                <strong>{funds.length}</strong> 个基金份额
              </p>
              <div className="tagged-funds-groups">
                {groups.map((group) => (
                  <section className="tagged-funds-group" key={group.indexId}>
                    <header className="tagged-funds-group-header">
                      <div>
                        <h3>{indexNames[group.indexId] ?? group.indexId}</h3>
                        <span>{group.funds.length} 个基金份额</span>
                        {tag === "recurring" ? <RecurringTotal funds={group.funds} /> : null}
                      </div>
                    </header>
                    <div className="tagged-funds-table-wrap">
                      <table className="tagged-funds-table">
                        <thead>
                          <tr>
                            <th>基金代码</th>
                            <th>基金份额</th>
                            <th>类型</th>
                            <th>币种</th>
                            <th>申购限额</th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.funds.map((fund) => {
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
                                <td>
                                  {fund.tradingVenue}
                                  {fund.exchange ? <small>{fund.exchange}</small> : null}
                                </td>
                                <td>{fund.currency}</td>
                                <td><SubscriptionLimit fund={fund} /></td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </section>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
