"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getComparison, getFunds, getIndices } from "@/lib/api";
import {
  keepAvailable,
  readFilterPreferences,
  writeFilterPreferences,
} from "@/lib/filter-preferences";
import {
  EXCHANGES,
  filterFundRows,
  sortFundRows,
  VENUES,
} from "@/lib/fund-list";
import type { FundSortKey, SortDirection, VenueFilter } from "@/lib/fund-list";
import type { FundComparisonRow, IndexSummary } from "@/lib/types";
import { CloseIcon, InfoIcon, MarkIcon, RefreshIcon, SearchIcon } from "./icons";
import { ComparisonView } from "./comparison-view";
import { FundCards, FundTable } from "./fund-table";

type CachedFunds = {
  items: FundComparisonRow[];
  lastSyncedAt: Date | null;
};

function formatSyncTime(value: Date | null) {
  if (!value) return "尚未同步";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(value);
}

function formatTradeDate(value: string | null) {
  if (!value) return "暂无交易日";
  return value.slice(5).replace("-", "/");
}

function comparisonScopeText(index: IndexSummary) {
  if (index.region === "中国内地") {
    return `当前展示跟踪${index.shortName}的基金；价格、全收益等具体口径以基金合同为准。`;
  }
  return `当前展示跟踪${index.shortName}的基金；收益指数及人民币折算口径以基金合同为准。`;
}

interface MultiSelectFilterProps {
  filterId: string;
  label: string;
  options: string[];
  selected: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onToggle: (value: string) => void;
  onClear: () => void;
}

