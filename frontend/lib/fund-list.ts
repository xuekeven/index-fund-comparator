import type { FundComparisonRow, TradingVenue } from "./types";

export type FundSortKey =
  | "code"
  | "name"
  | "expenseRate"
  | "scale"
  | "return1m"
  | "return3m"
  | "return6m"
  | "returnYtd"
  | "return1y";
export type SortDirection = "asc" | "desc";
export type VenueFilter = TradingVenue;

export const VENUES: VenueFilter[] = ["场内", "场外"];
export const EXCHANGES = ["上交所", "深交所"];
export const SUBSCRIPTION_STATUS_OPTIONS = ["开放", "暂停", "限额"];

const SUBSCRIPTION_STATUS_BY_LABEL: Record<string, FundComparisonRow["subscriptionStatus"]> = {
  开放: "open",
  暂停: "suspended",
  限额: "limited",
};

export interface FundFilters {
  venue: VenueFilter;
  exchanges: string[];
  shareClasses: string[];
  currencies: string[];
  subscriptionStatuses: string[];
  taggedOnly: boolean;
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
    if (fund.tradingVenue !== filters.venue) return false;
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
    if (
      filters.subscriptionStatuses.length > 0
      && !filters.subscriptionStatuses.some(
        (label) => SUBSCRIPTION_STATUS_BY_LABEL[label] === fund.subscriptionStatus,
      )
    ) {
      return false;
    }
    if (filters.taggedOnly && fund.tags.length === 0) {
      return false;
    }
    if (!normalized) return true;
    return [fund.code, fund.displayName, fund.fundCompany].some((value) =>
      value.toLocaleLowerCase().includes(normalized),
    );
  });
}

export function latestTradingDataDate(funds: FundComparisonRow[]) {
  const dates = funds.flatMap((fund) =>
    [fund.closeDate, fund.navDate].filter(
      (value): value is string => value !== null,
    ),
  );
  return dates.reduce<string | null>(
    (latest, value) => latest === null || value > latest ? value : latest,
    null,
  );
}

export function calculateQdiiPurchaseLimits(funds: FundComparisonRow[]) {
  let hasQdii = false;
  let cny = 0;
  let usd = 0;

  for (const fund of funds) {
    if (fund.tradingVenue !== "场外" || !fund.investmentScope.includes("QDII")) {
      continue;
    }
    hasQdii = true;
    if (fund.subscriptionStatus !== "limited" || fund.subscriptionLimitAmount === null) {
      continue;
    }
    const currency = fund.subscriptionLimitCurrency ?? fund.currency;
    if (currency === "美元") usd += fund.subscriptionLimitAmount;
    if (currency === "人民币") cny += fund.subscriptionLimitAmount;
  }

  return { hasQdii, cny, usd };
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
      if (sortKey === "code" || sortKey === "name") {
        const leftText = sortKey === "code" ? left.code : left.displayName;
        const rightText = sortKey === "code" ? right.code : right.displayName;
        const comparison = leftText.localeCompare(rightText, "zh-CN", { numeric: true });
        const tieBreaker = left.code.localeCompare(right.code, "zh-CN", { numeric: true });
        return comparison === 0
          ? tieBreaker === 0 ? leftItem.originalIndex - rightItem.originalIndex : tieBreaker
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
