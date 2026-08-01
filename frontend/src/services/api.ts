export type GoodNewsMode = "uplifting" | "high_signal" | "balanced";
export type Tone = "neutral" | "warm" | "punchy" | "analytical";
export type Length = "brief" | "standard" | "deep";

export interface RunConfig {
  theme: string;
  extra_themes?: string[];
  subtopic_count?: number;
  date_from?: string | null;
  date_to?: string | null;
  max_sources?: number;
  tone?: Tone;
  length?: Length;
  good_news_mode?: GoodNewsMode;
  enable_factcheck?: boolean;
  providers?: string[];
}

export interface CreateRunResponse {
  run_id: string;
  status: string;
}

export interface NodeEvent {
  node: string;
  status: "pending" | "running" | "done" | "error" | "skipped";
  at: string;
  branch: string | null;
  detail: string;
  counts: Record<string, number>;
}

export interface KeyFact {
  claim: string;
  quote: string;
  url: string;
  verified: boolean;
}

export interface ArticleScores {
  relevance: number;
  recency: number;
  credibility: number;
  goodness_valence: number;
  goodness_signal: number;
  composite: number;
}

export interface ArticleSummary {
  article_id: string;
  subtopic_id: string;
  headline: string;
  bullets: string[];
  key_facts: KeyFact[];
  url: string;
  source_name: string;
  published_at: string | null;
  image_url: string | null;
  scores: ArticleScores;
  summarized_by: "llm" | "heuristic";
}

export interface NewsletterSection {
  subtopic_id: string;
  title: string;
  blurb: string;
  items: ArticleSummary[];
}

export interface SourceRef {
  article_id: string;
  title: string;
  url: string;
  source_name: string;
  published_at: string | null;
}

export interface Conflict {
  claim: string;
  article_ids: string[];
  severity: "low" | "medium" | "high";
  note: string;
}

export interface Newsletter {
  title: string;
  subtitle: string;
  intro: string;
  sections: NewsletterSection[];
  sources: SourceRef[];
  outro: string;
  conflicts: Conflict[];
  degraded: boolean;
  notes: string[];
  generated_at: string;
}

export interface TopologyNode {
  id: string;
  label: string;
  kind: string;
  description: string;
}

export interface TopologyEdge {
  source: string;
  target: string;
  kind: string;
  label?: string;
}

export interface Topology {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface RunHistoryItem {
  run_id: string;
  config: RunConfig | null;
  status: string;
  created_at: string;
  finished_at: string | null;
}

export interface RunDetail {
  run_id: string;
  config: RunConfig | null;
  newsletter: Newsletter | null;
  status: string;
  created_at: string;
  finished_at: string | null;
}

export interface Bookmark {
  article_id: string;
  url: string;
  title: string;
  source_name: string;
  created_at: string;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function deleteJSON(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

export async function createRun(config: RunConfig): Promise<CreateRunResponse> {
  return postJSON("/api/runs", config);
}

export async function getTopology(): Promise<Topology> {
  return getJSON("/api/graph/topology");
}

export interface AppStatus {
  llm_provider: string;
  llm_model: string;
  search_providers: string[];
  using_real_data: boolean;
  rss_feeds_count: number;
}

export async function getStatus(): Promise<AppStatus> {
  return getJSON("/api/status");
}

export async function listRuns(): Promise<RunHistoryItem[]> {
  return getJSON("/api/runs");
}

export async function getRun(runId: string): Promise<RunDetail> {
  return getJSON(`/api/runs/${runId}`);
}

export async function deleteRun(runId: string): Promise<void> {
  await deleteJSON(`/api/runs/${runId}`);
}

export async function exportRun(runId: string, fmt: "markdown" | "html" | "pdf"): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/export/${fmt}`);
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

export async function listBookmarks(runId: string): Promise<Bookmark[]> {
  return getJSON(`/api/runs/${runId}/bookmarks`);
}

export async function addBookmark(
  runId: string,
  articleId: string,
  url: string,
  title: string,
  sourceName: string,
): Promise<void> {
  await postJSON(`/api/runs/${runId}/bookmarks`, {
    article_id: articleId,
    url,
    title,
    source_name: sourceName,
  });
}

export async function removeBookmark(runId: string, articleId: string): Promise<void> {
  await deleteJSON(`/api/runs/${runId}/bookmarks/${articleId}`);
}

export function streamRunEvents(
  runId: string,
  onNode: (event: NodeEvent) => void,
  onNewsletter: (newsletter: Newsletter) => void,
  onError: (message: string) => void,
  onDone: (status: string) => void,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/runs/${runId}/stream`, {
        signal: controller.signal,
      });
      const reader = res.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);
              if (currentEvent === "node") onNode(parsed);
              else if (currentEvent === "newsletter") onNewsletter(parsed);
              else if (currentEvent === "error") onError(parsed.message ?? "Unknown error");
              else if (currentEvent === "done") onDone(parsed.status ?? "done");
            } catch {
              // skip malformed
            }
            currentEvent = "";
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      onError(err instanceof Error ? err.message : "Stream failed");
    }
  })();

  return controller;
}
