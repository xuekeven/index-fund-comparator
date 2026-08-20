import assert from "node:assert/strict";
import test from "node:test";

import { filterFundRows, sortFundRows } from "./fund-list.ts";
import type { FundComparisonRow } from "./types.ts";

function fund(overrides: Partial<FundComparisonRow>): FundComparisonRow {
  return {
    id: "share-1",
    productId: "product-1",
    code: "510500",
    displayName: "中证500ETF",
    fundCompany: "示例基金",
    indexId: "csi-500",
    productStructure: "ETF",
    tradingVenue: "场内",
    investmentScope: ["中国内地"],
    trackingMethod: "被动指数",
    exactBenchmark: "中证500指数",
    shareClass: null,
    currency: "人民币",
    exchange: "上交所",
    managementFee: 0.15,
    custodyFee: 0.05,
    salesServiceFee: null,
    expenseRate: 0.2,
    closePrice: 8,
    closeDate: "2026-08-18",
    nav: 8,
    navDate: "2026-08-18",
    estimatedDeviation: 0,
    scaleBillionCny: 100,
    scaleDate: "2026-08-18",
    returns: [],
    dataStatus: "verified",
    sourceName: "示例来源",
    sourceUrl: null,
    sourceTime: null,
    note: null,
    ...overrides,
  };
}

test("filters funds by venue, exchange, and normalized search text", () => {
  const rows = [
    fund({ code: "510500", displayName: "中证500ETF" }),
    fund({
      id: "share-2",
      code: "000478",
      displayName: "中证500指数A",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      exchange: null,
      shareClass: "A",
    }),
  ];

  assert.deepEqual(
    filterFundRows(rows, {
      venue: "场内",
      exchanges: ["上交所"],
      shareClasses: [],
      currencies: [],
      query: "etf",
    }).map((item) => item.code),
    ["510500"],
  );
});

test("sorts numeric values while keeping missing values last", () => {
  const rows = [
    fund({ code: "3", expenseRate: null }),
    fund({ id: "share-2", code: "2", expenseRate: 0.5 }),
    fund({ id: "share-3", code: "1", expenseRate: 0.2 }),
  ];

  assert.deepEqual(
    sortFundRows(rows, "expenseRate", "asc").map((item) => item.code),
    ["1", "2", "3"],
  );
  assert.deepEqual(
    sortFundRows(rows, "expenseRate", "desc").map((item) => item.code),
    ["2", "1", "3"],
  );
});
