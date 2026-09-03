import type {
  ComparisonResponse,
  FundListResponse,
  FundTag,
  FundTagResponse,
  IndexSummary,
  InvestmentNote,
  InvestmentNotePayload,
  KnowledgeCategoryOrder,
  KnowledgeArticle,
  KnowledgeArticlePayload,
  TradingVenue,
} from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "/indexfund/api/v1";

export type SyncTaskKey = "all" | "A" | "B" | "C" | "D" | "E" | "F";
export type SyncTaskState = {
  status: "idle" | "queued" | "running" | "succeeded" | "failed";
  startedAt: string | null;
  finishedAt: string | null;
  lastSucceededAt: string | null;
  returnCode: number | null;
  output: string;
};
export type SyncTaskSnapshot = {
  activeJob: SyncTaskKey | null;
  currentScript: Exclude<SyncTaskKey, "all"> | null;
  tasks: Record<SyncTaskKey, SyncTaskState>;
};
export type SyncHistoryItem = {
  time: string;
  result: "succeeded" | "failed" | "stopped";
  method: "scheduled" | "dialog" | "terminal";
};
export type SyncHistoryResponse = {
  items: SyncHistoryItem[];
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

async function sendJson<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const responseBody = await response.json().catch(() => null) as {
      detail?: string;
    } | null;
    throw new Error(responseBody?.detail ?? `API request failed: ${response.status}`);
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

export function getSyncTaskHistory(
  task: SyncTaskKey,
  signal?: AbortSignal,
): Promise<SyncHistoryResponse> {
  return getJson<SyncHistoryResponse>(`/sync-tasks/${task}/history`, signal);
}

export function startSyncTask(task: SyncTaskKey): Promise<SyncTaskSnapshot> {
  return postJson<SyncTaskSnapshot>(`/sync-tasks/${task}`);
}


export function getInvestmentNotes(
  signal?: AbortSignal,
): Promise<InvestmentNote[]> {
  return getJson<InvestmentNote[]>("/notes", signal);
}

export function createInvestmentNote(
  payload: InvestmentNotePayload,
): Promise<InvestmentNote> {
  return sendJson<InvestmentNote>("/notes", "POST", payload);
}

export function updateInvestmentNote(
  noteId: number,
  payload: InvestmentNotePayload,
): Promise<InvestmentNote> {
  return sendJson<InvestmentNote>(`/notes/${noteId}`, "PUT", payload);
}

export function deleteInvestmentNote(noteId: number): Promise<{ deleted: boolean }> {
  return sendJson<{ deleted: boolean }>(`/notes/${noteId}`, "DELETE");
}

export function getKnowledgeArticles(signal?: AbortSignal): Promise<KnowledgeArticle[]> {
  return getJson<KnowledgeArticle[]>("/knowledge", signal);
}

export function createKnowledgeArticle(
  payload: KnowledgeArticlePayload,
): Promise<KnowledgeArticle> {
  return sendJson<KnowledgeArticle>("/knowledge", "POST", payload);
}

export function updateKnowledgeArticle(
  articleId: number,
  payload: KnowledgeArticlePayload,
): Promise<KnowledgeArticle> {
  return sendJson<KnowledgeArticle>(`/knowledge/${articleId}`, "PUT", payload);
}

export function reorderKnowledgeArticles(
  categories: KnowledgeCategoryOrder[],
): Promise<KnowledgeArticle[]> {
  return sendJson<KnowledgeArticle[]>("/knowledge/order", "PUT", { categories });
}

export function deleteKnowledgeArticle(articleId: number): Promise<{ deleted: boolean }> {
  return sendJson<{ deleted: boolean }>(`/knowledge/${articleId}`, "DELETE");
}
