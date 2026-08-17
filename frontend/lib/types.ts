export type DataStatus = "verified" | "delayed" | "estimated" | "sample" | "unavailable";
export type TradingVenue = "场内" | "场外";

export interface IndexSummary {
  id: string;
  name: string;
  shortName: string;
  region: string;
  currency: string;
  exactBenchmark: string;
  fundCount: number;
  status: DataStatus;
}

export interface MetricValue {
  period: string;
  value: number | null;
  startDate: string | null;
  endDate: string | null;
  status: DataStatus;
}

export interface FundComparisonRow {
  id: string;
  productId: string;
  code: string;
  displayName: string;
  fundCompany: string;
  indexId: string;
  productStructure: "ETF" | "普通开放式指数基金" | "ETF联接基金";
  tradingVenue: TradingVenue;
  investmentScope: string[];
  trackingMethod: "被动指数" | "指数增强";
  exactBenchmark: string;
  shareClass: string | null;
  currency: string;
  exchange: string | null;
  managementFee: number | null;
  custodyFee: number | null;
  salesServiceFee: number | null;
  expenseRate: number | null;
  closePrice: number | null;
  closeDate: string | null;
  nav: number | null;
  navDate: string | null;
  estimatedDeviation: number | null;
  scaleBillionCny: number | null;
  scaleDate: string | null;
  returns: MetricValue[];
  dataStatus: DataStatus;
  sourceName: string | null;
  sourceUrl: string | null;
  sourceTime: string | null;
  note: string | null;
}

export interface FundListResponse {
  index: IndexSummary;
  items: FundComparisonRow[];
  total: number;
  lastSyncedAt: string | null;
  generatedAt: string;
  dataMode: string;
}

export interface ComparisonResponse {
  items: FundComparisonRow[];
  generatedAt: string;
  warnings: string[];
  metadata: Record<string, unknown>;
}
