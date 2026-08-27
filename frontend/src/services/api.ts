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

export type RunStatus = "running" | "done" | "partial" | "error" | "cancelled";

export interface RunHistoryItem {
  run_id: string;
  config: RunConfig | null;
  status: RunStatus | string;
  error: string | null;
  source: string;
  created_at: string;
  finished_at: string | null;
}

export interface RunDetail extends RunHistoryItem {
  newsletter: Newsletter | null;
}

export interface Bookmark {
  run_id: string;
  article_id: string;
  url: string;
  title: string;
  source_name: string;
  created_at: string;
}

export interface Schedule {
  schedule_id: string;
  themes: string[];
  cron_expr: string;
  config: RunConfig | null;
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  last_run_id: string | null;
  next_run_at: string | null;
}

export interface AppStatus {
  app_name: string;
  version: string;
  environment: string;
  llm_provider: string;
  llm_model: string;
  search_providers: string[];
  using_real_data: boolean;
  rss_feeds_count: number;
  factcheck_enabled: boolean;
  scheduler_running: boolean;
}

export interface ValidationIssue {
  field: string;
  message: string;
  type: string;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

/**
 * The API reports validation failures as `{detail, errors: [{field, message}]}`.
 * Surfacing "theme: String should have at least 3 characters" beats surfacing
 * the raw JSON blob the previous client threw.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly issues: ValidationIssue[];

  constructor(status: number, message: string, issues: ValidationIssue[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.issues = issues;
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  const body = await res.text();
  try {
    const parsed = JSON.parse(body);
    const issues: ValidationIssue[] = Array.isArray(parsed.errors) ? parsed.errors : [];
    const message = issues.length
      ? issues.map((issue) => `${issue.field}: ${issue.message}`).join("; ")
      : (parsed.detail ?? body ?? res.statusText);
    return new ApiError(res.status, String(message), issues);
  } catch {
    return new ApiError(res.status, body || res.statusText);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : "Network request failed");
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function getJSON<T>(path: string): Promise<T> {
  return request<T>(path);
}

function postJSON<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function patchJSON<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function deleteJSON(path: string): Promise<void> {
  await request<unknown>(path, { method: "DELETE" });
}

// --- runs ---------------------------------------------------------------

export async function createRun(config: RunConfig): Promise<CreateRunResponse> {
  return postJSON("/api/runs", config);
}

export async function getTopology(): Promise<Topology> {
  return getJSON("/api/graph/topology");
}

export async function getStatus(): Promise<AppStatus> {
  return getJSON("/api/status");
}

export async function listRuns(limit = 50): Promise<RunHistoryItem[]> {
  return getJSON(`/api/runs?limit=${limit}`);
}

export async function getRun(runId: string): Promise<RunDetail> {
  return getJSON(`/api/runs/${runId}`);
}

export async function deleteRun(runId: string): Promise<void> {
  await deleteJSON(`/api/runs/${runId}`);
}

export type ExportFormat = "markdown" | "html" | "pdf";

export async function exportRun(runId: string, fmt: ExportFormat): Promise<Blob> {
  const res = await fetch(`${API_BASE}/api/runs/${runId}/export/${fmt}`);
  if (!res.ok) throw await toApiError(res);
  return res.blob();
}

// --- bookmarks ----------------------------------------------------------

export async function listBookmarks(runId: string): Promise<Bookmark[]> {
  return getJSON(`/api/runs/${runId}/bookmarks`);
}

export async function listAllBookmarks(limit = 200): Promise<Bookmark[]> {
  return getJSON(`/api/bookmarks?limit=${limit}`);
}

export async function addBookmark(
  runId: string,
  articleId: string,
  url: string,
  title: string,
  sourceName: string,
): Promise<Bookmark> {
  return postJSON(`/api/runs/${runId}/bookmarks`, {
    article_id: articleId,
    url,
    title,
    source_name: sourceName,
  });
}

export async function removeBookmark(runId: string, articleId: string): Promise<void> {
  await deleteJSON(`/api/runs/${runId}/bookmarks/${articleId}`);
}

// --- schedules ----------------------------------------------------------

export async function listSchedules(): Promise<Schedule[]> {
  return getJSON("/api/schedules");
}

export async function createSchedule(
  themes: string[],
  cronExpr: string,
  config: RunConfig,
): Promise<Schedule> {
  return postJSON("/api/schedules", { themes, cron_expr: cronExpr, config });
}

export async function toggleSchedule(scheduleId: string, enabled: boolean): Promise<Schedule> {
  return patchJSON(`/api/schedules/${scheduleId}`, { enabled });
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  await deleteJSON(`/api/schedules/${scheduleId}`);
}

export async function runScheduleNow(scheduleId: string): Promise<CreateRunResponse> {
  return postJSON(`/api/schedules/${scheduleId}/run`);
}

// --- feedback -----------------------------------------------------------

export interface FeedbackResponse {
  feedback_id: string;
  status: string;
}

export async function submitFeedback(
  runId: string | null,
  rating: number,
  comment?: string,
): Promise<FeedbackResponse> {
  return postJSON("/api/news/feedback", {
    run_id: runId,
    rating,
    comment: comment?.trim() || null,
  });
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
