import { getFundDetailUrl } from "@/lib/fund-links";
import type { FundSortKey, SortDirection } from "@/lib/fund-list";
import type { FundComparisonRow } from "@/lib/types";

interface FundListProps {
  funds: FundComparisonRow[];
  selected: string[];
  onToggle: (code: string) => void;
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
  sortKey,
  sortDirection,
  onSort,
}: FundTableProps) {
  return (
    <div className="table-wrap">
      <table className="fund-table">
        <thead>
          <tr>
            <th className="select-column"><span className="sr-only">选择</span></th>
            <th className="code-column" aria-sort={sortKey === "code" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="基金代码" sortKey="code" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="fund-column">基金份额</th>
            <th>交易与净值</th>
            <th className="fee-column" aria-sort={sortKey === "expenseRate" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="运作费率" sortKey="expenseRate" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th className="scale-column" aria-sort={sortKey === "scale" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="基金规模" sortKey="scale" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th aria-sort={sortKey === "return1m" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="近1月" sortKey="return1m" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th aria-sort={sortKey === "return3m" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="近3月" sortKey="return3m" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th aria-sort={sortKey === "return6m" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="近6月" sortKey="return6m" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th aria-sort={sortKey === "returnYtd" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="今年来" sortKey="returnYtd" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
            <th aria-sort={sortKey === "return1y" ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
              <SortableHeader label="近1年" sortKey="return1y" activeKey={sortKey} direction={sortDirection} onSort={onSort} />
            </th>
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
                </td>
                <td className="fund-cell">
                  <div className="fund-name-row">
                    <strong>{fund.displayName}</strong>
                  </div>
                  <span className="fund-company">{fund.fundCompany}</span>
                  <div className="tags"><span>{fund.productStructure}</span>{fund.investmentScope.map((item) => <span key={item}>{item}</span>)}{fund.exchange && <span>{fund.exchange}</span>}</div>
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
                  {fund.estimatedDeviation !== null && <em className={fund.estimatedDeviation >= 0 ? "warn" : "negative"}>偏离 {formatPercent(fund.estimatedDeviation)}</em>}
                </td>
                <td className="fee-cell">
                  <strong>{fund.expenseRate === null ? "—" : `${fund.expenseRate.toFixed(2)}%`}</strong>
                  <small>管理 {formatFee(fund.managementFee)}</small>
                  <small>托管 {formatFee(fund.custodyFee)}</small>
                  {fund.salesServiceFee !== null && <small>销售服务 {formatFee(fund.salesServiceFee)}</small>}
                </td>
                <td className="scale-cell">
                  <strong>{fund.scaleBillionCny?.toFixed(2) ?? "—"}</strong>
                  <small>亿元</small>
                </td>
                <td><ReturnValue value={getReturn(fund, "1月")} /></td>
                <td><ReturnValue value={getReturn(fund, "3月")} /></td>
                <td><ReturnValue value={getReturn(fund, "6月")} /></td>
                <td><ReturnValue value={getReturn(fund, "今年来")} /></td>
                <td><ReturnValue value={getReturn(fund, "1年")} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function FundCards({ funds, selected, onToggle }: FundListProps) {
  return (
    <div className="fund-cards">
      {funds.map((fund) => {
        const isSelected = selected.includes(fund.code);
        const detailUrl = getFundDetailUrl(fund);
        return (
          <article className={`fund-card ${isSelected ? "selected" : ""}`} key={fund.id}>
            <div className="card-head">
              <SelectBox checked={isSelected} disabled={!isSelected && selected.length >= 4} onChange={() => onToggle(fund.code)} label={`选择${fund.displayName}`} />
              <div>
                <strong>{fund.displayName}</strong>
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
              </div>
            </div>
            <div className="tags"><span>{fund.productStructure}</span>{fund.investmentScope.map((item) => <span key={item}>{item}</span>)}{fund.exchange && <span>{fund.exchange}</span>}</div>
            <div className="card-primary">
              <div><small>近1年收益</small><ReturnValue value={getReturn(fund, "1年")} /></div>
              <div><small>今年来</small><ReturnValue value={getReturn(fund, "今年来")} /></div>
              <div><small>运作费率</small><strong>{fund.expenseRate === null ? "—" : `${fund.expenseRate.toFixed(2)}%`}</strong></div>
            </div>
            <div className="card-details">
              <div><span>最新净值</span><strong>{formatNumber(fund.nav)}</strong></div>
              {fund.closePrice !== null && <div><span>收盘价</span><strong>{formatNumber(fund.closePrice, 3)}</strong></div>}
              <div><span>基金规模</span><strong>{fund.scaleBillionCny?.toFixed(2) ?? "—"} 亿</strong></div>
              <div><span>近1月</span><ReturnValue value={getReturn(fund, "1月")} /></div>
              <div><span>近3月</span><ReturnValue value={getReturn(fund, "3月")} /></div>
              <div><span>近6月</span><ReturnValue value={getReturn(fund, "6月")} /></div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
