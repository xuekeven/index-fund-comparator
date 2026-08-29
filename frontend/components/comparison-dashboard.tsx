"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getComparison, getFunds, getIndices, updateFundTags } from "@/lib/api";
import {
  keepAvailable,
  readFilterPreferences,
  writeFilterPreferences,
} from "@/lib/filter-preferences";
import {
  calculateQdiiPurchaseLimits,
  EXCHANGES,
  filterFundRows,
  latestTradingDataDate,
  sortFundRows,
  SUBSCRIPTION_STATUS_OPTIONS,
  VENUES,
} from "@/lib/fund-list";
import type { FundSortKey, SortDirection, VenueFilter } from "@/lib/fund-list";
import type { FundComparisonRow, FundTag, IndexSummary } from "@/lib/types";
import { CloseIcon, MarkIcon, SearchIcon } from "./icons";
import { ComparisonView } from "./comparison-view";
import { FundCards, FundTable } from "./fund-table";
import { ShareClassHelpDialog } from "./share-class-help-dialog";
import { SyncInfoDialog } from "./sync-info-dialog";

type CachedFunds = {
  items: FundComparisonRow[];
  lastSyncedAt: Date | null;
};

const INDEX_ORDER: Record<string, number> = {
  "sp-500": 0,
  "nasdaq-100": 1,
  "csi-500": 2,
};
const FUND_TAG_ORDER: FundTag[] = ["favorite", "holding", "recurring"];

function replaceFundTags(
  rows: FundComparisonRow[],
  code: string,
  tags: FundTag[],
) {
  return rows.map((fund) => fund.code === code ? { ...fund, tags } : fund);
}

function fundCacheKey(
  indexId: string,
  venue: VenueFilter,
  exchanges: string[],
) {
  const exchangeKey = venue === "场内" ? [...exchanges].sort().join(",") : "";
  return `${indexId}|${venue}|${exchangeKey}`;
}

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

function formatPurchaseLimit(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 2,
  }).format(value);
}

interface SingleSelectFilterProps {
  filterId: string;
  label: string;
  options: string[];
  selected: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (value: string | null) => void;
}

