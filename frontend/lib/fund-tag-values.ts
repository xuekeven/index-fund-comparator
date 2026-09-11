import type { FundComparisonRow, FundTag } from "./types";

const amountFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 6,
});

export function formatFundTagLabel(fund: FundComparisonRow, tag: FundTag) {
  if (tag === "holding") {
    return fund.holdingAmount === null
      ? "持有"
      : `持有${amountFormatter.format(fund.holdingAmount)}份额`;
  }
  if (tag === "recurring") {
    return fund.recurringAmount === null
      ? "定投"
      : `定投${amountFormatter.format(fund.recurringAmount)}${fund.currency === "美元" ? "美元" : "人民币"}`;
  }
  return "收藏";
}

export function calculateRecurringInvestmentTotals(funds: FundComparisonRow[]) {
  return funds.reduce(
    (totals, fund) => {
      if (fund.recurringAmount === null) return totals;
      if (fund.currency === "美元") {
        totals.usd += fund.recurringAmount;
        totals.hasUsd = true;
      } else {
        totals.cny += fund.recurringAmount;
        totals.hasCny = true;
      }
      return totals;
    },
    { cny: 0, usd: 0, hasCny: false, hasUsd: false },
  );
}
