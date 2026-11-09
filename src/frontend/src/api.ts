// All calls to the diagram API. The bundled build is served by the API itself (same origin);
// set VITE_API_BASE_URL at build time when the API runs on another host.
import type { CompanySummary, Content, NewsItem, PartnerPage, SearchHit, Side } from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const url = `${BASE}/api${path}${query.size ? `?${query}` : ""}`;
  const response = await fetch(url);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep the status text */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

const t = encodeURIComponent;

export const api = {
  search: (q: string) => get<SearchHit[]>("/companies/search", { q, limit: 12 }),
  featured: () => get<SearchHit[]>("/companies/featured"),
  company: (ref: string) => get<CompanySummary>(`/companies/${t(ref)}`),
  section: (ticker: string, key: string, page: number, pageSize: number, options: Record<string, string>) =>
    get<Content>(`/companies/${t(ticker)}/sections/${t(key)}`, { ...options, page, page_size: pageSize }),
  partners: (ticker: string, side: Side, offset: number, limit: number) =>
    get<PartnerPage>(`/companies/${t(ticker)}/partners`, { side, offset, limit }),
  partnerTransactions: (ticker: string, side: Side, key: string) =>
    get<Content>(`/companies/${t(ticker)}/partner-transactions`, { side, key }),
  news: (id: number) => get<NewsItem>(`/news/${id}`),
};
