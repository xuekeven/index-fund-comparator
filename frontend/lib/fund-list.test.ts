import assert from "node:assert/strict";
import test from "node:test";

import {
  calculateQdiiPurchaseLimits,
  EXCHANGES,
  filterFundRows,
  latestTradingDataDate,
  sortFundRows,
  VENUES,
} from "./fund-list.ts";
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
    subscriptionStatus: null,
    subscriptionLimitAmount: null,
    subscriptionLimitCurrency: null,
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
    tags: [],
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
      subscriptionStatuses: [],
      taggedOnly: false,
      query: "etf",
    }).map((item) => item.code),
    ["510500"],
  );
});

test("filters off-exchange funds by subscription status", () => {
  const rows = [
    fund({
      code: "000001",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      exchange: null,
      subscriptionStatus: "open",
    }),
    fund({
      id: "share-2",
      code: "000002",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      exchange: null,
      subscriptionStatus: "suspended",
    }),
    fund({
      id: "share-3",
      code: "000003",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      exchange: null,
      subscriptionStatus: "limited",
    }),
  ];

  assert.deepEqual(
    filterFundRows(rows, {
      venue: "场外",
      exchanges: [],
      shareClasses: [],
      currencies: [],
      subscriptionStatuses: ["暂停", "限额"],
      taggedOnly: false,
      query: "",
    }).map((item) => item.code),
    ["000002", "000003"],
  );
});

test("filters both exchange and off-exchange funds by any user tag", () => {
  const rows = [
    fund({ code: "510490" }),
    fund({ code: "510500", tags: ["favorite"] }),
    fund({ id: "share-2", code: "510510", tags: ["holding"] }),
    fund({ id: "share-3", code: "510520", tags: ["favorite", "holding"] }),
    fund({
      id: "share-4",
      code: "000001",
      tradingVenue: "场外",
      exchange: null,
      tags: ["holding"],
    }),
  ];

  assert.deepEqual(
    filterFundRows(rows, {
      venue: "场内",
      exchanges: [],
      shareClasses: [],
      currencies: [],
      subscriptionStatuses: [],
      taggedOnly: true,
      query: "",
    }).map((item) => item.code),
    ["510500", "510510", "510520"],
  );

  assert.deepEqual(
    filterFundRows(rows, {
      venue: "场外",
      exchanges: [],
      shareClasses: [],
      currencies: [],
      subscriptionStatuses: [],
      taggedOnly: true,
      query: "",
    }).map((item) => item.code),
    ["000001"],
  );
});

test("uses only returned quote and NAV dates for the displayed trade date", () => {
  assert.equal(
    latestTradingDataDate([
      fund({
        closeDate: "2026-08-26",
        navDate: "2026-08-25",
        scaleDate: "2026-08-27",
      }),
    ]),
    "2026-08-26",
  );
  assert.equal(
    latestTradingDataDate([
      fund({
        closeDate: null,
        navDate: null,
        scaleDate: "2026-08-27",
        sourceTime: "2026-08-27T20:00:00+08:00",
      }),
    ]),
    null,
  );
  assert.equal(
    latestTradingDataDate([
      fund({
        code: "off-exchange",
        closeDate: null,
        navDate: "2026-08-25",
        scaleDate: "2026-08-27",
      }),
      fund({
        id: "share-2",
        closeDate: "2026-08-26",
        navDate: "2026-08-24",
      }),
    ]),
    "2026-08-26",
  );
});

test("sums visible off-exchange QDII purchase limits by currency", () => {
  const rows = [
    fund({
      code: "000001",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      investmentScope: ["QDII"],
      exchange: null,
      subscriptionStatus: "limited",
      subscriptionLimitAmount: 120,
      subscriptionLimitCurrency: "人民币",
    }),
    fund({
      code: "000002",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      investmentScope: ["QDII"],
      exchange: null,
      subscriptionStatus: "limited",
      subscriptionLimitAmount: 80,
      subscriptionLimitCurrency: "人民币",
    }),
    fund({
      code: "000003",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      investmentScope: ["QDII"],
      currency: "美元",
      exchange: null,
      subscriptionStatus: "limited",
      subscriptionLimitAmount: 40,
      subscriptionLimitCurrency: "美元",
    }),
    fund({
      code: "000004",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      investmentScope: ["QDII"],
      exchange: null,
      subscriptionStatus: "open",
      subscriptionLimitAmount: null,
    }),
    fund({
      code: "000005",
      tradingVenue: "场外",
      productStructure: "普通开放式指数基金",
      investmentScope: ["中国内地"],
      exchange: null,
      subscriptionStatus: "limited",
      subscriptionLimitAmount: 999,
      subscriptionLimitCurrency: "人民币",
    }),
  ];

  assert.deepEqual(calculateQdiiPurchaseLimits(rows), {
    hasQdii: true,
    cny: 200,
    usd: 40,
  });
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

test("sorts fund shares by display name in both directions", () => {
  const rows = [
    fund({ code: "3", displayName: "华夏中证500ETF联接A" }),
    fund({ id: "share-2", code: "2", displayName: "嘉实中证500ETF联接A" }),
    fund({ id: "share-3", code: "1", displayName: "天弘中证500ETF联接A" }),
  ];

  assert.deepEqual(
    sortFundRows(rows, "name", "asc").map((item) => item.code),
    ["3", "2", "1"],
  );
  assert.deepEqual(
    sortFundRows(rows, "name", "desc").map((item) => item.code),
    ["1", "2", "3"],
  );
});

test("offers only explicit trading venue filters", () => {
  assert.deepEqual(VENUES, ["场内", "场外"]);
  assert.deepEqual(EXCHANGES, ["上交所", "深交所"]);
});
