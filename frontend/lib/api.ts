import type {
  ComparisonResponse,
  FundListResponse,
  IndexSummary,
  TradingVenue,
} from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:7006/api/v1";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getIndices(signal?: AbortSignal): Promise<IndexSummary[]> {
  return getJson<IndexSummary[]>("/indices", signal);
}

export function getFunds(
  indexId: string,
  venue?: TradingVenue,
  signal?: AbortSignal,
): Promise<FundListResponse> {
  const params = new URLSearchParams();
  if (venue) params.set("venue", venue);
  const suffix = params.size ? `?${params.toString()}` : "";
  return getJson<FundListResponse>(`/indices/${indexId}/funds${suffix}`, signal);
}

export function getComparison(
  fundCodes: string[],
  signal?: AbortSignal,
): Promise<ComparisonResponse> {
  const params = new URLSearchParams();
  fundCodes.forEach((code) => params.append("fundCodes", code));
  return getJson<ComparisonResponse>(`/comparisons?${params.toString()}`, signal);
}
