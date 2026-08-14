import type { FundComparisonRow } from "./types";

const SSE_CATEGORY_BY_INDEX: Record<string, string> = {
  "csi-500": "F112",
  "sp-500": "F131",
  "nasdaq-100": "F131",
};

export function getFundDetailUrl(fund: FundComparisonRow) {
  if (fund.exchange === "上交所") {
    const params = new URLSearchParams({ code: fund.code });
    const category = SSE_CATEGORY_BY_INDEX[fund.indexId];
    if (category) params.set("category", category);
    return `https://etf.sse.com.cn/fundlist/funddetail/index.shtml?${params.toString()}`;
  }

  if (fund.exchange === "深交所") {
    const params = new URLSearchParams({ stock: fund.code, name: fund.displayName });
    return `https://www.szse.cn/disclosure/fund/etf/index.html?${params.toString()}`;
  }

  return fund.sourceUrl;
}
