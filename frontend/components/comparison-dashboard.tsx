"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getFunds, getIndices } from "@/lib/api";
import type { FundComparisonRow, IndexSummary, TradingVenue } from "@/lib/types";
import { CloseIcon, InfoIcon, MarkIcon, RefreshIcon, SearchIcon } from "./icons";
import { FundCards, FundTable } from "./fund-table";

type VenueFilter = "全部" | TradingVenue;

const VENUES: VenueFilter[] = ["全部", "场内", "场外"];

type CachedFunds = {
  items: FundComparisonRow[];
  loadedAt: Date;
};

function formatUpdateTime(value: Date | null) {
  if (!value) return "尚未更新";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(value);
}

export function ComparisonDashboard() {
  const [indices, setIndices] = useState<IndexSummary[]>([]);
  const [activeIndex, setActiveIndex] = useState("csi-500");
  const [venue, setVenue] = useState<VenueFilter>("全部");
  const [funds, setFunds] = useState<FundComparisonRow[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const fundCache = useRef(new Map<string, CachedFunds>());

  const loadIndices = useCallback(async (signal?: AbortSignal) => {
    const items = await getIndices(signal);
    setIndices(items);
    if (items.length) {
      setActiveIndex((current) =>
        items.some((item) => item.id === current) ? current : items[0].id,
      );
    }
  }, []);

  const loadFunds = useCallback(async (signal?: AbortSignal, force = false) => {
    const cached = fundCache.current.get(activeIndex);
    if (cached && !force) {
      setFunds(cached.items);
      setUpdatedAt(cached.loadedAt);
      setError(null);
      setLoading(false);
      return;
    }

    setError(null);
    try {
      const response = await getFunds(activeIndex, undefined, signal);
      const loadedAt = new Date();
      fundCache.current.set(activeIndex, { items: response.items, loadedAt });
      setFunds(response.items);
      setUpdatedAt(loadedAt);
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setError("暂时无法连接数据服务，请稍后重试。");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [activeIndex]);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      loadIndices(controller.signal).catch((requestError) => {
        if (
          controller.signal.aborted ||
          (requestError instanceof DOMException && requestError.name === "AbortError")
        ) {
          return;
        }
        setError("指数列表加载失败，请稍后重试。");
        setLoading(false);
      });
    });
    return () => controller.abort();
  }, [loadIndices]);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => loadFunds(controller.signal));
    return () => controller.abort();
  }, [loadFunds]);

  const currentIndex = indices.find((item) => item.id === activeIndex);
  const visibleFunds = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return funds.filter((fund) => {
      if (venue !== "全部" && fund.tradingVenue !== venue) return false;
      if (!normalized) return true;
      return [fund.code, fund.displayName, fund.fundCompany].some((value) =>
        value.toLocaleLowerCase().includes(normalized),
      );
    });
  }, [funds, query, venue]);

  const selectedFunds = useMemo(
    () => funds.filter((fund) => selected.includes(fund.code)),
    [funds, selected],
  );

  function changeIndex(indexId: string) {
    if (indexId === activeIndex) return;
    const cached = fundCache.current.get(indexId);
    setLoading(!cached);
    if (cached) {
      setFunds(cached.items);
      setUpdatedAt(cached.loadedAt);
    }
    setActiveIndex(indexId);
    setVenue("全部");
    setSelected([]);
    setQuery("");
  }

  function changeVenue(nextVenue: VenueFilter) {
    setVenue(nextVenue);
  }

  function toggleFund(code: string) {
    setSelected((current) => {
      if (current.includes(code)) return current.filter((item) => item !== code);
      if (current.length >= 4) return current;
      return [...current, code];
    });
  }

  async function refresh() {
    setLoading(true);
    fundCache.current.delete(activeIndex);
    try {
      await Promise.all([loadIndices(), loadFunds(undefined, true)]);
    } catch {
      setError("刷新失败，请检查后端服务。");
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="同指数首页">
          <MarkIcon className="brand-mark" />
          <span>
            <strong>同指数</strong>
            <small>指数基金比较</small>
          </span>
        </a>
        <div className="topbar-actions">
          <button className="icon-button" type="button" onClick={refresh} aria-label="刷新数据">
            <RefreshIcon />
          </button>
        </div>
      </header>

      <main id="top">
        <section className="workspace page-width" aria-labelledby="workspace-title">
          <div className="workspace-head">
            <div>
              <span className="section-kicker">选择基准</span>
              <h2 id="workspace-title">比较同类基金</h2>
            </div>
            <div className="updated-at">
              <span className="status-dot" />
              更新时间 {formatUpdateTime(updatedAt)}
            </div>
          </div>

          <div className="index-tabs" role="tablist" aria-label="指数">
            {indices.map((index) => (
              <button
                key={index.id}
                className={`index-tab ${activeIndex === index.id ? "active" : ""}`}
                type="button"
                role="tab"
                aria-selected={activeIndex === index.id}
                onClick={() => changeIndex(index.id)}
              >
                <span>{index.shortName}</span>
                <small>{index.region} · {index.fundCount} 个份额</small>
              </button>
            ))}
          </div>

          {currentIndex && (
            <div className="benchmark-note">
              <InfoIcon />
              <div>
                <strong>当前比较口径</strong>
                <span>{currentIndex.exactBenchmark}</span>
              </div>
              {currentIndex.id !== "csi-500" && <b>精确基准待授权核验</b>}
            </div>
          )}

          <div className="toolbar">
            <div className="segment" aria-label="交易方式筛选">
              {VENUES.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={venue === item ? "active" : ""}
                  onClick={() => changeVenue(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            <label className="search-box">
              <SearchIcon />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索代码、名称或基金公司"
                aria-label="搜索基金"
              />
              {query && (
                <button type="button" onClick={() => setQuery("")} aria-label="清空搜索">
                  <CloseIcon />
                </button>
              )}
            </label>
          </div>

          {error ? (
            <div className="state-panel error-state">
              <strong>数据服务未连接</strong>
              <p>{error}</p>
              <button type="button" onClick={refresh}>重新连接</button>
            </div>
          ) : loading ? (
            <div className="state-panel loading-state">
              <span className="spinner" />
              <p>正在整理同类基金…</p>
            </div>
          ) : visibleFunds.length === 0 ? (
            <div className="state-panel">
              <strong>没有匹配的基金</strong>
              <p>试试切换交易方式，或清空搜索条件。</p>
            </div>
          ) : (
            <>
              <FundTable funds={visibleFunds} selected={selected} onToggle={toggleFund} />
              <FundCards funds={visibleFunds} selected={selected} onToggle={toggleFund} />
            </>
          )}

          <p className="table-footnote">
            估算偏离采用“收盘价 ÷ 最新可用净值 − 1”，QDII 净值日期可能滞后。
          </p>
        </section>
      </main>

      <footer className="footer page-width">
        <div className="brand footer-brand"><MarkIcon className="brand-mark" /><span><strong>同指数</strong><small>客观数据，不构成投资建议</small></span></div>
        <p>数据以来源页面及标注日期为准</p>
      </footer>

      {selected.length > 0 && (
        <aside className="selection-bar" aria-live="polite">
          <div className="selection-summary">
            <strong>已选 {selected.length}/4</strong>
            <span>{selectedFunds.map((fund) => fund.code).join(" · ")}</span>
          </div>
          <div className="selection-actions">
            <button className="ghost-button" type="button" onClick={() => setSelected([])}>清空</button>
            <button className="primary-button" type="button" disabled={selected.length < 2}>
              {selected.length < 2 ? "再选一个开始比较" : `比较 ${selected.length} 个份额`}
            </button>
          </div>
        </aside>
      )}
    </div>
  );
}
