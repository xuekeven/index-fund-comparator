import { useEffect } from "react";
import type { ReactNode } from "react";

import { getFundDetailUrl } from "@/lib/fund-links";
import type { FundComparisonRow } from "@/lib/types";
import { CloseIcon, ExternalIcon, InfoIcon } from "./icons";

interface ComparisonViewProps {
  funds: FundComparisonRow[];
  warnings: string[];
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onRetry: () => void;
}

function formatPercent(value: number | null, signed = false) {
  if (value === null) return "—";
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatNumber(value: number | null, digits = 4) {
  return value === null ? "—" : value.toFixed(digits);
}

function formatDate(value: string | null) {
  return value ?? "暂无日期";
}

function getReturn(fund: FundComparisonRow, period: string) {
  return fund.returns.find((item) => item.period === period)?.value ?? null;
}

function Value({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return <span className={muted ? "comparison-muted" : undefined}>{children}</span>;
}

function returnClass(value: number | null) {
  if (value === null) return "comparison-muted";
  return value >= 0 ? "positive" : "negative";
}

export function ComparisonView({
  funds,
  warnings,
  loading,
  error,
  onClose,
  onRetry,
}: ComparisonViewProps) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="comparison-overlay" role="dialog" aria-modal="true" aria-labelledby="comparison-title">
      <div className="comparison-sheet">
        <header className="comparison-header">
          <div>
            <span className="section-kicker">并排对照</span>
            <h2 id="comparison-title">基金比较</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭比较">
            <CloseIcon />
          </button>
        </header>

        {warnings.length > 0 && (
          <div className="comparison-warning">
            <InfoIcon />
            <span>{warnings.join("；")}</span>
          </div>
        )}

        {loading ? (
          <div className="comparison-state">
            <span className="spinner" />
            <p>正在生成比较结果…</p>
          </div>
        ) : error ? (
          <div className="comparison-state error-state">
            <strong>比较结果加载失败</strong>
            <p>{error}</p>
            <button type="button" onClick={onRetry}>重新加载</button>
          </div>
        ) : (
          <div className="comparison-scroll">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>比较指标</th>
                  {funds.map((fund) => {
                    const detailUrl = getFundDetailUrl(fund);
                    return (
                      <th key={fund.id}>
                        <div className="comparison-fund-head">
                          <strong>{fund.displayName}</strong>
                          <span>{fund.code} · {fund.fundCompany}</span>
                          <small>{fund.productStructure} · {fund.tradingVenue}{fund.exchange ? ` · ${fund.exchange}` : ""}</small>
                          {detailUrl && (
                            <a href={detailUrl} target="_blank" rel="noreferrer">
                              官方详情 <ExternalIcon />
                            </a>
                          )}
                        </div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>精确跟踪基准</th>
                  {funds.map((fund) => <td key={fund.id}>{fund.exactBenchmark}</td>)}
                </tr>
                <tr>
                  <th>投资范围</th>
                  {funds.map((fund) => <td key={fund.id}>{fund.investmentScope.join("、") || "—"}</td>)}
                </tr>
                <tr>
                  <th>收盘价</th>
                  {funds.map((fund) => (
                    <td key={fund.id}>
                      <Value>{formatNumber(fund.closePrice, 3)}</Value>
                      <small>{formatDate(fund.closeDate)}</small>
                    </td>
                  ))}
                </tr>
                <tr>
                  <th>单位净值</th>
                  {funds.map((fund) => (
                    <td key={fund.id}>
                      <Value>{formatNumber(fund.nav)}</Value>
                      <small>{formatDate(fund.navDate)}</small>
                    </td>
                  ))}
                </tr>
                <tr>
                  <th>同日估算偏离</th>
                  {funds.map((fund) => (
                    <td key={fund.id}>
                      <Value muted={fund.estimatedDeviation === null}>{formatPercent(fund.estimatedDeviation, true)}</Value>
                    </td>
                  ))}
                </tr>
                <tr>
                  <th>运作费率</th>
                  {funds.map((fund) => (
                    <td key={fund.id}>
                      <Value>{formatPercent(fund.expenseRate)}</Value>
                      <small>管理 {formatPercent(fund.managementFee)} · 托管 {formatPercent(fund.custodyFee)}</small>
                    </td>
                  ))}
                </tr>
                <tr>
                  <th>销售服务费</th>
                  {funds.map((fund) => <td key={fund.id}>{formatPercent(fund.salesServiceFee)}</td>)}
                </tr>
                {[
                  ["近1月收益", "1月"],
                  ["今年以来收益", "年初至今"],
                  ["近1年收益", "1年"],
                ].map(([label, period]) => (
                  <tr key={period}>
                    <th>{label}</th>
                    {funds.map((fund) => (
                      <td key={fund.id} className={returnClass(getReturn(fund, period))}>
                        {formatPercent(getReturn(fund, period), true)}
                      </td>
                    ))}
                  </tr>
                ))}
                <tr>
                  <th>近1年跟踪误差</th>
                  {funds.map((fund) => <td key={fund.id}>{formatPercent(fund.trackingError1y)}</td>)}
                </tr>
                <tr>
                  <th>基金规模</th>
                  {funds.map((fund) => (
                    <td key={fund.id}>
                      <Value>{fund.scaleBillionCny === null ? "—" : `${fund.scaleBillionCny.toFixed(2)} 亿元`}</Value>
                      <small>{formatDate(fund.scaleDate)}</small>
                    </td>
                  ))}
                </tr>
                <tr>
                  <th>数据来源</th>
                  {funds.map((fund) => (
                    <td key={fund.id}>
                      <Value muted={!fund.sourceName}>{fund.sourceName ?? "来源名称待补齐"}</Value>
                      <small>{fund.sourceTime ? new Date(fund.sourceTime).toLocaleString("zh-CN", { hour12: false }) : "采集时间待补齐"}</small>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}

        <footer className="comparison-footer">
          <p>“—”表示当前数据源尚未提供。比较结果仅展示客观数据，不构成投资建议。</p>
          <button className="primary-button" type="button" onClick={onClose}>返回基金列表</button>
        </footer>
      </div>
    </div>
  );
}
