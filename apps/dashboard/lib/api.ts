// ModelRail Admin API client.
// Base URL: NEXT_PUBLIC_MODELRAIL_API_URL (default http://localhost:8000)
// Auth: X-Admin-Token header; the token is typed by the operator in the UI
// and kept only in localStorage (never sent anywhere except the gateway).

export const API_URL =
  process.env.NEXT_PUBLIC_MODELRAIL_API_URL || "http://localhost:8000";

const TOKEN_KEY = "modelrail_admin_token";

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
  get isPermissionDenied() {
    return this.status === 401 || this.status === 403;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  if (token) headers["X-Admin-Token"] = token;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, `Cannot reach the ModelRail API at ${API_URL}. Is the gateway running?`);
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      message = body?.detail || body?.message || body?.error || message;
      if (typeof message !== "string") message = JSON.stringify(message);
    } catch { /* keep default */ }
    if (res.status === 401 || res.status === 403)
      message = "Permission denied — check that your admin token is set and has admin access.";
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- Flexible response shapes -------------------------------------------------
// List endpoints may return a bare array or { items|data|results: [...], total }.
export function asArray<T = Record<string, unknown>>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    for (const key of ["items", "data", "results", "requests", "models", "projects", "keys", "policies"]) {
      if (Array.isArray(obj[key])) return obj[key] as T[];
    }
  }
  return [];
}
export function num(v: unknown, fallback = 0): number {
  const n = typeof v === "string" ? Number(v) : (v as number);
  return typeof n === "number" && Number.isFinite(n) ? n : fallback;
}
export function str(v: unknown, fallback = "—"): string {
  return v === null || v === undefined || v === "" ? fallback : String(v);
}

// ---- Domain types (loose: backend may add fields) -----------------------------
export type Row = Record<string, unknown> & {
  id?: string | number;
  name?: string;
  alias?: string;
  provider?: string;
  upstream_model?: string;
  status?: string;
};

// ---- Endpoints ------------------------------------------------------------------
export const api = {
  // Models / routes
  listModels: () => request<unknown>("/admin/v1/models"),
  createModel: (body: Row) => request<Row>("/admin/v1/models", { method: "POST", body: JSON.stringify(body) }),
  updateModel: (id: string | number, body: Row) =>
    request<Row>(`/admin/v1/models/${id}`, { method: "PUT", body: JSON.stringify(body) }),

  // Projects
  listProjects: () => request<unknown>("/admin/v1/projects"),
  createProject: (body: Row) => request<Row>("/admin/v1/projects", { method: "POST", body: JSON.stringify(body) }),

  // API keys (create response contains plaintext `api_key` exactly once)
  listKeys: () => request<unknown>("/admin/v1/keys"),
  createKey: (body: Row) => request<Row>("/admin/v1/keys", { method: "POST", body: JSON.stringify(body) }),
  revokeKey: (id: string | number) => request<unknown>(`/admin/v1/keys/${id}`, { method: "DELETE" }),

  // Policies
  listPolicies: () => request<unknown>("/admin/v1/policies"),
  createPolicy: (body: Row) => request<Row>("/admin/v1/policies", { method: "POST", body: JSON.stringify(body) }),
  updatePolicy: (id: string | number, body: Row) =>
    request<Row>(`/admin/v1/policies/${id}`, { method: "PUT", body: JSON.stringify(body) }),

  // Usage / requests / audit
  usage: (params = "") => request<unknown>(`/admin/v1/usage${params}`),
  listRequests: (params = "") => request<unknown>(`/admin/v1/requests${params}`),
  getRequest: (id: string | number) => request<Row & { attempts?: Row[] }>(`/admin/v1/requests/${id}`),
  auditEvents: () => request<unknown>("/admin/v1/audit-events"),

  // Evaluations
  createEvaluation: (body: Row) => request<Row>("/admin/v1/evaluations", { method: "POST", body: JSON.stringify(body) }),
  getEvaluation: (id: string | number) => request<Row>(`/admin/v1/evaluations/${id}`),
};
