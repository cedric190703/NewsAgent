export type GoodNewsMode = "uplifting" | "high_signal" | "balanced";
export type Tone = "neutral" | "warm" | "punchy" | "analytical";
export type Length = "brief" | "standard" | "deep";

export interface RunConfig {
  theme: string;
  extra_themes?: string[];
  audience?: string;
  subtopic_count?: number;
  date_from?: string | null;
  date_to?: string | null;
  max_sources?: number;
  tone?: Tone;
  length?: Length;
  good_news_mode?: GoodNewsMode;
  enable_factcheck?: boolean;
  providers?: string[];
  custom_feeds?: string[];
  custom_urls?: string[];
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
  group_id: string | null;
  group_name: string | null;
  delivery_count: number;
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

async function getJSON<T>(path: string, adminKey?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (adminKey) headers["X-Admin-Key"] = adminKey;
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function deleteJSON(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

export async function createRun(config: RunConfig, adminKey?: string): Promise<CreateRunResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (adminKey) headers["X-Admin-Key"] = adminKey;
  const res = await fetch(`${API_BASE}/api/runs`, {
    method: "POST",
    headers,
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
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

export async function verifyAdminKey(adminKey: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/auth/verify`, {
    method: "POST",
    headers: { "X-Admin-Key": adminKey },
  });
  return res.ok;
}

export interface Topic {
  topic_id: string;
  title: string;
  config: RunConfig | null;
  created_at: string;
}

export interface NewsletterListItem {
  run_id: string;
  theme: string;
  title: string;
  subtitle: string;
  newsletter: Newsletter | null;
  group_id: string | null;
  group_name: string | null;
  created_at: string;
  finished_at: string | null;
}

export async function listTopics(): Promise<Topic[]> {
  return getJSON("/api/topics");
}

export async function createTopic(title: string, config: RunConfig, adminKey: string): Promise<{ topic_id: string }> {
  const res = await fetch(`${API_BASE}/api/topics?title=${encodeURIComponent(title)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey },
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteTopic(topicId: string, adminKey: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/topics/${topicId}`, {
    method: "DELETE",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function listNewsletters(): Promise<NewsletterListItem[]> {
  return getJSON("/api/newsletters");
}

export async function listMyNewsletters(token: string, email?: string): Promise<NewsletterListItem[]> {
  const params = new URLSearchParams();
  if (token) params.set("token", token);
  if (email) params.set("email", email);
  return getJSON(`/api/newsletters/mine?${params.toString()}`);
}

export interface SubscriberGroup {
  group_id: string;
  name: string;
}

export interface Subscriber {
  subscriber_id: string;
  email: string;
  name: string;
  created_at: string;
  groups?: SubscriberGroup[];
}

export interface Group {
  group_id: string;
  name: string;
  description: string;
  theme: string;
  created_at: string;
  subscriber_count: number;
}

export async function listSubscribers(): Promise<Subscriber[]> {
  return getJSON("/api/subscribers");
}

export async function addSubscriber(email: string, name: string, adminKey: string): Promise<{ subscriber_id: string }> {
  const params = new URLSearchParams({ email });
  if (name) params.set("name", name);
  const res = await fetch(`${API_BASE}/api/subscribers?${params}`, {
    method: "POST",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteSubscriber(subscriberId: string, adminKey: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/subscribers/${subscriberId}`, {
    method: "DELETE",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function sendNewsletter(runId: string, adminKey: string, groupIds?: string[]): Promise<{ sent: number; failed: number; detail: string }> {
  const params = new URLSearchParams();
  if (groupIds && groupIds.length > 0) params.set("group_ids", groupIds.join(","));
  const qs = params.toString() ? `?${params}` : "";
  const res = await fetch(`${API_BASE}/api/runs/${runId}/send${qs}`, {
    method: "POST",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listGroups(): Promise<Group[]> {
  return getJSON("/api/groups");
}

export async function createGroup(name: string, description: string, adminKey: string, theme?: string): Promise<{ group_id: string }> {
  const params = new URLSearchParams({ name });
  if (description) params.set("description", description);
  if (theme) params.set("theme", theme);
  const res = await fetch(`${API_BASE}/api/groups?${params}`, {
    method: "POST",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface BatchRunResult {
  created: { run_id: string; group_id: string; group_name: string; theme: string }[];
  skipped: { group_id: string; name: string; reason: string }[];
}

export async function batchCreateRuns(
  overrides: { audience?: string; tone?: string; length?: string; good_news_mode?: string; subtopic_count?: number; max_sources?: number; enable_factcheck?: boolean },
  adminKey: string,
): Promise<BatchRunResult> {
  const res = await fetch(`${API_BASE}/api/runs/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey },
    body: JSON.stringify(overrides),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface BatchExecuteResult {
  created: { run_id: string; group_id: string; group_name: string; theme: string }[];
  skipped: { group_id: string; name: string; reason: string }[];
  message: string;
}

export async function batchExecuteRuns(
  overrides: { audience?: string; tone?: string; length?: string; good_news_mode?: string; subtopic_count?: number; max_sources?: number; enable_factcheck?: boolean },
  adminKey: string,
): Promise<BatchExecuteResult> {
  const res = await fetch(`${API_BASE}/api/runs/batch/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey },
    body: JSON.stringify(overrides),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteGroup(groupId: string, adminKey: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/groups/${groupId}`, {
    method: "DELETE",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function addSubscriberToGroup(subscriberId: string, groupId: string, adminKey: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/subscribers/${subscriberId}/groups/${groupId}`, {
    method: "POST",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function removeSubscriberFromGroup(subscriberId: string, groupId: string, adminKey: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/subscribers/${subscriberId}/groups/${groupId}`, {
    method: "DELETE",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
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

// --- Questions & Registration ---

export interface QuestionOption {
  option_id: string;
  text: string;
  group_name: string;
  position: number;
}

export interface Question {
  question_id: string;
  text: string;
  position: number;
  options: QuestionOption[];
}

export async function listQuestions(): Promise<Question[]> {
  return getJSON("/api/questions");
}

export async function createQuestion(
  text: string,
  options: { text: string; group_name: string }[],
  adminKey: string
): Promise<{ question_id: string }> {
  const res = await fetch(`${API_BASE}/api/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey },
    body: JSON.stringify({ text, options }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteQuestion(questionId: string, adminKey: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/questions/${questionId}`, {
    method: "DELETE",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function registerSubscriber(
  email: string,
  name: string,
  answers: { question_id: string; option_ids: string[] }[]
): Promise<{ subscriber_id: string; token: string; assigned_groups: string[] }> {
  const res = await fetch(`${API_BASE}/api/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name, answers }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function unsubscribe(email: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/unsubscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface Schedule {
  schedule_id: string;
  themes: string[];
  cron_expr: string;
  config: Record<string, unknown> | null;
  enabled: boolean;
  created_at: string;
  last_run_at: string | null;
}

export async function listSchedules(adminKey: string): Promise<Schedule[]> {
  return getJSON("/api/schedules", adminKey);
}

export async function createSchedule(
  themes: string[],
  cronExpr: string,
  config: Record<string, unknown>,
  adminKey: string,
): Promise<{ schedule_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey },
    body: JSON.stringify({ themes, cron_expr: cronExpr, config }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function toggleSchedule(
  scheduleId: string,
  enabled: boolean,
  adminKey: string,
): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/schedules/${scheduleId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", "X-Admin-Key": adminKey },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteSchedule(scheduleId: string, adminKey: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/schedules/${scheduleId}`, {
    method: "DELETE",
    headers: { "X-Admin-Key": adminKey },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