function SingleSelectFilter({
  filterId,
  label,
  options,
  selected,
  open,
  onOpenChange,
  onSelect,
}: SingleSelectFilterProps) {
  const selectionLabel = selected ?? "全部";

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
            className={selected === null ? "active" : ""}
            onClick={() => {
              onSelect(null);
              onOpenChange(false);
            }}
          >
            全部
          </button>
          {options.map((option) => (
            <button
              key={option}
              type="button"
              className={selected === option ? "active" : ""}
              onClick={() => {
                onSelect(option);
                onOpenChange(false);
              }}
            >
              {option}
            </button>
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
  const [subscriptionStatuses, setSubscriptionStatuses] = useState<string[]>(
    initialFilters.subscriptionStatuses,
  );
  const [taggedOnly, setTaggedOnly] = useState(initialFilters.taggedOnly);
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
  const [syncInfoOpen, setSyncInfoOpen] = useState(false);
  const [shareClassHelpOpen, setShareClassHelpOpen] = useState(false);
  const [tagSavingCodes, setTagSavingCodes] = useState<string[]>([]);
  const [tagError, setTagError] = useState<string | null>(null);
  const fundCache = useRef(new Map<string, CachedFunds>());
  const fundController = useRef<AbortController | null>(null);
  const fundRequestId = useRef(0);
  const comparisonController = useRef<AbortController | null>(null);

  const loadIndices = useCallback(async (signal?: AbortSignal) => {
    const items = await getIndices(signal);
    const orderedItems = [...items].sort(
      (left, right) => (INDEX_ORDER[left.id] ?? 99) - (INDEX_ORDER[right.id] ?? 99),
    );
    setIndices(orderedItems);
    if (orderedItems.length) {
      setActiveIndex((current) =>
        orderedItems.some((item) => item.id === current) ? current : orderedItems[0].id,
      );
    }
  }, []);

  const loadFunds = useCallback(async (
    indexId: string,
    selectedVenue: VenueFilter,
    selectedExchanges: string[],
    signal?: AbortSignal,
    force = false,
  ) => {
    const requestId = ++fundRequestId.current;
    const cacheKey = fundCacheKey(indexId, selectedVenue, selectedExchanges);
    const cached = fundCache.current.get(cacheKey);
    if (cached && !force) {
      if (fundRequestId.current === requestId) {
        setFunds(cached.items);
        setLastSyncedAt(cached.lastSyncedAt);
        setError(null);
        setLoading(false);
      }
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await getFunds(
        indexId,
        selectedVenue,
        selectedVenue === "场内" ? selectedExchanges : [],
        signal,
      );
      const syncedAt = response.lastSyncedAt ? new Date(response.lastSyncedAt) : null;
      fundCache.current.set(cacheKey, {
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
    queueMicrotask(() => loadFunds(activeIndex, venue, exchanges, controller.signal));
    return () => {
      controller.abort();
      if (fundController.current === controller) fundController.current = null;
    };
  }, [activeIndex, exchanges, loadFunds, venue]);
  useEffect(() => {
    writeFilterPreferences({
      activeIndex,
      venue,
      exchanges,
      shareClasses,
      currencies,
      subscriptionStatuses,
      taggedOnly,
    });
  }, [activeIndex, currencies, exchanges, shareClasses, subscriptionStatuses, taggedOnly, venue]);


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
    () => filterFundRows(funds, {
      venue,
      exchanges,
      shareClasses,
      currencies,
      subscriptionStatuses,
      taggedOnly,
      query,
    }),
    [currencies, exchanges, funds, query, shareClasses, subscriptionStatuses, taggedOnly, venue],
  );

  const tradeDate = useMemo(
    () => latestTradingDataDate(visibleFunds),
    [visibleFunds],
  );

  const qdiiPurchaseLimits = useMemo(
    () => calculateQdiiPurchaseLimits(visibleFunds),
    [visibleFunds],
  );

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
    const cached = fundCache.current.get(
      fundCacheKey(indexId, "场内", []),
    );
    setLoading(!cached);
    if (cached) {
      setFunds(cached.items);
      setLastSyncedAt(cached.lastSyncedAt);
    }
    setActiveIndex(indexId);
    setVenue("场内");
    setExchanges([]);
    setShareClasses([]);
    setCurrencies([]);
    setSubscriptionStatuses([]);
    setTaggedOnly(false);
    setOpenFilter(null);
    setSelected([]);
    setQuery("");
  }

  function changeVenue(nextVenue: VenueFilter) {
    setVenue(nextVenue);
    setOpenFilter(null);
    setExchanges([]);
    if (nextVenue !== "场外") {
      setShareClasses([]);
      setCurrencies([]);
      setSubscriptionStatuses([]);
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

  function toggleFund(code: string) {
    setSelected((current) => {
      if (current.includes(code)) return current.filter((item) => item !== code);
      if (current.length >= 4) return current;
      return [...current, code];
    });
  }

  function applyFundTags(code: string, tags: FundTag[]) {
    setFunds((current) => replaceFundTags(current, code, tags));
    setComparisonFunds((current) => replaceFundTags(current, code, tags));
    fundCache.current.forEach((cached, key) => {
      fundCache.current.set(key, {
        ...cached,
        items: replaceFundTags(cached.items, code, tags),
      });
    });
  }

  async function saveFundTags(code: string, tags: FundTag[]) {
    const fund = funds.find((item) => item.code === code);
    if (!fund || tagSavingCodes.includes(code)) return false;

    const previousTags = fund.tags;
    const nextTags = FUND_TAG_ORDER.filter((item) => tags.includes(item));
    setTagError(null);
    setTagSavingCodes((current) => [...current, code]);
    applyFundTags(code, nextTags);
    try {
      const response = await updateFundTags(code, nextTags);
      applyFundTags(code, response.tags);
      return true;
    } catch {
      applyFundTags(code, previousTags);
      setTagError(`${code} 的标签保存失败，请稍后重试。`);
      return false;
    } finally {
      setTagSavingCodes((current) => current.filter((item) => item !== code));
    }
  }

  async function refresh() {
    setLoading(true);
    fundCache.current.delete(fundCacheKey(activeIndex, venue, exchanges));
    fundController.current?.abort();
    const controller = new AbortController();
    fundController.current = controller;
    try {
      await Promise.all([
        loadIndices(controller.signal),
        loadFunds(activeIndex, venue, exchanges, controller.signal, true),
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

  const closeSyncInfo = useCallback(() => setSyncInfoOpen(false), []);
  const closeShareClassHelp = useCallback(() => setShareClassHelpOpen(false), []);

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
          <button
            className="topbar-info-button"
            type="button"
            onClick={() => setSyncInfoOpen(true)}
            aria-label="查看数据同步机制"
            title="数据同步机制"
          >
            数据同步机制
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
                <SingleSelectFilter
                  filterId="exchange-filter"
                  label="交易所"
                  options={EXCHANGES}
                  selected={exchanges[0] ?? null}
                  open={openFilter === "exchange"}
                  onOpenChange={(open) => setOpenFilter(open ? "exchange" : null)}
                  onSelect={(value) => setExchanges(value ? [value] : [])}
                />
              )}
              {venue === "场外" && (
                <>
                  <SingleSelectFilter
                    filterId="share-class-filter"
                    label="份额类别"
                    options={shareClassOptions}
                    selected={shareClasses[0] ?? null}
                    open={openFilter === "share-class"}
                    onOpenChange={(open) => setOpenFilter(open ? "share-class" : null)}
                    onSelect={(value) => setShareClasses(value ? [value] : [])}
                  />
                  <SingleSelectFilter
                    filterId="subscription-filter"
                    label="申购"
                    options={SUBSCRIPTION_STATUS_OPTIONS}
                    selected={subscriptionStatuses[0] ?? null}
                    open={openFilter === "subscription"}
                    onOpenChange={(open) => setOpenFilter(open ? "subscription" : null)}
                    onSelect={(value) => setSubscriptionStatuses(value ? [value] : [])}
                  />
                  <SingleSelectFilter
                    filterId="currency-filter"
                    label="币种"
                    options={currencyOptions}
                    selected={currencies[0] ?? null}
                    open={openFilter === "currency"}
                    onOpenChange={(open) => setOpenFilter(open ? "currency" : null)}
                    onSelect={(value) => setCurrencies(value ? [value] : [])}
                  />
                </>
              )}
              <label className={`tag-filter-checkbox ${taggedOnly ? "active" : ""}`}>
                <span>标签</span>
                <input
                  type="checkbox"
                  checked={taggedOnly}
                  onChange={(event) => setTaggedOnly(event.target.checked)}
                />
                <i aria-hidden="true">{taggedOnly ? "✓" : ""}</i>
              </label>
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
                <span>同步时间</span>
                <strong>{formatSyncTime(lastSyncedAt)}</strong>
              </p>
              <p className="fund-trade-date">
                <span className="status-dot" />
                <span>交易日</span>
                <strong>{formatTradeDate(tradeDate)}</strong>
              </p>
              {venue === "场外" && qdiiPurchaseLimits.hasQdii && (
                <p className="fund-purchase-limit">
                  <span className="status-dot" />
                  <span className="fund-purchase-limit-copy">
                    <span>共可购买</span>
                    <strong>{formatPurchaseLimit(qdiiPurchaseLimits.cny)}</strong>
                    <span>人民币</span>
                    <strong>{formatPurchaseLimit(qdiiPurchaseLimits.usd)}</strong>
                    <span>美元</span>
                  </span>
                </p>
              )}
            </div>
          )}
          {tagError && <p className="tag-save-error" role="alert">{tagError}</p>}

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
                onTagsSave={saveFundTags}
                tagSavingCodes={tagSavingCodes}
                sortKey={sortKey}
                sortDirection={sortDirection}
                onSort={changeSort}
                onOpenShareClassHelp={() => setShareClassHelpOpen(true)}
              />
              <FundCards
                funds={sortedFunds}
                selected={selected}
                onToggle={toggleFund}
                onTagsSave={saveFundTags}
                tagSavingCodes={tagSavingCodes}
                onOpenShareClassHelp={() => setShareClassHelpOpen(true)}
              />
            </>
          )}

          <p className="table-footnote">
            “偏离”：QDII 使用最新中国交易日收盘价与最新可得境外净值计算；其他基金使用净值日对应的同日收盘价。公式均为“收盘价 ÷ 单位净值 − 1”。
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
      {syncInfoOpen && <SyncInfoDialog onClose={closeSyncInfo} />}
      {shareClassHelpOpen && (
        <ShareClassHelpDialog onClose={closeShareClassHelp} />
      )}
    </div>
  );
}
