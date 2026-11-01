export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Category = {
  id: string;
  name: string;
  description: string;
  color: string;
  source: "user" | "ai" | "default";
  count: number;
  covers: string[];
};
export type Suggestion = { category_id: string | null; name: string; score: number; source: string };
export type Doc = {
  id: string;
  filename: string;
  mime: string;
  kind: "photo" | "document";
  status: "pending" | "processing" | "ready" | "failed";
  error: string;
  title: string;
  summary: string;
  caption: string;
  category: Category | null;
  category_confidence: number;
  category_method: string;
  category_confirmed: boolean;
  suggestions: Suggestion[];
  favorite: boolean;
  taken_at: string | null;
  created_at: string;
  file_url: string;
};
export type DocDetail = Doc & {
  ocr_text: string;
  fields: { field: string; label: string; value: string }[];
  project_ids: string[];
};
export type Project = { id: string; name: string; created_at: string; document_count: number; documents: Doc[] };
export type SearchHit = { document: Doc; score: number; snippet: string; matched: string[] };
export type SearchFilters = {
  semantic_query: string;
  date_from: string | null;
  date_to: string | null;
  kind: string | null;
  category: string | null;
  min_amount: number | null;
  max_amount: number | null;
  parsed_by: string;
};
export type SearchResult = { results: SearchHit[]; filters: SearchFilters };
export type MergeSuggestion = { source: Category; target: Category; reason: string; score: number };
export type CategorySuggestions = {
  merges: MergeSuggestion[];
  proposed: { name: string; documents: Doc[] }[];
  unfiled: number;
};
export type Source = { n: number; document_id: string; title: string; text: string };
export type AskResult = { answer: string; sources: Source[] };
export type User = { id: string; email: string; name: string; picture: string };

const TOKEN_KEY = "di_token";
export const getToken = () => (typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY));
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined" && !location.pathname.startsWith("/login")) location.href = "/login";
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof body.detail === "string" ? body.detail : res.statusText);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const fileSrc = (d: Doc) => `${API_URL}${d.file_url}`;
export const apiSrc = (path: string) => `${API_URL}${path}`;
export const docDate = (d: Doc) => d.taken_at ?? d.created_at;

export function monthLabel(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export const COLORS = ["#2f6b45", "#b4452c", "#3d4f86", "#8a7a4f", "#e8825f", "#6b4f86", "#2f6b6b", "#a8432e"];

export function timeAgo(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 172800) return "Yesterday";
  return new Date(iso).toLocaleDateString();
}
