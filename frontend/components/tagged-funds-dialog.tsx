import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { groupFundRowsByIndex } from "@/lib/fund-list";
import { getFundDetailUrl } from "@/lib/fund-links";
import {
  calculateRecurringInvestmentTotals,
  formatFundTagLabel,
} from "@/lib/fund-tag-values";
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
  onAmountsSave: (
    tag: "holding" | "recurring",
    updates: Array<{ fundCode: string; amount: number | null }>,
  ) => Promise<boolean>;
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
  const unit = fund.subscriptionLimitCurrency === "美元" ? "美元" : "人民币";
  const label = amount === null
    ? "限额申购"
    : `限额${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(amount)}${unit}`;
  return <span className="subscription-tag limited">{label}</span>;
}

const amountFormatter = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 6 });

function RecurringTotal({
  funds,
  prefix = "总定投",
}: {
  funds: FundComparisonRow[];
  prefix?: string;
}) {
  const { cny, usd, hasCny, hasUsd } = calculateRecurringInvestmentTotals(funds);
  if (!hasCny && !hasUsd) {
    return <span className="tagged-recurring-total muted">{prefix}金额暂无</span>;
  }
  return (
    <span className="tagged-recurring-total">
      {prefix}
      {hasCny ? <> <strong>{amountFormatter.format(cny)}</strong> 人民币</> : null}
      {hasUsd ? <> <strong>{amountFormatter.format(usd)}</strong> 美元</> : null}
    </span>
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
  onAmountsSave,
}: TaggedFundsDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const meta = FUND_TAG_META[tag];
  const groups = groupFundRowsByIndex(funds);
  const [editingAmounts, setEditingAmounts] = useState(false);
  const [savingAmounts, setSavingAmounts] = useState(false);
  const [draftAmounts, setDraftAmounts] = useState<Record<string, string>>({});
  const [amountError, setAmountError] = useState<string | null>(null);

  function beginAmountEditing() {
    if (tag === "favorite") return;
    setDraftAmounts(Object.fromEntries(funds.map((fund) => {
      const amount = tag === "holding" ? fund.holdingAmount : fund.recurringAmount;
      return [fund.code, amount === null ? "" : String(amount)];
    })));
    setAmountError(null);
    setEditingAmounts(true);
  }

  async function saveAmounts() {
    if (tag === "favorite" || savingAmounts) return;
    const updates = funds.flatMap((fund) => {
      const draft = draftAmounts[fund.code] ?? "";
      const amount = draft.trim() === "" ? null : Number(draft);
      const previous = tag === "holding" ? fund.holdingAmount : fund.recurringAmount;
      return amount === previous ? [] : [{ fundCode: fund.code, amount }];
    });
    if (updates.some(({ amount }) => amount !== null && (!Number.isFinite(amount) || amount < 0))) {
      setAmountError("请输入 0 或大于 0 的数字，也可以留空。");
      return;
    }
    if (updates.length === 0) {
      setEditingAmounts(false);
      return;
    }
    setSavingAmounts(true);
    setAmountError(null);
    const saved = await onAmountsSave(tag, updates);
    setSavingAmounts(false);
    if (saved) {
      setEditingAmounts(false);
    } else {
      setAmountError("部分数据保存失败，请检查后重试。");
    }
  }

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
            <span className="section-kicker">指数基金</span>
            <h2 id="tagged-funds-title">{meta.title}</h2>
          </div>
          <div className="tagged-header-actions">
            {tag !== "favorite" && !editingAmounts ? (
              <button className="tagged-edit-button" type="button" onClick={beginAmountEditing}>
                编辑
              </button>
            ) : null}
            {tag !== "favorite" && editingAmounts ? (
              <>
                <button
                  className="tagged-edit-button secondary"
                  type="button"
                  disabled={savingAmounts}
                  onClick={() => setEditingAmounts(false)}
                >
                  取消
                </button>
                <button
                  className="tagged-edit-button primary"
                  type="button"
                  disabled={savingAmounts}
                  onClick={() => void saveAmounts()}
                >
                  {savingAmounts ? "保存中…" : "保存"}
                </button>
              </>
            ) : null}
            <button
              ref={closeButtonRef}
              className="icon-button"
              type="button"
              disabled={savingAmounts}
              onClick={onClose}
              aria-label={`关闭${meta.title}`}
            >
              <CloseIcon />
            </button>
          </div>
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
                {tag === "recurring" ? (
                  <>，<RecurringTotal funds={funds} prefix="合计定投" /></>
                ) : null}
              </p>
              {amountError ? <p className="tagged-amount-error">{amountError}</p> : null}
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
                      <table className={`tagged-funds-table ${tag === "favorite" ? "" : "has-tag-value-column"}`}>
                        <thead>
                          <tr>
                            <th className="tagged-code-column">基金代码</th>
                            <th className="tagged-name-column">基金份额</th>
                            <th className="tagged-type-column">类型</th>
                            <th className="tagged-currency-column">币种</th>
                            {tag !== "favorite" ? (
                              <th className="tagged-value-column">{meta.label}</th>
                            ) : null}
                            <th className="tagged-limit-column">申购限额</th>
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
                                {tag !== "favorite" ? (
                                  <td className="tagged-value-cell">
                                    {editingAmounts ? (
                                      <label className="tagged-amount-editor">
                                        <input
                                          type="number"
                                          min="0"
                                          step="any"
                                          inputMode="decimal"
                                          value={draftAmounts[fund.code] ?? ""}
                                          disabled={savingAmounts}
                                          aria-label={`${fund.displayName}${meta.label}${tag === "holding" ? "份额" : "金额"}`}
                                          onChange={(event) => setDraftAmounts((current) => ({
                                            ...current,
                                            [fund.code]: event.target.value,
                                          }))}
                                        />
                                        <span>{tag === "holding" ? "份额" : fund.currency}</span>
                                      </label>
                                    ) : (
                                      <span className={`user-tag tagged-user-tag ${tag}`}>
                                        {formatFundTagLabel(fund, tag)}
                                      </span>
                                    )}
                                  </td>
                                ) : null}
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