function MultiSelectFilter({
  filterId,
  label,
  options,
  selected,
  open,
  onOpenChange,
  onToggle,
  onClear,
}: MultiSelectFilterProps) {
  const selectionLabel = selected.length === 0
    ? "全部"
    : selected.length === 1
      ? selected[0]
      : `已选 ${selected.length} 项`;

  return (
    <div className={`multi-filter ${open ? "open" : ""}`}>
      <button
        className="multi-filter-trigger"
        type="button"
        aria-expanded={open}
        aria-controls={`${filterId}-menu`}
        onClick={() => onOpenChange(!open)}
      >
        <span>{label}</span>
        <strong>{selectionLabel}</strong>
      </button>
      {open && (
        <div className="multi-filter-menu" id={`${filterId}-menu`}>
          <button
            type="button"
            className={selected.length === 0 ? "active" : ""}
            onClick={() => {
              onClear();
              onOpenChange(false);
            }}
          >
            全部
          </button>
          {options.map((option) => (
            <label key={option}>
              <input
                type="checkbox"
                checked={selected.includes(option)}
                onChange={() => onToggle(option)}
              />
              <span aria-hidden="true">{selected.includes(option) ? "✓" : ""}</span>
              {option}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export function ComparisonDashboard() {
  const [initialFilters] = useState(readFilterPreferences);
  const [indices, setIndices] = useState<IndexSummary[]>([]);
  const [activeIndex, setActiveIndex] = useState(initialFilters.activeIndex);
  const [venue, setVenue] = useState<VenueFilter>(initialFilters.venue);
  const [exchanges, setExchanges] = useState<string[]>(initialFilters.exchanges);
  const [shareClasses, setShareClasses] = useState<string[]>(initialFilters.shareClasses);
  const [currencies, setCurrencies] = useState<string[]>(initialFilters.currencies);
  const [openFilter, setOpenFilter] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<FundSortKey | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [funds, setFunds] = useState<FundComparisonRow[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [comparisonFunds, setComparisonFunds] = useState<FundComparisonRow[]>([]);
  const [comparisonWarnings, setComparisonWarnings] = useState<string[]>([]);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const fundCache = useRef(new Map<string, CachedFunds>());
  const fundController = useRef<AbortController | null>(null);
  const fundRequestId = useRef(0);
  const comparisonController = useRef<AbortController | null>(null);

  const loadIndices = useCallback(async (signal?: AbortSignal) => {
    const items = await getIndices(signal);
    setIndices(items);
    if (items.length) {
      setActiveIndex((current) =>
        items.some((item) => item.id === current) ? current : items[0].id,
      );
    }
  }, []);

  const loadFunds = useCallback(async (
    indexId: string,
    signal?: AbortSignal,
    force = false,
  ) => {
    const requestId = ++fundRequestId.current;
    const cached = fundCache.current.get(indexId);
    if (cached && !force) {
      if (fundRequestId.current === requestId) {
        setFunds(cached.items);
        setLastSyncedAt(cached.lastSyncedAt);
        setError(null);
        setLoading(false);
      }
      return;
    }

    setError(null);
    try {
      const response = await getFunds(indexId, undefined, signal);
      const syncedAt = response.lastSyncedAt ? new Date(response.lastSyncedAt) : null;
      fundCache.current.set(indexId, {
        items: response.items,
        lastSyncedAt: syncedAt,
      });
      if (fundRequestId.current === requestId) {
        setFunds(response.items);
        setLastSyncedAt(syncedAt);
      }
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      if (fundRequestId.current === requestId) {
        setError("暂时无法连接数据服务，请稍后重试。");
      }
    } finally {
      if (!signal?.aborted && fundRequestId.current === requestId) setLoading(false);
    }
  }, []);

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
    fundController.current?.abort();
    fundController.current = controller;
    queueMicrotask(() => loadFunds(activeIndex, controller.signal));
    return () => {
      controller.abort();
      if (fundController.current === controller) fundController.current = null;
    };
  }, [activeIndex, loadFunds]);
  useEffect(() => {
    writeFilterPreferences({
      activeIndex,
      venue,
      exchanges,
      shareClasses,
      currencies,
    });
  }, [activeIndex, currencies, exchanges, shareClasses, venue]);


  useEffect(() => () => {
    fundController.current?.abort();
    comparisonController.current?.abort();
  }, []);

  useEffect(() => {
    if (!openFilter) return;

    function closeOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Element && target.closest(".multi-filter")) return;
      setOpenFilter(null);
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenFilter(null);
    }

    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [openFilter]);

  const currentIndex = indices.find((item) => item.id === activeIndex);
  const shareClassOptions = useMemo(
    () => Array.from(
      new Set(funds.flatMap((fund) => fund.shareClass ? [fund.shareClass] : [])),
    ).sort((left, right) => left.localeCompare(right, "zh-CN")),
    [funds],
  );
  const currencyOptions = useMemo(
    () => Array.from(new Set(funds.map((fund) => fund.currency)))
      .sort((left, right) => left.localeCompare(right, "zh-CN")),
    [funds],
  );
  useEffect(() => {
    if (venue !== "场外" || funds.length === 0) return;
    queueMicrotask(() => {
      setShareClasses((current) => keepAvailable(current, shareClassOptions));
      setCurrencies((current) => keepAvailable(current, currencyOptions));
    });
  }, [currencyOptions, funds.length, shareClassOptions, venue]);

  const visibleFunds = useMemo(
    () => filterFundRows(funds, { venue, exchanges, shareClasses, currencies, query }),
    [currencies, exchanges, funds, query, shareClasses, venue],
  );

  const tradeDate = useMemo(() => {
    const dates = visibleFunds.flatMap((fund) =>
      [fund.closeDate, fund.navDate, fund.scaleDate].filter(
        (value): value is string => value !== null,
      ),
    );
    return dates.length > 0 ? dates.sort().at(-1) ?? null : null;
  }, [visibleFunds]);

  const sortedFunds = useMemo(
    () => sortFundRows(visibleFunds, sortKey, sortDirection),
    [sortDirection, sortKey, visibleFunds],
  );

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
      setLastSyncedAt(cached.lastSyncedAt);
    }
    setActiveIndex(indexId);
    setVenue("全部");
    setExchanges([]);
    setShareClasses([]);
    setCurrencies([]);
    setOpenFilter(null);
    setSelected([]);
    setQuery("");
  }

  function changeVenue(nextVenue: VenueFilter) {
    setVenue(nextVenue);
    setOpenFilter(null);
    if (nextVenue !== "场内") setExchanges([]);
    if (nextVenue !== "场外") {
      setShareClasses([]);
      setCurrencies([]);
    }
  }

  function changeSort(key: FundSortKey) {
    if (sortKey === key) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
      return;
    }
    setSortKey(key);
    setSortDirection("asc");
  }

  function toggleValue(
    value: string,
    setter: React.Dispatch<React.SetStateAction<string[]>>,
  ) {
    setter((current) => (
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value]
    ));
  }

  function toggleExchange(value: string) {
    toggleValue(value, setExchanges);
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
    fundController.current?.abort();
    const controller = new AbortController();
    fundController.current = controller;
    try {
      await Promise.all([
        loadIndices(controller.signal),
        loadFunds(activeIndex, controller.signal, true),
      ]);
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setError("刷新失败，请检查后端服务。");
    } finally {
      if (fundController.current === controller) fundController.current = null;
    }
  }

  async function startComparison() {
    if (selected.length < 2) return;
    comparisonController.current?.abort();
    const controller = new AbortController();
    comparisonController.current = controller;
    setComparisonOpen(true);
    setComparisonLoading(true);
    setComparisonError(null);
    setComparisonFunds([]);
    setComparisonWarnings([]);
    try {
      const response = await getComparison(selected, controller.signal);
      setComparisonFunds(response.items);
      setComparisonWarnings(response.warnings);
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setComparisonError("暂时无法获取比较结果，请检查后端服务后重试。");
    } finally {
      if (!controller.signal.aborted) setComparisonLoading(false);
    }
  }

  const closeComparison = useCallback(() => {
    comparisonController.current?.abort();
    comparisonController.current = null;
    setComparisonOpen(false);
  }, []);

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
                <strong>比较范围</strong>
                <span>{comparisonScopeText(currentIndex)}</span>
              </div>
              {currentIndex.id !== "csi-500" && <b>精确基准待授权核验</b>}
            </div>
          )}

          <div className="toolbar">
            <div className="toolbar-filters">
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
              {venue === "场内" && (
                <MultiSelectFilter
                  filterId="exchange-filter"
                  label="交易所"
                  options={EXCHANGES}
                  selected={exchanges}
                  open={openFilter === "exchange"}
                  onOpenChange={(open) => setOpenFilter(open ? "exchange" : null)}
                  onToggle={toggleExchange}
                  onClear={() => setExchanges([])}
                />
              )}
              {venue === "场外" && (
                <>
                  <MultiSelectFilter
                    filterId="share-class-filter"
                    label="份额类别"
                    options={shareClassOptions}
                    selected={shareClasses}
                    open={openFilter === "share-class"}
                    onOpenChange={(open) => setOpenFilter(open ? "share-class" : null)}
                    onToggle={(value) => toggleValue(value, setShareClasses)}
                    onClear={() => setShareClasses([])}
                  />
                  <MultiSelectFilter
                    filterId="currency-filter"
                    label="币种"
                    options={currencyOptions}
                    selected={currencies}
                    open={openFilter === "currency"}
                    onOpenChange={(open) => setOpenFilter(open ? "currency" : null)}
                    onToggle={(value) => toggleValue(value, setCurrencies)}
                    onClear={() => setCurrencies([])}
                  />
                </>
              )}
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

          {!loading && !error && (
            <div className="fund-result-summary" aria-live="polite">
              <p className="fund-result-count">
                共有 <strong>{visibleFunds.length}</strong> 条基金
              </p>
              <p className="fund-last-synced">
                <span className="status-dot" />
                同步时间 {formatSyncTime(lastSyncedAt)}
              </p>
              <p className="fund-trade-date">
                <span className="status-dot" />
                交易日 {formatTradeDate(tradeDate)}
              </p>
            </div>
          )}

          {error ? (
            <div className="state-panel error-state">
              <strong>数据服务未连接</strong>
              <p>{error}</p>
              <button type="button" onClick={refresh}>重新连接</button>
            </div>
          ) : loading ? (
            <div className="state-panel loading-state">
              <span className="spinner" />
              <p>正在加载…</p>
            </div>
          ) : visibleFunds.length === 0 ? (
            <div className="state-panel">
              <strong>没有匹配的基金</strong>
              <p>试试切换交易方式，或清空搜索条件。</p>
            </div>
          ) : (
            <>
              <FundTable
                funds={sortedFunds}
                selected={selected}
                onToggle={toggleFund}
                sortKey={sortKey}
                sortDirection={sortDirection}
                onSort={changeSort}
              />
              <FundCards funds={sortedFunds} selected={selected} onToggle={toggleFund} />
            </>
          )}

          <p className="table-footnote">
            仅当收盘价和净值日期一致时，展示“收盘价 ÷ 单位净值 − 1”的同日偏离。
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
            <button className="primary-button" type="button" disabled={selected.length < 2} onClick={startComparison}>
              {selected.length < 2 ? "再选一个开始比较" : `比较 ${selected.length} 个份额`}
            </button>
          </div>
        </aside>
      )}

      {comparisonOpen && (
        <ComparisonView
          funds={comparisonFunds}
          warnings={comparisonWarnings}
          loading={comparisonLoading}
          error={comparisonError}
          onClose={closeComparison}
          onRetry={startComparison}
        />
      )}
    </div>
  );
}
