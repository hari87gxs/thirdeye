import {
  DocumentResponse,
  UploadResponse,
  DocumentAnalysis,
  AgentResult,
  TransactionsResponse,
  StatementMetrics,
  GroupResults,
  GroupStatus,
  UploadGroup,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("thirdeye_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 401) {
      // Token expired or invalid — clear session and redirect to login
      if (typeof window !== "undefined") {
        localStorage.removeItem("thirdeye_token");
        localStorage.removeItem("thirdeye_user");
        window.location.href = "/login";
      }
      throw new Error("Session expired. Please log in again.");
    }
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }
  return res.json();
}

// ─── Documents ───────────────────────────────────────────────────────────────

export async function uploadDocuments(files: File[]): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: formData,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function listDocuments(): Promise<DocumentResponse[]> {
  return fetchJSON<DocumentResponse[]>(`${API_BASE}/documents`);
}

export async function getDocument(id: string): Promise<DocumentResponse> {
  return fetchJSON<DocumentResponse>(`${API_BASE}/documents/${id}`);
}

export async function deleteDocument(id: string): Promise<void> {
  await fetchJSON<{ message: string }>(`${API_BASE}/documents/${id}`, {
    method: "DELETE",
  });
}

// ─── Analysis ────────────────────────────────────────────────────────────────

export async function analyzeDocument(documentId: string): Promise<{ message: string; document_id: string }> {
  return fetchJSON(`${API_BASE}/analyze/${documentId}`, { method: "POST" });
}

export async function getResults(documentId: string): Promise<DocumentAnalysis> {
  return fetchJSON<DocumentAnalysis>(`${API_BASE}/results/${documentId}`);
}

export async function getAgentResult(documentId: string, agentType: string): Promise<AgentResult> {
  return fetchJSON<AgentResult>(`${API_BASE}/results/${documentId}/${agentType}`);
}

// ─── Transactions & Metrics ──────────────────────────────────────────────────

export async function getTransactions(
  documentId: string,
  params?: { limit?: number; offset?: number; transaction_type?: string; category?: string }
): Promise<TransactionsResponse> {
  const searchParams = new URLSearchParams();
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));
  if (params?.transaction_type) searchParams.set("transaction_type", params.transaction_type);
  if (params?.category) searchParams.set("category", params.category);

  const qs = searchParams.toString();
  return fetchJSON<TransactionsResponse>(`${API_BASE}/transactions/${documentId}${qs ? `?${qs}` : ""}`);
}

export async function getMetrics(documentId: string): Promise<StatementMetrics> {
  return fetchJSON<StatementMetrics>(`${API_BASE}/metrics/${documentId}`);
}

// ─── Group Analysis ──────────────────────────────────────────────────────────

export async function listUploadGroups(): Promise<UploadGroup[]> {
  return fetchJSON<UploadGroup[]>(`${API_BASE}/groups`);
}

export async function analyzeGroup(
  uploadGroupId: string
): Promise<{ message: string; upload_group_id: string; document_ids: string[] }> {
  return fetchJSON(`${API_BASE}/analyze/group/${uploadGroupId}`, { method: "POST" });
}

export async function getGroupResults(uploadGroupId: string): Promise<GroupResults> {
  return fetchJSON<GroupResults>(`${API_BASE}/results/group/${uploadGroupId}`);
}

export async function getGroupStatus(uploadGroupId: string): Promise<GroupStatus> {
  return fetchJSON<GroupStatus>(`${API_BASE}/status/group/${uploadGroupId}`);
}

export async function getGroupMetrics(uploadGroupId: string): Promise<{
  aggregated: import("./types").AggregatedMetrics | null;
  per_statement: StatementMetrics[];
}> {
  return fetchJSON(`${API_BASE}/metrics/group/${uploadGroupId}`);
}

// ─── Health ──────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<{ status: string; service: string; version: string }> {
  const BASE = process.env.NEXT_PUBLIC_API_URL?.replace("/api", "") || "http://localhost:8000";
  return fetchJSON(`${BASE}/health`);
}
