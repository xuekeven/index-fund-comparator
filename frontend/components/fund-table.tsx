import type { FundComparisonRow } from "@/lib/types";
import { ExternalIcon } from "./icons";

interface FundListProps {
  funds: FundComparisonRow[];
  selected: string[];
  onToggle: (code: string) => void;
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

function dateLabel(value: string | null) {
  if (!value) return "暂无日期";
  return value.slice(5).replace("-", "/");
}

function getFundDetailUrl(fund: FundComparisonRow) {
  if (fund.exchange === "上交所") {
    return `https://etf.sse.com.cn/fundlist/funddetail/index.shtml?code=${encodeURIComponent(fund.code)}`;
  }
  if (fund.exchange === "深交所") {
    const params = new URLSearchParams({ stock: fund.code, name: fund.displayName });
    return `https://www.szse.cn/disclosure/fund/etf/index.html?${params.toString()}`;
  }
  return fund.sourceUrl;
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

export function FundTable({ funds, selected, onToggle }: FundListProps) {
  return (
    <div className="table-wrap">
      <table className="fund-table">
        <thead>
          <tr>
            <th className="select-column"><span className="sr-only">选择</span></th>
            <th className="code-column">基金代码</th>
            <th>基金份额</th>
            <th>交易与净值</th>
            <th>运作费率</th>
            <th>近1月</th>
            <th>今年以来</th>
            <th>近1年</th>
            <th>跟踪误差<br /><small>近1年</small></th>
            <th>基金规模<br /><small>亿元</small></th>
            <th><span className="sr-only">基金详情</span></th>
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
                <td className="code-column"><span>{fund.code}</span></td>
                <td className="fund-cell">
                  <div className="fund-name-row">
                    <strong>{fund.displayName}</strong>
                    {fund.shareClass && <span className="share-badge">{fund.shareClass}</span>}
                  </div>
                  <span className="fund-company">{fund.fundCompany}</span>
                  <div className="tags"><span>{fund.productStructure}</span>{fund.investmentScope.map((item) => <span key={item}>{item}</span>)}{fund.exchange && <span>{fund.exchange}</span>}</div>
                </td>
                <td className="price-cell">
                  {fund.closePrice !== null && <div><span>收盘</span><strong>{formatNumber(fund.closePrice, 3)}</strong><small>{dateLabel(fund.closeDate)}</small></div>}
                  <div><span>净值</span><strong>{formatNumber(fund.nav)}</strong><small>{dateLabel(fund.navDate)}</small></div>
                  {fund.estimatedDeviation !== null && <em className={fund.estimatedDeviation >= 0 ? "warn" : "negative"}>估算偏离 {formatPercent(fund.estimatedDeviation)}</em>}
                </td>
                <td className="fee-cell">
                  <strong>{fund.expenseRate === null ? "—" : `${fund.expenseRate.toFixed(2)}%`}</strong>
                  <small>管理 {formatFee(fund.managementFee)} · 托管 {formatFee(fund.custodyFee)}</small>
                  {fund.salesServiceFee !== null && <small>销售服务 {formatFee(fund.salesServiceFee)}</small>}
                </td>
                <td><ReturnValue value={getReturn(fund, "1月")} /></td>
                <td><ReturnValue value={getReturn(fund, "年初至今")} /></td>
                <td><ReturnValue value={getReturn(fund, "1年")} /></td>
                <td>{fund.trackingError1y === null ? <span className="pending-value">待核验</span> : <span>{fund.trackingError1y.toFixed(2)}%</span>}</td>
                <td className="scale-cell"><strong>{fund.scaleBillionCny?.toFixed(2) ?? "—"}</strong><small>{dateLabel(fund.scaleDate)}</small></td>
                <td>
                  {detailUrl && <a className="source-link" href={detailUrl} target="_blank" rel="noreferrer" title={`查看${fund.displayName}官方详情`} aria-label={`查看${fund.displayName}官方详情`}><ExternalIcon /></a>}
                </td>
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
              <div><strong>{fund.displayName}</strong><span>{fund.code} · {fund.fundCompany}</span></div>
              {detailUrl && <a className="source-link" href={detailUrl} target="_blank" rel="noreferrer" aria-label={`查看${fund.displayName}官方详情`}><ExternalIcon /></a>}
            </div>
            <div className="tags"><span>{fund.productStructure}</span>{fund.investmentScope.map((item) => <span key={item}>{item}</span>)}{fund.exchange && <span>{fund.exchange}</span>}</div>
            <div className="card-primary">
              <div><small>近1年收益</small><ReturnValue value={getReturn(fund, "1年")} /></div>
              <div><small>今年以来</small><ReturnValue value={getReturn(fund, "年初至今")} /></div>
              <div><small>运作费率</small><strong>{fund.expenseRate === null ? "—" : `${fund.expenseRate.toFixed(2)}%`}</strong></div>
            </div>
            <div className="card-details">
              <div><span>最新净值 <small>{dateLabel(fund.navDate)}</small></span><strong>{formatNumber(fund.nav)}</strong></div>
              {fund.closePrice !== null && <div><span>收盘价 <small>{dateLabel(fund.closeDate)}</small></span><strong>{formatNumber(fund.closePrice, 3)}</strong></div>}
              <div><span>基金规模 <small>{dateLabel(fund.scaleDate)}</small></span><strong>{fund.scaleBillionCny?.toFixed(2) ?? "—"} 亿</strong></div>
              <div><span>近1年跟踪误差</span><strong>{fund.trackingError1y === null ? "待核验" : `${fund.trackingError1y.toFixed(2)}%`}</strong></div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
