import type { FundComparisonRow, TradingVenue } from "./types";

export type FundSortKey =
  | "code"
  | "expenseRate"
  | "scale"
  | "return1m"
  | "return3m"
  | "return6m"
  | "returnYtd"
  | "return1y";
export type SortDirection = "asc" | "desc";
export type VenueFilter = "全部" | TradingVenue;

export const VENUES: VenueFilter[] = ["全部", "场内", "场外"];
export const EXCHANGES = ["深交所", "上交所"];

export interface FundFilters {
  venue: VenueFilter;
  exchanges: string[];
  shareClasses: string[];
  currencies: string[];
  query: string;
}

const RETURN_PERIOD_BY_SORT_KEY: Partial<Record<FundSortKey, string>> = {
  return1m: "1月",
  return3m: "3月",
  return6m: "6月",
  returnYtd: "今年来",
  return1y: "1年",
};

function fundSortValue(fund: FundComparisonRow, key: FundSortKey): number | null {
  if (key === "expenseRate") return fund.expenseRate;
  if (key === "scale") return fund.scaleBillionCny;
  const period = RETURN_PERIOD_BY_SORT_KEY[key];
  if (!period) return null;
  return fund.returns.find((item) => item.period === period)?.value ?? null;
}

export function filterFundRows(funds: FundComparisonRow[], filters: FundFilters) {
  const normalized = filters.query.trim().toLocaleLowerCase();
  return funds.filter((fund) => {
    if (filters.venue !== "全部" && fund.tradingVenue !== filters.venue) return false;
    if (
      filters.exchanges.length > 0
      && (!fund.exchange || !filters.exchanges.includes(fund.exchange))
    ) {
      return false;
    }
    if (
      filters.shareClasses.length > 0
      && (!fund.shareClass || !filters.shareClasses.includes(fund.shareClass))
    ) {
      return false;
    }
    if (filters.currencies.length > 0 && !filters.currencies.includes(fund.currency)) {
      return false;
    }
    if (!normalized) return true;
    return [fund.code, fund.displayName, fund.fundCompany].some((value) =>
      value.toLocaleLowerCase().includes(normalized),
    );
  });
}

export function sortFundRows(
  funds: FundComparisonRow[],
  sortKey: FundSortKey | null,
  sortDirection: SortDirection,
) {
  if (!sortKey) return funds;
  return funds
    .map((fund, originalIndex) => ({ fund, originalIndex }))
    .sort((leftItem, rightItem) => {
      const { fund: left } = leftItem;
      const { fund: right } = rightItem;
      if (sortKey === "code") {
        const comparison = left.code.localeCompare(right.code, "zh-CN", { numeric: true });
        return comparison === 0
          ? leftItem.originalIndex - rightItem.originalIndex
          : sortDirection === "asc" ? comparison : -comparison;
      }
      const leftValue = fundSortValue(left, sortKey);
      const rightValue = fundSortValue(right, sortKey);
      if (leftValue === null && rightValue === null) {
        return leftItem.originalIndex - rightItem.originalIndex;
      }
      if (leftValue === null) return 1;
      if (rightValue === null) return -1;
      if (leftValue === rightValue) {
        return left.code.localeCompare(right.code, "zh-CN", { numeric: true });
      }
      return sortDirection === "asc" ? leftValue - rightValue : rightValue - leftValue;
    })
    .map(({ fund }) => fund);
}
