import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { createPortal } from "react-dom";

import { getFundDetailUrl } from "@/lib/fund-links";
import type { FundSortKey, SortDirection } from "@/lib/fund-list";
import type { FundComparisonRow, FundTag } from "@/lib/types";
import { CloseIcon } from "./icons";

interface FundListProps {
  funds: FundComparisonRow[];
  selected: string[];
  onToggle: (code: string) => void;
  onTagsSave: (code: string, tags: FundTag[]) => Promise<boolean>;
  tagSavingCodes: string[];
  onOpenShareClassHelp: () => void;
}

interface FundTableProps extends FundListProps {
  sortKey: FundSortKey | null;
  sortDirection: SortDirection;
  onSort: (key: FundSortKey) => void;
}

function formatPercent(value: number | null, digits = 2) {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function formatNumber(value: number | null, digits = 4) {
  return value === null ? "—" : value.toFixed(digits);
}

function formatFee(value: number | null) {
  return value === null ? "—" : value.toFixed(2);
}

function getReturn(fund: FundComparisonRow, period: string) {
  return fund.returns.find((item) => item.period === period)?.value ?? null;
}

function ReturnValue({ value }: { value: number | null }) {
  return <span className={value === null ? "muted" : value >= 0 ? "positive" : "negative"}>{formatPercent(value)}</span>;
}

function SubscriptionTag({ fund }: { fund: FundComparisonRow }) {
  if (fund.tradingVenue !== "场外" || fund.subscriptionStatus === null) return null;
  if (fund.subscriptionStatus === "suspended") {
    return <span className="subscription-tag suspended">暂停申购</span>;
  }
  if (fund.subscriptionStatus === "limited") {
    const amount = fund.subscriptionLimitAmount;
    const unit = fund.subscriptionLimitCurrency === "美元" ? "美元" : "元";
    const label = amount === null
      ? "限额申购"
      : `限额${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(amount)}${unit}`;
    return <span className="subscription-tag limited">{label}</span>;
  }
  return <span className="subscription-tag open">开放申购</span>;
}

const USER_TAGS: Array<{ value: FundTag; label: string }> = [
  { value: "favorite", label: "收藏" },
  { value: "holding", label: "持有" },
  { value: "recurring", label: "定投" },
];

function FundUserTags({ fund }: { fund: FundComparisonRow }) {
  const tags = USER_TAGS.filter((tag) => fund.tags.includes(tag.value));
  if (tags.length === 0) return null;

  return (
    <div className="user-tag-list" aria-label="基金标签">
      {tags.map((tag) => (
        <span key={tag.value} className={`user-tag ${tag.value}`}>{tag.label}</span>
      ))}
    </div>
  );
}

function FundEditButton({
  fund,
  saving,
  onClick,
}: {
  fund: FundComparisonRow;
  saving: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="fund-edit-button"
      type="button"
      disabled={saving}
      onClick={onClick}
      aria-label={`编辑${fund.displayName}`}
    >
      {saving ? "保存中" : "编辑"}
    </button>
  );
}

function FundEditDialog({
  fund,
  saving,
  onSave,
  onClose,
}: {
  fund: FundComparisonRow;
  saving: boolean;
  onSave: (code: string, tags: FundTag[]) => Promise<boolean>;
  onClose: () => void;
}) {
  const [draftTags, setDraftTags] = useState<FundTag[]>(fund.tags);
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

  function toggleDraftTag(tag: FundTag) {
    setDraftTags((current) => (
      current.includes(tag)
        ? current.filter((item) => item !== tag)
        : USER_TAGS.map((item) => item.value).filter((item) => item === tag || current.includes(item))
    ));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    if (await onSave(fund.code, draftTags)) onClose();
  }

  return createPortal(
    <div
      className="comparison-overlay fund-edit-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="fund-edit-title"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <div className="fund-edit-sheet">
        <header className="comparison-header">
          <div>
            <span className="section-kicker">基金操作</span>
            <h2 id="fund-edit-title">编辑基金</h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            type="button"
            disabled={saving}
            onClick={onClose}
            aria-label="关闭编辑弹窗"
          >
            <CloseIcon />
          </button>
        </header>

        <form className="fund-edit-form" onSubmit={submit}>
          <label className="fund-edit-field">
            <span className="fund-edit-label">代码</span>
            <input type="text" value={fund.code} readOnly />
          </label>
          <label className="fund-edit-field">
            <span className="fund-edit-label">份额</span>
            <input type="text" value={fund.displayName} readOnly />
          </label>
          <div className="fund-edit-field">
            <span className="fund-edit-label">标签</span>
            <div className="fund-edit-tag-control">
              {USER_TAGS.map((tag) => (
                <label key={tag.value} className="fund-edit-tag-option">
                <input
                  type="checkbox"
                  checked={draftTags.includes(tag.value)}
                  disabled={saving}
                  onChange={() => toggleDraftTag(tag.value)}
                />
                  <span>{tag.label}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="fund-edit-actions">
            <button className="fund-edit-cancel" type="button" disabled={saving} onClick={onClose}>取消</button>
            <button className="fund-edit-save" type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}

function SelectBox({ checked, disabled, onChange, label }: { checked: boolean; disabled: boolean; onChange: () => void; label: string }) {
  return (
    <label className={`select-box ${disabled ? "disabled" : ""}`} title={disabled ? "最多选择4个份额" : undefined}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={onChange} aria-label={label} />
      <span>{checked ? "✓" : ""}</span>
    </label>
  );
}

function SortableHeader({
  label,
  sortKey,
  activeKey,
  direction,
  onSort,
}: {
  label: string;
  sortKey: FundSortKey;
  activeKey: FundSortKey | null;
  direction: SortDirection;
  onSort: (key: FundSortKey) => void;
}) {
  const active = activeKey === sortKey;
  const nextDirection = active && direction === "asc" ? "倒序" : "正序";

  return (
    <button
      className="sortable-header"
      type="button"
      onClick={() => onSort(sortKey)}
      aria-label={`${label}按${nextDirection}排列`}
    >
      <span>{label}</span>
      <span className={`sort-arrows ${active ? direction : ""}`} aria-hidden="true">
        <i className="sort-up" />
        <i className="sort-down" />
      </span>
    </button>
  );
}

export function FundTable({
  funds,
  selected,
  onToggle,
  onTagsSave,
  tagSavingCodes,
  sortKey,
  sortDirection,
  onSort,
  onOpenShareClassHelp,
}: FundTableProps) {
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const closeEditor = useCallback(() => setEditingCode(null), []);
  const editingFund = funds.find((fund) => fund.code === editingCode) ?? null;

  return (
    <>
      <div className="table-wrap">
      <table className="fund-table">
        <thead>
          <tr>
            <th className="select-column"><span className="sr-only">选择</span></th>
            <th className="code-column" aria-sort={sortKey === "code" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="基金代码" sortKey="code" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="fund-column" aria-sort={sortKey === "name" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <div className="fund-column-header">
                <SortableHeader label="基金份额" sortKey="name" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
                {funds.some((fund) => fund.tradingVenue === "场外") && (
                  <button
                    className="context-help-button"
                    type="button"
                    aria-label="查看基金份额说明"
                    title="查看基金份额说明"
                    onClick={onOpenShareClassHelp}
                  >
                    ?
                  </button>
                )}
              </div>
            </th>
            <th className="price-column">交易与净值</th>
            <th className="fee-column" aria-sort={sortKey === "expenseRate" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="运作费率" sortKey="expenseRate" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="scale-column" aria-sort={sortKey === "scale" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="规模" sortKey="scale" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="return-column" aria-sort={sortKey === "return1m" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="近1月" sortKey="return1m" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="return-column" aria-sort={sortKey === "return3m" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="近3月" sortKey="return3m" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="return-column" aria-sort={sortKey === "return6m" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="近6月" sortKey="return6m" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="return-column" aria-sort={sortKey === "returnYtd" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="今年来" sortKey="returnYtd" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="return-column" aria-sort={sortKey === "return1y" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="近1年" sortKey="return1y" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="action-column">操作</th>
          </tr>
        </thead>
        <tbody>
          {funds.map((fund) => {
            const isSelected = selected.includes(fund.code);
            const detailUrl = getFundDetailUrl(fund);
            return (
              <tr key={fund.id} className={isSelected ? "selected" : ""}>
                <td className="select-column">
                  <SelectBox checked={isSelected} disabled={!isSelected && selected.length >= 4} onChange={() => onToggle(fund.code)} label={`选择${fund.displayName}`} />
                </td>
                <td className="code-column">
                  <div className="fund-code-stack">
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
                    ) : <span>{fund.code}</span>}
                  </div>
                </td>
                <td className="fund-cell">
                  <div className="fund-name-row">
                    <strong>{fund.displayName}</strong>
                  </div>
                  <span className="fund-company">{fund.fundCompany}</span>
                  <FundUserTags fund={fund} />
                </td>
                <td className="price-cell">
                  {fund.closePrice !== null && (
                    <div>
                      <span>收盘</span>
                      <div className="price-value">
                        <strong>{formatNumber(fund.closePrice, 3)}</strong>
                      </div>
                    </div>
                  )}
                  <div>
                    <span>净值</span>
                    <div className="price-value">
                      <strong>{formatNumber(fund.nav)}</strong>
                    </div>
                  </div>
                  <SubscriptionTag fund={fund} />
                  {fund.estimatedDeviation !== null && <em className={fund.estimatedDeviation >= 0 ? "warn" : "negative"}>偏离 {formatPercent(fund.estimatedDeviation)}</em>}
                </td>
                <td className="fee-cell">
                  <strong>{fund.expenseRate === null ? "—" : `${fund.expenseRate.toFixed(2)}%`}</strong>
                  <small>管理 {formatFee(fund.managementFee)}</small>
                  <small>托管 {formatFee(fund.custodyFee)}</small>
                  {fund.salesServiceFee !== null && fund.salesServiceFee > 0 && (
                    <small>销售服务 {formatFee(fund.salesServiceFee)}</small>
                  )}
                </td>
                <td className="scale-cell">
                  <strong>{fund.scaleBillionCny?.toFixed(2) ?? "—"}</strong>
                  <small>亿元</small>
                </td>
                <td className="return-column"><ReturnValue value={getReturn(fund, "1月")} /></td>
                <td className="return-column"><ReturnValue value={getReturn(fund, "3月")} /></td>
                <td className="return-column"><ReturnValue value={getReturn(fund, "6月")} /></td>
                <td className="return-column"><ReturnValue value={getReturn(fund, "今年来")} /></td>
                <td className="return-column"><ReturnValue value={getReturn(fund, "1年")} /></td>
                <td className="action-cell">
                  <FundEditButton
                    fund={fund}
                    saving={tagSavingCodes.includes(fund.code)}
                    onClick={() => setEditingCode(fund.code)}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      {editingFund && (
        <FundEditDialog
          fund={editingFund}
          saving={tagSavingCodes.includes(editingFund.code)}
          onSave={onTagsSave}
          onClose={closeEditor}
        />
      )}
    </>
  );
}

export function FundCards({
  funds,
  selected,
  onToggle,
  onTagsSave,
  tagSavingCodes,
  onOpenShareClassHelp,
}: FundListProps) {
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const closeEditor = useCallback(() => setEditingCode(null), []);
  const editingFund = funds.find((fund) => fund.code === editingCode) ?? null;

  return (
    <>
      <div className="fund-cards">
      {funds.map((fund) => {
        const isSelected = selected.includes(fund.code);
        const detailUrl = getFundDetailUrl(fund);
        return (
          <article className={`fund-card ${isSelected ? "selected" : ""}`} key={fund.id}>
            <div className="card-head">
              <SelectBox checked={isSelected} disabled={!isSelected && selected.length >= 4} onChange={() => onToggle(fund.code)} label={`选择${fund.displayName}`} />
              <div>
                <div className="card-fund-name-row">
                  <strong>{fund.displayName}</strong>
                  {fund.tradingVenue === "场外" && (
                    <button
                      className="context-help-button"
                      type="button"
                      aria-label="查看基金份额说明"
                      title="查看基金份额说明"
                      onClick={onOpenShareClassHelp}
                    >
                      ?
                    </button>
                  )}
                </div>
                <span>
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
                  ) : fund.code}
                  {" · "}{fund.fundCompany}
                </span>
                <FundUserTags fund={fund} />
                <FundEditButton
                  fund={fund}
                  saving={tagSavingCodes.includes(fund.code)}
                  onClick={() => setEditingCode(fund.code)}
                />
              </div>
            </div>
            <div className="card-primary">
              <div><small>近1年收益</small><ReturnValue value={getReturn(fund, "1年")} /></div>
              <div><small>今年来</small><ReturnValue value={getReturn(fund, "今年来")} /></div>
              <div><small>运作费率</small><strong>{fund.expenseRate === null ? "—" : `${fund.expenseRate.toFixed(2)}%`}</strong></div>
            </div>
            <div className="card-details">
              <div>
                <span>最新净值</span>
                <div className="card-nav-value">
                  <strong>{formatNumber(fund.nav)}</strong>
                  <SubscriptionTag fund={fund} />
                </div>
              </div>
              {fund.closePrice !== null && <div><span>收盘价</span><strong>{formatNumber(fund.closePrice, 3)}</strong></div>}
              <div><span>规模</span><strong>{fund.scaleBillionCny?.toFixed(2) ?? "—"} 亿</strong></div>
              <div><span>近1月</span><ReturnValue value={getReturn(fund, "1月")} /></div>
              <div><span>近3月</span><ReturnValue value={getReturn(fund, "3月")} /></div>
              <div><span>近6月</span><ReturnValue value={getReturn(fund, "6月")} /></div>
            </div>
          </article>
        );
      })}
      </div>
      {editingFund && (
        <FundEditDialog
          fund={editingFund}
          saving={tagSavingCodes.includes(editingFund.code)}
          onSave={onTagsSave}
          onClose={closeEditor}
        />
      )}
    </>
  );
}
