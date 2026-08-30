import type {
  ComparisonResponse,
  FundListResponse,
  FundTag,
  FundTagResponse,
  IndexSummary,
  TradingVenue,
} from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "/indexfund/api/v1";

export type SyncTaskKey = "all" | "A" | "B" | "C" | "D" | "E" | "F";
export type SyncTaskState = {
  status: "idle" | "queued" | "running" | "succeeded" | "failed";
  startedAt: string | null;
  finishedAt: string | null;
  returnCode: number | null;
  output: string;
};
export type SyncTaskSnapshot = {
  activeJob: SyncTaskKey | null;
  currentScript: Exclude<SyncTaskKey, "all"> | null;
  tasks: Record<SyncTaskKey, SyncTaskState>;
};

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

async function putJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function getIndices(signal?: AbortSignal): Promise<IndexSummary[]> {
  return getJson<IndexSummary[]>("/indices", signal);
}

export function getFunds(
  indexId: string,
  venue?: TradingVenue,
  exchanges: string[] = [],
  signal?: AbortSignal,
): Promise<FundListResponse> {
  const params = new URLSearchParams();
  if (venue) params.set("venue", venue);
  exchanges.forEach((exchange) => params.append("exchange", exchange));
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

export function updateFundTags(
  fundCode: string,
  tags: FundTag[],
): Promise<FundTagResponse> {
  return putJson<FundTagResponse>(
    `/funds/${encodeURIComponent(fundCode)}/tags`,
    { tags },
  );
}

export function getSyncTasks(signal?: AbortSignal): Promise<SyncTaskSnapshot> {
  return getJson<SyncTaskSnapshot>("/sync-tasks", signal);
}

export function startSyncTask(task: SyncTaskKey): Promise<SyncTaskSnapshot> {
  return postJson<SyncTaskSnapshot>(`/sync-tasks/${task}`);
}
